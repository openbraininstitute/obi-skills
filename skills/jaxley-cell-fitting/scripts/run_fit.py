"""Run one Jaxley fit from a JSON config:   python run_fit.py config.json SEED

Writes <out_dir>/<name>_seed<SEED>.jsonl (every search candidate and Adam step: loss, gradient norm, all
parameter values) and, once finished, <name>_seed<SEED>.json (best parameters). A run stopped early can be
read with jxfit.result_from_log / load_runs.

Config keys
    name, out_dir, nwb, swc                  run name, output dir, recording (NWB), morphology (SWC, AIS stub)
    model                                    'passive_ih' | 'full'
    d_lambda, max_ncomp                      discretisation (default 0.3, no cap)
    fixed                                    [{region, name, value, profile?}] held fixed (earlier stages)
    params                                   free parameter specs (see jxfit.Params)
    train                                    [{protocol, key}] training sweeps
    pre_ms, post_ms, dt, bin_ms              simulated window around the step onset, time step, bin width
    loss                                     'trace_mse' | 'stats'
    base_window, win_start, win_stop,        'stats' only: see jxfit.stats_fn
    win_ms, sigma, peak_tau, vr_weight, vr_tau_ms
    random_search, rs_scale, include_init    forward-only candidates before Adam (seed 0 also tries `init`)
    n_steps, lr, decay_to, clip              Adam
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from jxfit import (Params, add_levels, build_batch, build_model, fit, make_simulator,  # sets JAX x64 + CPU
                   make_stats_loss, make_trace_mse, protocol_table)

import jax
import numpy as np

cfg = json.loads(pathlib.Path(sys.argv[1]).read_text()); seed = int(sys.argv[2])
out = pathlib.Path(cfg["out_dir"]); out.mkdir(parents=True, exist_ok=True)
tag = f"{cfg['name']}_seed{seed}"; log = out / f"{tag}.jsonl"; log.unlink(missing_ok=True)


def say(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------- model, with earlier stages' values held fixed
cell, profiles = build_model(cfg["swc"], cfg["model"], d_lambda=cfg.get("d_lambda", 0.3),
                             max_ncomp=cfg.get("max_ncomp"), fixed=cfg.get("fixed", []))
P = Params(cfg["params"])
say(tag, "model", cfg["model"], "comps", cell.nodes.shape[0], "free params", len(P.specs))

# ---------------- data
tables = {pr: add_levels(protocol_table(cfg["nwb"], pr)) for pr in {s["protocol"] for s in cfg["train"]}}
rows = [tables[s["protocol"]][tables[s["protocol"]].key == s["key"]].iloc[0] for s in cfg["train"]]
B = build_batch(cfg["nwb"], rows, cfg["pre_ms"], cfg["post_ms"], cfg["dt"], cfg["bin_ms"])
sim = make_simulator(cell, P, profiles, B["dt"], B["n_steps"], B["bin_steps"], v_init=cfg.get("v_init", -70.0))
say("batch", tuple(B["icmd"].shape), "bins", B["v"].shape[1])

# ---------------- loss
if cfg["loss"] == "trace_mse":
    loss_x = make_trace_mse(sim, B)
elif cfg["loss"] == "stats":
    loss_x = make_stats_loss(sim, B, base_window=tuple(cfg["base_window"]), win_start=cfg["win_start"],
                             win_stop=cfg["win_stop"], win_ms=cfg["win_ms"], sigma=cfg["sigma"],
                             peak_tau=cfg.get("peak_tau", 1.0), vr_weight=cfg.get("vr_weight", 0.0),
                             vr_tau_ms=cfg.get("vr_tau_ms", 25.0))
else:
    raise ValueError(cfg["loss"])


def loss_u(u):
    return loss_x(P.to_x(u))


# ---------------- initialisation: forward-only random search (cheap: no gradient)
rng = np.random.default_rng(seed)
cands = [P.to_u(P.init_x())] if cfg.get("include_init", True) and seed == 0 else []
if cfg.get("random_search", 0):
    cands += list(P.sample_u(rng, cfg["random_search"], scale=cfg.get("rs_scale")))
if not cands:
    cands = list(P.sample_u(rng, 1, scale=cfg.get("rs_scale")))
fl = jax.jit(loss_u)
best_u, best_l = None, np.inf
t0 = time.time()
for j, u in enumerate(cands):
    loss = float(fl(u))
    with open(log, "a") as fh:
        fh.write(json.dumps(dict(phase="search", cand=j, loss=loss, x=P.as_dict(P.to_x(u)))) + "\n")
    if np.isfinite(loss) and loss < best_l:
        best_u, best_l = u, loss
say(f"search: {len(cands)} candidates in {time.time() - t0:.0f}s, best loss {best_l:.4f}")

# ---------------- gradient descent
(best_loss, bu), hist = fit(loss_u, P, best_u, cfg["n_steps"], lr=cfg.get("lr", 0.05), log_path=log,
                            clip=cfg.get("clip", 1.0), decay_to=cfg.get("decay_to", 0.2))
res = dict(name=cfg["name"], seed=seed, loss_init=best_l, loss_best=best_loss, x_best=P.as_dict(P.to_x(bu)),
           specs=cfg["params"], n_steps=cfg["n_steps"],
           sec_per_step=float(np.median([h["sec"] for h in hist[1:]] or [0])))
(out / f"{tag}.json").write_text(json.dumps(res, indent=1))
say("DONE", tag, f"loss {best_l:.4f} -> {best_loss:.4f}")
