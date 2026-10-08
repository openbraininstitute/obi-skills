---
name: ngv-metabolism
description: Run and interpret the NGV (neuron-glia-vasculature) unit metabolism model in the OBI sandbox. A 151-ODE biophysical model of one neuron plus astrocyte, ECS, and capillary, with young/aged phenotypes and synaptic, current-injection, or noradrenergic stimuli (Shichkova et al. 2025, aging brain metabolism). Use whenever the user asks to simulate brain energy metabolism, ATP/lactate/glucose dynamics, the astrocyte-neuron lactate shuttle, NAD or Na/K-ATPase changes, aging effects on metabolism, or to compare young vs aged metabolic responses to stimulation. The model code lives in the sandbox at /home/jovyan/shared_data/ngv-unit; this skill drives it headlessly via execute-python and returns plots. Not an obi-one endpoint and not a pip package.
---

# NGV Unit Metabolism Model

> **Surface: this browser agent.** Runs entirely through `{obi}:execute-python` in the OBI sandbox — no notebook, no widgets. You import the model code, call one runner function, and plot the result. Nothing here needs `bash_tool`, ipywidgets, or a Jupyter UI.

> **Generic skills this builds on — follow them, don't re-derive:**
> - [[obi-logbook]] — topic-directory + logbook discipline. Write outputs under `/home/jovyan/<topic>/`, not the model folder.
> - [[obi-links]] — hand every produced plot back to the user as a JupyterLab link, not just inline.

> **OBI server naming:** the OBI connector can be named anything (`OBI-local`, `OBI-staging`, ...). `{obi}` stands for whatever it's called in this conversation; the tool suffix `execute-python` is fixed.

## What the model is

One NGV unit — a neuron, an astrocyte, the extracellular space, and a capillary/blood-flow compartment — as **151 coupled ODEs** covering glycolysis, TCA cycle, oxidative phosphorylation, the pentose-phosphate pathway, glutamate/glutamine cycling, ion homeostasis (Na⁺/K⁺, Ca²⁺), membrane potentials, and blood flow. It reproduces the astrocyte-neuron lactate shuttle and activity-driven ATP dynamics.

Two phenotypes:
- **young** — baseline.
- **aged** — RNA-scaled enzyme/fuel changes: reduced NAD pools, reduced NADH-shuttle capacity, halved synaptic coupling, and reduced Na⁺/K⁺-ATPase (`kPumpn`, `kPumpg`). Paper's key finding: aged action-potential impairment comes mainly from the reduced Na⁺/K⁺-ATPase; fuel/NAD edits restore ATP toward young levels but pump restoration is needed to recover AP shape.

Solver: SciPy BDF. Parity vs the original Julia model is close but not bit-identical (largest differences in `VNeu` near the stimulus). Fine for exploration; don't present it as validated to 1e-9 everywhere.

## Model location and how to run it

Code is on the sandbox at **`/home/jovyan/shared_data/ngv-unit`** (see the companion "what to put under ngv-unit" note). Put that on the path, then call `run_metabolism`. Do not modify files there — treat it as read-only model code; write all outputs to your topic directory.

```python
# {obi}:execute-python
import sys
sys.path.insert(0, "/home/jovyan/shared_data/ngv-unit")
from ngv_runner import run_metabolism, STATE_INDEX  # STATE_INDEX: name -> 0-based column

topic = "/home/jovyan/ngv-metabolism-demo"   # your topic dir, per [[obi-logbook]]
res = run_metabolism(phenotype="young", stimulus="mainSyn", outdir=f"{topic}/results")
# res -> {"t": np.ndarray (N,), "u": np.ndarray (N, 151), "t_csv": ..., "u_csv": ..., "config": {...}}
```

### `run_metabolism` arguments

| Argument | Default | Meaning |
|---|---|---|
| `phenotype` | `"young"` | `"young"` or `"aged"`. |
| `stimulus` | `"mainSyn"` | `"mainSyn"` (synaptic), `"train_inj"` (current injection), `"NEmodAndSyn"` (noradrenergic + synaptic). |
| `stim_window` | `(200.0, 220.0)` | `(onset_s, offset_s)`. The runner derives the model's onset/duration encoding internally — always pass wall-clock onset/offset. |
| `t_end` | `stim_window[1] + 80.0` | Simulation end (s). Sim starts at t=1 s. |
| `dt` | `1.0` | Output sample spacing (s). Keep at 1.0 unless spike-level detail is needed; smaller `dt` makes huge files. |
| `nak_mode` | `"cat"` | Aged Na/K-ATPase scaling: `"cat"` or `"full"`. Ignored for young. |
| `custom_preset` | `None` | `"1_blood_glc_ini"` (set blood glucose) or `"2_blood_lac_ini"` (set blood lactate). |
| `glc_mod` / `lac_mod` | `7.6` / `2.0` | Values for the custom presets above. |
| `param_overrides` | `None` | **The flexibility knob.** `{param_name: value}` applied to the model namespace after phenotype/preset setup, so it wins. Use for arbitrary perturbations (drug/disease edits). |
| `outdir` | required | Writable dir for CSVs — a path under your topic dir, never `/home/jovyan/shared_data/ngv-unit`. |

### Reading results by biological name

`res["u"]` is `(N, 151)`. Never hardcode column numbers — use `STATE_INDEX`:

