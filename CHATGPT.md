# Using obi-skills with ChatGPT

This guide explains how to install the OBI Agent Skills from this repository and
connect ChatGPT to the OBI platform through the **`neuroagent`** MCP server.

> **Applies to:** ChatGPT clients that support custom **connectors / MCP servers**
> (e.g. ChatGPT Developer Mode / connector settings). If your ChatGPT plan or
> client does not expose MCP connector settings, these steps will not be
> available to you.

---

## 1. Install the skills

The skills in this repo follow the [Agent Skills](https://agentskills.io/)
format and live under [`skills/`](./skills/). Each skill is a directory
containing a `SKILL.md`.

Pick whichever method fits your setup:

### Option A — skills CLI

```bash
npx skills add openbraininstitute/obi-skills
```

### Option B — clone and point your agent at the folder

```bash
git clone https://github.com/openbraininstitute/obi-skills.git
```

Then copy or symlink the skills you want into your agent's skills directory:

```bash
# example: symlink a single skill
ln -s "$(pwd)/obi-skills/skills/ngv-metabolism" ~/.config/<your-agent>/skills/ngv-metabolism
```

ChatGPT itself does not read a local `skills/` directory the way a CLI agent
does. The `SKILL.md` files are Markdown instructions — with ChatGPT you make a
skill's contents available to a conversation by one of:

- pasting the relevant `SKILL.md` into the chat (or a Project's custom
  instructions / files), or
- adding it to a **ChatGPT Project** as an attached file so it's in context for
  every chat in that project.

Whichever way you load a skill, the MCP connector below is what gives ChatGPT the
actual tools (e.g. `execute-python`) the skills tell it to call.

---

## 2. Add the `neuroagent` MCP connector

The skills drive the OBI platform through an MCP server. Add it as a connector
in ChatGPT's connector/MCP settings.

**Connector settings:**

| Field | Value |
| --- | --- |
| Name | `neuroagent` |
| Type | `http` (streamable HTTP / remote MCP) |
| URL | `https://cell-a.openbraininstitute.org/api/agent-ts/mcp` |
| Auth | OAuth |
| OAuth client ID | `obi-mcp` |
| OAuth callback port | `8080` |
| OAuth scopes | `openid profile email` |

If your client accepts a JSON server definition, use:

```json
{
  "neuroagent": {
    "type": "http",
    "url": "https://cell-a.openbraininstitute.org/api/agent-ts/mcp",
    "oauth": {
      "clientId": "obi-mcp",
      "callbackPort": 8080,
      "scopes": "openid profile email"
    }
  }
}
```

> **URL note:** use the production host
> `https://cell-a.openbraininstitute.org/api/agent-ts/mcp`.
> A staging variant (`https://staging.cell-a.openbraininstitute.org/...`) exists
> for testing, but the connector above targets production.

### OAuth sign-in

The connector uses OAuth. On first use ChatGPT opens an OBI sign-in flow; the
`callbackPort` (`8080`) must be free on the machine handling the OAuth redirect.
Sign in with your OBI account and approve the requested scopes
(`openid profile email`). Once authorized, ChatGPT can call the MCP tools.

---

## 3. Verify the setup

1. Confirm the `neuroagent` connector shows as connected/authorized in ChatGPT.
2. Start a chat and load a skill (e.g. paste
   [`skills/ngv-metabolism/SKILL.md`](./skills/ngv-metabolism/SKILL.md)).
3. Ask the model to perform a simple action the skill describes. For the
   `ngv-metabolism` skill, a good smoke test is a minimal run:

   > Run the NGV unit metabolism model for the `young` phenotype with `mainSyn`
   > stimulation and plot neuronal ATP.

   The model should call the connector's `execute-python` tool, run
   `run_metabolism`, and return a plot. If it reports it has no such tool, the
   `neuroagent` connector is not attached to that conversation.

---

## Troubleshooting

- **No MCP/connector option in ChatGPT** — your client or plan may not support
  custom connectors. This integration requires MCP connector support.
- **OAuth callback fails** — ensure port `8080` is free and not blocked by a
  firewall; retry the authorization from the connector settings.
- **`401`/`403` from the MCP server** — the OAuth token is missing or expired.
  Re-authorize the `neuroagent` connector.
- **Tools not offered in a chat** — attach/enable the `neuroagent` connector for
  that specific conversation or Project, and make sure the relevant `SKILL.md`
  is in context.
- **Wrong host** — double-check the URL is
  `https://cell-a.openbraininstitute.org/api/agent-ts/mcp` (production), not the
  `staging.` host, unless you are deliberately testing against staging.
