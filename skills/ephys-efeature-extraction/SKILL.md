---
name: ephys-efeature-extraction
description: Guide for computing electrophysiology (e-feature) metrics from an intracellular recording trace via the obi-one and EntityCore REST APIs — spike counts, firing rates, AP shape, input resistance, sag, adaptation, and other eFEL features, per stimulus protocol and amplitude. Use when the user wants ephys metrics on a trace, to characterize a recording's firing behaviour, or to compute eFEL e-features for a single electrical cell recording (as analysis, not as the target-defining stage of e-model optimization).
license: Apache-2.0
---

# Ephys E-Feature Extraction (recording metrics)

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — obtain, exchange, and refresh OBI credentials. The examples assume a token obtained that way.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) run the extraction on the OBI sandbox and get result files back to the user.
> - [[obi-logbook]] — **mandatory.** Keep a scientific logbook for every session.
> - [[obi-links]] — every entity id and sandbox file goes out as a hyperlink.
> - [[emodel-building]] — the *building* counterpart. If the goal is to fit an e-model, e-feature extraction there is a launchable optimization-target stage. **This** skill is for computing e-features on a single recording as **analysis / characterization**.

## Overview

This computes **electrophysiology metrics (eFEL e-features)** for a single intracellular recording: spike counts and timing, firing rate, AP amplitude/width/kinetics, input resistance, voltage base, sag, adaptation, burst metrics, and more — optionally restricted to particular stimulus protocols and amplitudes. It is powered by `bluepyefe` + `efel` over the recording's traces.

**This is a read-only analysis task, not a launch-system campaign.** In obi-one it is `electrophysiology_metrics` (local-only: no `generate-grid` endpoint, no `/task/launch`). There are two ways to run it:

1. **REST (simplest)** — a synchronous GET that returns the metrics directly.
2. **In-sandbox** — via the `obi_one` `ElectrophysiologyMetricsTask` for scans/batches over many traces.

## Entity Model

```
ElectricalCellRecording (trace)   ← input, from EntityCore (trace_id)
    │   bluepyefe + efel  (obi-one electrophysiology_metrics)
    ▼
ElectrophysiologyMetricsOutput   ← per-feature values (with units), by protocol/amplitude
```

No new entity is registered — the output is returned/kept as data.

## Authentication

- `Authorization: Bearer <keycloak_token>`, `virtual-lab-id` / `project-id` headers from `$OBI_VLAB_ID` / `$OBI_PROJECT_ID`.

Read from the environment, never from memory. See [[virtual-lab-manager-api]] and [[obi-sandbox-auth]].

Base URLs: `https://staging.cell-a.openbraininstitute.org` / `https://cell-a.openbraininstitute.org`.

## Pre-requisite: Find the Recording

```
GET /api/entitycore/electrical-cell-recording?project_id=<project-id>
```

Note the trace's `recording_type`, `ljp` (liquid junction potential, mV), and available stimuli — they determine which protocols/features are meaningful.

## Option 1 — REST (synchronous)

**Endpoint:** `GET /api/obi-one/declared/electrophysiologyrecording-metrics/{trace_id}`

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `requested_metrics` | list[feature] | Which eFEL features to compute (see Feature Reference). Omit → all applicable |
| `protocols` | list[stimulus] | Restrict to these stimulus types (see Protocol Reference). Omit → all |
| `min_value`, `max_value` | float (query) | Amplitude range in **nA**. Supply both bounds to filter; if either is omitted, the current implementation applies no amplitude filter. Equal values target one amplitude with a 10% tolerance. |

Returns an `ElectrophysiologyMetricsOutput` with the feature values (and their units, via `efel.units`). Returns **404** if a requested protocol is not present in the trace.

Example:

```
GET /api/obi-one/declared/electrophysiologyrecording-metrics/<trace-uuid>?protocols=idrest&requested_metrics=mean_frequency&requested_metrics=AP_amplitude
```

