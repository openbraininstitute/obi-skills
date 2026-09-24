---
name: skeletonization-api
description: Guide for creating, generating, and launching skeletonization campaigns via the obi-one and EntityCore REST APIs. Use when the user wants to skeletonize EM cell meshes, create skeletonization campaigns, or launch morphology_skeletonization tasks.
license: Apache-2.0
---

# Skeletonization Campaign: End-to-End API Flow

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — how to obtain, exchange, and refresh OBI credentials, and the offline-access consent flow before long-running jobs. Never construct auth calls ad hoc; the "Authentication" section below assumes a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) run heavy work on the OBI sandbox, and get result files (skeletons, figures) back to the user from there.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every skeletonization session. See the Logbook section below.
> - [[obi-links]] — every entity id, sandbox file, and launched campaign handed to the user goes out as a hyperlink, never as a bare UUID or path. See the Linking section below.

## Overview

A skeletonization campaign converts EM cell meshes into skeleton morphologies. The flow involves 3 steps across 2 APIs:

1. **Generate the campaign** → `POST` to obi-one, which creates entities in EntityCore
2. **Estimate cost** → `POST` to obi-one with the *child* config ID
3. **Launch the job** → `POST` to obi-one with the *child* config ID

## Entity Model

```
skeletonization__campaign (task-config)       ← parent, stores grid-scan parameters
    │
    ├── skeletonization__config (task-config)  ← child, one per grid coordinate, LAUNCHABLE
    │       └── task_config_generator_id → campaign ID
    │
    └── task-activity (skeletonization__config_generation)  ← links campaign → configs
```

- **Campaign** stores `obi_one_scan.json` (full grid parameters, type: `GridScanGenerationTask`)
- **Config(s)** store `obi_one_coordinate.json` (single concrete config, type: `SkeletonizationSingleConfig`)

## Authentication (all requests)

Every request requires:

- `Authorization: Bearer <keycloak_token>` — OIDC token from Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` — HTTP header, from `$OBI_VLAB_ID` in the sandbox
- `project-id: <uuid>` — HTTP header, from `$OBI_PROJECT_ID` in the sandbox

Read both from the environment, never from memory: a tool call can be redirected to another project, and the environment follows while remembered ids do not. See [[virtual-lab-manager-api]].

Base URLs:

- Staging: `https://staging.cell-a.openbraininstitute.org`
- Production: `https://cell-a.openbraininstitute.org`

## Pre-requisite: Finding EM Cell Mesh IDs

Before creating a campaign, you need mesh IDs:

```
GET /api/entitycore/em-cell-mesh?project_id=<project-id>
```

This returns available meshes in the project that can be skeletonized.

## Step 1: Generate the Campaign

**Endpoint:** `POST /api/obi-one/generated/skeletonization-scan-config-generate-grid`

**Request body:**

```json
{
  "type": "SkeletonizationScanConfig",
  "info": {
    "type": "Info",
    "campaign_name": "My Skeletonization Campaign",
    "campaign_description": "Skeletonizing kaust_1 meshes"
  },
  "initialize": {
    "type": "SkeletonizationScanConfig.Initialize",
    "cell_mesh": {
      "type": "EMCellMeshFromID",
      "id_str": "<em-cell-mesh-uuid>"
    },
    "neuron_voxel_size": 0.1,
    "spines_voxel_size": 0.1,
    "write_raw_spines": true
  }
}
```

### Parameter Sweep

To generate multiple coordinates in the grid, pass lists instead of scalars:

```json
"neuron_voxel_size": [0.05, 0.08, 0.1]
```

This creates 3 child configs (one per value).

### Multiple Meshes

```json
"cell_mesh": [
  {"type": "EMCellMeshFromID", "id_str": "<mesh-uuid-1>"},
  {"type": "EMCellMeshFromID", "id_str": "<mesh-uuid-2>"}
]
```

### Response

`200 OK` with the **campaign ID** as a plain string:

```
"797b737d-8f2c-42a1-8811-b8e4520dad04"
```

### What This Creates in EntityCore

| Entity | Type | Asset | Role |
|--------|------|-------|------|
| Campaign | `task-config` (task_config_type: `skeletonization__campaign`) | `obi_one_scan.json` | Parent — stores grid parameters |
| Config(s) | `task-config` (task_config_type: `skeletonization__config`) | `obi_one_coordinate.json` | Child — one per grid coordinate, launchable |
| Activity | `task-activity` (type: `skeletonization__config_generation`) | — | Links campaign → configs |

Each child config has `task_config_generator_id` = campaign ID.

## Step 2: Find the Child Config IDs

The generate endpoint returns the **campaign** ID, not the launchable config IDs. To find the children, query EntityCore:

```
GET /api/entitycore/task-config?task_config_type=skeletonization__config&task_config_generator_id=<campaign-id>
```

The child config ID(s) are what you pass to estimate and launch.

## Step 3: Estimate Cost (optional but recommended)

**Endpoint:** `POST /api/obi-one/declared/task/estimate`

**Request body:**

```json
{
  "task_type": "morphology_skeletonization",
  "config_id": "<child-config-uuid>"
}
```

**Response:**

```json
{
  "task_type": "morphology_skeletonization",
  "config_id": "<child-config-uuid>",
  "cost": 240.55,
  "parameters": { "..." }
}
```

## Step 4: Launch the Job

**Endpoint:** `POST /api/obi-one/declared/task/launch`

**Request body:**

```json
{
  "task_type": "morphology_skeletonization",
  "config_id": "<child-config-uuid>"
}
```

