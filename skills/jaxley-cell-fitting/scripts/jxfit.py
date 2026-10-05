"""Fit Jaxley models of OBI cells to OBI recordings: helpers for the jaxley-cell-fitting skill.

Run in a *separate process* (script or notebook executed in the background), never in the sandbox tool kernel.

Sections
    morphology      trim_axon_swc, build_cell, insert_l5pc_channels, ih_profile, build_model
    recordings      load_sweep, clean_step, step_command, STEP_TIMES, protocol_table, add_levels, efel_features
    parameters      Params (bounded <-> unbounded), targets, param_state, apply_x, specs_to_fixed
    simulation      make_simulator, bin_data, build_batch, simulate_rows
    losses          make_trace_mse, stats_fn, make_stats_loss, make_vr_term
    optimisation    fit (Adam), result_from_log
    notebooks       run_seeds (parallel seeds within the pod's memory), load_runs, plot_morph

Units: conductances S/cm2, capacitance uF/cm2, axial resistivity Ohm cm, current nA, voltage mV, time ms.
"""
import json
import pathlib
import site
import time as _time
import warnings

site.addsitedir(site.getusersitepackages())       # `pip install --user` lands in the EFS home
from jax import config

config.update("jax_enable_x64", True)
config.update("jax_platform_name", "cpu")

import h5py
import jax
import jax.numpy as jnp
import jaxley as jx
import numpy as np
import optax
import pandas as pd
from jaxley.channels import Leak
from jaxley.morphology import distance_direct
from jaxley_mech.channels.l5pc import (CaHVA, CaLVA, CaNernstReversal, CaPump, H, KPst, KTst, M,
                                       NaTaT, NapEt2, NaTs2T, SKE2, SKv3_1)

warnings.simplefilter("ignore", category=pd.errors.PerformanceWarning)


# ================================================================ morphology
def trim_axon_swc(src, dst, keep_um=60.0):
    """Keep soma + dendrites + the first `keep_um` of axon (BBP-style axon-initial-segment stub)."""
    a = np.loadtxt(src, comments="#")
    ids, typ, xyz, par = a[:, 0].astype(int), a[:, 1].astype(int), a[:, 2:5], a[:, 6].astype(int)
    idx = {i: k for k, i in enumerate(ids)}
    dist = np.zeros(len(a))
    for k in range(len(a)):
        pk = idx.get(par[k])
        if typ[k] == 2 and pk is not None and typ[pk] == 2:
            dist[k] = dist[pk] + np.linalg.norm(xyz[k] - xyz[pk])
    keep = (typ != 2) | (dist <= keep_um)
    np.savetxt(dst, a[keep], fmt=["%d", "%d", "%.4f", "%.4f", "%.4f", "%.4f", "%d"])
    return dst


def build_cell(swc, d_lambda=0.3, freq=100.0, max_ncomp=None, cm_dend=2.0, ra=100.0):
    """read_swc + passive cable properties + d_lambda discretisation (as in Jaxley's L5PC example)."""
    cell = jx.read_swc(str(swc), ncomp=1)
    cell.set("axial_resistivity", ra)
    cell.apical.set("capacitance", cm_dend)
    cell.basal.set("capacitance", cm_dend)
    for branch in cell.branches:
        d = 2 * branch.nodes["radius"].to_numpy()[0]
        cm = branch.nodes["capacitance"].to_numpy()[0]
        length = branch.nodes["length"].to_numpy()[0]
        lam = 1e5 * np.sqrt(d / (4 * np.pi * freq * cm * ra))
        n = int((length / (d_lambda * lam) + 0.9) / 2) * 2 + 1
        branch.set_ncomp(min(n, max_ncomp) if max_ncomp else n, initialize=False)
    cell.initialize()
    return cell


def _distances(cell):
    cell.compute_compartment_centers()
    cell.nodes["dist_from_soma"] = distance_direct(cell.soma.branch(0).comp(0), cell)


