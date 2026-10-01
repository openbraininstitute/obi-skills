---
name: emodel-building
description: Guide for building electrical (e-)models via the obi-one and EntityCore REST APIs — a two-stage workflow of e-feature extraction from electrophysiology recordings followed by BluePyEModel optimization against those features. Optimization registers a draft EModel (and a draft MEModel pairing it with the exemplar morphology). Use when the user wants to fit an e-model to experimental traces, extract e-features for optimization targets, or run an emodel optimization campaign.
license: Apache-2.0
---

# E-Model Building: Feature Extraction + Optimization

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — obtain, exchange, and refresh OBI credentials, and the offline-access consent flow before long-running optimization jobs. The "Authentication" section assumes a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) run heavy work on the OBI sandbox and get result files back to the user.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every e-model building session.
> - [[obi-links]] — every entity id, sandbox file, and launched campaign goes out as a hyperlink.
> - [[parameter-scan]] — the shared scan → estimate → launch mechanics and the campaign-vs-config distinction, used by both stages.
> - [[ephys-efeature-extraction]] — the *analysis* counterpart: computing ephys metrics on a single trace without building an e-model. This skill is about extraction as the **target-defining stage of optimization**, which is a different, launchable task.

## Overview

Building an e-model is a **two-stage** workflow, each stage a launch-system-backed obi-one task:

1. **E-feature extraction** (`task_type: efeature_extraction`) — from electrophysiology recordings, extract the e-features (per protocol) that become the **optimization targets**.
2. **E-model optimization** (`task_type: emodel_optimization`) — run BluePyEModel/NEURON to fit ion-channel parameters so the model reproduces the extracted features. On success it registers a **draft EModel** and a **draft MEModel** (the e-model paired with its exemplar morphology).

Both stages use the standard scan → estimate → launch pattern (see [[parameter-scan]]).

> **Optimization is an optional obi-one capability.** It requires the `bluepyemodel` extra. If the deployment was built without it, the optimization endpoint and task are not registered — extraction still works. Check that the optimization endpoint exists before relying on it.

## Entity Model

```
ElectricalCellRecording(s)   ← input traces, from EntityCore
    │
    ▼   Stage 1: e-feature extraction  (Extract activity)
efeature_extraction__campaign / __config (task-config)   → LAUNCHABLE
    │   task_type = efeature_extraction
    ▼
extracted e-features (optimization targets)
    │
    │   + exemplar morphology + ion channel models
    ▼   Stage 2: optimization  (optimize / Build activity)
emodel_optimization__campaign / __config (task-config)   → LAUNCHABLE
    │   task_type = emodel_optimization
    ▼
EModel (draft)  +  MEModel (draft)   ← outputs
    (EModel: iteration, score, seed, exemplar_morphology, ion_channel_models, mtypes/etypes)
```

## Authentication (all requests)

- `Authorization: Bearer <keycloak_token>` — Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` / `project-id: <uuid>` — HTTP headers from `$OBI_VLAB_ID` / `$OBI_PROJECT_ID`

Read from the environment, never from memory. See [[virtual-lab-manager-api]].

Base URLs: `https://staging.cell-a.openbraininstitute.org` / `https://cell-a.openbraininstitute.org`.

---

## Stage 1 — E-feature Extraction

### Pre-requisite: Find the Recordings

```
GET /api/entitycore/electrical-cell-recording?project_id=<project-id>
```

Each `electrical-cell-recording` (trace) carries `ljp` (liquid junction potential, mV), `recording_location`, `recording_type`, and its stimuli — the raw material for feature extraction.

### Step 1: Generate the Campaign

**Endpoint:** `POST /api/obi-one/generated/e-model-e-feature-extraction-scan-config-generate-grid`

Body is an `EModelEFeatureExtractionScanConfig` selecting the recording(s) and the protocols/features to extract (the "select e-features by protocol" selection in the web app). Returns the **campaign ID**.

### Step 2–4: Find child, estimate, launch

```
GET /api/entitycore/task-config?task_config_type=efeature_extraction__config&task_config_generator_id=<campaign-id>
POST /api/obi-one/declared/task/estimate   { "task_type": "efeature_extraction", "config_id": "<child-config-uuid>" }
POST /api/obi-one/declared/task/launch     { "task_type": "efeature_extraction", "config_id": "<child-config-uuid>" }
```

