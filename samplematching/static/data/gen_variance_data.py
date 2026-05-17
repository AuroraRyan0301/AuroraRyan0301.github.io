"""Pre-compute per-grid-cell variance of three 1D extinction-gradient
estimators on a handful of random density/albedo configurations.

Ports the three algorithms from
  AuroraRyan0301/drt_1d/yuchen branch  slangpy/{drt,sample-matching}.slang

  * Sample Matching (SM)              s1 = s2  (locked sample)
  * Sample Not Matched (NM)           s1 ⊥ s2  (their reformulation, no lock)
  * Vanilla DRT (DRT)                 single sample per segment used for both
                                      terms but NOT through the joint-domain
                                      reformulation -- i.e. the delta-tracked t
                                      drives the gradient with no auxiliary s.

Ground-truth gradients are computed by central finite differences against a
ray-marching forward pass (M=2000 jittered samples per ray evaluation).

The output JSON has, per case:
  density        : float[N]      σ_t grid values
  albedo         : float[N]      single-scatter albedo grid values
  gt             : float[N]      finite-difference ∂L/∂σ_t[k]
  var_sm/nm/drt  : float[N]      per-cell variance of the (128-spp average) estimator
  vmax           : float         shared color-bar maximum (max across the three)
"""

import json
import math
import os
import random
from pathlib import Path

import numpy as np

# ---------------- scene parameters -------------------------------------------
N        = 128
X_MIN    = 0.0
X_MAX    = 1.0
DX       = (X_MAX - X_MIN) / (N - 1)
L_LIGHT  = 5.0
L_BG     = 0.1
SPP      = 128       # samples per gradient estimate
R        = 96        # number of independent SPP-averaged estimates per case
EPSILON  = 1e-3      # finite difference step
M_GT     = 2000      # ray-march samples for GT forward
N_CASES  = 3
MAX_BOUNCES = 32

# ---------------- numpy helpers ----------------------------------------------

def interp(grid, x):
    u = (x - X_MIN) / DX
    i = int(u)
    if i < 0: i = 0
    if i > N - 2: i = N - 2
    f = u - i
    if f < 0: f = 0.0
    if f > 1: f = 1.0
    return (1.0 - f) * grid[i] + f * grid[i + 1]

def interp_bwd(out, x, val):
    """Accumulate ∂/∂grid[k] of `interp(grid,x)*val` into `out`."""
    u = (x - X_MIN) / DX
    i = int(u)
    if i < 0: i = 0
    if i > N - 2: i = N - 2
    f = u - i
    if f < 0: f = 0.0
    if f > 1: f = 1.0
    out[i]     += (1.0 - f) * val
    out[i + 1] += f * val

# ---------------- forward radiance (ray-march, no grad) ----------------------

def ray_march_radiance(sigma_t, albedo, M=M_GT, seed=0):
    """High-resolution ray-march estimate of L."""
    rng = np.random.default_rng(seed)
    L_acc = 0.0
    for trial in range(8):  # average over 8 jittered rays to drop variance
        jitter = rng.random(M)
        ts = (np.arange(M) + jitter) / M  # uniform in (0, 1)
        # interp sigma_t and albedo at each step
        sigma_vals = np.array([interp(sigma_t, t) for t in ts])
        alb_vals   = np.array([interp(albedo,  t) for t in ts])
        dt = (X_MAX - X_MIN) / M
        # transmittance along the path (cumulative)
        # Simple emission/absorption + single scattering toward camera approx:
        # L = ∫ T(t) σ_t(t) albedo(t) L_light dt + T(X_MAX) L_light
        # (light is the back wall; this matches the slang setup where the
        # forward pass terminates at x_max with radiance L_light.)
        tau = np.concatenate(([0.0], np.cumsum(sigma_vals * dt)))[:-1]
        T = np.exp(-tau)
        emit = T * sigma_vals * alb_vals * L_LIGHT * dt
        L_acc += emit.sum() + np.exp(-(sigma_vals * dt).sum()) * L_LIGHT
    return L_acc / 8.0

def fd_gradient(sigma_t, albedo):
    """Central-difference ∂L/∂σ_t[k] for every k."""
    grad = np.zeros(N)
    base_seed = 12345
    # Use the SAME RNG seed for + and - so the FD signal isn't drowned in noise.
    for k in range(N):
        sp = sigma_t.copy(); sp[k] += EPSILON
        sm = sigma_t.copy(); sm[k] -= EPSILON
        Lp = ray_march_radiance(sp, albedo, M=M_GT, seed=base_seed + k * 17)
        Lm = ray_march_radiance(sm, albedo, M=M_GT, seed=base_seed + k * 17)
        grad[k] = (Lp - Lm) / (2.0 * EPSILON)
    return grad

# ---------------- estimators -------------------------------------------------

