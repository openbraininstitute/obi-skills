---
name: ion-channel-api
description: Guide for building ion channel models from recordings and running ion channel model simulations via the obi-one and EntityCore REST APIs. Use when the user wants to fit ion channel models from electrophysiology traces, simulate ion channel models, or manage ion channel entities.
license: Apache-2.0
---

# Ion Channel Building & Simulation: End-to-End API Flow

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — how to obtain, exchange, and refresh OBI credentials, and the offline-access consent flow before long-running fits/simulations. Never construct auth calls ad hoc; the "Authentication" section below assumes a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) run heavy work on the OBI sandbox, and get result files (traces, fit plots, `.mod` files) back to the user from there.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every fitting or simulation session. See the Logbook section below.
> - [[obi-links]] — every entity id, sandbox file, and launched campaign handed to the user goes out as a hyperlink, never as a bare UUID or path. See the Linking section below.

## Overview

There are two distinct workflows for ion channels:

1. **Ion Channel Fitting** — Build an ion channel model (`.mod` file) from electrophysiology recordings
2. **Ion Channel Model Simulation** — Simulate one or more existing ion channel models with custom stimuli/recordings

Both use the same endpoint patterns as other obi-one campaign workflows.

## Authentication (all requests)

Every request requires:

- `Authorization: Bearer <keycloak_token>` — OIDC token from Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` — HTTP header, from `$OBI_VLAB_ID` in the sandbox
- `project-id: <uuid>` — HTTP header, from `$OBI_PROJECT_ID` in the sandbox

Read both from the environment, never from memory: a tool call can be redirected to another project, and the environment follows while remembered ids do not. See [[virtual-lab-manager-api]].

Base URLs:

- Staging: `https://staging.cell-a.openbraininstitute.org`
- Production: `https://cell-a.openbraininstitute.org`

---

## Part 1: Ion Channel Fitting (Building a Model)

### Concept

Takes electrophysiology recordings (NWB files stored as `ion-channel-recording` entities) and fits Hodgkin-Huxley-style equations to produce an ion channel model (`.mod` file registered as `ion-channel-model` entity).

### Entity Model

```
IonChannelRecording (input)
    │
    ▼
IonChannelFittingScanConfig (obi-one form)
    │
    ├── IonChannelModelingCampaign (EntityCore)
    │       └── campaign_generation_config asset (JSON)
    │
    ├── IonChannelModelingConfig (EntityCore, one per coordinate)
    │       └── ion_channel_modeling_generation_config asset (JSON)
    │
    └── IonChannelModelingConfigGeneration (EntityCore activity, links them)
    │
    ▼
IonChannelModel (output) — contains .mod file + figures
```

### Pre-requisite: Finding Ion Channel Recordings

```
GET /api/entitycore/ion-channel-recording?project_id=<project-id>
```

Each recording has metadata including `temperature`, `ljp` (liquid junction potential), `brain_region`, and `subject`.

### Step 1: Generate the Fitting Campaign

**Endpoint:** `POST /api/obi-one/generated/ion-channel-fitting-scan-config-generate-grid`

**Request body:**

```json
{
  "type": "IonChannelFittingScanConfig",
  "info": {
    "type": "Info",
    "campaign_name": "My Ion Channel Fitting",
    "campaign_description": "Fitting Kv channel from patch-clamp data"
  },
  "initialize": {
    "type": "IonChannelFittingScanConfig.Initialize",
    "recordings": {
      "type": "IonChannelRecordingFromID",
      "id_str": "<ion-channel-recording-uuid>"
    },
    "ion_channel_name": "Kv1_custom"
  },
  "minf_eq": {
    "type": "<MInf equation class name>",
    "equation_key": "sig_fit_minf"
  },
  "mtau_eq": {
    "type": "<MTau equation class name>",
    "equation_key": "sig_fit_mtau"
  },
  "hinf_eq": {
    "type": "<HInf equation class name>",
    "equation_key": "sig_fit_hinf"
  },
  "htau_eq": {
    "type": "<HTau equation class name>",
    "equation_key": "sig_fit_htau"
  },
  "gate_exponents": {
    "type": "IonChannelFittingScanConfig.GateExponents",
    "m_power": 1,
    "h_power": 1
  }
}
```

### Available Equation Types

| Parameter | Available `equation_key` values | Description |
|-----------|-------------------------------|-------------|
| `minf_eq` | `sig_fit_minf` | Sigmoidal fit for m∞ |
| `mtau_eq` | `sig_fit_mtau`, `thermo_fit_mtau`, `thermo_fit_mtau_v2`, `bell_fit_mtau` | Time constant for m |
| `hinf_eq` | `sig_fit_hinf` | Sigmoidal fit for h∞ |
| `htau_eq` | `sig_fit_htau` | Time constant for h |

### Gate Exponents

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `m_power` | int | 1 | 1–4 | Exponent p in g = ḡ · mᵖ · hᵍ |
| `h_power` | int | 1 | 0–4 | Exponent q in g = ḡ · mᵖ · hᵍ |

### Ion Channel Name Constraints

- Must start with a letter or underscore
- Can only contain letters, numbers, and underscores
- Used as the SUFFIX in the generated `.mod` file

