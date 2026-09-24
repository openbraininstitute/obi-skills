---
name: data-integration-api
description: Guide for ingesting data into the OBI platform via obi-one REST API. Covers morphology validation, registration, mesh generation, circuit registration, metadata registration (contributors, subjects, publications), and morphology metrics. Morphologies and circuits cannot be created in EntityCore — as of today they are registered only through obi-one's declared endpoints, which handle validation, format conversion, and asset generation automatically. Other entity types can be created in EntityCore, but the declared endpoints are preferred where they exist.
license: Apache-2.0
---

# Data Integration via obi-one API

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — how to obtain, exchange, and refresh OBI credentials, and the offline-access consent flow. Never construct auth calls ad hoc; the "Authorization" section below assumes a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) run heavy or scientific work on the OBI sandbox, and get result files back to the user from there.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every ingestion session. See the Logbook section below.
> - [[obi-links]] — every entity id, sandbox file, and launched job handed to the user goes out as a hyperlink, never as a bare UUID or path. See the Linking section below.

## Overview

**Morphologies and circuits cannot be created in EntityCore.** As of today they are registered only through obi-one's `/declared/` endpoints (`register-morphology-with-calculated-metrics`, `circuit/register`) — there is no supported path that creates either one directly.

Other entity types *can* be created in EntityCore, but prefer obi-one's `/declared/` endpoints wherever one exists (subjects, contributors, publications), because obi-one handles:
- File validation and format conversion
- Metadata resolution (DOI, ORCID, ROR lookups)
- Asset generation (meshes, LODs, metrics)
- Async validation jobs
- Proper entity linking

## Authentication (all requests)

- `Authorization: Bearer <keycloak_token>` — Keycloak (realm: SBO)
- `virtual-lab-id: <uuid>` — HTTP header, from `$OBI_VLAB_ID` in the sandbox
- `project-id: <uuid>` — HTTP header, from `$OBI_PROJECT_ID` in the sandbox

Read both from the environment, never from memory: a tool call can be redirected to another project, and the environment follows while remembered ids do not. See [[virtual-lab-manager-api]].

Base URLs:
- Staging: `https://staging.cell-a.openbraininstitute.org/api/obi-one`
- Production: `https://cell-a.openbraininstitute.org/api/obi-one`

---

## Morphology Ingestion

### Step 1: Validate a Morphology File

Before registering, validate the file and get converted formats.

**Endpoint:** `POST /declared/test-neuron-file`

**Content-Type:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file upload | Morphology file (.swc, .h5, or .asc) |
| `single_point_soma` | bool (query) | Convert soma to single point (default: false) |

**Response:** ZIP file containing the morphology converted to all supported formats (.swc, .h5, .asc).

If validation fails, the response contains diagnostic errors.

**Supported formats:** `.swc`, `.h5`, `.asc`

### Step 2: Register the Morphology

**Endpoint:** `POST /declared/register-morphology-with-calculated-metrics`

**Content-Type:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file upload | Morphology file (.swc, .h5, or .asc) — **required** |
| `metadata` | string (JSON) | Entity metadata (name, brain_region, subject, contributions, …). Defaults to `{}` |

This one call registers the entity, uploads the asset, computes and registers the measurements, and — when it can — generates the GLB surface mesh. It is the whole of Steps 3 and 4 below as well, so a plain morphology ingestion needs nothing else.

**Response:**
```json
{
  "entity_id": "<cell-morphology-uuid>",
  "measurement_entity_id": "<measurement-uuid>",
  "mesh_asset_id": "<glb-asset-uuid>",
  "status": "success",
  "morphology_name": "<name>"
}
```

`mesh_asset_id` is **nullable** — the mesh is generated "when possible", so a `null` here means registration succeeded but the GLB did not. Check it, and fall back to Step 3 if you need the mesh.

