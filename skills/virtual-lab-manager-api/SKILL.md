---
name: virtual-lab-manager-api
description: Virtual labs and projects on the OBI (Open Brain Institute) platform — the workspace every piece of work belongs to and every credit is charged against. Covers how the current virtual lab/project is decided and how to target a different one (get-default-virtual-lab-and-project, list-virtual-labs-and-projects, the optional vlab_id/project_id arguments on the sandbox tools), what is and is not shared between per-project sandboxes (the home directory is shared per user; /tmp, kernel state and entity-asset mounts are not), and the virtual-lab-manager REST API for creating a project and transferring credits between a lab and its projects. Read it whenever the user asks where they are, wants to work somewhere else, asks about credits or budget, wants a new project, or when a tool reports that no workspace could be determined.
license: Apache-2.0
---

# Virtual labs, projects, and credits

> **Related generic skills:** [[obi-sandbox-auth]] — every REST call below needs a bearer token obtained that way; never construct auth ad hoc. [[obi-links]] — hand the user a link to a lab or project, never a bare UUID.

## The model

Work on OBI lives in a two-level workspace:

- A **virtual lab** is the billing and membership boundary. Credits are bought and held here.
- A **project** inside a lab is where work actually happens — entities are registered against it, and sandbox compute is charged to it.

**Credits sit on the lab, not on its projects.** A brand-new project has a budget of zero and cannot run anything until credits are transferred into it from the lab. This trips people up constantly: the project exists, the user has credits, and jobs still fail. Check the budget before blaming anything else.

A user typically belongs to several labs and several projects within them, with different roles in each.

## Where am I?

**Call `get-default-virtual-lab-and-project` early in a conversation**, before running anything that costs compute, and tell the user in one line where their work will land. In the web app the user can see this in the GUI; in an MCP client they cannot, so saying it is the only way they know.

It returns the ids, their names, and a `source`:

| `source` | What it means | Stable? |
|---|---|---|
| `tool-args` | You passed `vlab_id`/`project_id` on that call | One call only |
| `headers` | Pinned in the user's MCP client config (`X-Vlab-Id` / `X-Project-Id`) | Whole session |
| `thread` | The vlab/project this conversation belongs to | Whole conversation |
| `recent-workspace` | Whatever the user last opened in the web app | **Can change at any moment** |

That last row is the one to take seriously. Under `recent-workspace` the default follows the user's clicking; a value you read at the start of the conversation may be stale an hour later. Re-check rather than caching it, especially before a long or expensive run.

`list-virtual-labs-and-projects` returns every lab/project the user can act in, each with a link to its home page. Use it when the user asks what they have, when they want to work somewhere else, or when you need an id to pass to another tool.

## Targeting a different project

Every sandbox tool — `execute-python`, `execute-shell`, `kill-sandbox`, `get-sandbox-download-url`, `get-sandbox-upload-url` — takes optional `vlab_id` and `project_id`.

Three rules:

1. **Pass both or neither.** A project only exists inside a specific lab; half a pair is rejected.
2. **They apply to one call.** There is no "switch project for the rest of the conversation". If the user asked to work in project B, pass B's ids on *every* subsequent sandbox call, not just the first — otherwise the next one silently goes back to the default.
3. **Each project gets its own sandbox pod, but the home directory is shared.** The pod is keyed on (user, project), so switching project is a *different machine* — with one large exception: `/home/jovyan` is an EFS volume mounted per **user**, identical in every project.

### What carries across projects and what doesn't

| | Scope | Notes |
|---|---|---|
| `/home/jovyan` (`~`) | **Per user — shared** | Your files, notebooks, and `pip install --user` packages in `~/.local` are visible from every project |
| `/tmp` and the rest of the container filesystem | Per project | A file in `/tmp` under project A does not exist under project B |
| Running kernel state (Python variables, imports, loaded data) | Per project | `execute-python` under B starts a fresh kernel; variables defined under A raise `NameError` |
| Packages installed into the container (`apt`, conda, plain `pip` into `/opt/conda`) | Per project | Reinstall, or install with `--user` so it lands in shared `~/.local` |
| `/data/aws_s3_internal/private/{vlab}/{project}` | Per project | Only the **current** project's entity assets are mounted. Switching project makes A's assets invisible, so `entitysdk`'s local-store fast path falls back to network downloads |
| `/data/aws_s3_open`, `/data/aws_s3_internal/public`, `/home/shared_data` | Global, read-only | Same everywhere |

Two consequences worth holding onto:

- **Don't re-copy files between projects.** They are already there — `~` is the same directory. Conversely, **don't assume your outputs are isolated**: two projects both writing `~/results.csv` overwrite each other. Name outputs distinctly, or put them in a per-project subdirectory.
- **Cold starts are real.** Targeting a project whose pod isn't running spins one up, which takes tens of seconds. Don't ping-pong between projects mid-task.

For `get-sandbox-download-url` / `get-sandbox-upload-url`, pass the same ids you used for the call that wrote the file. A path under `~` happens to resolve from either pod, but a `/tmp` path does not, and using the wrong ids can cold-start a pod you didn't need.

Every sandbox tool echoes a `workspace` block in its result showing which vlab/project it actually used and why. When the user cares where something ran, read it back from there rather than assuming.

If a tool reports that no workspace could be determined, the user has no recent workspace and pinned no headers. Call `list-virtual-labs-and-projects`, ask which they want, and pass the ids explicitly.

