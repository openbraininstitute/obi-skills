---
name: obi-logbook
description: Generic skill — the scientific logbook convention for every OBI (Open Brain Institute) scientific workflow. Defines where the logbook lives (the project's shared research log, written with the logbook-* tools), when to write to it, and (most importantly) what belongs in it — the science, not the plumbing. Invoke this skill at the start of any OBI scientific session (circuit simulation, disease modeling, single-cell/ME model building, ion channel fitting, skeletonization, data integration, visualization) and keep adding to the logbook as the session progresses. Every OBI scientific skill defers to this one for logbook mechanics and content rules, so read it once per session rather than re-deriving a format.
license: Apache-2.0
---

# OBI Scientific Logbook

Every OBI scientific session keeps a logbook. It is the lab notebook for the work: a colleague who was not in the room should be able to read it and understand **what scientific question was asked, what was done to answer it, what came out, and whether to trust it** — without ever needing to know which API was called.

> **Related generic skills:** [[obi-sandbox-auth]] for credentials and consent flows. It does not belong in the logbook's *content* — see "What never goes in" below. [[obi-links]] governs how ids, files, and jobs are turned into links; of those, only **entity links** belong in the logbook — see "Links in the logbook" below.

---

## Where the logbook lives

The logbook is the project's **research log**: one shared, live record in the OBI web app. Every member of the project, and their agents, read it while you write. You write it only with the `logbook-*` tools.

| What | Where it goes | How |
|---|---|---|
| The logbook text | The research log | `logbook-add-entry`, `logbook-edit` |
| Plots, results, inputs, scripts | The research log's files, in EntityCore | `logbook-save-file` from the topic folder, then one entry that shows it |
| Scratch files | The sandbox, under `{topic_dir}` | They stay there; nobody else needs them |

- **No `logbook.md`.** Never create or append to a logbook file in the sandbox. When another OBI skill shows `logbook.md` in a folder layout, appends to it, or hands the file to the user, do what this skill says instead.
- **The sandbox is the workshop.** Run code there as usual. As soon as a plot, result, input or script matters to the user, save it to the research log: a colleague cannot open your sandbox.
- **Everything you write is visible at once**, under the user's name with your agent label. There is no draft and no approval step.

---

## The one rule

**Log the science, not the plumbing.**

The logbook is written for a neuroscientist reading it six months later, not for a developer debugging a request. If a sentence would only make sense to someone looking at a terminal, it does not belong in the logbook.

### What goes in

| Category | Examples |
|---|---|
| **Question** | What is being investigated, and why this approach can answer it |
| **Model / data provenance** | Which circuit, morphology, e-model, recording, or mesh was used — name, brain region, species/strain, scale (neuron counts, cell types), and *why it was chosen over the alternatives* |
| **Scientific parameters** | Every biophysical value set or changed: quantity, baseline → new value, **units**, which cell type / compartment / synapse type it applies to, and the **citation** justifying it |
| **Protocol** | Stimulus type and amplitude, duration, temperature, holding potential, number of repetitions/seeds, what was recorded and where |
| **Comparisons** | What is the control, what is the perturbed condition, and what is held identical between them |
| **Results** | The actual numbers with units (firing rates in Hz, latencies in ms, voltages in mV, feature values), plus the figures produced and what each one shows |
| **Interpretation** | What the result means for the question — including when it *contradicts* the hypothesis |
| **Caveats & limitations** | Small N, unvalidated parameter, arbitrary choice, known model limitation, approximation taken |
| **Provenance IDs** | EntityCore IDs of the entities used and produced, in a compact table — these are scientific provenance, not plumbing |
| **Next steps** | What the result suggests trying next |

### What never goes in

Do not write any of these into the logbook:

- HTTP verbs, endpoint paths, status codes, request/response bodies, `curl` commands
- Authentication: tokens, token exchange, refresh, consent URLs, `virtual-lab-id` / `project-id` headers, anything from [[obi-sandbox-auth]] — **never write a token or any part of one into the logbook**
- Tool names, MCP connector names, sandbox lifecycle (kill/restart), sandbox numbers and kernel names, polling loops, retries, timeouts
- Bugs, workarounds, and error messages encountered along the way — those are session chatter, and the platform-level ones already live in the relevant skill's Known Issues section
- Intermediate/scratch file paths and download plumbing

One exception, scientific in nature: **a technical fact that changes the scientific reading of a result** — e.g. "the simulation was cut to 500 ms, so late-phase adaptation is not captured". Write it as a scientific caveat, in scientific terms, not as an incident report.

> **Sanity check before adding an entry:** would this line still make sense if the platform were replaced tomorrow by a completely different one? If yes, it is science — write it. If no, leave it out.

---

## Links in the logbook

[[obi-links]] governs how ids, files, and jobs become clickable for the user. Only part of that belongs in the permanent record:

| | In the logbook? |
|---|---|
| **Entity links** — `https://{domain}/app/entity/{id}` | **Yes.** Provenance IDs are science; make the id cells in the provenance table links so a reader can open the entity. Use the domain of the environment the work ran against. |
| **Saved files** — plots, results, inputs, scripts | **Yes, saved with `logbook-save-file`.** Refer to them by the exact name the tool returns (`plots/rate.3fa9c1d2e4b7.png`): that name is that exact file, for ever. A sandbox path is not a link: nobody but the user can open it. |
| **Workflow activity links** | **No.** Session plumbing — hand them to the user in the reply instead. |
| **Download URLs, tokens, consent URLs** | **Never.** Credentials, not provenance — see "What never goes in" above. |

## The sandbox directory convention

The sandbox is where code runs. This layout governs **all** OBI scientific work on the sandbox. Every skill that writes a file follows it.

**One directory per topic, at the root of the persistent volume:**

```
/home/jovyan/<topic>/
```

`<topic>` is the scientific subject of the conversation, in kebab-case — `alzheimer-ca1`, `nav1.6-fitting`, `v1-microcircuit`, `thalamic-mesh-skeletons`. It names *what is being studied*, not which workflow or API is being used: everything a conversation produces lands under one topic, even when the work spans several skills. One conversation, one topic directory, one research log.

### Inside a topic directory

A fixed backbone, plus input directories named for what they actually hold:

```
/home/jovyan/<topic>/
├── manifest.json       ← written by logbook-open-folder; never touch it
├── <inputs…>/          ← one dir per input kind, named for its contents
├── results/            ← raw outputs; one subdir per condition when comparing
│   ├── <condition-a>/
│   └── <condition-b>/
├── plots/              ← figures
└── code/               ← every script written, for reproducibility
```

`plots/`, `code/`, and `results/` are the backbone — always present, always named this way, so any skill and any later conversation can find them without asking. The input directories are workflow-specific: name them for their contents (`circuit-original/`, `circuit-disease/`, `meshes/`, `recordings/`, `morphologies/`), and create them yourself inside the topic directory. Where a workflow compares conditions, mirror those condition names under `results/`.

### Opening the topic directory

Open it with `logbook-open-folder`, right after the research log is found or created, **before any scientific work starts**. Never create the topic directory by hand.

- **The log already has a folder** (an earlier conversation, or the same home in another project) → the tool answers its path. Use it.
- **The log has no folder yet** → the tool asks for a `topic`. Call again with the kebab-case topic name: it creates `/home/jovyan/<topic>/` with `plots/`, `results/` and `code/`, and writes its `manifest.json`.
- **That name belongs to another log** → choose a more specific topic name (`alzheimer-ca1-hcn-sweep` rather than a second `alzheimer-ca1`). A name that collides is usually a name that was too vague anyway.
- **That folder exists with no manifest** (work from before the research log) → ask the user whether it holds the work of this log. Only on a yes, call again with `adopt: true`. Adopting uploads nothing.
- **Never write, edit, move or delete `manifest.json`.** It ties the folder to its research log and its project, and `logbook-save-file` checks it before every save.

**Use the returned path as `topic_dir`, the root for every sandbox path for the rest of the conversation.** Build absolute paths from it — never scatter files in `/tmp`, `~`, or a bare `/home/jovyan/outputs`, which either do not survive or cannot be traced back to the work that produced them.

### A research log in another project

A research log belongs to one project, and its files may be written only from that project.

- The user names a log that `logbook-list` does not find in the current project → `logbook-list` again with `all_projects: true`. Each log it answers carries its `vlab_id` and `project_id`.
- The log is in another project → tell the user which project it is in and ask whether to work there. Ask **once per topic** in the conversation, not on every call.
- On a yes, pass that `vlab_id` and `project_id` on **every** logbook and sandbox call for this topic. Nothing is copied between projects; the home is the same, so `logbook-open-folder` finds the folder if the user worked on it before.
- A tool answer "This research log belongs to project …" means the same thing: ask the user, then call again with that project.

### Saving files

- Save any file of the topic directory that a colleague needs: figures, results, inputs, and the scripts in `code/` that produced them.
- **Save a file only after the run that writes it has finished.**
- The tool answers the saved name, made from the file's content: `plots/rate.png` is saved as `plots/rate.3fa9c1d2e4b7.png`. Use that exact name in the entry: `![Firing rate under HCN block](plots/rate.3fa9c1d2e4b7.png)`, or `::file[fit.py]{path=code/fit.3fa9c1d2e4b7.py}` for a file that is not an image.
- **A saved file is never replaced.** A changed file gets a new name by itself, so an earlier entry keeps showing the file it described. The same content saved again uploads nothing (`already_saved: true`).
- The answer "changed while it was being saved" means a run is still writing the file: wait until it has finished, then save it again.

### Using saved files again

A saved file stays in the sandbox too: saving is a copy. `logbook-open-folder` lists the files the research log saved and marks those missing from the folder (`in_folder: false`), for example a colleague's files or a cleaned folder.

- Fetch only the files the task needs, with `logbook-fetch-file` and the saved name. Without a `path`, the copy goes to its name in the folder (`plots/rate.3fa9c1d2e4b7.png` goes to `<topic_dir>/plots/rate.png`).
- Fetch everything only when the user asks for it.
- A file saved several times has one saved name per version; `newest` marks the latest. Fetch an older version by its full saved name, to another `path` if the newest is already there.

---

## When to write

Add as you go. **Never reconstruct the logbook at the end of the session** — by then the reasoning behind each choice has been lost, and a session that fails partway leaves nothing behind.

| Moment | Add |
|---|---|
| Session start | The scientific question / objective |
| A scientific choice is made | What was chosen, and the reason it was chosen over alternatives |
| A parameter is set or changed | Value, units, scope, and citation — before running anything with it |
| An input is prepared | Save it if it matters to the user (a recording, a modified circuit, a parameter table), then say what it is |
| A run is launched | What is being run, under what protocol, and what it is expected to show |
| A run finishes | The numbers that came out, with units; save the result files that matter and the script that produced them |
| A figure is produced | Save it, then one line on what it shows |
| Interpretation forms | What the result means, including surprises and negative results |
| Session end | Results summary, caveats, next steps, and that the work is complete |

**Cite before you use.** Any biophysical parameter that came from the literature gets its reference recorded at the moment it is adopted. An unattributed parameter is a defect, not a shortcut.

### The calls

| Moment | Call |
|---|---|
| Session start | `logbook-list`: the research logs of the project (with `all_projects: true` when the user names a log that is not in the current project, see "A research log in another project"). Is this topic already there? Match by meaning, not by spelling: a person may have typed the title in the web app. **Found** → resume that log and say so. **Not found** → `logbook-create`, with the title as its name and the scientific question as its description |
| Right after the log is found or created | `logbook-open-folder` with its id: the topic directory, see "Opening the topic directory" |
| Then | `logbook-list-pages`: its main page (the report) and the section pages already there, with their ids. Keep the ids for the whole session |
| Every moment of the table above | One `logbook-add-entry` on the page of that section of the Structure below (its `page_id`), added at the end of that page. It needs no read first. The section has no page yet → `logbook-create-page` with the section's name as its title, once, then write there |
| A plot, result, input or script that matters, once the run that writes it has finished | `logbook-save-file` with its sandbox path, then one `logbook-add-entry` on the page of the section it belongs to (a figure under Results, an input under Inputs & Provenance, a script under Outputs) that shows it by the saved name the tool returned and says what it shows |
| Changing or removing earlier text | `logbook-read` of that page first: it returns the blocks, each with an `id`, a `rev` and its markdown. Then one `logbook-edit` on the same page with the operations: `replace` (the whole block with the words changed; it keeps its id), `delete`, `insert_after` or `insert_before`, each naming a block by `id` and, for replace and delete, its `rev`. A `block-changed` answer means someone edited that block since your read: read again and redo the edit on the new text, never over it |
| Session end | The last entry, then the report on the main page (no `page_id`): see "The main page" below. Then give the user the `url` of the log |

- **Never make a section twice.** Before `logbook-create-page`, look in the pages you listed for one with that title (a person may have made it in the web app, or an earlier call may have made it before it failed): reuse it. The tool also checks: for a title that is there already it answers that page with `already_exists: true` and makes nothing.
- **A `page_id` belongs to one research log.** Always pass it with the `log_id` of its own log: a page of another log is refused.

- **At most 1 MB of markdown per call.** A longer text (a big table, a long raw output) goes in several `logbook-add-entry` calls, or better as a saved file with a short entry that points to it.
- **A call fails** → the tools already retry a "not stored yet" answer safely. If a call still fails, `logbook-read` to see whether your entry is there, and send it again only if it is missing. Sending the very same entry again is safe (it is added once); an entry with any word changed is a new one.
- **`already_sent: true`** in the answer of `logbook-add-entry` or `logbook-edit` means this very same change was sent before: it is applied once, not twice. If its text is not on the page (`logbook-read`), someone removed it since: send it with a word changed if it must be there.
- **An old `logbook.md`** in the topic directory (work from before the research log): add its text as the first entry of the log, then replace the content of the file with one line that gives the `url` of the log. After that, write only to the log.

### The tools

Every tool also takes `vlab_id` and `project_id`, both or neither: the project to work in, when it is not the default one. A `log_id` and a `page_id` are UUIDs, as the tools answer them.

| Tool | Arguments | Answer |
|---|---|---|
| `logbook-list` | `search` (optional: words of the name, in order), `page_size` (1–50, default 20), `all_projects` (default false) | `logs` (each with `id`, `name`, `description`, `vlab_id`, `project_id`, `url`), `total`; with `all_projects`, also `failed_projects` and maybe a `note` |
| `logbook-create` | `name` (at most 300 characters), `description` (at most 2000) | the new log, with its `id` and `url` |
| `logbook-open-folder` | `log_id`, `topic` (kebab-case, only for a log with no folder yet), `adopt` (default false) | `path`, `created`, `adopted`, `files` (each with `in_folder`) |
| `logbook-list-pages` | `log_id` | `pages`: `id`, `kind` (`main` or `section`), `title`, `position` |
| `logbook-create-page` | `log_id`, `title` | `page`, `already_exists` |
| `logbook-read` | `log_id`, `page_id` (optional: the main page) | `page_id`, `blocks`: `id`, `type`, `rev`, `markdown` |
| `logbook-add-entry` | `log_id`, `page_id` (optional), `markdown` | `page_id`, `blocks`, `already_sent` |
| `logbook-edit` | `log_id`, `page_id` (optional), `ops`: 1 to 50 operations, see below | `page_id`, `blocks`, `already_sent` |
| `logbook-save-file` | `log_id`, `path` (absolute, inside the topic directory) | `name` (the saved name), `size`, `already_saved`, `log_url` |
| `logbook-list-files` | `log_id` | `files`: `name`, `local_name`, `newest`, `size`, `last_modified` |
| `logbook-fetch-file` | `log_id`, `name` (a saved name), `path` (optional: absolute target in the sandbox) | `name`, `path`, `size` |

The `ops` of `logbook-edit`, applied in order, all or none:

- `{ "append": "<markdown>" }` adds at the end of the page.
- `{ "insert_after": "<block id>", "markdown": "…" }` and `{ "insert_before": "<block id>", "markdown": "…" }` add next to a block.
- `{ "replace": "<block id>", "rev": "<rev>", "markdown": "…" }` rewrites a block; it keeps its id.
- `{ "delete": "<block id>", "rev": "<rev>" }` removes a block.

Limits: 1 MB of markdown per call; a saved file at most 5 GiB; a fetched file at most 50 MB.

### Answers that need you

A tool that cannot do its work answers `{ "error": "…" }`, and the message says what to do. An argument the tool refuses (an id that is not a UUID, more than 1 MB of markdown) is an input error that names the argument: fix it and call again. The answers to know:

| The answer says | Do |
|---|---|
| `block-changed` | Someone edited that block since your read. `logbook-read` again and redo the edit on the new text. |
| `block-missing` | The block is gone. `logbook-read` again. |
| `This research log belongs to project …` | Ask the user whether to work in that project, then call again with its `vlab_id` and `project_id`. |
| `… the research log was not found in this project` | `logbook-list` with `all_projects: true`, ask the user, then pass that project. |
| `This log has no folder in the sandbox yet` | Call `logbook-open-folder` again with a `topic`. |
| `… belongs to research log …` | The topic name is taken: choose a more specific one. |
| `… exists and has no manifest` | Ask the user; on a yes, call again with `adopt: true`. |
| `… has no manifest` / `No folder for this log in the sandbox` | Call `logbook-open-folder` for this log first. |
| `… changed while it was being saved` | A run is still writing the file. Wait until it ends, then save again. |
| `Page … is not a page of research log …` | Use a `page_id` from `logbook-list-pages` of that log. |
| `This research log has no page yet and you may only read it` | You may not write in this log. Tell the user. |
| `The sandbox is still starting` | Call again in a minute. |
| `Too large for one call` | Split the text into several calls. |
| `The sandbox did not finish within 10 minutes` | Call again; if it times out again, tell the user. |
| `Unexpected failure: …` | `logbook-read` (or `logbook-list-files`) to see what was done, then call again once. If it fails again, tell the user. |

---

## Structure

A research log is a set of pages that people and agents edit at the same time. Each page is edited on its own, so a colleague can fix the Caveats while you add to the Results.

### The main page

The first page of every log. It is the report a reader opens first, short:

- At session start: the scientific question in one or two sentences, and why this workflow can answer it.
- At session end: what was found, in a few sentences with the key numbers and units, and whether to trust it. Name the sections a reader should open for the detail (they are listed beside the page in the web app: no links needed).

The detail never goes here: it goes in the section pages.

### The section pages

One page per section of the shape below, titled with the section's name exactly as written here (`Objective`, `Inputs & Provenance`, `Parameters`, `Protocol`, `Runs`, `Results`, `Interpretation`, `Caveats`, `Outputs`, `Next Steps`), created the first time that section has something to say, so the pages come in the order the work happened. Each moment of "When to write" adds one entry to its section's page; a section grows by entries, it is never written once at the end. A section that does not apply to a given workflow gets no page — this is a shape to fill in, not a form to complete. The name and description of the research log replace a title block: there is no front matter and no status field. Each page starts with its content: no `##` heading that repeats its title.

The shape: each `##` line below is a section page's title, and what follows it is what goes on that page.

```markdown
## Objective
<The scientific question, and why this workflow can answer it.>

## Inputs & Provenance
| Entity | Name | Key properties | EntityCore ID |
|---|---|---|---|
| <circuit / morphology / e-model / recording / mesh> | <name> | <region, species, scale…> | [`<uuid>`](https://<domain>/app/entity/<uuid>) |

Why these: <rationale for the selection over alternatives>

## Parameters
| Parameter | Baseline | Used | Units | Applies to | Reference |
|---|---|---|---|---|---|

## Protocol
<Stimulus, duration, recordings, conditions, replicates/seeds, what is held constant between conditions.>

## Runs
| Condition | What it tests | Result entity ID |
|---|---|---|
| <condition> | <what it tests> | [`<uuid>`](https://<domain>/app/entity/<uuid>) |

## Results
<Numbers with units. Each saved figure: its name and one line on what it shows.>

## Interpretation
<What this means for the objective. Include negative and surprising results.>

## Caveats
<Limits on how far the result can be pushed.>

## Outputs
- Saved files: <names returned by logbook-save-file>
- Code: <names returned by logbook-save-file for the scripts in code/>

## Next Steps
<What the result suggests doing next.>
```

---

## Presenting it

The logbook is a deliverable, not a byproduct. At the end of the session, and any time the user asks what was done, give them the `url` of the research log. Nothing is copied or bridged: the user and their colleagues open it in the web app, with the saved figures in it.

---

## Guardrails

- **One research log per topic.** Resuming earlier work means continuing that topic's log, found with `logbook-list`, not starting a fresh one — say so explicitly when resuming.
- **Write it during the session, not after.**
- **Never log secrets.** No tokens, no consent URLs, no auth headers — see [[obi-sandbox-auth]].
- **Record negative results.** A modification that changed nothing is a finding and belongs in the logbook.
- **Units are mandatory** on every numeric value.
- **Never invent a citation.** If a parameter has no source, record it explicitly as an assumption under Caveats.
- **Save what a colleague needs.** A figure, result or script that stays only in the sandbox is invisible to everyone but the user.
- **Never touch `manifest.json`**, and never write to a research log of another project without the user's yes.
