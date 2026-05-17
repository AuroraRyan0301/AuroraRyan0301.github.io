"""Numba-JIT version of gen_variance_data.py for high-R production runs.

Same algorithm semantics as the original (see slangpy/sample-matching.slang and
drt.slang in AuroraRyan0301/drt_1d), just rewritten so numba can compile the
inner loops. Yields a ~100x speedup over pure Python on a typical laptop.
"""

import json
import math
import os
import time
from pathlib import Path

import numpy as np
from numba import njit, prange

# ---------------- scene parameters -------------------------------------------
N        = 256                       # grid resolution
X_MIN    = 0.0
X_MAX    = 1.0
DX       = (X_MAX - X_MIN) / (N - 1)
L_LIGHT  = 5.0
SPP      = 128                       # samples per gradient estimate
R        = 5120                      # number of SPP-averaged estimates per case
M_GT     = 1500
EPSILON  = 1e-3
N_CASES  = 3
MAX_BOUNCES = 32

# Mode IDs: 0=SM, 1=DRT, 2=FF, 3=NM (two paths)
MODE_SM, MODE_DRT, MODE_FF, MODE_NM = 0, 1, 2, 3

# ---------------- jitted core ------------------------------------------------

@njit(inline='always', cache=True, fastmath=True)
def _pcg(state):
    s = (state[0] * np.uint64(1664525) + np.uint64(1013904223)) & np.uint64(0xFFFFFFFF)
    state[0] = s
    return float(s) / 4294967296.0

@njit(inline='always', cache=True, fastmath=True)
def _interp(grid, x, x_min, dx, N):
    u = (x - x_min) / dx
    i = int(u)
    if i < 0: i = 0
    if i > N - 2: i = N - 2
    f = u - i
    if f < 0.0: f = 0.0
    if f > 1.0: f = 1.0
    return (1.0 - f) * grid[i] + f * grid[i + 1]

@njit(inline='always', cache=True, fastmath=True)
def _interp_bwd(out, x, val, x_min, dx, N):
    u = (x - x_min) / dx
    i = int(u)
    if i < 0: i = 0
    if i > N - 2: i = N - 2
    f = u - i
    if f < 0.0: f = 0.0
    if f > 1.0: f = 1.0
    out[i]     += (1.0 - f) * val
    out[i + 1] += f * val

@njit(cache=True, fastmath=True)
def _grad_one(sigma_t, albedo, sigma_bar, state, mode, out,
              x_min, x_max, dx, N, max_bounces, L_light):
    positions = np.empty(max_bounces + 1, dtype=np.float64)
    positions[0] = x_min
    n_b = 0
    x = x_min
    for b in range(max_bounces):
        t_abs = x
        scattered = False
        for step in range(4096):
            u = _pcg(state)
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= x_max: break
            sig = _interp(sigma_t, t_abs, x_min, dx, N)
            if _pcg(state) < sig / sigma_bar:
                scattered = True
                break
        if not scattered: break
        n_b += 1
        positions[n_b] = t_abs
        x = t_abs

    L = np.empty(n_b + 1, dtype=np.float64)
    L[n_b] = L_light
    for j in range(n_b - 1, -1, -1):
        L[j] = _interp(albedo, positions[j + 1], x_min, dx, N) * L[j + 1]

    for j in range(n_b + 1):
        seg_start = positions[j]
        seg_end = positions[j + 1] if j < n_b else x_max
        seg_len = seg_end - seg_start
        if seg_len <= 0: continue
        L_next = L[j + 1] if j < n_b else L_light

        t_abs = seg_start
        seg_scat = False
        for step in range(4096):
            u = _pcg(state)
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= seg_end: break
            sig = _interp(sigma_t, t_abs, x_min, dx, N)
            if _pcg(state) < sig / sigma_bar:
                seg_scat = True
                break
        t_clamped = min(t_abs - seg_start, seg_len)

        if seg_scat:
            h_t = _interp(albedo, t_abs, x_min, dx, N) * L_next
        else:
            h_t = L_next

        s1 = seg_start
        s2 = seg_start
        if mode == 0:    # SM
            s = _pcg(state) * t_clamped
            s1 = seg_start + s
            s2 = s1
        elif mode == 1:  # DRT
            s1 = seg_start + _pcg(state) * t_clamped
            s2 = seg_start + _pcg(state) * t_clamped
        elif mode == 2:  # FF (rejection ∝ σ_t)
            s1 = seg_start + 0.5 * t_clamped
            for k in range(64):
                ss = seg_start + _pcg(state) * t_clamped
                if _pcg(state) < _interp(sigma_t, ss, x_min, dx, N) / sigma_bar:
                    s1 = ss; break
            s2 = seg_start + 0.5 * t_clamped
            for k in range(64):
                ss = seg_start + _pcg(state) * t_clamped
                if _pcg(state) < _interp(sigma_t, ss, x_min, dx, N) / sigma_bar:
                    s2 = ss; break

        h_s = _interp(albedo, s1, x_min, dx, N) * L_next
        _interp_bwd(out, s1, t_clamped * h_s,  x_min, dx, N)
        _interp_bwd(out, s2, t_clamped * (-h_t), x_min, dx, N)