def insert_l5pc_channels(cell):
    """BBP / Hay et al. 2011 canonical channel set (jaxley-mech l5pc), kinetics fixed at 34 degC."""
    cell.apical.insert(NaTs2T()); cell.apical.insert(SKv3_1()); cell.apical.insert(M()); cell.apical.insert(H())
    cell.soma.insert(NaTs2T()); cell.soma.insert(SKv3_1()); cell.soma.insert(SKE2())
    ca = CaNernstReversal(); ca.channel_constants["T"] = 307.15
    cell.soma.insert(ca); cell.soma.insert(CaPump()); cell.soma.insert(CaHVA()); cell.soma.insert(CaLVA())
    cell.soma.insert(H())
    cell.basal.insert(H())
    cell.insert(CaNernstReversal())
    for ch in (NaTaT(), NapEt2(), KTst(), CaPump(), SKE2(), CaHVA(), KPst(), SKv3_1(), CaLVA()):
        cell.axon.insert(ch)
    cell.insert(Leak())
    cell.set("CaCon_i", 5e-05); cell.set("CaCon_e", 2.0)
    cell.set("eNa", 50.0); cell.set("eK", -85.0)
    _distances(cell)
    return cell


def ih_profile(cell, view):
    """Hay et al. 2011 exponential Ih distribution shape (multiplies a density; 1.22 at the soma)."""
    d = view.nodes["dist_from_soma"].to_numpy()
    return -0.8696 + 2.087 * np.exp(d * 0.0031)


def add_dend_group(cell):
    if "dend" not in cell.nodes.columns:
        cell.basal.add_to_group("dend"); cell.apical.add_to_group("dend")
    return cell


def build_model(swc, model="full", d_lambda=0.3, max_ncomp=None, fixed=()):
    """model: 'passive_ih' (leak + Ih in soma/basal/apical) or 'full' (insert_l5pc_channels).
    `fixed`: [{region, name, value, profile?}] values written onto the cell (e.g. an earlier stage's fit).
    Returns (cell, profiles) with profiles['hay'] = Ih shape over the apical compartments."""
    cell = build_cell(swc, d_lambda=d_lambda, max_ncomp=max_ncomp)
    add_dend_group(cell)
    if model == "passive_ih":
        cell.insert(Leak()); cell.soma.insert(H()); cell.basal.insert(H()); cell.apical.insert(H())
        _distances(cell)
    else:
        insert_l5pc_channels(cell)
    profiles = {"hay": jnp.asarray(ih_profile(cell, cell.apical))}
    for f in fixed:
        view = cell if f["region"] == "all" else getattr(cell, f["region"])
        view.set(f["name"], f["value"] * (np.asarray(profiles[f["profile"]]) if f.get("profile") else 1.0))
    return cell, profiles


# ================================================================ recordings (BBP NWB layout)
def load_sweep(nwb_path, key):
    """t (ms), v (mV), i (nA) for one acquisition key, e.g. 'ic__IDRest__083'.
    The stimulus channel is the *measured* current (noise, spike artefacts): use clean_step, do not inject it."""
    with h5py.File(nwb_path) as f:
        g = f["acquisition"][key]; ds = g["data"]
        v = ds[()] * ds.attrs.get("conversion", 1.0) * 1e3
        rate = g["starting_time"].attrs["rate"]
        skey = key.replace("ic__", "ics__", 1).replace("ccs__", "ccss__", 1)
        si = f["stimulus"]["presentation"][skey]["data"]
        i = si[()] * si.attrs.get("conversion", 1.0) * 1e9
    t = np.arange(len(v)) * (1e3 / rate)          # exact for 4 kHz; arange / rate * 1e3 is not
    return t, v, i


def clean_step(t, i, t_on, t_off):
    """Measured current -> (holding, step amplitude), medians away from the edges."""
    hold = np.median(i[(t > 2) & (t < t_on - 2)])
    amp = np.median(i[(t > t_on + 5) & (t < t_off - 5)]) - hold
    return float(hold), float(amp)


def step_command(hold, amp, t_on, t_off, t_max, dt):
    tt = np.arange(0, t_max + dt / 2, dt)
    return tt, np.where((tt >= t_on) & (tt < t_off), hold + amp, hold)


# Step timing (ms) of the BBP/LNMC protocols in the Romand / Toledo-Rodriguez recordings. Check other datasets.
STEP_TIMES = {"IV": (20.0, 1020.0), "IDRest": (700.0, 2700.0), "IDThreshold": (700.0, 2700.0),
              "IDhyperpol": (700.0, 2700.0), "sAHP": (521.0, 721.0)}