## Passing the workspace to the other OBI APIs

entitycore, obi-one, thumbnail-generation and the rest scope every request to a vlab/project pair sent as two HTTP headers (note the spelling — hyphens, not the underscores used in the tool arguments):

```
virtual-lab-id: <uuid>
project-id: <uuid>
```

**Inside the sandbox, read those values from the environment — never hardcode them:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "virtual-lab-id: $OBI_VLAB_ID" -H "project-id: $OBI_PROJECT_ID" \
  "https://<obi-host>/api/entitycore/..."
```

```python
import os
headers = {
    "Authorization": f"Bearer {token}",
    "virtual-lab-id": os.environ["OBI_VLAB_ID"],
    "project-id": os.environ["OBI_PROJECT_ID"],
}
```

`OBI_VLAB_ID` and `OBI_PROJECT_ID` are set per sandbox, so they already reflect whichever project the tool call targeted — including one you redirected with `vlab_id`/`project_id`. Reading them keeps downstream requests in step automatically.

This is why hardcoding is a trap: ids you captured from `get-default-virtual-lab-and-project` earlier in the conversation are the *default*, and after an override the sandbox is a different project while your literals still say the old one. Nothing errors — entities get registered in the wrong project. The same applies to `entitysdk`'s `ProjectContext(virtual_lab_id=..., project_id=...)`: build it from the environment.

The one place to use explicit ids rather than the environment is the virtual-lab-manager API below, where the lab and project are path segments and you may legitimately be acting on a project other than the one the sandbox is running in.

### What actually happens if you omit them

Other skills describe these headers as "required". At the HTTP layer they are not — both services declare them optional and accept a bare bearer token. What you get instead depends on the endpoint, and one of the three outcomes is silent:

- **Reads (most of entitycore and obi-one) succeed, and return _more_ than you expect.** With no `project-id`, authorization falls back to every project the user belongs to via their Keycloak groups. So omitting the header does not scope you to public data — it **widens** the search across all your projects. Never conclude "this entity is in my project" from an unscoped read; the hit may be in a completely different one. Always send the header when the question is about a specific project.
- **Writes and other project-scoped endpoints fail loudly** with `403 "The headers virtual-lab-id and project-id are required"`. Self-correcting: you will see it.
- **obi-one job launches fail with `400 "No virtual lab ID found"`** when the virtual lab is missing, since it needs one to pick a compute cell.

There is also a quiet one inside obi-one: it builds its entitysdk client with a project context **only when both ids are present**, and with `project_context=None` otherwise. So a partially-scoped request degrades to an unscoped one rather than complaining.

Sending a pair the user is not a member of is a hard `403` ("User not authorized for the given virtual-lab-id or project-id") — a permissions answer, not a transient failure. Do not retry it; re-check the ids with `list-virtual-labs-and-projects`.

(entitycore will infer the virtual lab from a lone `project-id`, but do not lean on that — obi-one does not, and the tool arguments here reject a half pair outright.)

## The virtual-lab-manager REST API

Creating projects and moving credits have no dedicated tools — call the API directly from the sandbox with `execute-shell`.

**Base URL:** `https://<obi-host>/api/virtual-lab-manager`
**Full spec:** `<base>/openapi.json` — fetch it when you need a request body shape rather than guessing. Responses are wrapped as `{"message": ..., "data": ...}`.

**Auth:** `Authorization: Bearer <token>` with a token minted per [[obi-sandbox-auth]]. No vlab/project headers — the path carries them.

### Reading

```bash
# Labs you belong to
curl -s -H "Authorization: Bearer $TOKEN" \
  "$VLM/virtual-labs?page=1&page_size=100"

# Projects in one lab
curl -s -H "Authorization: Bearer $TOKEN" \
  "$VLM/virtual-labs/<vlab_id>/projects"
```

For a plain listing prefer the `list-virtual-labs-and-projects` tool — it already does this and returns links.

### Creating a project

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"<name>","description":"<description>"}' \
  "$VLM/virtual-labs/<vlab_id>/projects"
```

**A 403 here is an answer, not a bug.** Creating projects requires an admin role in that virtual lab, and plenty of users do not have it in every lab they belong to. Say so plainly and suggest the lab's admin, rather than retrying or hunting for a workaround.

**Confirm the lab with the user before creating.** A project in the wrong lab draws down the wrong budget and is visible to the wrong people.

### Transferring credits

A new project starts with nothing. To fund it:

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"amount":<amount>}' \
  "$VLM/virtual-labs/<vlab_id>/projects/<project_id>/accounting/budget/assign"
```

`.../budget/reverse` moves an amount back from the project to the lab.

**Always state the amount and the destination project and get the user's agreement in words before sending this request.** This moves real money-equivalent credits, and nothing in the platform asks them to confirm on your behalf — you are the only checkpoint. "Shall I move 500 credits from *Lab X* into *Project Y*?" and a yes. Never infer an amount the user did not give; ask.

After creating a project, the natural sequence is: create → report it with a link → *ask* whether to transfer credits and how many → transfer → confirm the new budget.

The project's credits page is at `https://{domain}/app/virtual-lab/{vlab_id}/{project_id}/credits`; link it rather than describing it.

## Switching the web app

You cannot change which project the *GUI* is showing, and in the browser assistant you cannot change which project the conversation belongs to. Both are the user's to do. When they want to move, give them the project's link from `list-virtual-labs-and-projects` and let them click it — then the default follows.
