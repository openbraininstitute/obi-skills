---
name: parameter-scan
description: Generic skill — the shared parameter-scan model behind every obi-one scan-config workflow (simulations, circuit extraction, synaptome/e-model/synapse building, EM mapping, and more). Explains how a ScanConfig with list-valued parameters becomes a multi-dimensional grid of single configs, the campaign-vs-child-config distinction, and the generate → count → estimate → launch → poll REST flow. Read it once per session; every obi-one workflow skill defers to this one for scan mechanics rather than re-deriving them. Use whenever a task sweeps a parameter, runs a campaign, or mentions grid/scan coordinates.
license: Apache-2.0
---

# Parameter Scans in obi-one

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — credentials, and the offline-access consent flow before launching long-running or >20-neuron jobs.
> - [[obi-links]] — link every campaign, config, and generated entity handed to the user.
> - [[obi-logbook]] — record the scientific design of the scan (what was varied and why), not the grid mechanics.
>
> **Workflow skills that defer to this one:** [[obi-circuit-simulation]], [[single-cell-simulation-api]], [[ion-channel-api]], [[skeletonization-api]], [[circuit-extraction]], [[build-synaptome]], [[synapse-parameterization]], [[em-synapse-mapping]], [[emodel-building]], [[connectivity-matrix-extraction]], [[ephys-efeature-extraction]].

## The core idea

obi-one is built on a small set of abstractions shared by *every* workflow:

- **Block** — a group of parameters (an `Initialize` block, a stimulus, a neuron set, a recording…).
- **ScanConfig** — a whole workflow configuration, composed of Blocks.
- **SingleConfig** — one concrete point: every parameter has a single value.
- **Scan** — the crucial rule: **any Block parameter given as a *list* becomes a dimension of a multi-dimensional grid.** The scan is the Cartesian product of all list-valued parameters; each combination is one `SingleConfig` ("coordinate").

So a simulation with `duration = [100, 200, 300]` and `input_current = [0.1, 0.2]` produces a **3 × 2 = 6** coordinate grid — six single configs generated from one scan config. This is how OBI runs parameter sweeps uniformly across simulations, extractions, e-model optimization seeds, and so on.

> **Scalar vs list is the whole trick.** A scalar is a fixed value; a list is an axis to sweep. Some fields deliberately avoid list semantics (e.g. EM synapse mapping wraps its neuron set in a *named tuple* so a set of neurons is not mistaken for a scan axis — a *list of* named tuples sweeps over different sets). When in doubt, check the workflow skill.

## Two execution styles

Not every task runs the same way. There are two families:

1. **Launch-system-backed tasks** (circuit simulation, circuit extraction, synaptome build, synapse parameterization, EM synapse mapping, e-feature extraction, e-model optimization, skeletonization, …). These generate persistent **task-config** entities in EntityCore and are launched as jobs. This skill's REST flow applies.
2. **Local-only tasks** (connectivity matrix extraction, electrophysiology metrics, morphology metrics/containerization, folder compression, …). These have **no `/task/launch` path**; you run them through the `obi_one` Python library in the sandbox. The *scan model* (lists → grid) is identical, but you drive it in-process, not via the campaign REST flow below.

Each workflow skill states which family it belongs to.

## Authentication (all requests)

- `Authorization: Bearer <keycloak_token>` — Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` / `project-id: <uuid>` — HTTP headers from `$OBI_VLAB_ID` / `$OBI_PROJECT_ID`

Read from the environment, never from memory. See [[virtual-lab-manager-api]].

Base URLs: `https://staging.cell-a.openbraininstitute.org` / `https://cell-a.openbraininstitute.org`.

## The scan REST flow (launch-system-backed tasks)

### 0. (Optional) Preview the grid size before generating

**Endpoint:** `POST /api/obi-one/declared/scan_config/grid-scan-coordinate-count`

Body: the full ScanConfig form. Returns the integer number of coordinates the sweep would produce. Use it to catch an accidental combinatorial explosion (e.g. three lists of ten → 1000 jobs) *before* creating anything.

### 1. Generate the campaign

**Endpoint:** `POST /api/obi-one/generated/<scan-config-kebab>-generate-grid`

The endpoint name is derived from the ScanConfig class name (CamelCase → kebab-case). Each workflow skill gives its exact path, e.g.:

| Workflow | Generate endpoint |
|----------|-------------------|
| Circuit simulation | `/generated/circuit-simulation-scan-config-generate-grid` |
| Circuit extraction | `/generated/circuit-extraction-scan-config-generate-grid` |
| Build synaptome | `/generated/me-model-synaptic-model-placement-scan-config-generate-grid` |
| Synapse parameterization | `/generated/synapse-parameterization-scan-config-generate-grid` |
| EM synapse mapping | `/generated/em-synapse-mapping-scan-config-generate-grid` |
| E-feature extraction | `/generated/e-model-e-feature-extraction-scan-config-generate-grid` |
| E-model optimization | `/generated/e-model-optimization-scan-config-generate-grid` |

The body carries an `info` block (`campaign_name`, `campaign_description`), an `initialize` block (the primary input), and the workflow's parameter blocks. **Returns the campaign ID** as a plain string.

> Some scan configs (notably simulations and morphology metrics) execute their single configs **immediately** on generation; extraction/build/optimization/skeletonization tasks only *generate* the configs, leaving you to estimate and launch. The workflow skill says which.

### 2. Find the launchable child config IDs

The generate endpoint returns the **campaign** ID, not the launchable configs. Query EntityCore for the children:

```
GET /api/entitycore/task-config?task_config_type=<workflow>__config&task_config_generator_id=<campaign-id>
```

Each child has `task_config_generator_id` = the campaign ID. There is one child per grid coordinate.

### 3. Estimate cost (optional but recommended)

**Endpoint:** `POST /api/obi-one/declared/task/estimate`

```json
{ "task_type": "<task_type>", "config_id": "<child-config-uuid>" }
```

### 4. Launch each child config

**Endpoint:** `POST /api/obi-one/declared/task/launch`

```json
{ "task_type": "<task_type>", "config_id": "<child-config-uuid>" }
```

Returns `{ task_type, config_id, activity_id, job_id }`. Launch each coordinate you want to run.

### 5. Poll / stream

- `GET /api/obi-one/declared/task/<job_id>` — job status
- `GET /api/obi-one/declared/task/<job_id>/stream` — NDJSON progress stream

## Critical: Campaign ID ≠ Launchable Config ID

This is the single most common mistake:

| ID | Returned by | Use for |
|----|-------------|---------|
| **Campaign ID** | the `…-generate-grid` endpoint | querying EntityCore for children; tracking the campaign |
| **Child config ID** | the EntityCore `task-config` query (step 2) | `/task/estimate` and `/task/launch` |

**Passing the campaign ID to `/task/launch` fails with a 500** — the launcher tries to parse the campaign's grid-scan JSON (a `GridScanGenerationTask`) as a single config and fails validation. Always launch the *child* config.

## `task_type` values (for estimate / launch)

| Workflow | `task_type` | Family |
|----------|-------------|--------|
| Circuit simulation | `circuit_simulation` | launch |
| Circuit extraction | `circuit_extraction` | launch |
| Build synaptome | `circuit_single_build` | launch |
| Synapse parameterization | `circuit_synaptic_physiology_assignment` | launch |
| EM synapse mapping | `em_synapse_mapping` | launch |
| E-feature extraction | `efeature_extraction` | launch |
| E-model optimization | `emodel_optimization` | launch (optional extra) |
| Skeletonization | `morphology_skeletonization` | launch |
| Connectivity matrix extraction | `connectivity_matrix_extraction` | local-only |
| Electrophysiology metrics | `electrophysiology_metrics` | local-only |

## Logbook

Per [[obi-logbook]], the scan's **scientific design** belongs in the logbook: what parameters were swept, over what ranges, and **why** — what each axis controls biologically and what the sweep is meant to reveal. Record the resulting coordinate count and which coordinates were actually launched. Do **not** log the campaign-vs-config mechanics, endpoint paths, job polling, or the 500-on-campaign-id gotcha — those are plumbing.

## Linking

Per [[obi-links]], link the campaign, the launched jobs, and every generated entity. Launched campaigns resolve to the workflows activity page: `https://{domain}/app/virtual-lab/{vlab_id}/{project_id}/workflows?tactivity=<activity>&ttype=<campaign_type>` — the workflow skill gives the right `tactivity` (Build / Extract / Simulate / …) and `ttype`. `{domain}` matches the environment the calls ran against.