def protocol_table(nwb_path, proto):
    """One row per sweep of a protocol: key, holding and step current (nA), baseline V, spike count (-20 mV)."""
    with h5py.File(nwb_path) as f:
        keys = sorted(k for k in f["acquisition"] if k.split("__")[1] == proto)
    t_on, t_off = STEP_TIMES[proto]
    rows = []
    for k in keys:
        t, v, i = load_sweep(nwb_path, k)
        if t[-1] < t_off + 50:                    # a variant of the protocol with other timing
            continue
        hold, amp = clean_step(t, i, t_on, t_off)
        nsp = int(np.sum((v[1:] >= -20) & (v[:-1] < -20) & (t[1:] > t_on) & (t[1:] < t_off)))
        rows.append(dict(key=k, hold_nA=round(hold, 4), amp_nA=round(amp, 4),
                         v_base=round(float(np.median(v[(t > t_on - 15) & (t < t_on - 1)])), 2),
                         n_spikes=nsp, t_on=t_on, t_off=t_off, t_end=float(t[-1])))
    return pd.DataFrame(rows)


def add_levels(df, gap=0.02):
    """Group near-identical step amplitudes (repetitions) into nominal levels: level, level_amp_nA."""
    order = np.argsort(df["amp_nA"].to_numpy()); lv = np.zeros(len(df), int); cur = 0
    amps = df["amp_nA"].to_numpy()[order]
    for j in range(1, len(amps)):
        if amps[j] - amps[j - 1] > gap:
            cur += 1
        lv[order[j]] = cur
    df = df.copy(); df["level"] = lv
    df["level_amp_nA"] = df.groupby("level")["amp_nA"].transform("mean").round(3)
    return df


SPIKE_FEATS = ["Spikecount", "mean_frequency", "time_to_first_spike", "AP_amplitude", "AP_duration_half_width",
               "AHP_depth_abs", "ISI_CV", "adaptation_index2", "voltage_base"]
SUB_FEATS = ["voltage_base", "steady_state_voltage_stimend", "voltage_deflection", "sag_amplitude", "sag_ratio1",
             "decay_time_constant_after_stim"]


def efel_features(t, v, t_on, t_off, feats):
    """eFEL features of one trace (threshold -20 mV), NaN where eFEL returns nothing."""
    import efel
    efel.set_setting("Threshold", -20.0); efel.set_setting("interp_step", 0.025)
    tr = {"T": np.asarray(t, float), "V": np.asarray(v, float), "stim_start": [t_on], "stim_end": [t_off]}
    out = efel.get_feature_values([tr], feats, raise_warnings=False)[0]
    return {k: float(np.mean(out[k])) if out.get(k) is not None and len(out[k]) else np.nan for k in feats}


# ================================================================ parameters
class Params:
    """Bounded parameters <-> unbounded optimisation space u: x = lo*(hi/lo)**sigmoid(u) (log, default)
    or lo + (hi-lo)*sigmoid(u) (log=False).

    A spec: dict(region, name, lo, hi, init[, log][, profile]) acting on one region ('all', 'soma', 'axon',
    'basal', 'apical', 'dend'), or dict(name, lo, hi, init, targets=[{region[, profile]}, ...]) sharing one
    value between regions (e.g. one Ih density: soma, basal, apical x Hay profile)."""

    def __init__(self, specs):
        self.specs = specs
        self.names = [("+".join(t["region"] + (f"*{t['profile']}" if t.get("profile") else "") for t in s["targets"])
                       + "." + s["name"]) if "targets" in s
                      else f"{s['region']}.{s['name']}" + (f"*{s['profile']}" if s.get("profile") else "")
                      for s in specs]
        self.lo = jnp.asarray([s["lo"] for s in specs], dtype=float)
        self.hi = jnp.asarray([s["hi"] for s in specs], dtype=float)
        self.log = jnp.asarray([bool(s.get("log", True)) for s in specs])
        self.llo = jnp.where(self.log, jnp.log(jnp.maximum(self.lo, 1e-30)), self.lo)
        self.lhi = jnp.where(self.log, jnp.log(jnp.maximum(self.hi, 1e-30)), self.hi)

    def to_x(self, u):
        z = self.llo + (self.lhi - self.llo) * jax.nn.sigmoid(u)
        return jnp.where(self.log, jnp.exp(z), z)

    def to_u(self, x):
        x = jnp.asarray(x, dtype=float)
        z = jnp.where(self.log, jnp.log(jnp.maximum(x, 1e-30)), x)
        s = jnp.clip((z - self.llo) / (self.lhi - self.llo), 1e-4, 1 - 1e-4)
        return jnp.log(s / (1 - s))

    def init_x(self):
        return jnp.asarray([s["init"] for s in self.specs], dtype=float)

    def sample_u(self, rng, n, scale=None):
        """Uniform in the bounded (log) box; `scale` < 1 samples around the box centre."""
        s = rng.uniform(1e-3, 1 - 1e-3, size=(n, len(self.specs)))
        if scale is not None:
            s = 0.5 + (s - 0.5) * scale
        return jnp.asarray(np.log(s / (1 - s)))

    def as_dict(self, x):
        return {n: float(v) for n, v in zip(self.names, np.asarray(x))}