def gradient_estimate(sigma_t, albedo, sigma_bar, rng, mode):
    """One SPP of ∂L/∂σ_t[k] using a delta-tracked path.

    mode:
      'sm'  - sample matching, s1 = s2 (locked)
      'drt' - their reformulation but s1 ⊥ s2 (no lock) — exactly what
              drt.slang in the repo does.  Path is shared between the two
              terms; only the segment-local s decorrelates.
      (the 'nm' / two-independent-paths case is a separate function below)
    """
    g = np.zeros(N)

    # ---- forward path: delta-tracking bounces ---------------------------
    positions = [X_MIN]
    x = X_MIN
    for _ in range(MAX_BOUNCES):
        t_abs = x
        scattered = False
        for _ in range(4096):
            u = rng.random()
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= X_MAX:
                break
            if rng.random() < interp(sigma_t, t_abs) / sigma_bar:
                scattered = True
                break
        if not scattered:
            break
        positions.append(t_abs)
        x = t_abs
    n_b = len(positions) - 1

    # ---- backward radiance through scatter vertices ---------------------
    L = [0.0] * (n_b + 1)
    L[n_b] = L_LIGHT
    for j in range(n_b - 1, -1, -1):
        L[j] = interp(albedo, positions[j + 1]) * L[j + 1]

    # ---- per-segment gradient -------------------------------------------
    for j in range(n_b + 1):
        seg_start = positions[j]
        seg_end   = positions[j + 1] if j < n_b else X_MAX
        seg_len   = seg_end - seg_start
        if seg_len <= 0:
            continue
        L_next = L[j + 1] if j < n_b else L_LIGHT

        # delta-track t inside the segment
        t_abs = seg_start
        seg_scat = False
        for _ in range(4096):
            u = rng.random()
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= seg_end:
                break
            if rng.random() < interp(sigma_t, t_abs) / sigma_bar:
                seg_scat = True
                break
        t_clamped = min(t_abs - seg_start, seg_len)

        if seg_scat:
            h_t = interp(albedo, t_abs) * L_next
        else:
            h_t = L_next

        if mode == 'sm':
            s = rng.random() * t_clamped
            s1 = seg_start + s
            s2 = s1
        elif mode == 'drt':
            s1 = seg_start + rng.random() * t_clamped
            s2 = seg_start + rng.random() * t_clamped
        elif mode == 'ff':
            # Free-flight sampling: rejection-sample s ∝ σ_t(s) inside
            # [seg_start, seg_start + t_clamped].  Biased (cells with σ_t≈0
            # never get hit), but we only care about the variance pattern.
            def ff_one():
                hi = seg_start + t_clamped
                lo = seg_start
                if hi <= lo:
                    return lo
                for _ in range(64):
                    s = lo + rng.random() * (hi - lo)
                    if rng.random() < interp(sigma_t, s) / sigma_bar:
                        return s
                return lo + 0.5 * (hi - lo)  # fallback
            s1 = ff_one()
            s2 = ff_one()
        else:
            raise ValueError(mode)

        h_s = interp(albedo, s1) * L_next
        scat_val  = t_clamped * h_s
        trans_val = t_clamped * (-h_t)
        interp_bwd(g, s1, scat_val)
        interp_bwd(g, s2, trans_val)
    return g


def two_path_estimate(sigma_t, albedo, sigma_bar, rng):
    """Sample-Not-Matched estimator.

    Run *two independent path replays*.  Path 1 contributes only the
    scattering term, path 2 contributes only the transmittance term.  Each
    path is unbiased for its own term, so the sum is unbiased for the full
    ∂L/∂σ_t -- but the two terms no longer share path structure at all, so
    the negative correlation that helped DRT is gone too.
    """
    g = np.zeros(N)

    def _one_path(term):
        # forward delta-track
        positions = [X_MIN]
        x = X_MIN
        for _ in range(MAX_BOUNCES):
            t_abs = x; scattered = False
            for _ in range(4096):
                u = rng.random()
                if u < 1e-10: u = 1e-10
                t_abs += -math.log(u) / sigma_bar
                if t_abs >= X_MAX: break
                if rng.random() < interp(sigma_t, t_abs) / sigma_bar:
                    scattered = True; break
            if not scattered: break
            positions.append(t_abs); x = t_abs
        n_b = len(positions) - 1

        # backward radiance
        L = [0.0] * (n_b + 1)
        L[n_b] = L_LIGHT
        for j in range(n_b - 1, -1, -1):
            L[j] = interp(albedo, positions[j + 1]) * L[j + 1]

        # per-segment, accumulate only the requested term
        for j in range(n_b + 1):
            seg_start = positions[j]
            seg_end   = positions[j + 1] if j < n_b else X_MAX
            seg_len   = seg_end - seg_start
            if seg_len <= 0: continue
            L_next = L[j + 1] if j < n_b else L_LIGHT

            t_abs = seg_start; seg_scat = False
            for _ in range(4096):
                u = rng.random()
                if u < 1e-10: u = 1e-10
                t_abs += -math.log(u) / sigma_bar
                if t_abs >= seg_end: break
                if rng.random() < interp(sigma_t, t_abs) / sigma_bar:
                    seg_scat = True; break
            t_clamped = min(t_abs - seg_start, seg_len)
            s = seg_start + rng.random() * t_clamped

            if term == 'scat':
                h_s = interp(albedo, s) * L_next
                interp_bwd(g, s, t_clamped * h_s)
            else:  # 'trans'
                h_t = interp(albedo, t_abs) * L_next if seg_scat else L_next
                interp_bwd(g, s, t_clamped * (-h_t))

    _one_path('scat')
    _one_path('trans')
    return g

