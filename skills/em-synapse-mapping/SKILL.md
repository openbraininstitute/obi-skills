---
name: em-synapse-mapping
description: Guide for mapping the locations of afferent synapses reconstructed from electron-microscopy (EM) onto one or more spiny morphologies, producing a SONATA circuit, via the obi-one and EntityCore REST APIs. Neurons are supplied as cell morphologies or ME-models; the output circuit carries physical and virtual edge populations built from the EM synapse locations. Use when the user wants to map EM synapses onto morphologies, build an EM-derived synaptome/circuit, or turn dense EM reconstruction synapses into a simulatable circuit.
license: Apache-2.0
---

# EM Synapse Mapping: End-to-End API Flow

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — obtain, exchange, and refresh OBI credentials, and the offline-access consent flow before long-running jobs. The "Authentication" section assumes a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) run heavy work on the OBI sandbox and get result files back to the user.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every mapping session.
> - [[obi-links]] — every entity id, sandbox file, and launched campaign goes out as a hyperlink.
> - [[parameter-scan]] — the shared scan → estimate → launch mechanics and the campaign-vs-config distinction.
> - [[obi-circuit-simulation]] — SONATA node/edge populations; where the resulting circuit goes next.

## Overview

EM synapse mapping takes the **afferent synapse locations reconstructed from electron microscopy** and maps them onto one or more **spiny morphologies**, producing a SONATA circuit. The input neurons are supplied as cell morphologies or ME-models; the output circuit carries a **physical** edge population (connections between circuit neurons) and a **virtual** edge population (afferents from external presynaptic neurons), with node populations for the biophysical and virtual neurons.

This is a launch-system-backed task following the standard scan → estimate → launch pattern (see [[parameter-scan]]). In the web app it is the **Build** activity, "Map synapse locations".

## Entity Model

```
CellMorphology / MEModel neurons (≥1)   ← input, from EntityCore
   (supplied as an EMSynapseMappingInputNamedTuple of one or more elements)
    │
    ▼
em_synapse_mapping__campaign (task-config)      ← parent
    │
    ├── em_synapse_mapping__config (task-config) ← child, LAUNCHABLE
    │       └── task_config_generator_id → campaign ID
    │
    └── task-activity (em_synapse_mapping__config_generation)

on launch → task-activity (em_synapse_mapping__execution)
         → Circuit   ← output
             ├── biophysical_neurons node population        (physical neurons)
             ├── virtual_afferent_neurons node population    (external presynaptic)
             ├── physical_connections edge population
             └── virtual_afferents edge population
```

## Authentication (all requests)

- `Authorization: Bearer <keycloak_token>` — Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` / `project-id: <uuid>` — HTTP headers from `$OBI_VLAB_ID` / `$OBI_PROJECT_ID`

Read from the environment, never from memory. See [[virtual-lab-manager-api]].

Base URLs: `https://staging.cell-a.openbraininstitute.org` / `https://cell-a.openbraininstitute.org`.

## Pre-requisite: Find the Neurons

The neurons to include are cell morphologies or ME-models (must be spiny morphologies):

```
GET /api/entitycore/cell-morphology?project_id=<project-id>
GET /api/entitycore/memodel?project_id=<project-id>
```

## Step 1: Generate the Campaign

**Endpoint:** `POST /api/obi-one/generated/em-synapse-mapping-scan-config-generate-grid`

**Request body** (`EMSynapseMappingScanConfig`):

```json
{
  "type": "EMSynapseMappingScanConfig",
  "info": {
    "type": "Info",
    "campaign_name": "EM afferents onto L2/3 PCs",
    "campaign_description": "Map dense-reconstruction synapses onto spiny morphologies"
  },
  "initialize": {
    "type": "EMSynapseMappingScanConfig.Initialize",
    "neurons": {
      "name": "set1",
      "elements": [
        { "type": "CellMorphologyFromID", "id_str": "<morphology-uuid>" }
      ]
    }
  },
  "advanced_options": {
    "type": "AdvancedEMSynapseMappingOptions",
    "include_spiny_morphologies": true
  }
}
```