def targets(s):
    return s["targets"] if "targets" in s else [dict(region=s["region"], profile=s.get("profile"))]


def param_state(cell, P, x, profiles):
    """Parameter values x (bounded space) -> Jaxley param_state for jx.integrate (differentiable)."""
    ps = None
    for k, s in enumerate(P.specs):
        for tg in targets(s):
            view = cell if tg["region"] == "all" else getattr(cell, tg["region"])
            ps = view.data_set(s["name"], x[k] * profiles[tg["profile"]] if tg.get("profile") else x[k], ps)
    return ps


def apply_x(cell, specs, x, profiles):
    """Write values onto the cell (not differentiable; for evaluation)."""
    for s, val in zip(specs, np.asarray(x)):
        for tg in targets(s):
            view = cell if tg["region"] == "all" else getattr(cell, tg["region"])
            view.set(s["name"], float(val) * np.asarray(profiles[tg["profile"]]) if tg.get("profile") else float(val))


def specs_to_fixed(specs, x):
    """Fitted values -> the `fixed` list of a later stage / build_model."""
    return [dict(region=tg["region"], name=s["name"], value=float(v), **({"profile": tg["profile"]} if tg.get("profile") else {}))
            for s, v in zip(specs, np.asarray(x)) for tg in targets(s)]


# ================================================================ simulation
def make_simulator(cell, P, profiles, dt, n_steps, bin_steps, v_init=-70.0, checkpoint=True):
    """sim(x, icmd_batch) -> somatic V, shape (n_sweeps, n_bins), averaged over bins of `bin_steps` steps.
    Sweeps are vmapped; 2-level checkpointing keeps gradient memory small."""
    cell.delete_stimuli(); cell.delete_recordings()
    cell.soma.branch(0).loc(0.5).record("v", verbose=False)
    cell.set("v", v_init); cell.init_states()
    ck = [int(np.ceil(n_steps ** 0.5))] * 2 if checkpoint else None
    nb = n_steps // bin_steps

    def one(x, icmd):
        ps = param_state(cell, P, x, profiles)
        ds = cell.soma.branch(0).loc(0.5).data_stimulate(icmd, None, verbose=False)
        v = jx.integrate(cell, param_state=ps, data_stimuli=ds, delta_t=dt, checkpoint_lengths=ck)[0]
        return v[1: nb * bin_steps + 1].reshape(nb, bin_steps).mean(axis=1)   # integrate returns N+1 samples

    return jax.vmap(one, in_axes=(None, 0))


def bin_data(t, v, t0, n_bins, bin_ms):
    """Average the recording into bins [t0 + k*bin_ms, t0 + (k+1)*bin_ms). A bin that receives no sample is
    interpolated: left at 0 mV it would be a fake spike in the target."""
    k = np.floor((t - t0) / bin_ms + 1e-6).astype(int)
    ok = (k >= 0) & (k < n_bins)
    s = np.bincount(k[ok], weights=v[ok], minlength=n_bins); c = np.bincount(k[ok], minlength=n_bins)
    out = s / np.maximum(c, 1)
    empty = c == 0
    if empty.any() and (~empty).sum() > 1:
        idx = np.arange(n_bins); out[empty] = np.interp(idx[empty], idx[~empty], out[~empty])
    return out


