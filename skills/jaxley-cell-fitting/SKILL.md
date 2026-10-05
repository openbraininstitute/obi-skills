---
name: jaxley-cell-fitting
description: Fit a morphologically detailed, conductance-based single-neuron model to a patch-clamp recording with Jaxley (differentiable simulation + gradient descent, JAX) inside the OBI sandbox — morphology and ElectricalCellRecording both taken from EntityCore, BBP/Hay L5PC ion-channel set from jaxley-mech. Covers finding a matched (ideally same-cell) morphology + recording pair, reading BBP NWB sweeps, building the Jaxley cell, a staged fit (passive + Ih by trace MSE — reliable; then active conductances by windowed summary statistics — experimental, did not beat literature values in testing), validation on held-out sweeps with eFEL against the unfitted literature model, and the sandbox's hard limits (2 GiB RAM, 4 CPUs, no GPU, ~30 s tool calls). Use when the user wants to fit a cell model with Jaxley or by gradient descent, to try a differentiable alternative to BluePyEModel, or to run Jaxley simulations/optimisations on OBI data in the sandbox.
license: Apache-2.0
---

# Fitting a detailed cell model to an OBI recording with Jaxley

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[virtual-lab-manager-api]] — which project the sandbox runs in, and the **long-running work** pattern (background process + polling). Every fit here is long-running.
> - [[obi-sandbox-auth]] — tokens. Read "Data first, fit offline" below for why this skill fetches everything up front.
> - [[obi-logbook]] — **mandatory.** One topic directory, one `logbook.md`.
> - [[obi-links]] — entity ids, sandbox files and notebooks go out as links.
> - [[emodel-building]] — the platform's own route to the same goal (BluePyEModel + NEURON, evolutionary search, launched as an obi-one task, registers an EModel). Offer it when the user needs a *registered* e-model; this skill produces files only.
> - [[ephys-efeature-extraction]] — the eFEL feature names used for validation.

## What this is, and what to expect