@njit(cache=True, fastmath=True)
def _paper_drt(sigma_t, albedo, sigma_bar, state, out,
               x_min, x_max, dx, N, max_bounces, L_light):
    """Paper-DRT (Nimier-David et al. 2022, List 1) via weighted reservoir
    sampling along the ray. WRS gives a single scat-sample y with PDF
    ∝ T(y); contribution simplifies to (∫T)·α(y)·L_s(y)·∂σ_t.
    Trans term stays as Eq.5 per segment."""
    # ---- forward path (delta tracking) ------------------------------
    positions = np.empty(max_bounces + 1, dtype=np.float64)
    positions[0] = x_min
    n_b = 0
    x = x_min
    for b in range(max_bounces):
        t_abs = x
        scattered = False
        for step in range(4096):
            u = _pcg(state)
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= x_max: break
            sig = _interp(sigma_t, t_abs, x_min, dx, N)
            if _pcg(state) < sig / sigma_bar:
                scattered = True
                break
        if not scattered: break
        n_b += 1
        positions[n_b] = t_abs
        x = t_abs

    L = np.empty(n_b + 1, dtype=np.float64)
    L[n_b] = L_light
    for j in range(n_b - 1, -1, -1):
        L[j] = _interp(albedo, positions[j + 1], x_min, dx, N) * L[j + 1]

    # ---- WRS ∝ T(t) along the ray ----------------------------------
    t_walk = x_min
    tau    = 0.0
    w_sum  = 0.0
    y_res  = x_min
    for stepc in range(4096):
        if t_walk >= x_max: break
        u = _pcg(state)
        if u < 1e-10: u = 1e-10
        dt = -math.log(u) / sigma_bar
        t_next = t_walk + dt
        if t_next > x_max:
            dt = x_max - t_walk
            t_next = x_max
        t_mid = t_walk + 0.5 * dt
        sig_mid = _interp(sigma_t, t_mid, x_min, dx, N)
        T_mid = math.exp(-(tau + 0.5 * sig_mid * dt))
        w_i = T_mid * dt
        w_sum += w_i
        if _pcg(state) * w_sum < w_i:
            y_res = t_walk + _pcg(state) * dt
        tau += sig_mid * dt
        t_walk = t_next

    # scat contribution = w_sum * α(y) * L_s(y)
    alpha_y = _interp(albedo, y_res, x_min, dx, N)
    # locate segment containing y_res
    seg_idx = n_b
    for j in range(n_b):
        if y_res < positions[j + 1]:
            seg_idx = j
            break
    L_next_scat = L[seg_idx + 1] if seg_idx < n_b else L_light
    _interp_bwd(out, y_res, w_sum * alpha_y * L_next_scat, x_min, dx, N)

    # ---- trans term per segment (Eq.5) -----------------------------
    for j in range(n_b + 1):
        seg_start = positions[j]
        seg_end = positions[j + 1] if j < n_b else x_max
        seg_len = seg_end - seg_start
        if seg_len <= 0: continue
        L_next = L[j + 1] if j < n_b else L_light

        t_abs = seg_start
        seg_scat = False
        for step in range(4096):
            u = _pcg(state)
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= seg_end: break
            sig = _interp(sigma_t, t_abs, x_min, dx, N)
            if _pcg(state) < sig / sigma_bar:
                seg_scat = True
                break
        t_clamped = min(t_abs - seg_start, seg_len)
        h_t = _interp(albedo, t_abs, x_min, dx, N) * L_next if seg_scat else L_next
        s2 = seg_start + _pcg(state) * t_clamped
        _interp_bwd(out, s2, t_clamped * (-h_t), x_min, dx, N)