def build_batch(nwb, rows, pre_ms, post_ms, dt, bin_ms, edge_mask=(1.0, 4.0)):
    """Sweeps (protocol_table rows) -> dict(icmd[n, steps+1] clean step commands incl. holding current,
    v[n, bins] binned recording, mask[n, bins] (no data / bridge artefacts at current edges excluded),
    tb = bin centres relative to step onset). The simulation starts `pre_ms` before the step onset."""
    rows = list(rows.itertuples()) if hasattr(rows, "itertuples") else rows
    t_sim = pre_ms + post_ms
    n_steps = int(round(t_sim / dt)); bin_steps = int(round(bin_ms / dt)); nb = n_steps // bin_steps
    tb = (np.arange(nb) + 0.5) * bin_ms - pre_ms
    I, V, Msk = [], [], []
    for r in rows:
        t, v, _ = load_sweep(nwb, r.key)
        dur = r.t_off - r.t_on
        _, ic = step_command(r.hold_nA, r.amp_nA, pre_ms, pre_ms + dur, t_sim - dt, dt)
        I.append(ic[:n_steps + 1] if len(ic) > n_steps else np.pad(ic, (0, n_steps + 1 - len(ic)), mode="edge"))
        V.append(bin_data(t, v, r.t_on - pre_ms, nb, bin_ms))
        m = (tb + r.t_on >= 0) & (tb + r.t_on <= t[-1])
        for e in (0.0, dur):
            m &= ~((tb >= e - edge_mask[0]) & (tb <= e + edge_mask[1]))
        Msk.append(m)
    return dict(icmd=jnp.asarray(np.stack(I)), v=jnp.asarray(np.stack(V)), mask=jnp.asarray(np.stack(Msk)),
                tb=tb, n_steps=n_steps, bin_steps=bin_steps, dt=dt, keys=[r.key for r in rows])


def simulate_rows(cell, profiles, nwb, rows, pre_ms, post_ms, dt, bin_ms, v_init=-70.0, chunk=4):
    """Forward-simulate sweeps with the cell's current values (see build_model `fixed`). Adds B['vm']."""
    B = build_batch(nwb, rows, pre_ms, post_ms, dt, bin_ms)
    sim = jax.jit(make_simulator(cell, Params([]), profiles, B["dt"], B["n_steps"], B["bin_steps"],
                                 v_init=v_init, checkpoint=False))
    x0 = jnp.zeros((0,))
    B["vm"] = np.concatenate([np.asarray(sim(x0, B["icmd"][k:k + chunk])) for k in range(0, B["icmd"].shape[0], chunk)])
    return B


# ================================================================ losses
def make_trace_mse(sim, B):
    """Mean squared error (mV^2) over unmasked bins. For subthreshold sweeps only."""
    mask = B["mask"]

    def loss_x(x):
        vm = sim(x, B["icmd"])
        return jnp.sum(jnp.where(mask, (vm - B["v"]) ** 2, 0.0)) / jnp.sum(mask)

    return loss_x


def stats_fn(B, base_window=(-50.0, -2.0), win_start=0.0, win_stop=800.0, win_ms=100.0,
             sigma=None, peak_tau=1.0, spike_thr=-20.0, spike_k=2.0):
    """Standardised, differentiable summary statistics of one binned spiking trace: mean V before the step;
    per window the mean of V, SD of V and a soft spike count; soft max of V (AP peak). The soft count is the
    sum of positive increments of sigmoid((V - thr)/k), ~1 per upward threshold crossing. Without it a silent
    trace at the right mean voltage can beat a spiking one."""
    sigma = {**dict(base=1.0, mean=2.0, std=2.0, count=1.0, peak=5.0), **(sigma or {})}
    tb = B["tb"]; m0 = np.asarray(B["mask"][0])
    W, kind, sg = [], [], []
    a, b = base_window
    W.append((tb >= a) & (tb < b) & m0); kind.append("mean"); sg.append(sigma["base"])
    edges = np.arange(win_start, win_stop + 1e-9, win_ms)
    for a, b in zip(edges[:-1], edges[1:]):
        w = (tb >= a) & (tb < b) & m0
        W += [w, w, w]; kind += ["mean", "std", "count"]; sg += [sigma["mean"], sigma["std"], sigma["count"]]
    W = np.stack(W).astype(float)
    Wn = jnp.asarray(W / W.sum(1, keepdims=True)); Wc = jnp.asarray(W)
    is_std = jnp.asarray([k == "std" for k in kind]); is_cnt = jnp.asarray([k == "count" for k in kind])
    sg = jnp.asarray(sg)
    pk = jnp.asarray((tb >= 0) & (tb < win_stop) & m0)

    def stats(v):
        mu = Wn @ v
        sd = jnp.sqrt(jnp.maximum((Wn * (v[None, :] - mu[:, None]) ** 2).sum(1), 1e-9))
        s = jax.nn.sigmoid((v - spike_thr) / spike_k)
        cnt = Wc @ jnp.concatenate([jnp.zeros(1), jax.nn.relu(s[1:] - s[:-1])])
        st = jnp.where(is_cnt, cnt, jnp.where(is_std, sd, mu))
        peak = peak_tau * jax.nn.logsumexp(jnp.where(pk, v, -200.0) / peak_tau)
        return jnp.concatenate([st / sg, jnp.asarray([peak / sigma["peak"]])])

    return stats


