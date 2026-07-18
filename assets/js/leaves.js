/* Falling-leaves ambient background for the home page.
 *
 * Design notes:
 * - Everything lives on one fixed, pointer-events:none canvas behind the
 *   content (z-index:-1), so text/cards are never obscured.
 * - Leaves are pre-rendered to small offscreen sprites (3 shapes, soft
 *   autumn hues jittered in HSL to sit well on the warm-white page).
 * - Depth of field: each leaf gets a depth z; far leaves are smaller,
 *   fainter and pre-blurred, near ones slightly soft — the mid plane is
 *   in focus. A few leaves spawn far away and slowly drift closer.
 * - Wind is a sum of slow sines of time and height, so the motion never
 *   repeats or jumps — the "loop" is seamless by construction.
 * - Extras: warm corner glow + faint sun beams + drifting bokeh motes.
 * - Respects prefers-reduced-motion (renders nothing at all).
 */
(function () {
  'use strict';

  if (window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var canvas = document.createElement('canvas');
  canvas.id = 'leaves-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.appendChild(canvas);
  var ctx = canvas.getContext('2d');

  var DPR = Math.min(window.devicePixelRatio || 1, 2);
  var W = 0, H = 0;
  var leaves = [], motes = [];
  var rnd = Math.random;

  /* ---- sprite factory --------------------------------------------------- */

  function leafPath(c, type, s) {
    var i, a, r, na, x, y, nx, ny;
    c.beginPath();
    if (type === 0) {
      /* stylized 5-lobe maple */
      var tips = [-2.2, -1.1, 0, 1.1, 2.2];
      var rad  = [0.55, 0.85, 1.0, 0.85, 0.55];
      c.moveTo(0, 0.6 * s);
      for (i = 0; i < 5; i++) {
        a = tips[i]; r = rad[i] * s;
        na = i === 0 ? -2.65 : (tips[i - 1] + a) / 2;
        nx = Math.sin(na) * 0.42 * s; ny = -Math.cos(na) * 0.42 * s;
        x = Math.sin(a) * r;          y = -Math.cos(a) * r;
        c.quadraticCurveTo(nx, ny, x, y);
      }
      c.quadraticCurveTo(Math.sin(2.65) * 0.42 * s, -Math.cos(2.65) * 0.42 * s,
                         0, 0.6 * s);
    } else if (type === 1) {
      /* pointed oval (beech-like) */
      c.moveTo(0, -s);
      c.bezierCurveTo( 0.58 * s, -0.45 * s,  0.5 * s, 0.5 * s, 0, s);
      c.bezierCurveTo(-0.5 * s,   0.5 * s, -0.58 * s, -0.45 * s, 0, -s);
    } else {
      /* small rounded leaf */
      c.moveTo(0, -0.9 * s);
      c.bezierCurveTo( 0.75 * s, -0.7 * s,  0.7 * s, 0.55 * s, 0, 0.9 * s);
      c.bezierCurveTo(-0.7 * s,   0.55 * s, -0.75 * s, -0.7 * s, 0, -0.9 * s);
    }
    c.closePath();
  }

  function makeSprite(size, type, hue, sat, lit, blur) {
    var S = Math.ceil(size * 3 + blur * 6);
    var c = document.createElement('canvas');
    c.width = c.height = Math.ceil(S * DPR);
    var g = c.getContext('2d');
    g.scale(DPR, DPR);
    g.translate(S / 2, S / 2);
    if (blur > 0.05 && 'filter' in g) g.filter = 'blur(' + blur.toFixed(1) + 'px)';
    g.scale(0.85 + rnd() * 0.3, 1);            /* aspect jitter */

    g.fillStyle = 'hsl(' + hue + ',' + sat + '%,' + lit + '%)';
    leafPath(g, type, size);
    g.fill();

    /* stem + center vein, slightly darker */
    g.strokeStyle = 'hsla(' + hue + ',' + (sat + 6) + '%,' + (lit - 17) + '%,0.5)';
    g.lineWidth = size * 0.055 + 0.3;
    g.beginPath();
    g.moveTo(0, size * (type === 0 ? 0.95 : 1.15));
    g.lineTo(0, -size * 0.55);
    g.stroke();

    return { img: c, S: S };
  }

  function moteSprite() {
    var S = 64;
    var c = document.createElement('canvas');
    c.width = c.height = S;
    var g = c.getContext('2d');
    var grad = g.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    grad.addColorStop(0,   'rgba(255,232,190,0.9)');
    grad.addColorStop(0.5, 'rgba(255,222,170,0.28)');
    grad.addColorStop(1,   'rgba(255,222,170,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, S, S);
    return c;
  }
  var MOTE = moteSprite();

  /* ---- particles --------------------------------------------------------- */

  function newLeaf(initial) {
    var approaching = rnd() < 0.18;
    var z = approaching ? 1.7 + rnd() * 0.5 : 0.7 + rnd() * 1.1;

    /* soft muted autumn reds; a third of the leaves lean deeper crimson */
    var deep = rnd() < 0.33;
    var hue = deep ? 2 + rnd() * 10 : 10 + rnd() * 22;
    var sat = 40 + rnd() * 18;
    var lit = deep ? 48 + rnd() * 9 : 54 + rnd() * 13;

    var size = 10 + rnd() * 9;
    var type = rnd() < 0.45 ? 0 : (rnd() < 0.65 ? 1 : 2);

    /* bake depth-of-field blur into the sprite (mid plane ~1.0 is sharp) */
    var blur = z < 0.85 ? 0.6 : (z > 1.3 ? (z - 1.3) * 1.8 + 0.8 : 0);
    var sp = makeSprite(size, type, Math.round(hue), Math.round(sat),
                        Math.round(lit), blur);

    var fromSide = !initial && rnd() < 0.25;
    return {
      sprite: sp,
      x: fromSide ? -40 : rnd() * W,
      y: initial ? rnd() * H : (fromSide ? rnd() * H * 0.7 : -40),
      z: z,
      dz: approaching ? -(0.045 + rnd() * 0.05) : 0,
      fall: 20 + rnd() * 15,                    /* px/s at z = 1 */
      swayA: 8 + rnd() * 12,
      swayF: 0.4 + rnd() * 0.5,
      swayP: rnd() * 6.283,
      angle: rnd() * 6.283,
      rotV: (rnd() - 0.5) * 1.2,
      flip: rnd() * 6.283,
      flipV: 0.5 + rnd() * 1.1,
      alpha: 0.55 + rnd() * 0.3,
      ramp: initial ? 1 : 0
    };
  }

  function respawn(f) {
    var nf = newLeaf(false);
    nf.sprite = f.sprite;                       /* reuse the baked sprite */
    nf.z = f.dz ? nf.z : f.z;                   /* keep depth ≈ blur match */
    return nf;
  }

  function newMote() {
    return {
      x: rnd() * W, y: rnd() * H,
      r: 8 + rnd() * 26,
      vy: -(2 + rnd() * 5),
      swayP: rnd() * 6.283,
      a: 0.05 + rnd() * 0.09,
      tw: 0.3 + rnd() * 0.5
    };
  }

  /* ---- environment ------------------------------------------------------- */

  function windX(t, y) {
    return 6 + 10 * Math.sin(t * 0.11)
             +  5 * Math.sin(t * 0.23 + y * 0.002 + 1.3)
             +  3 * Math.sin(t * 0.47);
  }

  function drawLight(t) {
    /* warm glow bleeding in from the upper left */
    var breathe = 0.05 + 0.02 * Math.sin(t * 0.06);
    var g = ctx.createRadialGradient(W * 0.12, -H * 0.05, 0,
                                     W * 0.12, -H * 0.05, Math.max(W, H) * 0.75);
    g.addColorStop(0, 'rgba(255,215,150,' + (breathe + 0.05).toFixed(3) + ')');
    g.addColorStop(1, 'rgba(255,215,150,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    /* three faint sun beams slanting through */
    for (var i = 0; i < 3; i++) {
      var a = 0.028 * (1 + 0.5 * Math.sin(t * 0.09 + i * 2.1));
      if (a <= 0.004) continue;
      ctx.save();
      ctx.translate(W * (0.06 + i * 0.17), -80);
      ctx.rotate(0.48 - i * 0.05 + 0.015 * Math.sin(t * 0.07 + i));
      var w = 70 + i * 45;
      var lg = ctx.createLinearGradient(-w / 2, 0, w / 2, 0);
      lg.addColorStop(0,   'rgba(255,225,170,0)');
      lg.addColorStop(0.5, 'rgba(255,225,170,' + a.toFixed(3) + ')');
      lg.addColorStop(1,   'rgba(255,225,170,0)');
      ctx.fillStyle = lg;
      ctx.fillRect(-w / 2, 0, w, H * 1.7);
      ctx.restore();
    }
  }

  /* ---- main loop ---------------------------------------------------------- */

  function step(t, dt) {
    ctx.clearRect(0, 0, W, H);
    drawLight(t);

    leaves.sort(function (a, b) { return b.z - a.z; });   /* far first */

    for (var i = 0; i < leaves.length; i++) {
      var f = leaves[i];
      f.ramp = Math.min(1, f.ramp + dt / 1.6);
      if (f.dz) { f.z += f.dz * dt; if (f.z < 0.75) f.dz = 0; }
      var scale = 1 / f.z;

      f.x += (windX(t, f.y) * scale +
              Math.sin(t * f.swayF + f.swayP) * f.swayA) * dt;
      f.y += f.fall * scale * dt;
      f.angle += f.rotV * dt;
      f.flip  += f.flipV * dt;

      if (f.y > H + 50 || f.x < -70 || f.x > W + 70) {
        leaves[i] = respawn(f);
        continue;
      }

      var depthA = Math.min(0.9, Math.max(0.35, 1.25 - 0.4 * f.z));
      ctx.globalAlpha = f.alpha * depthA * f.ramp;
      ctx.save();
      ctx.translate(f.x, f.y);
      ctx.rotate(f.angle);
      /* tumble: squash on one axis to fake a 3D turn */
      ctx.scale(scale * (0.3 + 0.7 * Math.abs(Math.cos(f.flip))), scale);
      var S = f.sprite.S;
      ctx.drawImage(f.sprite.img, -S / 2, -S / 2, S, S);
      ctx.restore();
    }

    /* bokeh motes drifting up, softly twinkling */
    for (var j = 0; j < motes.length; j++) {
      var m = motes[j];
      m.y += m.vy * dt;
      m.x += Math.sin(t * 0.3 + m.swayP) * 4 * dt;
      if (m.y < -m.r * 2) { motes[j] = newMote(); motes[j].y = H + m.r; continue; }
      ctx.globalAlpha = m.a * (0.6 + 0.4 * Math.sin(t * m.tw + m.swayP));
      ctx.drawImage(MOTE, m.x - m.r, m.y - m.r, m.r * 2, m.r * 2);
    }
    ctx.globalAlpha = 1;
  }

  var last = performance.now();
  function frame(now) {
    var dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    step(now / 1000, dt);
    requestAnimationFrame(frame);
  }

  /* ---- setup / housekeeping ----------------------------------------------- */

  function resize() {
    W = window.innerWidth;
    H = window.innerHeight;
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.ceil(W * DPR);
    canvas.height = Math.ceil(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

    var want = Math.round(Math.min(32, Math.max(14, W * H / 42000)));
    while (leaves.length < want) leaves.push(newLeaf(true));
    if (leaves.length > want) leaves.length = want;

    var wantM = Math.round(Math.min(10, Math.max(4, W * H / 180000)));
    while (motes.length < wantM) motes.push(newMote());
    if (motes.length > wantM) motes.length = wantM;
  }

  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', function () {
    last = performance.now();                   /* avoid a dt jump on return */
  });

  resize();
  requestAnimationFrame(frame);
})();
