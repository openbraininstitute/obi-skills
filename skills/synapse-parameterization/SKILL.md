---
name: synapse-parameterization
description: Guide for assigning synaptic physiology (synaptic model parameters) to the connections of a SONATA circuit via the obi-one and EntityCore REST APIs — the "circuit synaptic physiology assignment" workflow. Synaptic model assigners write parameters back onto edge populations and register a new parameterized Circuit. Use when the user wants to parameterize synapses on a circuit, assign synaptic physiology models to connections, or build circuit synaptic physiology.
license: Apache-2.0
---

# Synapse Parameterization: End-to-End API Flow

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — obtain, exchange, and refresh OBI credentials, and the offline-access consent flow before long-running jobs. The "Authentication" section assumes a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) run heavy work on the OBI sandbox and get result files back to the user.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every parameterization session.
> - [[obi-links]] — every entity id, sandbox file, and launched campaign goes out as a hyperlink.
> - [[obi-circuit-simulation]] — what a SONATA circuit's edge populations are; where the parameterized circuit goes next (simulation).
> - [[parameter-scan]] — the shared scan → estimate → launch mechanics and the campaign-vs-config distinction.

## Overview

Synapse parameterization — internally **circuit synaptic physiology assignment** — takes an existing circuit and **assigns synaptic physiology model parameters to its connections**. *Synaptic model assigners* map synaptic models onto edge populations (by connection type, source/target selection, etc.), write those parameters back into the edge files (and the required MOD files), and register a new **parameterized Circuit**.

This is a launch-system-backed task following the standard scan → estimate → launch pattern (see [[parameter-scan]]).

> In the web app this is the **Build** activity, "circuit synaptic physiology". Distinguish it from [[build-synaptome]] (which places synapses on a *single* ME-model) — this one parameterizes synapses across a *whole circuit* that already has connectivity.

## Entity Model

```
Circuit (with connectivity)   ← input, from EntityCore
    │
    ▼
circuit_synaptic_physiology_assignment__campaign (task-config)      ← parent
    │
    ├── circuit_synaptic_physiology_assignment__config (task-config) ← child, LAUNCHABLE
    │       └── task_config_generator_id → campaign ID
    │
    └── task-activity (…__config_generation)

on launch → task-activity (…__execution)
         → Circuit (parameterized; synaptic physiology assigned)   ← output
```

## Authentication (all requests)

- `Authorization: Bearer <keycloak_token>` — Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` / `project-id: <uuid>` — HTTP headers from `$OBI_VLAB_ID` / `$OBI_PROJECT_ID`

Read from the environment, never from memory. See [[virtual-lab-manager-api]].

Base URLs: `https://staging.cell-a.openbraininstitute.org` / `https://cell-a.openbraininstitute.org`.

## Pre-requisite: Find the Circuit

```
GET /api/entitycore/circuit?project_id=<project-id>
```

Pick a circuit that already has connectivity (`number_connections`, `number_synapses` > 0) — parameterization assigns physiology to existing connections, it does not create them.

## Step 1: Generate the Campaign

**Endpoint:** `POST /api/obi-one/generated/synapse-parameterization-scan-config-generate-grid`

Body is a `SynapseParameterizationScanConfig` selecting the target circuit and defining the **synaptic model assigners**: which synaptic physiology model applies to which connections (edge population + selection), and the parameter values (or distributions). Returns the **campaign ID**.

## Step 2: Find the Child Config ID

```
GET /api/entitycore/task-config?task_config_type=circuit_synaptic_physiology_assignment__config&task_config_generator_id=<campaign-id>
```

## Step 3: Estimate Cost (optional)

`POST /api/obi-one/declared/task/estimate` with `{ "task_type": "circuit_synaptic_physiology_assignment", "config_id": "<child-config-uuid>" }`.

## Step 4: Launch the Job

`POST /api/obi-one/declared/task/launch` with `{ "task_type": "circuit_synaptic_physiology_assignment", "config_id": "<child-config-uuid>" }` → `{ task_type, config_id, activity_id, job_id }`.

## Step 5: Monitor and Collect

- **Poll:** `GET /api/obi-one/declared/task/<job-id>`
- **Stream:** `GET /api/obi-one/declared/task/<job-id>/stream`

On success a new **parameterized Circuit** is registered (edge populations now carry the assigned synaptic parameters, plus the MOD files for the synaptic mechanisms). It is ready for simulation.

## Critical: Campaign ID ≠ Launchable Config ID

The generate endpoint returns the campaign ID; estimate/launch need the child config ID from Step 2. See [[parameter-scan]].

---

## Working directory

```
/home/jovyan/<topic>/
├── logbook.md
├── results/            ← parameterized circuit(s); one subdir per parameter setting
├── plots/              ← synaptic parameter distributions, PSP/PSC checks
└── code/
```

## Logbook

Every parameterization session is logged per [[obi-logbook]].

Record, as the session goes:

- **Objective** — what the parameterization is for (e.g. matching in-vitro PSP amplitudes for a given pathway) and why this circuit.
- **Target circuit** — its provenance, brain region, scale, and its connectivity before parameterization.
- **Assignment scheme** — for each connection type: the synaptic physiology model assigned, the parameters and their values/distributions, and the experimental basis (which paired-recording data, which pathway). This is the core record.
- **Result** — the parameterized circuit and the resulting synaptic properties per pathway (conductances, release probabilities, kinetics — with units).
- **Caveats** — pathways left at defaults, assumptions in the parameter sources, connection types not covered.

Do **not** log endpoints, campaign-vs-config mechanics, cost estimates, job polling, or auth — see [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], `{domain}` matches the environment the calls ran against.

- **Entities** — `https://{domain}/app/entity/{id}`. Link the input circuit and the parameterized output circuit; link id cells in the provenance table.
- **Sandbox files** — parameter-distribution and PSP/PSC plots: `download_url` from `{obi}:get-sandbox-download-url` with `/files/` → `/lab/tree/`.
- **Launched campaigns** — parameterization lives under the **Build** activity: `https://{domain}/app/virtual-lab/{vlab_id}/{project_id}/workflows?tactivity=build&ttype=circuit_synaptic_physiology_assignment_campaign`.