### Response

Returns the **campaign ID** (IonChannelModelingCampaign entity):

```
"<campaign-uuid>"
```

### Note on Launching

Ion channel fitting uses **legacy entity types** (IonChannelModelingCampaign, IonChannelModelingConfig) rather than the generic task-config system. The fitting task is **not** in the `/declared/task/launch` mappings — it is executed as part of the grid scan generation itself (i.e., `execute_single_config_task=False` in the endpoint config, meaning it runs inline during generation, not as a separate launched job).

### Output: IonChannelModel Entity

After fitting, the result is registered as an `ion-channel-model` entity in EntityCore with:
- `.mod` file (NEURON mechanism)
- Thumbnail (PNG)
- Figures (PDF) — traces, stimuli, steady state, time constant plots
- Figure summary JSON
- Metadata: `nmodl_suffix`, `conductance_name`, `neuron_block`, `temperature_celsius`, `brain_region`, `subject`

Query the output:
```
GET /api/entitycore/ion-channel-model?project_id=<project-id>
```

---

## Part 2: Ion Channel Model Simulation

### Concept

Simulate one or more existing ion channel models with customizable stimuli, recordings, and temperature. Produces SONATA-format simulation results.

### Entity Model

```
IonChannelModel(s) (input)
    │
    ▼
IonChannelModelSimulationScanConfig (obi-one form)
    │
    ├── SimulationCampaign (EntityCore)
    ├── Simulation(s) (EntityCore, one per coordinate)
    └── SimulationCampaignGeneration (activity)
    │
    ▼ (launch each simulation)
    │
SimulationExecution (activity) → Job (launch-system)
    │
    ▼
Simulation results (SONATA output files)
```

### Pre-requisite: Finding Ion Channel Models

```
GET /api/entitycore/ion-channel-model?project_id=<project-id>
```

Important fields: `id`, `nmodl_suffix`, `conductance_name`, `max_permeability_name`.

### Step 1: Generate the Simulation Campaign

**Endpoint:** `POST /api/obi-one/generated/ion-channel-model-simulation-scan-config-generate-grid`

**Request body:**

```json
{
  "type": "IonChannelModelSimulationScanConfig",
  "info": {
    "type": "Info",
    "campaign_name": "Ion Channel Simulation",
    "campaign_description": "Simulating Kv1 model"
  },
  "initialize": {
    "type": "IonChannelModelSimulationScanConfig.Initialize",
    "duration": 100.0,
    "temperature": 34.0
  },
  "ion_channel_models": {
    "my_channel": {
      "type": "IonChannelModelWithConductance",
      "ion_channel_model": {
        "type": "IonChannelModelFromID",
        "id_str": "<ion-channel-model-uuid>"
      },
      "conductance": 0.001
    }
  },
  "stimuli": {
    "step_current": {
      "type": "<StimulusType>",
      ...
    }
  },
  "recordings": {
    "voltage": {
      "type": "<RecordingType>",
      ...
    }
  },
  "timestamps": {}
}
```

### Ion Channel Model Reference Types

| Type | Use when |
|------|----------|
| `IonChannelModelWithConductance` | Model has a `conductance_name` (most common) |
| `IonChannelModelWithMaxPermeability` | Model has a `max_permeability_name` (e.g., calcium channels) |
| `IonChannelModelWithoutConductance` | Model has neither (auxiliary mechanisms) |

### Parameter Sweep

Any numeric field can be a list to create a grid:

```json
"conductance": [0.0001, 0.001, 0.01],
"temperature": [22.0, 34.0, 37.0]
```

This creates 3×3 = 9 simulations.

### Response

Returns the **campaign ID** (SimulationCampaign):

```
"<campaign-uuid>"
```

### Step 2: Find Simulations to Launch

The simulation generation creates `Simulation` entities linked to the campaign:

```
GET /api/entitycore/simulation?simulation_campaign_id=<campaign-id>
```

### Step 3: Launch Simulations

**Endpoint:** `POST /api/obi-one/declared/task/launch`

**Request body:**

```json
{
  "task_type": "ion_channel_model_simulation_execution",
  "config_id": "<simulation-uuid>"
}
```

Note: The `task_type` for ion channel simulation execution is `ion_channel_model_simulation_execution` (legacy entity path using `Simulation` entity directly, not `task-config`).

### Step 4: Monitor

```
GET /api/obi-one/declared/task/<job-id>
GET /api/obi-one/declared/task/<job-id>/stream
```

---

## EntityCore Entity Types Reference

| Entity Type | API Route | Description |
|-------------|-----------|-------------|
| `ion-channel-recording` | `/api/entitycore/ion-channel-recording` | Input electrophysiology traces (NWB) |
| `ion-channel-model` | `/api/entitycore/ion-channel-model` | Built model (.mod + metadata) |
| `ion-channel-modeling-campaign` | `/api/entitycore/ion-channel-modeling-campaign` | Fitting campaign |
| `ion-channel-modeling-config` | `/api/entitycore/ion-channel-modeling-config` | Single fitting config |
| `simulation-campaign` | `/api/entitycore/simulation-campaign` | Simulation campaign |
| `simulation` | `/api/entitycore/simulation` | Individual simulation |