@njit(cache=True, fastmath=True)
def _grad_one_term(sigma_t, albedo, sigma_bar, state, term, out,
                   x_min, x_max, dx, N, max_bounces, L_light):
    """One-path estimator that accumulates only the scat (term=0) or
    trans (term=1) term — used for the two-path NM estimator."""
    positions = np.empty(max_bounces + 1, dtype=np.float64)
    positions[0] = x_min
    n_b = 0
    x = x_min
    for b in range(max_bounces):
        t_abs = x
        scattered = False
        for step in range(4096):
            u = _pcg(state)
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= x_max: break
            sig = _interp(sigma_t, t_abs, x_min, dx, N)
            if _pcg(state) < sig / sigma_bar:
                scattered = True
                break
        if not scattered: break
        n_b += 1
        positions[n_b] = t_abs
        x = t_abs

    L = np.empty(n_b + 1, dtype=np.float64)
    L[n_b] = L_light
    for j in range(n_b - 1, -1, -1):
        L[j] = _interp(albedo, positions[j + 1], x_min, dx, N) * L[j + 1]

    for j in range(n_b + 1):
        seg_start = positions[j]
        seg_end = positions[j + 1] if j < n_b else x_max
        seg_len = seg_end - seg_start
        if seg_len <= 0: continue
        L_next = L[j + 1] if j < n_b else L_light

        t_abs = seg_start
        seg_scat = False
        for step in range(4096):
            u = _pcg(state)
            if u < 1e-10: u = 1e-10
            t_abs += -math.log(u) / sigma_bar
            if t_abs >= seg_end: break
            sig = _interp(sigma_t, t_abs, x_min, dx, N)
            if _pcg(state) < sig / sigma_bar:
                seg_scat = True
                break
        t_clamped = min(t_abs - seg_start, seg_len)
        s = seg_start + _pcg(state) * t_clamped
        if term == 0:    # scattering term
            h_s = _interp(albedo, s, x_min, dx, N) * L_next
            _interp_bwd(out, s, t_clamped * h_s, x_min, dx, N)
        else:            # transmittance term
            h_t = _interp(albedo, t_abs, x_min, dx, N) * L_next if seg_scat else L_next
            _interp_bwd(out, s, t_clamped * (-h_t), x_min, dx, N)


@njit(cache=True, fastmath=True)
def _variance_pass(sigma_t, albedo, sigma_bar, mode, R, SPP, seed_base,
                   x_min, x_max, dx, N, max_bounces, L_light):
    estimates = np.zeros((R, N), dtype=np.float64)
    spp_buf   = np.empty(N, dtype=np.float64)
    one_buf   = np.empty(N, dtype=np.float64)
    state = np.empty(1, dtype=np.uint64)
    for r in range(R):
        seed = (seed_base + np.uint64(r) * np.uint64(7919)) & np.uint64(0xFFFFFFFF)
        if seed == 0: seed = np.uint64(1)
        state[0] = seed
        spp_buf[:] = 0.0
        for s in range(SPP):
            one_buf[:] = 0.0
            if mode == MODE_NM:
                _grad_one_term(sigma_t, albedo, sigma_bar, state, 0, one_buf,
                               x_min, x_max, dx, N, max_bounces, L_light)
                _grad_one_term(sigma_t, albedo, sigma_bar, state, 1, one_buf,
                               x_min, x_max, dx, N, max_bounces, L_light)
            elif mode == MODE_DRT:
                _paper_drt(sigma_t, albedo, sigma_bar, state, one_buf,
                           x_min, x_max, dx, N, max_bounces, L_light)
            else:
                _grad_one(sigma_t, albedo, sigma_bar, state, mode, one_buf,
                          x_min, x_max, dx, N, max_bounces, L_light)
            for k in range(N):
                spp_buf[k] += one_buf[k]
        for k in range(N):
            estimates[r, k] = spp_buf[k] / SPP

    mean = np.zeros(N, dtype=np.float64)
    for r in range(R):
        for k in range(N):
            mean[k] += estimates[r, k]
    for k in range(N):
        mean[k] /= R
    var = np.zeros(N, dtype=np.float64)
    for r in range(R):
        for k in range(N):
            d = estimates[r, k] - mean[k]
            var[k] += d * d
    for k in range(N):
        var[k] /= R
    return var