- `neurons` is a **named tuple** of one or more neuron references (at least one). It is deliberately a named tuple rather than a plain list so it is *not* treated as a scan dimension. To sweep over **different sets** of neurons, pass a list of named tuples (each must have a unique `name`) — see [[parameter-scan]].
- `elements` accept `CellMorphologyFromID` or `MEModelFromID`.

Returns the **campaign ID**.

## Step 2: Find the Child Config ID

```
GET /api/entitycore/task-config?task_config_type=em_synapse_mapping__config&task_config_generator_id=<campaign-id>
```

## Step 3: Estimate Cost (optional)

`POST /api/obi-one/declared/task/estimate` with `{ "task_type": "em_synapse_mapping", "config_id": "<child-config-uuid>" }`.

## Step 4: Launch the Job

`POST /api/obi-one/declared/task/launch` with `{ "task_type": "em_synapse_mapping", "config_id": "<child-config-uuid>" }` → `{ task_type, config_id, activity_id, job_id }`.

## Step 5: Monitor and Collect

- **Poll:** `GET /api/obi-one/declared/task/<job-id>`
- **Stream:** `GET /api/obi-one/declared/task/<job-id>/stream`

On success a **Circuit** is registered with the node/edge populations shown in the entity model.

## Field Reference

### EMSynapseMappingScanConfig.Initialize

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `neurons` | named tuple of `CellMorphologyFromID` / `MEModelFromID` (or list thereof) | ✓ | Neurons to include (≥ 1). A list of named tuples sweeps over different neuron sets. |

### AdvancedEMSynapseMappingOptions

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `custom_physical_edge_population_name` | string | `physical_connections` | Name for connections between circuit neurons |
| `custom_virtual_edge_population_name` | string | `virtual_afferents` | Name for connections from virtual neurons |
| `custom_biophysical_node_population` | string | `biophysical_neurons` | Name for the physical neuron population |
| `custom_virtual_node_population` | string | `virtual_afferent_neurons` | Name for the external presynaptic population |
| `include_spiny_morphologies` | bool | `true` | Include a container of spiny morphologies in the output circuit |

## Critical: Campaign ID ≠ Launchable Config ID

The generate endpoint returns the campaign ID; estimate/launch need the child config ID from Step 2. See [[parameter-scan]].

---

## Working directory

```
/home/jovyan/<topic>/
├── logbook.md
├── models/             ← the morphologies / ME-models pulled from EntityCore
├── results/            ← mapped circuit(s); one subdir per neuron set
├── plots/              ← synapse-location overlays on morphologies
└── code/
```

## Logbook

Every EM synapse mapping session is logged per [[obi-logbook]].

Record, as the session goes:

- **Objective** — what the mapped circuit is for and why these neurons.
- **Source EM data** — which dense-reconstruction dataset the afferent synapses come from, species/region, and the reconstruction's provenance.
- **Target neurons** — the morphologies/ME-models, their cell types, and why they were chosen; note spiny-morphology requirement.
- **Mapping outcome** — number of physical vs virtual connections and synapses produced, and how faithfully the EM afferent structure is represented.
- **Provenance table** — morphology/ME-model IDs (and EM dataset) in → Circuit out.
- **Caveats** — synapses that could not be mapped, boundary/truncation effects from the EM volume, idealisations in the physical/virtual split.

Do **not** log endpoints, campaign-vs-config mechanics, cost estimates, job polling, or auth — see [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], `{domain}` matches the environment the calls ran against.

- **Entities** — `https://{domain}/app/entity/{id}`. Link the input morphologies/ME-models and the output Circuit; link id cells in the provenance table.
- **Sandbox files** — synapse-location overlays: `download_url` from `{obi}:get-sandbox-download-url` with `/files/` → `/lab/tree/`.
- **Launched campaigns** — mapping lives under the **Build** activity: `https://{domain}/app/virtual-lab/{vlab_id}/{project_id}/workflows?tactivity=build&ttype=em_synapse_mapping_campaign`.
