/* Dedicated Web Worker: streams running per-cell variance estimates for the
 * four 1-D extinction-gradient estimators (SM, DRT, NM, FF), one rep at a
 * time, so the page can paint colour strips as R grows. */

const X_MIN = 0.0;
const X_MAX = 1.0;
const MAX_BOUNCES = 24;
const L_LIGHT = 5.0;

let N = 256;     // grid resolution (rewritten per job)
let DX = (X_MAX - X_MIN) / (N - 1);

/* ---- PCG-flavoured deterministic uint32 RNG ---------------------------- */
function makeRng(seed) {
  let s = (seed >>> 0) || 1;
  return function () {
    s = ((s * 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/* ---- 1-D piecewise-linear grid interpolation (+ backward) ------------- */
function interp(grid, x) {
  const u = (x - X_MIN) / DX;
  let i = u | 0;
  if (i < 0) i = 0;
  if (i > N - 2) i = N - 2;
  let f = u - i;
  if (f < 0) f = 0;
  if (f > 1) f = 1;
  return (1 - f) * grid[i] + f * grid[i + 1];
}
function interpBwd(out, x, val) {
  const u = (x - X_MIN) / DX;
  let i = u | 0;
  if (i < 0) i = 0;
  if (i > N - 2) i = N - 2;
  let f = u - i;
  if (f < 0) f = 0;
  if (f > 1) f = 1;
  out[i]     += (1 - f) * val;
  out[i + 1] += f * val;
}

/* ---- Forward path via delta tracking ----------------------------------- */
function buildPath(sigmaT, sigmaBar, rng) {
  const positions = [X_MIN];
  let x = X_MIN;
  for (let b = 0; b < MAX_BOUNCES; b++) {
    let tAbs = x;
    let scattered = false;
    for (let step = 0; step < 4096; step++) {
      let u = rng();
      if (u < 1e-10) u = 1e-10;
      tAbs += -Math.log(u) / sigmaBar;
      if (tAbs >= X_MAX) break;
      if (rng() < interp(sigmaT, tAbs) / sigmaBar) { scattered = true; break; }
    }
    if (!scattered) break;
    positions.push(tAbs);
    x = tAbs;
  }
  return positions;
}
function backwardRadiance(positions, albedo) {
  const nb = positions.length - 1;
  const L = new Float64Array(nb + 1);
  L[nb] = L_LIGHT;
  for (let j = nb - 1; j >= 0; j--) {
    L[j] = interp(albedo, positions[j + 1]) * L[j + 1];
  }
  return L;
}

/* ---- SM / DRT / FF: one shared path, per-segment Eq.4+Eq.5 ------------- */
function gradEstimate(sigmaT, albedo, sigmaBar, rng, mode) {
  const grad = new Float64Array(N);
  const positions = buildPath(sigmaT, sigmaBar, rng);
  const nb = positions.length - 1;
  const L = backwardRadiance(positions, albedo);

  for (let j = 0; j <= nb; j++) {
    const segStart = positions[j];
    const segEnd   = j < nb ? positions[j + 1] : X_MAX;
    const segLen   = segEnd - segStart;
    if (segLen <= 0) continue;
    const Lnext = j < nb ? L[j + 1] : L_LIGHT;

    // delta-track t inside segment
    let tAbs = segStart;
    let segScat = false;
    for (let step = 0; step < 4096; step++) {
      let u = rng();
      if (u < 1e-10) u = 1e-10;
      tAbs += -Math.log(u) / sigmaBar;
      if (tAbs >= segEnd) break;
      if (rng() < interp(sigmaT, tAbs) / sigmaBar) { segScat = true; break; }
    }
    const tClamped = Math.min(tAbs - segStart, segLen);
    const ht = segScat ? interp(albedo, tAbs) * Lnext : Lnext;

    let s1, s2;
    if (mode === 'sm') {
      const s = rng() * tClamped;
      s1 = segStart + s; s2 = s1;
    } else if (mode === 'drt') {
      s1 = segStart + rng() * tClamped;
      s2 = segStart + rng() * tClamped;
    } else if (mode === 'ff') {
      const hi = segStart + tClamped;
      function ffOne() {
        if (hi <= segStart) return segStart;
        for (let k = 0; k < 64; k++) {
          const ss = segStart + rng() * (hi - segStart);
          if (rng() < interp(sigmaT, ss) / sigmaBar) return ss;
        }
        return segStart + 0.5 * (hi - segStart);
      }
      s1 = ffOne();
      s2 = ffOne();
    }

    const hs = interp(albedo, s1) * Lnext;
    interpBwd(grad, s1, tClamped * hs);
    interpBwd(grad, s2, tClamped * (-ht));
  }
  return grad;
}

/* ---- NM (Unlock SM, two-path) ----------------------------------------- */
function twoPathEstimate(sigmaT, albedo, sigmaBar, rng) {
  const grad = new Float64Array(N);
  for (const term of ['scat', 'trans']) {
    const positions = buildPath(sigmaT, sigmaBar, rng);
    const nb = positions.length - 1;
    const L = backwardRadiance(positions, albedo);
    for (let j = 0; j <= nb; j++) {
      const segStart = positions[j];
      const segEnd   = j < nb ? positions[j + 1] : X_MAX;
      const segLen   = segEnd - segStart;
      if (segLen <= 0) continue;
      const Lnext = j < nb ? L[j + 1] : L_LIGHT;

      let tAbs = segStart;
      let segScat = false;
      for (let step = 0; step < 4096; step++) {
        let u = rng();
        if (u < 1e-10) u = 1e-10;
        tAbs += -Math.log(u) / sigmaBar;
        if (tAbs >= segEnd) break;
        if (rng() < interp(sigmaT, tAbs) / sigmaBar) { segScat = true; break; }
      }
      const tClamped = Math.min(tAbs - segStart, segLen);
      const s = segStart + rng() * tClamped;
      if (term === 'scat') {
        const hs = interp(albedo, s) * Lnext;
        interpBwd(grad, s, tClamped * hs);
      } else {
        const ht = segScat ? interp(albedo, tAbs) * Lnext : Lnext;
        interpBwd(grad, s, tClamped * (-ht));
      }
    }
  }
  return grad;
}

/* ---- Worker job loop --------------------------------------------------- */
let job = null;
let cancel = false;
self.addEventListener('message', (e) => {
  const m = e.data;
  if (m.type === 'cancel') { cancel = true; return; }
  if (m.type !== 'start')  return;

  cancel = false;
  N = m.N | 0;
  DX = (X_MAX - X_MIN) / (N - 1);

  const sigmaT  = m.sigmaT;
  const albedo  = m.albedo;
  // σ̄ = max σ_t * 1.01
  let smax = 0;
  for (let i = 0; i < N; i++) if (sigmaT[i] > smax) smax = sigmaT[i];
  const sigmaBar = smax * 1.01;

  const modes = m.modes;
  const R   = m.R | 0;
  const SPP = m.SPP | 0;
  const seed0 = (m.seed >>> 0) || 12345;

  // Welford online stats for per-cell variance
  const accs = {};
  for (const mode of modes) {
    accs[mode] = {
      mean: new Float64Array(N),
      m2:   new Float64Array(N),
      vSum: new Float64Array(N),  // for fallback: sum of estimates
      vSum2: new Float64Array(N), // sum of squared estimates
    };
  }

  let r = 0;
  function step() {
    if (cancel) return;
    if (r >= R) {
      self.postMessage({ type: 'done', r });
      return;
    }

    // One rep of each estimator (SPP-averaged)
    for (const mode of modes) {
      const sppAvg = new Float64Array(N);
      const rng = makeRng(seed0 * 1009 + r * 31337 + modeHash(mode));
      for (let s = 0; s < SPP; s++) {
        const g = (mode === 'nm')
                  ? twoPathEstimate(sigmaT, albedo, sigmaBar, rng)
                  : gradEstimate(sigmaT, albedo, sigmaBar, rng, mode);
        for (let i = 0; i < N; i++) sppAvg[i] += g[i];
      }
      for (let i = 0; i < N; i++) sppAvg[i] /= SPP;

      const acc = accs[mode];
      const n = r + 1;
      for (let i = 0; i < N; i++) {
        const x = sppAvg[i];
        const d = x - acc.mean[i];
        acc.mean[i] += d / n;
        acc.m2[i]   += d * (x - acc.mean[i]);
      }
    }

    r++;
    // Post per-cell variance (m2 / max(n-1, 1)) for each mode
    const out = { type: 'progress', r, R };
    for (const mode of modes) {
      const v = new Float32Array(N);
      const denom = Math.max(r - 1, 1);
      for (let i = 0; i < N; i++) v[i] = accs[mode].m2[i] / denom;
      out['var_' + mode] = v;
    }
    self.postMessage(out, modes.map(m => out['var_' + m].buffer));
    // Yield to event loop so cancellations can land
    setTimeout(step, 0);
  }

  step();
});

function modeHash(s) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) h = (h ^ s.charCodeAt(i)) * 16777619 >>> 0;
  return h >>> 0;
}