> Register metadata prerequisites (subject, contributors, publications) **before** this call, so their IDs can go in `metadata`. See [Metadata Registration](#metadata-registration).

Steps 3 and 4 exist for morphologies that are **already registered** — enriching an existing entity, or filling in a mesh that came back null. They are not part of a fresh ingestion.

### Step 3: Generate a 3D Mesh from the Morphology

**Endpoint:** `POST /declared/convert-morphology-to-registered-mesh/{cell_morphology_id}`

Converts the SWC asset on an existing `cell-morphology` entity to an annotated GLB mesh and uploads it as a new asset.

**Response:**
```json
{
  "asset_id": "<glb-asset-uuid>",
  "status": "success"
}
```

**Errors:**
- 404 — Morphology not found
- 409 — GLB asset already exists
- 422 — No SWC asset on the morphology

### Step 4: Compute and Register Morphology Metrics

**Endpoint:** `POST /declared/neuron-morphology-metrics/{cell_morphology_id}/register`

Computes morphology metrics (neurite lengths, branching, etc.) and registers them as a measurement entity linked to the morphology.

**Response:**
```json
{
  "measurement_entity_id": "<uuid>",
  "measurement_kinds": [...],
  "status": "success"
}
```

### Optional: Preview Metrics Without Registering

**Endpoint:** `GET /declared/neuron-morphology-metrics/{cell_morphology_id}/measurement-kinds?morphology_format=swc`

Returns the computed measurement kinds without persisting anything.

### Optional: Get Morphology Metrics (after registration)

**Endpoint:** `GET /declared/neuron-morphology-metrics/{cell_morphology_id}`

Returns the computed metrics for a morphology.

---

## Circuit Registration

### Full Circuit Upload

**Endpoint:** `POST /declared/circuit/register`

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✓ | Circuit name |
| `description` | string | ✓ | Description |
| `brain_region_id` | UUID | ✓ | Brain region entity ID |
| `subject_id` | UUID | ✓ | Subject entity ID |
| `build_category` | string | ✓ | e.g. "experimental", "reconstructed" |
| `target_simulator` | string | ✓ | e.g. "NEURON" |
| `circuit_archive` | file | ✓ | `.tar.gz` SONATA circuit archive |
| `scale_override` | string | | e.g. "pair", "microcircuit", "mesocircuit" |
| `parent_circuit_id` | UUID | | Parent circuit (for derived circuits) |
| `derivation_type` | string | | Required if parent set: e.g. "customization" |
| `atlas_id` | UUID | | Brain atlas entity ID |
| `license_id` | UUID | | License entity ID (required if `authorized_public=true`) |
| `contact_email` | string | | Contact email |
| `published_in` | string | | Publication reference |
| `experiment_date` | string | | ISO date |
| `contributions` | JSON string | | `{"Agent Name": {"type": "person", "role": "..."}}` |
| `publications` | JSON string | | `{"10.1234/doi": {"type": "..."}}` |
| `overview_image` | file | | Pre-computed overview image (.png/.webp) |
| `sim_designer_image` | file | | Simulation designer image (.png) |
| `authorized_public` | bool | | Make publicly visible (default: false) |
| `dry_run` | bool | | Validate without registering (default: false) |

**Response:**
```json
{
  "circuit_id": "<uuid>",
  "status": "draft",
  "number_neurons": 1000,
  "number_synapses": 500000,
  "number_connections": 10000,
  "scale": "microcircuit"
}
```

**What happens:**
1. Archive is extracted, SONATA config validated
2. Circuit entity created in `draft` lifecycle_status
3. Async validation job triggered (checks SONATA conformance)
4. If validation passes → status becomes `active`

### Trigger Re-Validation

**Endpoint:** `POST /declared/circuit/{circuit_id}/validate?force=false`

Re-triggers validation for a draft circuit. Pass `force=true` to re-validate active/disqualified circuits.

### Generate Circuit Assets

**Endpoint:** `POST /declared/circuit/{circuit_id}/generate-assets?force=false`

Generates compressed circuit and connectivity matrices for an active circuit.

---

## EM Cell Mesh Registration

### Upload a Mesh to an Existing Entity

**Endpoint:** `POST /declared/{entity_id}/register-mesh`

**Content-Type:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | GLB mesh file |
| `lod_mesh_format` | string | Source format for LOD generation (default: "obj") |

**Response:**
```json
{
  "entity_id": "<uuid>",
  "glb_asset_id": "<uuid>",
  "task_job_id": "<uuid>",
  "status": "pending"
}
```

Automatically triggers an async LOD (Level of Detail) generation job.

### Generate LOD from Existing Mesh

**Endpoint:** `POST /declared/{entity_id}/generate-lod`

Triggers LOD generation for an entity that already has a mesh asset. Prefers OBJ; falls back to GLB.

---

## Metadata Registration

### Contributors (Persons & Organizations)

**Look up:** `GET /declared/contributor?identifier=<orcid-or-ror-url>`

Resolves metadata from ORCID (persons) or ROR (organizations). Returns whether already registered.

**Register:** `POST /declared/contributor?identifier=<orcid-or-ror-url>`

Creates the person/organization entity from the resolved metadata.

**Identifier formats:**
- ORCID: `https://orcid.org/0000-0002-1234-5678`
- ROR: `https://ror.org/03yrm5c26`

**Response (person):**
```json
{
  "id": "<uuid>",
  "pref_label": "Jean-Denis Courcol",
  "given_name": "Jean-Denis",
  "family_name": "Courcol",
  "orcid": "https://orcid.org/..."
}
```

### Subjects (Species/Strain)

**Search:** `GET /declared/subject?name=<name>`

**Register:** `POST /declared/subject`

```json
{
  "name": "Average Rat",
  "description": "Average adult Wistar rat",
  "sex": "male",
  "weight": 300.0,
  "age_value": 7776000,
  "age_period": "postnatal",
  "species_id": "<species-uuid>",
  "strain_id": "<strain-uuid>"
}
```

**Required:** `name`, `description`, `species_id`, `sex`, `age_value`, `age_period`. `strain_id` and `weight` are optional.

> **`age_value` is a duration, not a plain number of days.** The underlying model is a `timedelta` (EntityCore's `SubjectUserUpdate` types it as an ISO-8601 `duration` string), and obi-one's schema exposes it as a bare `number` — which is interpreted as **seconds**. So a 90-day-old rat is `7776000` (90 × 86400), *not* `90`. Passing `90` will not fail validation; it will silently register a 90-second-old animal. Convert explicitly, and state the age in the logbook in the units a reader expects.

**Other fields:** `weight` is in **grams**. `age_min` / `age_max` exist on the entity for expressing an age range instead of a point value.

**Note:** Duplicate detection normalizes names (case-insensitive, strips punctuation).

### Publications

**Register:** `POST /declared/publication/register`

```json
{
  "DOI": "10.1038/s41586-024-07487-2"
}
```

Fetches metadata (title, authors, year, abstract) from Crossref and creates the entity. Returns 409 if already registered.

---

## Electrophysiology Protocol Validation

**Endpoint:** `POST /declared/validate-electrophysiology-protocol-nwb-file`

Validates NWB files containing electrophysiology recordings before they are registered.

---

## Complete Morphology Ingestion Workflow

```
1. Validate file
   POST /declared/test-neuron-file (upload .swc/.h5/.asc)
   → ZIP with converted formats + validation result

2. Register metadata prerequisites (if not already present)
   - POST /declared/subject (species/strain)
   - POST /declared/contributor?identifier=<orcid>
   - POST /declared/publication/register (DOI)
   → collect their IDs for the metadata payload below

3. Register the morphology — entity, asset, metrics and mesh in one call
   POST /api/obi-one/declared/register-morphology-with-calculated-metrics
   multipart: file=<.swc/.h5/.asc>, metadata=<JSON with name, brain_region,
                                               subject, contributions, …>
   → { entity_id, measurement_entity_id, mesh_asset_id, status, morphology_name }

4. If mesh_asset_id came back null, generate the mesh separately
   POST /api/obi-one/declared/convert-morphology-to-registered-mesh/{id}
   → GLB mesh asset created

5. (Optional) Use in simulations or visualization
```

Step 3 replaces what would otherwise be three calls (entity creation, metrics, mesh). Only reach for the individual endpoints when working on a morphology that is **already registered**.

## Complete Circuit Ingestion Workflow

```
1. Register prerequisites
   - Subject (POST /declared/subject)
   - Contributors (POST /declared/contributor)
   - Publications (POST /declared/publication/register)

2. Upload circuit
   POST /declared/circuit/register (multipart: archive + metadata)
   → Circuit created in draft status, validation job triggered

3. Wait for validation
   GET /api/entitycore/circuit/{id}
   → Check lifecycle_status: "draft" → "active" (or "disqualified")

4. Generate additional assets (if needed)
   POST /declared/circuit/{id}/generate-assets
   → Compressed circuit + connectivity matrices

5. Circuit is ready for simulation campaigns
```

## Important Rules

- **Never create morphologies or circuits via EntityCore.** As of today they can only be registered through obi-one `/declared/` endpoints (`register-morphology-with-calculated-metrics`, `circuit/register`). This restriction is specific to these two types — other entities can be created in EntityCore, though the `/declared/` endpoints are preferred where they exist, since they resolve identifiers and generate assets. Reading from EntityCore (e.g. `GET /api/entitycore/circuit/{id}` to poll validation status) is fine — the rule is about creating these two types.
- **Always validate morphology files first** — invalid files will cause downstream failures in mesh generation and simulations.
- **Circuit archives must be valid SONATA** — the async validation job checks conformance and will set status to `disqualified` if it fails.
- **Contributors use persistent identifiers** — ORCID for persons, ROR for organizations. Don't create them with freeform names.
- **Duplicate checking is automatic** — the API returns 409 Conflict if entities already exist.

---

## Working directory

When ingestion runs from the sandbox, all files go under the conversation's topic directory on the persistent volume, per the convention in [[obi-logbook]] — one directory per scientific topic (`smith-2025-ca1-morphologies`, `v1-circuit-upload`), created before any work starts, reused if it already exists:

```
/home/jovyan/<topic>/
├── logbook.md
├── source/             ← the files as received, untouched
├── converted/          ← validated/converted formats returned by obi-one
├── results/            ← metrics, validation reports
├── plots/
└── code/
```

`logbook.md`, `results/`, `plots/`, and `code/` are fixed by [[obi-logbook]]. **Keep `source/` pristine** — never overwrite the received files with converted ones; provenance depends on being able to go back to exactly what was handed over.

## Logbook

Every ingestion session is logged per [[obi-logbook]] — read it for the location, format, and content rules. An ingestion logbook is the provenance record for the data: months later it is what tells a scientist where a morphology or circuit came from and whether it can be trusted.

Record, as the session goes:

- **What is being ingested and why** — the dataset, its scientific purpose, who produced it.
- **Source & provenance** — original source (lab, publication DOI, public repository), contributors (with ORCID/ROR), subject species/strain/age, brain region, experimental protocol behind the data.
- **Scientific properties of each item** — for morphologies: cell type, reconstruction method, and the computed metrics (total dendritic length, branch counts, soma diameter — with units); for circuits: neuron counts, populations, cell types, connectivity scale.
- **Validation outcome in scientific terms** — "3 of 40 morphologies rejected for disconnected neurites", not the HTTP status that reported it.
- **Registered entities** — a provenance table of what now exists in EntityCore: type, name, ID.
- **Caveats** — anything about the data a downstream modeller must know: unusual staining/shrinkage correction, partial reconstructions, mixed protocols, missing metadata.

Do **not** log endpoints, `multipart/form-data` details, tokens, job polling, or 409/422 handling — see the "What never goes in" list in [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], every registered entity and every file mentioned in a reply goes out as a hyperlink — a bare UUID or a bare path is a defect, not a style choice. `{domain}` is `staging.openbraininstitute.org` on staging, `www.openbraininstitute.org` on production, and must match the environment the registration calls ran against — a staging link to a production entity is worse than no link.

- **Registered entities** — `https://{domain}/app/entity/{id}`. This is the main deliverable of an ingestion session: every morphology, circuit, mesh, subject, contributor, and publication that was registered should reach the user as a link, and the provenance table's id cells should be links too. The route resolves any entity type, so no per-type URL is needed.
- **Sandbox files** — source files staged for upload, validation reports, and metric summaries: take the `download_url` from `{obi}:get-sandbox-download-url` and swap `/files/` for `/lab/tree/`, keeping the rest of the path (`home/jovyan` included).
- **Jobs** — ingestion registers entities rather than launching a campaign, so there is normally no workflows activity page to link. If a session goes on to launch one (e.g. skeletonization of registered meshes), link it per [[obi-links]].