## Key Differences from Generic Task-Config Flow (e.g., Skeletonization)

| Aspect | Ion Channel Fitting | Ion Channel Simulation | Skeletonization |
|--------|--------------------|-----------------------|-----------------|
| Entity types | Legacy (dedicated models) | Legacy (Simulation) | Generic (task-config) |
| Campaign entity | `IonChannelModelingCampaign` | `SimulationCampaign` | `task-config` (type: `skeletonization__campaign`) |
| Child config | `IonChannelModelingConfig` | `Simulation` | `task-config` (type: `skeletonization__config`) |
| Launch via | Not launched (runs inline) | `/declared/task/launch` with `ion_channel_model_simulation_execution` | `/declared/task/launch` with `morphology_skeletonization` |
| Config ID for launch | N/A | Simulation entity ID | task-config child ID |

## Ion Channel Model Fields (EntityCore)

| Field | Type | Description |
|-------|------|-------------|
| `nmodl_suffix` | string | NEURON mechanism suffix (e.g., "Kv1_custom") |
| `conductance_name` | string or null | Name of conductance RANGE variable (e.g., "gKv1_custombar") |
| `max_permeability_name` | string or null | Name of max permeability variable |
| `temperature_celsius` | float | Temperature at which model was fitted |
| `is_ljp_corrected` | bool | Whether liquid junction potential was corrected |
| `is_temperature_dependent` | bool | Whether model includes temperature dependence |
| `is_stochastic` | bool | Whether model is stochastic |
| `neuron_block` | object | NEURON block metadata (RANGE vars, useion, etc.) |
| `brain_region` | object | Brain region the recording came from |
| `subject` | object | Subject metadata |

---

## Working directory

All files this workflow produces go under the conversation's topic directory on the persistent volume, per the convention in [[obi-logbook]] — one directory per scientific topic (`nav1.6-fitting`, `kv4.2-inactivation`), created before any work starts, reused if it already exists:

```
/home/jovyan/<topic>/
├── logbook.md
├── recordings/         ← NWB traces pulled from EntityCore
├── models/             ← fitted .mod files
├── results/            ← simulated traces, per condition
├── plots/              ← fit quality, I-V and activation curves
└── code/
```

`logbook.md`, `results/`, `plots/`, and `code/` are fixed by [[obi-logbook]]; `recordings/` and `models/` are this workflow's inputs and outputs.

## Logbook

Every fitting or ion-channel-simulation session is logged per [[obi-logbook]] — read it for the location, format, and content rules.

Record, as the session goes:

**For fitting (Part 1):**
- **Objective** — which channel, in which cell type / brain region / species, and what the model is for.
- **Recordings used** — which ion-channel recordings, the experimental protocol behind them (voltage steps, holding potential, temperature, solutions if known), and why these recordings suit the channel being fitted.
- **Model form** — the equation type and gate exponents chosen, and the **biophysical justification**: which gating processes (activation, inactivation) are being represented and why that form is appropriate for this channel.
- **Fit outcome** — the fitted kinetic parameters with units, the resulting voltage-dependence (V½, slope, time constants), and how well the model reproduces the recorded traces. Include the fit-quality figures.
- **Caveats** — temperature the fit is valid at, voltage range covered by the data, any gating process deliberately not modelled.

**For simulation (Part 2):**
- **Objective and models** — which ion channel models are being compared or characterised, and what question the simulation answers.
- **Protocol** — stimulus waveform, voltage range, durations, temperature, what is recorded.
- **Parameter sweep** — what is varied, over what range, and the biophysical reason.
- **Results** — current amplitudes, activation/inactivation curves, time constants (with units), plus the figures and what each shows.
- **Interpretation** — what the simulated behaviour means for the channel's role in cell excitability.

Do **not** log endpoints, campaign/config ID relationships, launch calls, polling, or auth — see the "What never goes in" list in [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], every entity, file, and campaign mentioned in a reply goes out as a hyperlink — a bare UUID or a bare path is a defect, not a style choice. `{domain}` is `staging.openbraininstitute.org` on staging, `www.openbraininstitute.org` on production, and must match the environment the calls ran against.

- **Entities** — `https://{domain}/app/entity/{id}`. Link the ion channel recordings used as fitting input, the `IonChannelModel` produced by the fit, the models fed into a simulation, and the campaign entities themselves.
- **Sandbox files** — traces, `.mod` files, fit-quality and I-V/activation plots: take the `download_url` from `{obi}:get-sandbox-download-url` and swap `/files/` for `/lab/tree/`, keeping the rest of the path (`home/jovyan` included). Link the `plots/` directory when there are several figures.
- **Launched campaigns** — `https://{domain}/app/virtual-lab/{vlab_id}/{project_id}/workflows?tactivity=build&ttype=ion_channel_modeling_campaign` for a fitting campaign (Part 1), and `…?tactivity=simulate&ttype=ion_channel_model_simulation` for a simulation campaign (Part 2). Send both query parameters — `ttype` alone leaves the page on the default Build tab.