```python
u, t = res["u"], res["t"]
atp_n  = u[:, STATE_INDEX["ATP_n"]]     # neuronal cytosolic ATP
lac_n  = u[:, STATE_INDEX["Lac_n"]]     # neuronal lactate
lac_a  = u[:, STATE_INDEX["Lac_a"]]     # astrocytic lactate
vneu   = u[:, STATE_INDEX["VNeu"]]      # neuronal membrane potential
```

Common variables: `ATP_n`, `ATP_a`, `ADP_n`, `Lac_n`, `Lac_a`, `Lac_ecs`, `Glc_n`, `Glc_a`, `Pyr_n`, `NADH_n`, `NADH_a`, `O2_n`, `VNeu`, `Va`, `Na_n`, `K_out`, `Ca_n`, `PCr_n`. `STATE_INDEX` holds all 151 (`print(sorted(STATE_INDEX))` to list them).

### The parameter to biology map (for `param_overrides`)

`param_overrides` sets any named model parameter, letting the user model conditions beyond the built-in young/aged presets:

| To model... | Override | Direction |
|---|---|---|
| Reduced Na⁺/K⁺-ATPase (aged AP impairment) | `kPumpn`, `kPumpg` | decrease |
| NAD depletion | `NADtot_n`, `NADtot_a` | decrease |
| Impaired NADH shuttle | `NADHshuttle_aging_n`, `NADHshuttle_aging_a` | decrease (1.0 = intact) |
| Weakened synaptic coupling | `syn_aging_coeff` | decrease (1.0 = full) |
| Altered blood glucose / lactate | `C_Glc_a`, `C_Lac_a` | either (or use `custom_preset`) |

Record any override and its literature basis in the logbook.

### Adding a process the model lacks — `extra_flux`

`param_overrides` changes existing rate constants. When the user wants a process
the model has no parameter for — a drug that *clears* a metabolite, an exogenous
*infusion*, a pathological *leak* — use `extra_flux`. It **adds a term to a
state's derivative**, superposed on the frozen equations (empty `extra_flux`
reproduces the baseline exactly):

```
d[state]/dt  =  model's own equation  +  your extra term
```

Each entry maps a state name to either a string expression in state names and
`t`, or a callable `f(t, u, S)` (S is `STATE_INDEX`):

```python
# A drug that clears extracellular lactate (first-order removal):
res = run_metabolism("young", "mainSyn",
                     extra_flux={"Lac_ecs": "-0.05*Lac_ecs"},
                     outdir=f"{topic}/results")

# A timed glucose infusion into blood (callable form):
res = run_metabolism("young", "mainSyn",
                     extra_flux={"Glc_b": lambda t, u, S: 0.001 if t > 150 else 0.0},
                     outdir=f"{topic}/results")
```

Rules for `extra_flux`:
- **Units and sign are yours to get right** — the term is in the model's internal
  units for that state (mM/s etc.). Negative removes, positive adds. State a
  biological rationale and the units in the logbook, same as `param_overrides`.
- **Too large a term destabilizes the stiff solver.** A moderate term returns a
  result (possibly with a non-negativity warning); an excessive one makes
  `run_metabolism` raise a clear error asking you to reduce its magnitude — do
  that, don't retry unchanged.
- **`extra_flux` adds processes; it does not rewrite existing equations.** For
  genuine structural model changes (new states, rewritten fluxes), that's an
  offline, reviewed model-development task — not a sandbox run.

Applied `extra_flux` terms are recorded in `res["config"]["extra_flux"]`.

## Plotting

Always `matplotlib.use("Agg")` (headless). Save under `{topic}/plots/`. Make figures presentable: titles, axis labels with units (mV, mM, s), a shaded stimulus window, legends, and `dpi=150`.

```python
# {obi}:execute-python
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

def shade_stim(ax, window=(200, 220)):
    ax.axvspan(*window, color="0.85", zorder=0, label="stimulus")

fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
a1.plot(t, u[:, STATE_INDEX["ATP_n"]], color="#c0392b", lw=1.4)
a1.set_ylabel("ATP neuron (mM)"); shade_stim(a1); a1.legend(loc="upper right")
a2.plot(t, u[:, STATE_INDEX["Lac_ecs"]], color="#2c7fb8", lw=1.4)
a2.set_ylabel("Lactate ECS (mM)"); a2.set_xlabel("Time (s)")
fig.suptitle("NGV unit — young, synaptic stimulation")
fig.tight_layout(); fig.savefig(f"{topic}/plots/atp_lactate.png", dpi=150)
```

For young-vs-aged comparisons, run twice and overlay the same variable in two colors (e.g. steelblue = young, firebrick = aged) with a shared stimulus band.

## Handing results back

Per [[obi-links]], give the user each plot as a JupyterLab link (and bridge/present it if the surface supports it). Take the sandbox path and build the `/lab/tree/...` URL — don't leave the figure only on disk.

## Guardrails

- **Never write into `/home/jovyan/shared_data/ngv-unit`** — it's model code. All outputs go under the topic dir.
- **Non-negativity warning:** aggressive `param_overrides` can drive concentration-like states negative; `run_metabolism` surfaces a warning when that happens. Report it — the run may be unphysical past that point rather than a real biological result.
- **Execution time:** default runs (~300 s sim, `dt=1.0`) are quick. Long `t_end` or tiny `dt` can approach the sandbox execution cap — keep `dt=1.0` unless spike resolution is explicitly needed.
- **Parity honesty:** describe results as exploratory; the port matches Julia closely but not exactly, most notably `VNeu` near the stimulus.
- **Cite overrides:** any `param_overrides` used to model a condition needs a stated biological rationale in the logbook.