The extracted features are the input targets for Stage 2. In the web app, extraction is the **Extract** activity, from an `ElectricalCellRecording` → `EFeatureExtractionCampaign`.

---

## Stage 2 — E-model Optimization

> Requires the `bluepyemodel` extra (see Overview). Skip this stage if the endpoint is absent.

### Step 1: Generate the Campaign

**Endpoint:** `POST /api/obi-one/generated/e-model-optimization-scan-config-generate-grid`

Body is an `EModelOptimizationScanConfig`: the extracted e-features (targets), an **exemplar morphology**, the ion-channel **mechanisms** and their **parameters** (with bounds), and optimization settings. Returns the **campaign ID**.

### Step 2–4: Find child, estimate, launch

```
GET /api/entitycore/task-config?task_config_type=emodel_optimization__config&task_config_generator_id=<campaign-id>
POST /api/obi-one/declared/task/estimate   { "task_type": "emodel_optimization", "config_id": "<child-config-uuid>" }
POST /api/obi-one/declared/task/launch     { "task_type": "emodel_optimization", "config_id": "<child-config-uuid>" }
```

Optimization is heavy (BluePyEModel + NEURON on a launch-system worker) and long-running — obtain offline-access consent first, per [[obi-sandbox-auth]]. Sweeping `seed` (a list) is the common way to run several optimization replicas; each becomes a scan coordinate (see [[parameter-scan]]).

### Step 5: Monitor and Collect

- **Poll:** `GET /api/obi-one/declared/task/<job-id>`
- **Stream:** `GET /api/obi-one/declared/task/<job-id>/stream`

On success, a **draft EModel** and a **draft MEModel** are registered:

```
GET /api/entitycore/emodel/{id}     → iteration, score, seed, exemplar_morphology, ion_channel_models, mtypes/etypes
GET /api/entitycore/memodel/{id}    → morphology_id, emodel_id, validation_status
```

Review the `score` and per-feature errors before promoting the draft.

## Critical: Campaign ID ≠ Launchable Config ID (both stages)

Each generate endpoint returns the campaign ID; estimate/launch need the child config ID. See [[parameter-scan]].

---

## Working directory

```
/home/jovyan/<topic>/
├── logbook.md
├── recordings/         ← ephys traces pulled from EntityCore
├── features/           ← extracted e-features (optimization targets)
├── results/            ← optimized e-models; one subdir per seed / parameter setting
├── plots/              ← feature fits, traces, convergence
└── code/
```

## Logbook

Every e-model building session is logged per [[obi-logbook]].

Record, as the session goes:

- **Objective** — the cell type (e-type) being modelled and what the e-model is for.
- **Experimental data** — which recordings, from which cells/protocols, species and brain region, LJP correction, and why those traces.
- **Extracted features** — which e-features per protocol became targets, and any that were excluded and why. Report values with units.
- **Optimization setup** — the exemplar morphology, the mechanisms and free parameters (with bounds and the biophysical reasoning), and how many seeds.
- **Outcome** — the resulting e-model(s): scores, which features are well/poorly fit, and the chosen model with justification.
- **Provenance table** — recording IDs in → EModel/MEModel IDs out.
- **Caveats** — features that could not be matched, over-fitting risks, morphology–electrophysiology mismatch.

Do **not** log endpoints, campaign-vs-config mechanics, cost estimates, job polling, or auth — see [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], `{domain}` matches the environment the calls ran against.

- **Entities** — `https://{domain}/app/entity/{id}`. Link the input recordings, the extracted-feature results, and the output EModel and MEModel; link id cells in the provenance table.
- **Sandbox files** — feature plots, trace fits, convergence figures: `download_url` from `{obi}:get-sandbox-download-url` with `/files/` → `/lab/tree/`.
- **Launched campaigns** — e-feature extraction is the **Extract** activity: `...workflows?tactivity=extract&ttype=efeature_extraction_campaign`. E-model optimization is the **Build** activity: `...workflows?tactivity=build&ttype=emodel_optimization_campaign`. Base: `https://{domain}/app/virtual-lab/{vlab_id}/{project_id}/workflows`.