**Response:**

```json
{
  "task_type": "morphology_skeletonization",
  "config_id": "<child-config-uuid>",
  "activity_id": "<task-activity-uuid>",
  "job_id": "<job-uuid>"
}
```

## Step 5: Monitor the Job

**Poll status:**

```
GET /api/obi-one/declared/task/<job-id>
```

**Stream output (NDJSON):**

```
GET /api/obi-one/declared/task/<job-id>/stream
```

## Critical: Campaign ID ≠ Launchable Config ID

| ID | Use for |
|----|---------|
| Campaign ID (returned by generate-grid) | Querying EntityCore to find children, tracking the campaign |
| Child config ID(s) | `/task/estimate` and `/task/launch` |

**Passing the campaign ID to `/task/launch` will result in a 500 error** — it tries to parse the grid-scan JSON (`GridScanGenerationTask`) as a `SkeletonizationSingleConfig` and fails Pydantic validation.

## Optional: Count Grid Coordinates Before Generating

To preview how many configs will be generated without actually creating them:

**Endpoint:** `POST /api/obi-one/declared/scan_config/grid-scan-coordinate-count`

**Request body:** Same as the generate endpoint (the full `SkeletonizationScanConfig` form).

**Response:** Integer count of coordinates (e.g., `3`).

## Field Reference

### SkeletonizationScanConfig.Initialize

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `cell_mesh` | `EMCellMeshFromID` or list | required | — | EM cell mesh(es) to skeletonize |
| `neuron_voxel_size` | float or list[float] | 0.1 | 0.005–0.1 μm | Neuron reconstruction resolution |
| `spines_voxel_size` | float or list[float] | 0.1 | 0.1–0.5 μm | Spine reconstruction resolution |
| `write_raw_spines` | bool | true | — | Include full-resolution spine meshes in output |

### EMCellMeshFromID

| Field | Type | Description |
|-------|------|-------------|
| `type` | literal | Always `"EMCellMeshFromID"` |
| `id_str` | string (UUID) | EntityCore ID of the em-cell-mesh entity |

### Info

| Field | Type | Description |
|-------|------|-------------|
| `type` | literal | Always `"Info"` |
| `campaign_name` | string (min 1 char) | Display name for the campaign |
| `campaign_description` | string (min 1 char) | Description of the campaign |

---

## Working directory

All files this workflow produces go under the conversation's topic directory on the persistent volume, per the convention in [[obi-logbook]] — one directory per scientific topic (`thalamic-mesh-skeletons`, `v1-l4-em-reconstruction`), created before any work starts, reused if it already exists:

```
/home/jovyan/<topic>/
├── logbook.md
├── meshes/             ← EM cell meshes pulled from EntityCore
├── results/            ← skeleton morphologies; one subdir per parameter setting
├── plots/              ← morphometrics, skeleton overlays
└── code/
```

`logbook.md`, `results/`, `plots/`, and `code/` are fixed by [[obi-logbook]]; `meshes/` holds this workflow's inputs. Name the `results/` subdirectories after the parameter setting that produced them, so a skeleton can always be traced back to its grid coordinate.

## Logbook

Every skeletonization session is logged per [[obi-logbook]] — read it for the location, format, and content rules.

Record, as the session goes:

- **Objective** — what these skeletons are for (morphometric analysis, circuit building, comparison across cell types) and why skeletonization is the right step.
- **Input meshes** — which EM cell meshes, from which dataset/volume, species and brain region, cell type where known, and how many. Note why those meshes were chosen.
- **Skeletonization parameters** — the values swept and, crucially, **why that range** — what morphological feature the parameter controls and what a too-low/too-high value would do to the reconstruction. Record units.
- **Grid design** — how many coordinates the sweep produced and what each axis varies.
- **Outcome per condition** — resulting skeleton morphologies and their morphometrics (neurite length, branch points, tortuosity — with units); which parameter settings gave anatomically plausible skeletons and which produced artefacts (spurious branches, merged neurites, truncation).
- **Chosen setting** — which parameterisation is adopted for downstream use, and the morphological reasoning behind it.
- **Provenance table** — mesh IDs in, morphology IDs out.
- **Caveats** — mesh quality, segmentation errors inherited from the EM volume, incomplete arbors at the volume boundary.

Do **not** log endpoints, campaign-vs-config ID mechanics, cost estimates, job status polling, or auth — see the "What never goes in" list in [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], every entity, file, and campaign mentioned in a reply goes out as a hyperlink — a bare UUID or a bare path is a defect, not a style choice. `{domain}` is `staging.openbraininstitute.org` on staging, `www.openbraininstitute.org` on production, and must match the environment the calls ran against.

- **Entities** — `https://{domain}/app/entity/{id}`. Link the input EM cell meshes, the skeletonization campaign, and each skeleton morphology produced. In the provenance table (meshes in → morphologies out), link the id cells themselves.
- **Sandbox files** — meshes, skeletons, and morphometric plots: take the `download_url` from `{obi}:get-sandbox-download-url` and swap `/files/` for `/lab/tree/`, keeping the rest of the path (`home/jovyan` included). A `results/<parameter-setting>/` directory link is often more useful than one link per skeleton.
- **Launched campaigns** — `https://{domain}/app/virtual-lab/{vlab_id}/{project_id}/workflows?tactivity=process&ttype=skeletonization_campaign`. Skeletonization lives under the **Process data** activity, so send `tactivity=process`; `ttype` alone leaves the page on the default Build tab and shows nothing.