def make_vr_term(B, tau_ms=25.0, spike_thr=-20.0, spike_k=2.0, t_start=0.0, t_stop=800.0):
    """van Rossum-style spike-train distance, differentiable through a soft spike indicator (positive increments
    of sigmoid((V - thr)/k), filtered by exp(-t/tau)). Moving a spike changes it continuously, so it carries
    spike-timing gradients that windowed statistics lack. Experimental: not yet validated (see SKILL.md)."""
    tb = B["tb"]; bin_ms = float(tb[1] - tb[0])
    sel = jnp.asarray((tb >= t_start) & (tb < t_stop))
    ker = jnp.exp(-np.arange(0.0, 5 * tau_ms, bin_ms) / tau_ms)

    def train(v):
        s = jax.nn.sigmoid((v - spike_thr) / spike_k)
        up = jnp.concatenate([jnp.zeros(1), jax.nn.relu(s[1:] - s[:-1])]) * sel
        return jnp.convolve(up, ker, mode="full")[: v.shape[0]]

    R_data = jax.vmap(train)(B["v"])
    return lambda vm: jnp.mean((jax.vmap(train)(vm) - R_data) ** 2) * (tau_ms / bin_ms)


def make_stats_loss(sim, B, vr_weight=0.0, vr_tau_ms=25.0, **kw):
    """Mean absolute standardised error of the summary statistics (+ vr_weight x van Rossum term)."""
    stats = stats_fn(B, **kw)
    S_data = jax.vmap(stats)(B["v"])
    vr = make_vr_term(B, tau_ms=vr_tau_ms, t_stop=kw.get("win_stop", 800.0)) if vr_weight else None

    def loss_x(x):
        vm = sim(x, B["icmd"])
        loss = jnp.mean(jnp.abs(jax.vmap(stats)(vm) - S_data))
        return loss + vr_weight * vr(vm) if vr is not None else loss

    return loss_x