# ---------------- ground truth via finite differences ------------------------
@njit(cache=True, fastmath=True)
def _ray_march(sigma_t, albedo, jitter, M, x_min, x_max, dx, N, L_light):
    L_acc = 0.0
    n_jitters = jitter.shape[0]  # = trials * M
    M_steps = M
    dt = (x_max - x_min) / M
    trials = n_jitters // M
    for t in range(trials):
        tau_sum = 0.0
        emit = 0.0
        for i in range(M):
            ti = (i + jitter[t * M + i]) / M
            si = _interp(sigma_t, ti, x_min, dx, N)
            ai = _interp(albedo,  ti, x_min, dx, N)
            T = math.exp(-tau_sum)
            emit += T * si * ai * L_light * dt
            tau_sum += si * dt
        L_acc += emit + math.exp(-tau_sum) * L_light
    return L_acc / trials

def fd_gradient(sigma_t, albedo):
    rng = np.random.default_rng(12345)
    trials = 8
    jitter = rng.random(trials * M_GT).astype(np.float64)
    L0 = _ray_march(sigma_t, albedo, jitter, M_GT, X_MIN, X_MAX, DX, N, L_LIGHT)
    grad = np.zeros(N, dtype=np.float64)
    for k in range(N):
        sp = sigma_t.copy(); sp[k] += EPSILON
        sm = sigma_t.copy(); sm[k] -= EPSILON
        Lp = _ray_march(sp, albedo, jitter, M_GT, X_MIN, X_MAX, DX, N, L_LIGHT)
        Lm = _ray_march(sm, albedo, jitter, M_GT, X_MIN, X_MAX, DX, N, L_LIGHT)
        grad[k] = (Lp - Lm) / (2.0 * EPSILON)
    return grad


# ---------------- random scene generator -------------------------------------
def random_curve(seed, n=N):
    rng = np.random.default_rng(seed)
    nB = int(rng.integers(3, 6))
    mus  = rng.uniform(0.1, 0.9, nB)
    sigs = rng.uniform(0.05, 0.15, nB)
    amps = rng.uniform(0.2, 1.0, nB) * rng.choice([-1, 1], nB)
    xs = np.linspace(0, 1, n)
    y = np.zeros(n)
    for mu, sig, amp in zip(mus, sigs, amps):
        y += amp * np.exp(-0.5 * ((xs - mu) / sig) ** 2)
    y = (y - y.min()) / max(y.max() - y.min(), 1e-9)
    return y.astype(np.float64)

def make_case(seed):
    sigma_t = random_curve(seed) * 4.5 + 0.3
    albedo  = random_curve(seed + 1000) * 0.75 + 0.15
    return sigma_t, albedo


# ---------------- main -------------------------------------------------------
def main():
    print(f"N={N}  SPP={SPP}  R={R}  N_CASES={N_CASES}")
    out_cases = []
    t_total = time.time()
    for c in range(N_CASES):
        seed = 4242 + c * 23
        print(f"\n=== case {c}  (seed {seed}) ===")
        sigma_t, albedo = make_case(seed)
        sigma_bar = float(sigma_t.max()) * 1.01

        case = {"density": sigma_t.tolist(), "albedo": albedo.tolist()}
        print("  GT ...", end="", flush=True)
        t0 = time.time()
        gt = fd_gradient(sigma_t, albedo)
        print(f" {time.time()-t0:.1f}s, ‖gt‖∞ = {np.abs(gt).max():.4f}")
        case["gt"] = gt.tolist()

        for mode_name, mode_id in (("sm", MODE_SM), ("drt", MODE_DRT),
                                    ("nm", MODE_NM), ("ff", MODE_FF)):
            t0 = time.time()
            seed_base = np.uint64(10000 * (c + 1) + (hash(mode_name) & 0xFFFFFFFF))
            var = _variance_pass(sigma_t, albedo, sigma_bar, mode_id,
                                 R, SPP, seed_base,
                                 X_MIN, X_MAX, DX, N, MAX_BOUNCES, L_LIGHT)
            case[f"var_{mode_name}"] = var.tolist()
            print(f"  {mode_name.upper():>3} {time.time()-t0:6.1f}s  "
                  f"mean var = {var.mean():.3e}")

        case["vmax"] = max(max(case[f"var_{m}"]) for m in ("sm", "drt", "nm", "ff"))
        out_cases.append(case)

    out = {"N": N, "x_min": X_MIN, "x_max": X_MAX,
           "spp": SPP, "reps": R, "cases": out_cases}
    dest = Path(__file__).with_name("variance_data.json")
    dest.write_text(json.dumps(out))
    print(f"\nTOTAL {time.time()-t_total:.1f}s  →  {dest}")

if __name__ == "__main__":
    main()