# ---------------- variance pre-computation ----------------------------------

def per_cell_variance(sigma_t, albedo, sigma_bar, mode, seed_base):
    """For R independent 128-spp averaged gradient estimates, compute per-cell
    variance. Returns float[N]."""
    estimates = np.zeros((R, N), dtype=np.float64)
    for r in range(R):
        rng = np.random.default_rng(seed_base + r * 7919)
        acc = np.zeros(N)
        for _ in range(SPP):
            if mode == 'nm':
                acc += two_path_estimate(sigma_t, albedo, sigma_bar, rng)
            else:
                acc += gradient_estimate(sigma_t, albedo, sigma_bar, rng, mode)
        estimates[r] = acc / SPP
    return estimates.var(axis=0)

def per_cell_mean(sigma_t, albedo, sigma_bar, mode, seed_base):
    """For sanity-checking unbiasedness: mean estimate across R*SPP samples."""
    acc = np.zeros(N)
    total = 0
    for r in range(R):
        rng = np.random.default_rng(seed_base + r * 7919)
        for _ in range(SPP):
            if mode == 'nm':
                acc += two_path_estimate(sigma_t, albedo, sigma_bar, rng)
            else:
                acc += gradient_estimate(sigma_t, albedo, sigma_bar, rng, mode)
            total += 1
    return acc / total

# ---------------- random case generators ------------------------------------

def random_curve(seed, n=N, smooth=8):
    """Random smooth-ish curve in [0, 1] -- low-frequency Gaussian-mixture-ish."""
    rng = np.random.default_rng(seed)
    n_bumps = rng.integers(3, 6)
    mus  = rng.uniform(0.1, 0.9, n_bumps)
    sigs = rng.uniform(0.05, 0.15, n_bumps)
    amps = rng.uniform(0.2, 1.0, n_bumps) * rng.choice([-1, 1], n_bumps)
    xs = np.linspace(0, 1, n)
    y = np.zeros(n)
    for mu, sig, amp in zip(mus, sigs, amps):
        y += amp * np.exp(-0.5 * ((xs - mu) / sig) ** 2)
    # normalize to [0, 1]
    y = (y - y.min()) / max(y.max() - y.min(), 1e-9)
    return y.astype(np.float64)

def make_case(seed):
    sigma_t = random_curve(seed)        * 4.5 + 0.3      # σ_t in ~[0.3, 4.8]
    albedo  = random_curve(seed + 1000) * 0.75 + 0.15    # albedo in [0.15, 0.9]
    return sigma_t.astype(np.float64), albedo.astype(np.float64)

# ---------------- main -------------------------------------------------------

def main():
    out_cases = []
    for c in range(N_CASES):
        seed = 4242 + c * 23
        print(f"\n=== case {c}  (seed {seed}) ===")
        sigma_t, albedo = make_case(seed)
        sigma_bar = float(sigma_t.max()) * 1.01
        print(f"  σ_t range [{sigma_t.min():.3f}, {sigma_t.max():.3f}]"
              f"  albedo range [{albedo.min():.3f}, {albedo.max():.3f}]")

        print("  computing GT (finite differences) ...")
        gt = fd_gradient(sigma_t, albedo)
        print(f"    ‖gt‖_∞ = {np.abs(gt).max():.3f}")

        case = {
            "density": sigma_t.tolist(),
            "albedo":  albedo.tolist(),
            "gt":      gt.tolist(),
        }

        for mode in ("sm", "drt", "nm", "ff"):
            print(f"  running {mode.upper()}  ({R} reps × {SPP} spp) ...")
            var = per_cell_variance(sigma_t, albedo, sigma_bar, mode,
                                    seed_base=10_000 * (c + 1) + hash(mode) % 997)
            case[f"var_{mode}"] = var.tolist()
            print(f"    mean per-cell variance = {var.mean():.3e}")

        # shared colormap max so all strips compare visually
        case["vmax"] = max(max(case["var_sm"]),
                           max(case["var_drt"]),
                           max(case["var_nm"]),
                           max(case["var_ff"]))
        out_cases.append(case)

    out = {"N": N, "x_min": X_MIN, "x_max": X_MAX,
           "spp": SPP, "reps": R, "cases": out_cases}
    dest = Path(__file__).with_name("variance_data.json")
    dest.write_text(json.dumps(out))
    print(f"\nwrote {dest}  ({dest.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