# ================================================================ optimisation
def fit(loss_fn, P, u0, n_steps, lr=0.05, log_path=None, clip=1.0, decay_to=0.2):
    """Adam on u with global-norm clipping and exponential lr decay (lr -> lr*decay_to over n_steps).
    Appends one JSON line per step (loss, grad_norm, sec, x) to log_path. Returns ((best_loss, best_u), hist)."""
    sched = optax.exponential_decay(lr, transition_steps=max(n_steps, 1), decay_rate=decay_to)
    opt = optax.chain(optax.clip_by_global_norm(clip), optax.adam(sched))
    vg = jax.jit(jax.value_and_grad(loss_fn))
    u = jnp.asarray(u0); st = opt.init(u)
    best = (np.inf, u); hist = []
    for k in range(n_steps + 1):
        t0 = _time.time()
        loss, g = vg(u)
        loss = float(loss); gn = float(jnp.linalg.norm(g))       # float() blocks: timing is real
        if np.isfinite(loss) and loss < best[0]:
            best = (loss, u)
        rec = dict(step=k, loss=loss, grad_norm=gn, sec=round(_time.time() - t0, 2), x=P.as_dict(P.to_x(u)))
        hist.append(rec)
        if log_path:
            with open(log_path, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
        if k == n_steps or not np.isfinite(gn):
            break
        upd, st = opt.update(jnp.nan_to_num(g), st, u)
        u = optax.apply_updates(u, upd)
    return best, hist


def result_from_log(jsonl):
    """Best-so-far result from a run_fit JSONL log; works for runs that were stopped early."""
    L = [json.loads(line) for line in pathlib.Path(jsonl).read_text().splitlines()]
    srch = [h for h in L if h.get("phase") == "search"]; gd = [h for h in L if "step" in h]
    b = min(gd, key=lambda h: h["loss"])
    return dict(loss_init=min(h["loss"] for h in srch) if srch else gd[0]["loss"], loss_best=b["loss"],
                best_step=b["step"], x_best=b["x"], steps_done=gd[-1]["step"],
                sec_per_step=float(np.median([h["sec"] for h in gd[1:]] or [np.nan])))


# ================================================================ notebooks
def run_seeds(cfg, seeds, max_parallel=1, poll=60, runner=None):
    """Run run_fit.py once per seed that has no result yet, at most `max_parallel` at once, printing progress.
    The OBI sandbox pod has 2 GiB: two passive fits fit, a full-channel fit (~1.4 GB) runs alone; an extra
    process is OOM-killed silently (exit code -9)."""
    import subprocess
    import sys
    runner = runner or str(pathlib.Path(__file__).with_name("run_fit.py"))
    res_dir = pathlib.Path(cfg["out_dir"]); res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "config.json").write_text(json.dumps(cfg, indent=1))
    todo = [s for s in seeds if not (res_dir / f"{cfg['name']}_seed{s}.json").exists()]
    print("to run:", todo, flush=True)
    running, t0 = {}, _time.time()
    while todo or running:
        while todo and len(running) < max_parallel:
            s = todo.pop(0)
            running[s] = subprocess.Popen([sys.executable, runner, str(res_dir / "config.json"), str(s)],
                                          stdout=open(res_dir / f"seed{s}.log", "w"), stderr=subprocess.STDOUT)
        _time.sleep(poll)
        for s, p in list(running.items()):
            if p.poll() is not None:
                print(f"seed {s} exited with code {p.returncode}", flush=True); running.pop(s)
        prog = {}
        for s in seeds:
            f = res_dir / f"{cfg['name']}_seed{s}.jsonl"
            lines = f.read_text().splitlines() if f.exists() else []
            last = json.loads(lines[-1]) if lines else {}
            prog[s] = (last.get("step", last.get("phase")), round(last.get("loss", float("nan")), 3))
        print(f"{(_time.time() - t0) / 60:5.1f} min {prog}", flush=True)


def load_runs(res_dir, name, seeds):
    """Per seed: best-so-far result + 'hist' (Adam steps) + 'search' (candidates) + 'complete'."""
    out = {}
    for s in seeds:
        j, log = pathlib.Path(res_dir) / f"{name}_seed{s}.json", pathlib.Path(res_dir) / f"{name}_seed{s}.jsonl"
        if log.exists() and any('"step"' in line for line in log.read_text().splitlines()):
            r = result_from_log(log)
            L = [json.loads(line) for line in log.read_text().splitlines()]
            r["hist"] = [h for h in L if "step" in h]; r["search"] = [h for h in L if h.get("phase") == "search"]
            r["complete"] = j.exists(); out[s] = r
    return out


def plot_morph(ax, swc, title=None, lw=0.5):
    """2-D projection of an SWC (black soma, blue axon, red basal, purple apical)."""
    from matplotlib.collections import LineCollection
    a = np.loadtxt(swc, comments="#")
    idx = {int(i): k for k, i in enumerate(a[:, 0])}
    cols = {1: "k", 2: "tab:blue", 3: "tab:red", 4: "tab:purple"}
    segs, cs = [], []
    for k in range(len(a)):
        pk = idx.get(int(a[k, 6]))
        if pk is not None:
            segs.append([a[pk, 2:4], a[k, 2:4]]); cs.append(cols.get(int(a[k, 1]), "gray"))
    ax.add_collection(LineCollection(segs, colors=cs, linewidths=lw))
    ax.autoscale(); ax.set_aspect("equal"); ax.set_xlabel("x (um)"); ax.set_ylabel("y (um)")
    if title:
        ax.set_title(title)