[Jaxley](https://github.com/jaxleyverse/jaxley) is a differentiable compartmental simulator written in JAX. Gradients of any loss with respect to every channel density come from one backward pass, so in principle a 20-parameter fit takes tens to hundreds of gradient steps instead of thousands of simulations. On OBI this runs in the user's sandbox as plain Python: no obi-one task, no launch system, nothing registered.

**Measured on a real same-cell pair** (C060114A7, rat P12 L5 TTPC, 415 compartments, staging sandbox, Oct 2026):

| stage | outcome | wall time |
|---|---|---|
| A: passive + Ih, 4 parameters, trace MSE | **works**: < 1 mV RMS on training sweeps, 1.24 mV on held-out repetitions, input resistance within 2 % | 5–10 min |
| B: 20 active densities + E_leak, summary statistics | **does not yet beat the literature start**: lower loss came with unphysiological spikes, or with a worse f–I curve (Step 6) | 20–30 min per attempt |
| Validation: 62 sweeps, eFEL, vs the unfitted literature model | subthreshold within 1–2 mV; spiking: the literature start validated **better** than the Stage-B fit (spikes per 2 s: recording 20.8, literature 24.5, fitted 38.7) | ~13 min |

So use this skill to fit passive/Ih properties, to run Jaxley simulations of OBI morphologies, and to explore gradient-based fitting with the user as an experiment: report it as such. For a production e-model, offer [[emodel-building]] (BluePyEModel, evolutionary search on cluster resources).

The workflow:

```
EntityCore: CellMorphology (SWC)  +  ElectricalCellRecording (NWB)      ← fetched once, cached
        │                                     │
        ▼                                     ▼
  axon → 60 µm AIS stub,              sweeps → clean step commands
  d_lambda discretisation             (holding + step), binned targets
        │                                     │
        └──────────────► Jaxley cell ◄────────┘
                           │  jaxley-mech L5PC channel set (34 °C)
        Stage A  passive + Ih ── trace MSE on hyperpolarising steps
        Stage B  20 active conductances ── windowed mean / SD / soft spike count on depolarising steps
        Validate held-out levels / repetitions / protocols with eFEL
```

## Sandbox facts that shape everything

Check them yourself at the start (`cat /sys/fs/cgroup/memory.max`, `nproc`) — they decide how many fits can run at once.

| | measured on staging, Oct 2026 | consequence |
|---|---|---|
| Memory | **2 GiB cgroup limit** for the whole pod (`free` shows the host's 15 GB — ignore it) | a passive + Ih fit process ≈ 0.9 GB (two fit); a full-channel fit ≈ 1.4 GB (**one at a time**). An extra process gets OOM-killed *silently* — no traceback; `grep oom_kill /sys/fs/cgroup/memory.events`. Near the limit, page-cache thrashing makes everything crawl. |
| CPU | 4 cores, no quota, **no GPU** | JAX uses ~1 core for these workloads → parallelise by *processes* (multi-start), not threads |
| Tool calls | `execute-python` / `execute-shell` return after ~30 s | every fit and every notebook run goes in the background ([[virtual-lab-manager-api]]) |
| `execute-shell` | runs inside the *same IPython kernel* as `execute-python`; only the **first line** is shell, later lines are parsed as Python | keep shell commands to one line (`a && b; c`); a multi-line command fails with a Python `SyntaxError` and runs nothing |
| Packages | `jax`, `jaxley`, `jaxley-mech`, `optax` are **not** preinstalled | `pip install --user` (lands in the EFS home, shared by all your projects, survives restarts) |

**Never run JAX in the tool kernel.** The `execute-python` kernel is shared with `execute-shell`, holds memory for the whole session, and a JAX workload there competes with your background fits for the 2 GiB. It is also what you need to stay responsive for polling. If the kernel hangs: `kill-sandbox` (files in `~` survive) — or free it with `import os; os._exit(0)` (the next call starts a fresh kernel). All simulation and fitting runs as **separate processes**: scripts launched with `nohup … &`, or notebooks executed with `jupyter nbconvert --execute` in the background.

## Setup

```bash
# execute-shell (one line). Never `tail` a pip log: progress bars make it megabytes long.
mkdir -p ~/<topic>/{code,recordings,morphologies,results,plots} && (nohup pip install --user "jaxley==0.14.0" "jaxley-mech==0.3.1" optax > ~/<topic>/results/pip.log 2>&1 &)
# later:
python -c "import jax, jaxley, jaxley_mech, optax; print(jax.__version__, jaxley.__version__)"
```

A kernel that was already running before `~/.local/lib/python3.12/site-packages` existed will not see the packages; new processes do. (`site.addsitedir(site.getusersitepackages())` fixes an old kernel, but you should not be importing JAX there anyway.)

Copy the helper module and the fit runner from this skill's `scripts/` directory into `~/<topic>/code/`. Everything below uses them:

- `scripts/jxfit.py` — sweep loading, model building, channel insertion, parameter transforms, batched simulator, losses, Adam loop, notebook helpers (`run_seeds`, `load_runs`).
- `scripts/run_fit.py` — one fit from a JSON config (keys documented in its header): `python run_fit.py config.json SEED` → `<name>_seed<SEED>.jsonl` (every candidate and step, with all parameter values) + `<name>_seed<SEED>.json` (best parameters, written at the end).

To get them there: `get-sandbox-upload-url` for each target path, then `PUT` a JSON body `{"type":"file","format":"base64","name":…,"path":"home/jovyan/<topic>/code/jxfit.py","content":<base64 of the file>}` with the returned token (HTTP 201 = written). Where only `execute-python` is available, write the file text with `pathlib.Path(...).write_text(r'''…''')` — the scripts contain no `'''`. If the scripts are not available at all, the steps below contain the essential code.

## Data first, fit offline

Fetch and cache **everything** (NWB, SWC, entity JSON) in the first minutes of the session, then let the fitting run without network access:

- The pod's `OBI_ACCESS_TOKEN` lives ~1 h. With an MCP-issued token (`azp: obi-mcp`) the auth-manager `token-exchange` of [[obi-sandbox-auth]] is refused (`400 validation_error … creating a new session is needed`), so there may be no way to mint a fresh one mid-session short of `kill-sandbox` — which also kills running fits.
- Fits run for tens of minutes to hours; they must not depend on a token.

```python
# execute-python — light, no JAX. EC = https://staging.openbraininstitute.org/api/entitycore (or production)
import os, requests, json, pathlib
H = {"Authorization": f"Bearer {os.environ['OBI_ACCESS_TOKEN']}",
     "virtual-lab-id": os.environ["OBI_VLAB_ID"], "project-id": os.environ["OBI_PROJECT_ID"]}
def download_asset(route, entity_id, suffix, out_dir):
    e = requests.get(f"{EC}/{route}/{entity_id}", headers=H, timeout=60).json()
    a = next(a for a in e["assets"] if a["path"].endswith(suffix))
    out = pathlib.Path(out_dir) / a["path"]
    r = requests.get(f"{EC}/{route}/{entity_id}/assets/{a['id']}/download", headers=H, timeout=300); r.raise_for_status()
    out.write_bytes(r.content); (out.with_suffix(".entity.json")).write_text(json.dumps(e, indent=1))
    return out
nwb = download_asset("electrical-cell-recording", REC_ID, ".nwb", f"{topic}/recordings")
swc = download_asset("cell-morphology", MORPH_ID, ".swc", f"{topic}/morphologies")
```

Many paginated queries in one call will hit the 30 s limit — run long listing loops in a `threading.Thread` inside the tool kernel and poll a shared dict (fine for plain `requests`; just not for JAX).

## Step 1 — Choose the recording and the morphology

**Recording** (`ElectricalCellRecording`): needs current-clamp steps that are both **subthreshold** (passive + sag) and **suprathreshold at several amplitudes** (f–I, adaptation). Check `stimuli` and `recording_origin`.

- `recording_origin: "in_silico"` entries (e.g. 720 `S1HL_L*_cADpyr_*` "simulated electrophysiology traces") are model output, not data — fine for a parameter-recovery test, wrong as an experimental target.
- BBP rat SSCx recordings carry ~20 protocols with repetitions, and `etypes` but no `mtypes`. `C…-SR-C1`: L5 thick-tufted pyramidal cells recorded by S. Romand (LNMC/BBP; the id encodes the 2006–2008 recording date; P12 and P14 in the cells checked). `C…-MT-C1`: M. Toledo-Rodriguez.

**Morphology** (`CellMorphology`): the best case is the **same neuron**. For BBP's Romand cells the reconstruction is named after the recording without `-SR-C1` — `C060114A7-SR-C1` ↔ `C060114A7`. 20 of the 43 cADpyr SR recordings have one (C060109A1–A3, C060110A2/A3/A5, C060112A7, C060114A2/A4–A7, C060116A1/A3/A5, C060202A4–A6, C080501A5, C080501B2). Each is listed **twice** — pick the rat entry (`brain_region` PSAH, created 2021), not the "Translated to mouse from rat data" copy (SSp, 2024). Names like `dend-X_axon-Y_…`, `…_-_Scale_…`, `…_-_Clone_N` are mosaics / scaled clones used to build circuits: not the cell itself.

```python
r = requests.get(f"{EC}/cell-morphology", params={"name__ilike": "C060114A7", "page_size": 10}, headers=H).json()
```

Without a same-cell reconstruction, match species, region, layer and m-type to the recording's cell class (e.g. a cADpyr L5 recording → an `L5_TPC:A` `digital_reconstruction`), and say clearly in the logbook that the morphology is a stand-in.

## Step 2 — Read the sweeps (BBP NWB)

```
acquisition/ic__<Protocol>__<NNN>/data            voltage, unit 'volts' (× conversion)
acquisition/ic__<Protocol>__<NNN>/starting_time   attrs['rate'] = 4000 Hz for the Romand cells
stimulus/presentation/ics__<Protocol>__<NNN>/data current, unit 'amperes'
```

(some files use `ccs__`/`ccss__` instead of `ic__`/`ics__`.)

- **The stimulus channel is the *measured* current**, with noise and spike-coupled capacitive artefacts. Do not inject it. Rebuild the command: holding = median before the step, amplitude = median during the step minus holding (`jxfit.clean_step`).
- **A holding current is applied** (≈ −0.08 nA in IV, ≈ −0.11 nA in IDRest for C060114A7) to keep V ≈ −69 mV. The model must receive the same holding current, and needs a few hundred ms of simulated pre-step time to settle (the IV protocol has only 20 ms of data before its step).
- **Bridge artefacts** — sub-millisecond V jumps at every current transition. Mask ~1 ms before to ~4 ms after each edge in the loss.
- Protocol timing (Romand cells): `IV` step 20–1020 ms of 1320 ms; `IDRest` / `IDThreshold` step 700–2700 ms of 3000 ms (`jxfit.STEP_TIMES`). C060114A7 has 10 IV levels (−0.28…+0.14 nA) × 3 repetitions and 16 IDRest levels (+0.25…+1.0 nA) × 2. Some early `IDRest` sweeps have a different length — `jxfit.protocol_table` skips sweeps whose duration does not fit the protocol. Check other datasets' timing before reusing `STEP_TIMES`.
- 4 kHz sampling resolves AP *width* only coarsely (2–2.5 ms half-width measured); AP *height* is still a reliable target and needs a tight tolerance (Stage B).
- Group repetitions by amplitude (`jxfit.add_levels`) and **hold out whole repetitions and whole levels** for validation.

## Step 3 — Build the Jaxley cell

```python
cell = jx.read_swc(swc_with_ais_stub, ncomp=1)           # ~4–25 s; graph backend
cell.set("axial_resistivity", 100.0); cell.apical.set("capacitance", 2.0); cell.basal.set("capacitance", 2.0)
for branch in cell.branches:                              # d_lambda rule (Jaxley L5PC example)
    d = 2 * branch.nodes["radius"].to_numpy()[0]; cm = branch.nodes["capacitance"].to_numpy()[0]
    lam = 1e5 * np.sqrt(d / (4 * np.pi * 100.0 * cm * 100.0)); L = branch.nodes["length"].to_numpy()[0]
    branch.set_ncomp(int((L / (0.3 * lam) + 0.9) / 2) * 2 + 1, initialize=False)
cell.initialize()
```

- **Axon:** keep only the first ~60 µm (AIS stub, BBP practice) — trim the SWC before reading it (`jxfit.trim_axon_swc`). C060114A7: 324 branches with 15 mm of axon → 197 branches, 415 compartments at d_lambda 0.3 (979 at 0.1).
- **Channels** (`jxfit.insert_l5pc_channels`), all from `jaxley_mech.channels.l5pc`, kinetics fixed at 34 °C (Q10 2.3) — the same family as BBP's NEURON e-models:

| region | channels |
|---|---|
| soma | NaTs2T, SKv3_1, SKE2, CaHVA, CaLVA, CaPump, CaNernstReversal (`channel_constants["T"] = 307.15`), H, Leak |
| axon (AIS) | NaTaT, NapEt2, KTst, KPst, SKv3_1, SKE2, CaHVA, CaLVA, CaPump, CaNernstReversal, Leak |
| apical | NaTs2T, SKv3_1, M, H (Hay exponential gradient `(-0.8696 + 2.087·e^{0.0031·d}) × g`), Leak |
| basal | H, Leak |

  Set `CaCon_i = 5e-5`, `CaCon_e = 2.0`, `eNa = 50`, `eK = -85`. Distances from the soma: `cell.compute_compartment_centers(); cell.nodes["dist_from_soma"] = jaxley.morphology.distance_direct(cell.soma.branch(0).comp(0), cell)`.
- Conductances are in **S/cm²**, currents injected in **nA**, time in **ms**.
- `jx.integrate` returns **one more sample than the stimulus** (N + 1) — slice before plotting/comparing.

## Step 4 — The simulator and the parameterisation

- Free parameters live in an unbounded space `u`; `x = lo · (hi/lo)^sigmoid(u)` for conductances (log-scaled), `lo + (hi−lo)·sigmoid(u)` for potentials (`jxfit.Params`). Gradient steps then make sense across parameters spanning 1e-6–1 S/cm².
- Set them per call with `view.data_set(name, value, param_state)` — a value can be an array over the view's compartments (that is how the apical Ih profile is scaled).
- Batch sweeps with `jax.vmap` over the stimulus (`data_stimulate`), and use 2-level checkpointing (`checkpoint_lengths=[⌈√N⌉, ⌈√N⌉]`) so gradient memory stays small.
- **Always `jax.jit`.** Un-jitted `jx.integrate` is ~6× slower (Python overhead dominates).

## Step 5 — Stage A: passive membrane + Ih (trace MSE)

Model: leak + H only. Data: one repetition of the hyperpolarising IV steps (6 sweeps), 300 ms of holding-only pre-time + the 1300-ms sweep, **dt = 0.2 ms** (ample below threshold), 1-ms bins, edge masks. Loss: mean squared error in mV². Adam, lr 0.1 → 0.01 (exponential decay), global-norm clip 1, ~60 steps.

**Constrain the parameters a somatic recording cannot see.** With everything free (`g_leak`, `E_leak`, `gH` soma / basal / apical-scale separately, dendritic `C_m`, `R_a`), two starts reached the *same* error (≈ 0.9 mV², < 1 mV RMS) with very different models: Ih spread over soma and apical tree with R_a ≈ 90 Ω·cm, versus Ih almost only in basal dendrites with R_a ≈ 260 Ω·cm and E_leak 6 mV higher. Somatic current steps do not tell *where* Ih sits, nor R_a from dendritic C_m. Use the constrained parameterisation:

```python
PARAMS_A = [
    dict(region="all",  name="Leak_gLeak", lo=5e-6, hi=3e-4, init=3e-5),               # S/cm2, log-scaled
    dict(region="all",  name="Leak_eLeak", lo=-95.0, hi=-50.0, init=-75.0, log=False), # mV
    dict(name="H_gH", lo=1e-6, hi=1e-3, init=8e-5,                                     # ONE Ih density, Hay distribution
         targets=[dict(region="soma"), dict(region="basal"), dict(region="apical", profile="hay")]),
    dict(region="dend", name="capacitance", lo=0.8, hi=3.0, init=2.0, log=False),      # uF/cm2 (spine factor)
]   # R_a fixed at 100 Ohm cm
```

Measured on C060114A7 (P12 L5 TTPC):

- From literature starting values, MSE 33.7 → 0.91 mV² in ~30 Adam steps (≈ 9 s/step, ~5 min). Training RMSE 0.95 mV; held-out repetitions 1.24 mV; input resistance 59.5 vs 58.2 MΩ recorded.
- **Start from literature values or from the best of a short random search, not from a random point.** A start near the box edges (gIh 3e-6, C_m 2.9, E_leak −52 mV) was still at 2.9 mV² after 60 steps: Adam moves each parameter ≤ ~lr per step in the unbounded space, so far starts need many steps.
- What the passive + Ih model cannot do: sag amplitude is under-estimated at strong hyperpolarisation (3.9 vs 5.5 mV) and the recorded sag/rebound is slower than Hay's Ih kinetics. Only densities are fitted; channel *kinetics* are fixed by the jaxley-mech models. Depolarising subthreshold steps overshoot (RMSE 3.8 mV) until the active channels are added.

## Step 6 — Stage B: active conductances (summary statistics)

Trace MSE does not work for spiking: a spike 2 ms late costs as much as a missing one and the gradient carries no useful direction. Use windowed summary statistics (after Jaxley's L5PC example; `jxfit.stats_fn` / `make_stats_loss`):

- per consecutive **100-ms** window over the step: mean of V, SD of V, and a **soft spike count** — the sum of positive increments of `sigmoid((V + 20)/2)`, ≈ 1 per upward crossing of −20 mV;
- mean V in [−50, −2] ms before the step (rest at the holding current);
- soft maximum of V over the step, `τ·logsumexp(V/τ)` with τ = 1 mV (AP height);
- each standardised by a tolerance (base 1 mV, mean 2 mV, SD 2 mV, count 1 spike, peak 2 mV); loss = mean absolute standardised error.

Three failure modes met on the way, all silent:

- **Without the count term a silent cell wins.** With mean/SD in 50-ms windows only, the best of 25 random candidates — and every Adam step after it — produced *no spikes at all* and still scored better than a spiking Hay-type model: at a few spikes per window, SD flips with spike *timing*, so a flat trace at the right mean voltage is a cheap local optimum. Check spike counts of the starting point before trusting a descending loss.
- **Bin the data on an exact time grid.** `t = arange(n) / rate * 1e3` is not exact for 4 kHz; flooring it into 0.25-ms bins leaves ~1 % of bins empty, and an empty bin read as 0 mV is a fake spike in the *target*. Use `t = arange(n) * (1e3 / rate)` and interpolate any empty bin (`jxfit.bin_data` does both).
- **Lowest loss ≠ good model.** With a 5-mV AP-peak tolerance (1 statistic among ~25 per sweep) the best-loss model had APs peaking near −10 mV instead of +25 mV (AIS Na⁺ collapsed to its lower bound), slid into depolarisation block at the highest current, and parked E_leak on its bound — while matching window means and spike counts. A random search ranked by that loss *chose* such a start over the Hay-type values, which already spiked with full-size APs at nearly the right rates. After every fit, look at the traces and list parameters sitting on a bound.

Recipe: freeze the Stage-A values; free the 20 active parameters (bounds from Jaxley's L5PC example, log-scaled) plus `E_leak` bounded to a physiological range (−85…−55 mV). Data: 3 IDRest levels (one repetition), 200 ms before to 800 ms into the step, **dt = 0.05 ms** (0.1 ms drifts spike times by several ms within 100 ms; 0.025 ms is the reference). **Start from the literature (Hay-type) values**; use a random search only as a comparison, and check the spike count and AP height of whatever it selects. Tolerances: AP peak **2 mV**, the rest as above. Adam lr 0.05 → 0.015, ~40 steps. **One Stage-B process at a time** (~1.4 GB).

**Measured on C060114A7 — set expectations accordingly.** Neither run produced a model better than the literature starting point:

| | start | loss (own weighting) | spikes in first 800 ms at +0.35 / +0.56 / +0.81 nA (recorded 4 / 9 / 13) | AP peak | grad norm |
|---|---|---|---|---|---|
| Hay-type values, unfitted | — | 3.17 | 7 / 9 / 13 | ≈ +30 mV | — |
| variant 1: best of 41 random candidates, peak tol. 5 mV | 2.47 | → 2.14 (36 steps, plateau) | 7 / 14 / 12, block at +0.81 | ≈ −10 mV | 1–15 |
| variant 2: Hay-type start, peak tol. 2 mV | 3.17 | → 3.06 (12 steps, stalled) | 10 / 14 / 20 | +20…+27 mV | 10⁵–10⁶ |

Treat Stage B as **experimental**: run it, but compare against the unfitted literature model on held-out sweeps (Step 7), and keep whichever is better. Do not report a Stage-B fit as an e-model without that comparison.

## Step 7 — Validate

Forward-simulate everything not used for training — other levels, the other repetition, the **full** step duration, other protocols — at dt = 0.025 ms (`jxfit.simulate_rows`, chunks of 4 sweeps). Compare eFEL features (`Spikecount`, `mean_frequency`, `time_to_first_spike`, `AP_amplitude`, `AHP_depth_abs`, `ISI_CV`, sag, steady-state V, input resistance) and the f–I curve against the recording, **and against the unfitted literature model** — that comparison is what the fitting bought. Put the recording's own repetition-to-repetition difference next to each error as the noise floor. The training loss alone says nothing about generalisation.

Measured on C060114A7 (variant-2 model; 32 IDRest + 30 IV sweeps at dt 0.025 ms, ~4 min per 32 × 2.6 s):

| | recording | gradient-fitted | literature (unfitted) | recording rep-to-rep |
|---|---|---|---|---|
| IV steady states (10 levels) | — | within 1–2 mV | — | — |
| input resistance | 58.2 MΩ | 55.3 MΩ | — | — |
| sag at −0.28 nA | 5.5 mV | 3.6 mV | — | — |
| IDRest spikes / 2 s (held out) | 20.8 | 38.7 | **24.5** | 1.3 |
| first-spike latency | 24 ms | 12 ms | 12 ms | 2.4 ms |
| AHP depth | −51.8 mV | −61.6 mV | −61.1 mV | 3.1 mV |
| AP half-width (4 kHz) | 2.3 ms | 0.8 ms | 0.8 ms | 0.2 ms |

The best model for this cell was **Stage-A passive/Ih + literature active densities**; the Stage-B fit made the f–I curve worse (rheobase far too low: 17 spikes at +0.25 nA vs 1). The AP width and AHP mismatch, shared by both, is a kinetics problem (adult Hay kinetics vs a P12 cell), not a density problem.

## Cost reference (staging sandbox, 1 core per process, C060114A7, 415 compartments)

| what | time | memory (RSS) |
|---|---|---|
| `read_swc` + d_lambda + channel insertion | 7 s alone, ~25 s+ when several processes start together | — |
| jitted forward, full model, 300 ms at dt 0.05 ms | 0.5 s (un-jitted: 3.3 s) | — |
| same, 4 sweeps vmapped: forward / value-and-grad | 1.6 s / 8.6 s (vs 2.1 s / 12.4 s one by one) | — |
| Stage A Adam step (passive + Ih, 6 sweeps × 1.6 s, dt 0.2 ms) | 8.8 s (two processes in parallel) | ~0.9 GB per process |
| Stage B random-search candidate (full model, 3 sweeps × 1 s, dt 0.05 ms, forward only) | 5 s | — |
| Stage B Adam step (same batch, value-and-grad) | 22 s (one process alone) | ~1.4 GB: **only one Stage-B fit fits in the pod** |
| first call of any new jitted function (XLA compile) | 20–60 s, minutes when processes compete | peaks above steady state |

Gradient cost ≈ 5–6 × forward cost. Cost scales linearly with simulated time, number of sweeps and (roughly) compartments; halving dt doubles it. Python imports from the EFS home are slow when several processes start at once — stagger launches.

## Limitations and open questions

Say these to the user when presenting a fit — they decide how far to trust it:

- **Identifiability.** Somatic current-clamp data constrain lumped properties (input resistance, membrane time constant, sag, f–I, AP shape at the soma). They do not constrain where conductances sit in the dendrites, R_a vs dendritic C_m, or most apical active densities. Equally good fits with different parameters are the norm, not a bug — constrain with priors (distributions, fixed R_a) and say which parameters are pinned by data and which by assumption.
- **Kinetics are fixed.** Only densities (and Ca-buffer constants) are fitted; kinetics come from the jaxley-mech Hay/BBP models (adult rat L5PC, 34 °C). Cells that differ — young animals (the Romand cells checked are P12–P14), other cell types, other species, other temperatures — show up as residual misfit that no density can remove (here: APs 0.8 vs 2.3 ms wide, AHPs ~10 mV too deep, slower and deeper sag than Hay's Ih). Jaxley *can* fit kinetic parameters, but only for channels that expose them as parameters (write a custom `jaxley.channels.Channel` with e.g. V½ shifts and τ scales).
- **Gradients through long spiking simulations explode.** From a start with full-size APs the gradient norm of the summary-statistic loss was 10⁵–10⁶ (1–15 for a model with small spikes); spike times hundreds of ms into a sweep are extremely sensitive to every conductance — the exploding-gradient problem of recurrent nets. Clipping + Adam keep steps bounded but make them nearly sign-like, so progress is slow and noisy. Mitigations to try: shorter simulated windows (more, shorter sweeps; 200–300 ms after the step), Jaxley's Polyak-normalised steps, smaller learning rates, a loss with bounded spike-timing sensitivity (`make_vr_term`, untested).
- **Spiking losses are hand-designed.** Summary statistics trade timing precision for smoothness; the window length, tolerances and the count term change the answer. Gradient descent finds a local optimum from wherever it starts — the choice of start, and checking its spike counts and AP height, matter as much as the optimiser.
- **Compute.** One core and ≤ 2 GiB per pod: tens of minutes per stage and one full-model fit at a time. Jaxley's main advantage — thousands of simulations batched on a GPU — is not available in the sandbox today.
- **Nothing is registered.** There is no Jaxley e-model entity type. The channel set is the BBP one, so fitted densities could in principle be mapped onto the BBP mod-file parameters (`gNaTs2_tbar_NaTs2_t` ↔ `NaTs2T_gNaTs2T`, S/cm² in both) and registered via [[emodel-building]]'s entity types — untested; say so if the user asks.
- **Stimulus fidelity.** Only somatic injection of a clean step command; bridge-balance and capacitance-compensation errors of the real recording are masked, not modelled; 4 kHz data limit AP-shape targets.

## Working directory

Per [[obi-logbook]]:

```
/home/jovyan/<topic>/              e.g. l5tpc-c060114a7-jaxley-fit
├── logbook.md
├── recordings/                    NWB + entity JSON
├── morphologies/                  SWC (+ trimmed AIS-stub SWC) + entity JSON
├── code/                          jxfit.py, run_fit.py, per-stage configs
├── results/<stage>/               <name>_seed<k>.jsonl / .json, logs
├── plots/
└── 01_….ipynb …                   notebooks, executed in the background with nbconvert
```

Make notebooks **idempotent**: the cell that launches fits skips seeds whose result file exists, so re-executing a notebook after a crash or an OOM-kill only redoes what is missing.

## Logbook

Record: the cell and why this morphology/recording pair (same cell or stand-in); protocols, levels and repetitions used for training vs held out; holding currents; the channel set and which parameters were free (with bounds) or frozen; per stage the loss before/after and across seeds; validation features model vs recording with units; and the limitations below that apply. Not the pip installs, OOM-kills, token problems or tool timeouts — see [[obi-logbook]].

## Linking

Per [[obi-links]]: the recording and morphology as `https://{domain}/app/entity/{id}`; notebooks, plots and result files as JupyterLab links built from `get-sandbox-download-url` (`/files/` → `/lab/tree/`). Nothing is registered, so there is no workflow link.
