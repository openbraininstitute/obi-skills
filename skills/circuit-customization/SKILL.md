---
name: circuit-customization
description: Guide for creating a customized circuit derived from an existing (active) parent circuit by uploading override files — edges, e-models (HOC), mechanisms (MOD), nodes, node sets, or a circuit_config — via the obi-one REST API. Unlike other circuit workflows this is a single synchronous multipart call, not a scan/campaign. The new circuit is created in draft and becomes active after async validation. Use when the user wants to modify a circuit's synapses, add/replace e-models, swap mechanisms, or edit node/edge populations.
license: Apache-2.0
---

# Circuit Customization: API Flow

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — obtain, exchange, and refresh OBI credentials. The "Authentication" section assumes a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) stage the override files on the OBI sandbox and get result links back to the user.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every customization session.
> - [[obi-links]] — every entity id, sandbox file, and job goes out as a hyperlink.
> - [[obi-circuit-simulation]] — what a SONATA circuit is (nodes, edges, circuit_config, model_template/HOC, MOD mechanisms). Read it first if the circuit file layout is unfamiliar.

## Overview

Circuit customization **derives a new circuit from an existing active parent circuit** by uploading one or more override files. It is used to:

- modify synapses (upload new **edge** population files) → derivation label `synaptic_modification`
- add or replace **e-models** (upload HOC files, optionally mapped to populations) → `emodel_addition` / `emodel_modification`
- swap **mechanisms** (upload MOD files)
- edit **node** populations, **node sets**, or the **circuit_config** itself → `population_modification`

Unlike extraction, synaptome, or simulation, this is **not** a scan/campaign task. It is a single **synchronous multipart POST**. The new circuit is created with `lifecycle_status = draft` and transitions to `active` after an async validation job passes.

## Entity Model

```
Circuit (parent, must be lifecycle_status = active)   ← input
    │  upload overrides (edges / emodels / mechanisms / nodes / node_sets / circuit_config)
    ▼
Circuit (child, draft)   ← created immediately, derived from parent
    │  async validation job
    ▼
Circuit (child, active)  ← after validation passes

derivation: used_id = parent, generated_id = child,
            derivation_type = circuit_customization,
            label ∈ { synaptic_modification, emodel_addition,
                      emodel_modification, population_modification }
```

## Authentication

- `Authorization: Bearer <keycloak_token>` — Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` / `project-id: <uuid>` — HTTP headers, from `$OBI_VLAB_ID` / `$OBI_PROJECT_ID`

Read from the environment, never from memory. See [[virtual-lab-manager-api]].

Base URLs: `https://staging.cell-a.openbraininstitute.org` / `https://cell-a.openbraininstitute.org`.

## Pre-requisite: An Active Parent Circuit

```
GET /api/entitycore/circuit/{parent_circuit_id}
```

The parent **must** have `lifecycle_status = active` — only validated circuits can be customized. A draft or disqualified parent returns 409.

## The Call

**Endpoint:** `POST /api/obi-one/declared/circuit/customize`

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `parent_circuit_id` | UUID (form) | ✓ | The active circuit to derive from |
| `name` | string (form) | ✓ | Name for the new circuit |
| `description` | string (form) | | Description (default: empty) |
| `edges_files` | file[] | | Edge population H5 files (synapse modifications) |
| `emodel_files` | file[] | | HOC e-model files |
| `emodel_population_manifest` | string (form, JSON) | | Maps HOC filename → population name, e.g. `{"MyCell.hoc": "my_population"}`, for per-population placement |
| `mechanism_files` | file[] | | MOD mechanism files |
| `node_files` | file[] | | Node population H5 files |
| `node_sets_file` | file | | SONATA node-set JSON file |
| `circuit_config_file` | file | | `circuit_config.json` override |

**At least one override file is required** (otherwise 422).

**Rules for combined uploads:**
- When uploading nodes or edges **alongside a `circuit_config` override**, every uploaded file must be referenced in the config's `networks` section — that config is authoritative.
- A `node_sets` upload **replaces** the file the circuit config references when it carries the same name; otherwise it is added and the config is repointed at it.
- To place HOC files into a population-specific model directory, supply `emodel_population_manifest`.

### Response

```json
{
  "circuit_id": "<uuid>",
  "status": "draft",
  "message": "...",
  "job_id": "<uuid-or-null>"
}
```

The circuit is created immediately in **draft**. Poll for it to become **active**:

```
GET /api/entitycore/circuit/{circuit_id}
→ lifecycle_status: "draft" → "active" (or "disqualified" if validation fails)
```

## Validation (Layer 1, synchronous)

Before the entity is created, obi-one runs structural checks on the uploads and rejects malformed files up front:
- **edges** — each population must carry `source_node_id`, `target_node_id`, `edge_type_id`
- **HOC / MOD / nodes / node_sets** — structural conformance and, for mechanisms, that they are not shadowing built-in NEURON mechanisms

A failure here returns an HTTP error immediately (nothing is registered). Deeper SONATA conformance is checked by the async validation job that flips draft → active.

---

## Working directory

```
/home/jovyan/<topic>/
├── logbook.md
├── overrides/          ← the edge/hoc/mod/node/config files being uploaded (keep pristine)
├── results/            ← notes on the derived circuit, validation outcome
└── code/               ← scripts that generated the override files
```

Keep `overrides/` as the exact files uploaded — provenance of the customization depends on being able to reproduce them.

## Logbook

Every customization session is logged per [[obi-logbook]].

Record, as the session goes:

- **Objective** — what is being changed and the scientific reason (e.g. "strengthen E→I synapses to test disinhibition", "swap in a calibrated L5 e-model").
- **Parent circuit** — its provenance, brain region, scale, and what it represented before customization.
- **The modification, in scientific terms** — which populations/synapses/mechanisms changed and how (e.g. "AMPA conductance doubled on PC→PV connections"), not the filenames. Record the derivation category (synaptic / e-model / population modification).
- **Result** — the derived circuit and how it differs biologically from the parent; whether validation passed.
- **Caveats** — anything a downstream modeller must know: partial overrides, assumptions baked into the new files, consistency risks between edited and untouched parts.

Do **not** log endpoint details, multipart mechanics, HTTP status codes, or auth — see [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], `{domain}` matches the environment the calls ran against.

- **Entities** — `https://{domain}/app/entity/{id}`. Link the parent circuit and the derived circuit; link id cells in the provenance table (parent in → derived out).
- **Sandbox files** — the override files and any diff/summary: `download_url` from `{obi}:get-sandbox-download-url` with `/files/` → `/lab/tree/`.
- **Jobs** — customization registers a circuit rather than launching a scan campaign, so there is normally no workflows activity page to link. Link the derived circuit entity instead. If validation exposes a follow-up job, link it per [[obi-links]].
