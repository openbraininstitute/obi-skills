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
| Plots, pictures, results, inputs | The research log's files, in EntityCore | `logbook-save-file` from the sandbox, then one entry that shows it |
| Code you ran, scratch files | The sandbox, under `{topic_dir}` | They stay there; nobody else needs them |

- **No `logbook.md`.** Never create or append to a logbook file in the sandbox. When another OBI skill shows `logbook.md` in a folder layout, appends to it, or hands the file to the user, do what this skill says instead.
- **The sandbox is the workshop.** Run code there as usual. As soon as a plot, picture, result or input matters to the user, save it to the research log: a colleague cannot open your sandbox.
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
- Tool names, MCP connector names, sandbox lifecycle (kill/restart), polling loops, retries, timeouts
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
| **Saved files** — plots, pictures, results, inputs | **Yes, saved with `logbook-save-file`.** Refer to them by the name the tool returns. A sandbox path is not a link: nobody but the user can open it. |
| **Workflow activity links** | **No.** Session plumbing — hand them to the user in the reply instead. |
| **Download URLs, tokens, consent URLs** | **Never.** Credentials, not provenance — see "What never goes in" above. |

## The sandbox directory convention

The sandbox is where code runs. This layout governs **all** OBI scientific work on the sandbox. Every skill that writes a file follows it.

**One directory per topic, at the root of the persistent volume:**

```
/home/jovyan/<topic>/
```

`<topic>` is the scientific subject of the conversation, in kebab-case — `alzheimer-ca1`, `nav1.6-fitting`, `v1-microcircuit`, `thalamic-mesh-skeletons`. It names *what is being studied*, not which workflow or API is being used: everything a conversation produces lands under one topic, even when the work spans several skills. One conversation, one topic directory, one research log.

### If the topic directory already exists

Check before creating, and **never write blind into an existing topic directory** — another conversation's results may be in it.

- **Continuing that work** → reuse the directory, and continue the research log found with `logbook-list`, stating explicitly that you are resuming it. Do not start a second log.
- **Unrelated work that happens to collide** → choose a more specific topic name (`alzheimer-ca1-hcn-sweep` rather than a second `alzheimer-ca1`). A name that collides is usually a name that was too vague anyway.

### Inside a topic directory

A fixed backbone, plus input directories named for what they actually hold:

```
/home/jovyan/<topic>/
├── <inputs…>/          ← one dir per input kind, named for its contents
├── results/            ← raw outputs; one subdir per condition when comparing
│   ├── <condition-a>/
│   └── <condition-b>/
├── plots/              ← figures
└── code/               ← every script written, for reproducibility
```

`plots/`, `code/`, and `results/` are the backbone — always present, always named this way, so any skill and any later conversation can find them without asking. The input directories are workflow-specific: name them for their contents (`circuit-original/`, `circuit-disease/`, `meshes/`, `recordings/`, `morphologies/`). Where a workflow compares conditions, mirror those condition names under `results/`.

Set this up **before any scientific work starts**:

```python
# on the OBI sandbox
import os

topic_dir = "/home/jovyan/<topic>"                 # kebab-case scientific subject of this conversation

if os.path.exists(topic_dir):
    print("EXISTS — resume this topic, or pick a more specific name:")
    print(sorted(os.listdir(topic_dir)))
else:
    for sub in ["results", "plots", "code"]:       # + the input dirs this workflow needs,
        os.makedirs(f"{topic_dir}/{sub}")          # + results/<condition> per condition
print(topic_dir)
```

**Use `topic_dir` as the root for every sandbox path for the rest of the conversation.** Build absolute paths from it — never scatter files in `/tmp`, `~`, or a bare `/home/jovyan/outputs`, which either do not survive or cannot be traced back to the work that produced them.

### Using saved files again

A saved file stays in the sandbox too: saving is a copy. To use it later, read the sandbox copy if it is still there. If it is gone (another project's sandbox, a colleague's research, a cleaned folder), `logbook-list-files` shows what the research saved and `logbook-fetch-file` puts a copy back in the sandbox.

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
| A run finishes | The numbers that came out, with units; save the result files that matter |
| A figure is produced | Save it, then one line on what it shows |
| Interpretation forms | What the result means, including surprises and negative results |
| Session end | Results summary, caveats, next steps, and that the work is complete |

**Cite before you use.** Any biophysical parameter that came from the literature gets its reference recorded at the moment it is adopted. An unattributed parameter is a defect, not a shortcut.

### The calls

Each tool's own description gives its exact arguments.

| Moment | Call |
|---|---|
| Session start | `logbook-list`: the research logs of the project. Is this topic already there? Match by meaning, not by spelling: a person may have typed the title in the web app. **Found** → resume that log and say so. **Not found** → `logbook-create`, with the title as its name and the scientific question as its description |
| Every moment of the table above | One `logbook-add-entry` with markdown: one section of the Structure below, added at the end. It needs no read first |
| A plot, picture, result or input that matters | `logbook-save-file` with its sandbox path and its kind, then one `logbook-add-entry` that shows it and says what it shows |
| Changing or removing earlier text | `logbook-read` first: it returns the blocks, each with an `id`, a `rev` and its markdown. Then one `logbook-edit` with the operations: `replace` (the whole block with the words changed; it keeps its id), `delete`, `insert_after` or `insert_before`, each naming a block by `id` and, for replace and delete, its `rev`. A `block-changed` answer means someone edited that block since your read: read again and redo the edit on the new text, never over it |
| A long log | `logbook-list-pages` and `logbook-create-page` split it into section pages. One page is enough for most sessions |
| Session end | The last entry, then give the user the `url` of the log |

- **A call fails** → the tools already retry a "not stored yet" answer safely. If a call still fails, `logbook-read` to see whether your entry is there, and send it again only if it is missing: a new call with the same entry adds it twice.
- **An old `logbook.md`** in the topic directory (work from before the research log): add its text as the first entry of the log, then replace the content of the file with one line that gives the `url` of the log. After that, write only to the log.

---

## Structure

Sections in the order the work happened; each section is one entry. The name and description of the research log replace a title block: there is no front matter and no status field. Sections that do not apply to a given workflow are simply omitted — this is a shape to fill in, not a form to complete.

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
- Code: in the user's sandbox, <topic_dir>/code/

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
- **Save what a colleague needs.** A figure or result that stays only in the sandbox is invisible to everyone but the user.