For amplitudes from 0.2 to 1.0 nA, append `&min_value=0.2&max_value=1.0`.

## Option 2 — In-sandbox (obi_one), for batches / scans

Configure an `ElectrophysiologyMetricsScanConfig` and run its task via `obi_one` in the sandbox. Its `Initialize` block takes `trace_id`, `protocols`, `requested_metrics`, and `amplitude`. Pass lists to sweep over several traces or protocol sets — see [[parameter-scan]] (driven through `obi_one`, since this task is local-only).

> A batch/scan over many traces can exceed the sandbox's ~30 s tool-call timeout — run it as a background process and poll, per the "Long-running work" section of [[virtual-lab-manager-api]].

## Protocol Reference (`protocols`)

`spontaneous`, `idrest`, `idthreshold`, `apwaveform`, `iv`, `step`, `sponaps`, `firepattern`, `spontaneousnohold`, `starthold`, `startnohold`, `delta`, `sahp`, `idhyperpol`, `irdepol`, `irhyperpol`, `iddepol`, `apthreshold`, `hyperdepol`, `negcheops`, `poscheops`, `spikerec`, `sinespec`, `genericstep`.

Step-like protocols (used for most spiking features): `idrest`, `idthreshold`, `apwaveform`, `iv`, `step`, `firepattern`, `delta`, `genericstep`.

## Feature Reference (`requested_metrics`)

Spiking / rate: `spike_count`, `mean_frequency`, `time_to_first_spike`, `time_to_last_spike`, `inv_time_to_first_spike`, `doublet_ISI`, `inv_first_ISI`, `ISI_log_slope`, `ISI_CV`, `irregularity_index`, `adaptation_index`.

Bursting: `strict_burst_number`, `strict_burst_mean_freq`, `spikes_per_burst`.

AP shape: `AP_height`, `AP_amplitude`, `AP1_amp`, `APlast_amp`, `AP_duration_half_width`, `AP_peak_upstroke`, `AP_peak_downstroke`.

Sub-threshold / passive: `voltage_base`, `voltage_after_stim`, `ohmic_input_resistance_vb_ssse`, `steady_state_voltage_stimend`, `sag_amplitude`, `decay_time_constant_after_stim`.

After-hyperpolarization: `AHP_depth`, `AHP_time_from_peak`.

Other: `depol_block_bool`.

> eFEL settings used: `Threshold = -20 mV`, `interp_step = 0.025`, `strict_stiminterval = true`.

---

## Working directory

```
/home/jovyan/<topic>/
├── logbook.md
├── recordings/         ← traces pulled from EntityCore (if downloaded)
├── results/            ← extracted feature tables (one per trace / protocol set)
├── plots/              ← trace overlays, feature-vs-amplitude curves
└── code/
```

## Logbook

Every session is logged per [[obi-logbook]].

Record, as the session goes:

- **Objective** — what the characterization is for (classifying an e-type, QC of a recording, building an f–I curve).
- **Recording** — which trace(s), cell type, species/region, protocols available, LJP correction.
- **What was computed** — the features requested, over which protocols and amplitudes, and why those.
- **Findings** — the feature values with units and their scientific reading (e.g. "adapting firing, input resistance ≈ 120 MΩ, prominent sag") — not the JSON.
- **Caveats** — protocols missing from the trace, amplitude coverage, noisy sweeps excluded.

Do **not** log endpoint/query details, obi_one call signatures, or auth — see [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], `{domain}` matches the environment the calls ran against.

- **Entities** — `https://{domain}/app/entity/{id}`. Link the source `ElectricalCellRecording`.
- **Sandbox files** — feature tables and trace/feature plots: take the `download_url` from `{obi}:get-sandbox-download-url` and swap `/files/` for `/lab/tree/`, keeping the rest of the path.
- **Jobs** — this task launches no campaign, so there is no workflows activity page to link.
