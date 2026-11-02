// The film's 3D shots: for film time t, the pose of the camera, the closed MacBook, the phone and its screen.
// Units are metres. The Mac sits centred at the origin, closed, its front edge at z = +0.11, the lid's outer shell at
// y = 0.0081; the sticker is on the lid at the front right corner (STICKER). Phone-local: screen up (+Y), top to -Z;
// rot = [pitch, yaw, roll] (pitch < 0 tips the top end down). `touch` puts the phone's top-back point (its NFC antenna)
// on a scene point; `lift` moves it from there.
// Times come from window.TM (sound/mix.py: scene windows, picture cues, the real tap's timeline) and window.VO.
(function () {
  const TM = window.TM, C = TM.cues, REC = TM.rec, REC0 = TM.rec0;
  const BG = "radial-gradient(120% 100% at 50% 38%, #fffaf0 0%, #fff7e8 55%, #f6ead4 100%)";
  const STICKER = [0.104, 0.0085, 0.066];

  // ---- helpers
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const io = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);   // cubic in-out
  const oc = (x) => 1 - Math.pow(1 - x, 3);                                         // cubic out
  const mix = (a, b, k) => (Array.isArray(a) ? a.map((v, i) => v + (b[i] - v) * k) : a + (b - a) * k);
  const key = (t, ks, ease = io) => {
    if (t <= ks[0][0]) return ks[0][1];
    for (let i = 1; i < ks.length; i++) if (t <= ks[i][0]) {
      const [t0, a] = ks[i - 1], [t1, b] = ks[i];
      return mix(a, b, ease((t - t0) / (t1 - t0)));
    }
    return ks[ks.length - 1][1];
  };
  // orbit the camera around a target: azimuth (0 = straight in front, + = to the right), elevation, radius
  const orbit = (target, az, el, r) => [target[0] + r * Math.sin(az) * Math.cos(el), target[1] + r * Math.sin(el), target[2] + r * Math.cos(az) * Math.cos(el)];
  // the same, panned: the camera and its target slide sideways so the subject sits `pan` of the frame's width to the right
  // of centre (leaving the left of the frame to the scene's text); the perspective is unchanged
  const view = (target, az, el, r, pan = 0, fov = 30) => {
    const k = pan * 2 * r * Math.tan(fov * Math.PI / 360) * 16 / 9;
    const tg = [target[0] - Math.cos(az) * k, target[1], target[2] + Math.sin(az) * k];
    return { pos: orbit(tg, az, el, r), target: tg, fov };
  };
  // the phone's screen: film time -> frame of the recording (30 fps), t0 = the film time of recording time `r0`
  const frameAt = (t, t0, r0 = 0) => Math.max(0, Math.min(659, Math.round((r0 + (t - t0)) * 30)));
  const pulseAt = (t, tc) => (t >= tc && t < tc + 1.3 ? (t - tc) / 1.1 : null);

  // the tap: in from the right of frame, low (as a hand brings it), top end first, onto the sticker; held there;
  // then lifted towards the camera. `from` is the start offset from the touch point, `dur` the flight's length.
  const TOUCH_ROT = [-0.36, 0.62, 0.0];
  function tapPhone(t, tc, held, heldRot, heldLift, from, dur) {
    const kin = clamp((t - (tc - dur)) / dur), kup = clamp((t - (tc + 0.55)) / 0.9);
    let lift = mix(from, [0, 0, 0], oc(kin));
    let rot = mix([-0.20, 1.10, 0.10], TOUCH_ROT, oc(kin));
    if (held) { lift = mix(lift, heldLift, io(kup)); rot = mix(rot, heldRot, io(kup)); }
    return { touch: STICKER, lift, rot };
  }

  // ---------------------------------------------------------------- s1 hook: the closed Mac, the phone comes down
  function s1(t) {
    const t0 = TM.s1[0], tc = C.h_contact;
    const target = key(t, [[t0, [0.07, 0.01, 0.04]], [tc, [0.10, 0.02, 0.075]], [tc + 1.6, [0.14, 0.06, 0.12]],
                            [C.h_rise, [0.14, 0.06, 0.12]], [C.h_rise + 1.8, [0.06, 0.03, 0.04]]]);
    const az = key(t, [[t0, 0.80], [tc, 0.66], [tc + 1.6, 0.50], [C.h_rise, 0.47], [C.h_rise + 1.8, 0.42], [TM.s1[1], 0.36]]);
    const el = key(t, [[t0, 0.40], [tc, 0.62], [tc + 1.6, 0.80], [C.h_rise, 0.82], [C.h_rise + 1.8, 0.50]]);
    const r = key(t, [[t0, 0.50], [tc, 0.40], [tc + 1.6, 0.40], [C.h_rise, 0.39], [C.h_rise + 1.8, 0.78], [TM.s1[1], 0.82]]);
    return {
      bg: BG, shadow: 0.16, cam: view(target, az, el, r, key(t, [[t0, 0.16], [tc, 0.17], [C.h_rise + 1.8, 0.19]])),
      phone: tapPhone(t, tc, true, [-0.12, 0.42, 0.10], [0.03, 0.07, 0.05], [0.20, 0.07, -0.12], 1.9),
      pscreen: t < tc ? 0 : frameAt(t, tc, REC.tap), pulse: pulseAt(t, tc),
    };
  }

  // ---------------------------------------------------------------- s3 the real tap, in real time
  // Recording time r shows at film time REC0 + r. The tap lands at REC0 + REC.tap; the screen plays on unbroken.
  function s3(t) {
    const t0 = TM.s3[0], tc = C.t_contact, mv = C.t_to_mac;
    // from the front left; in onto the phone while it listens; out to a wide (the Mac's panel above it) as it stops
    const target = key(t, [[t0, [0.02, 0.02, 0.02]], [tc - 0.2, [0.08, 0.02, 0.06]], [tc + 1.4, [0.14, 0.065, 0.11]],
                            [mv, [0.14, 0.065, 0.11]], [mv + 1.1, [0.05, 0.085, 0.02]], [TM.s3[1], [0.03, 0.085, 0.02]]]);
    const az = key(t, [[t0, -0.30], [tc - 0.2, 0.22], [tc + 1.4, 0.36], [mv, 0.40], [mv + 1.1, 0.30], [TM.s3[1], 0.12]]);
    const el = key(t, [[t0, 0.42], [tc - 0.2, 0.60], [tc + 1.4, 0.82], [mv, 0.82], [mv + 1.1, 0.40], [TM.s3[1], 0.36]]);
    const r = key(t, [[t0, 0.82], [tc - 0.2, 0.62], [tc + 1.4, 0.40], [mv, 0.39], [mv + 1.1, 0.98], [TM.s3[1], 1.04]]);
    return {
      bg: BG, shadow: 0.16, cam: view(target, az, el, r, key(t, [[t0, 0.14], [tc + 1.4, 0.16], [mv, 0.16], [mv + 1.1, 0.24], [TM.s3[1], 0.17]])),
      phone: tapPhone(t, tc, true, [-0.10, 0.30, 0.12], [0.04, 0.08, 0.06], [0.42, 0.07, 0.12], 1.5),
      pscreen: frameAt(t, REC0), pulse: pulseAt(t, tc),
    };
  }

  // ---------------------------------------------------------------- s6 proof: the Mac shut, the phone beside it
  function s6(t) {
    const u = (t - TM.s6[0]) / (TM.s6[1] - TM.s6[0]);
    const target = [0.04, 0.0, 0.04];
    return {
      bg: BG, shadow: 0.15, cam: view(target, 0.40 - 0.12 * u, 0.62 - 0.06 * u, 1.10 - 0.05 * u, 0.205),
      phone: { pos: [0.215, -0.0008, 0.085], rot: [0.0, 0.35, 0] }, pscreen: 300,   // flat on the desk, on its camera bump
    };
  }

  // ---------------------------------------------------------------- s7 end card: on the right of the lockup
  function s7(t) {
    const u = t - TM.s7[0];
    const k = oc(clamp(u / 1.4));
    const target = [0.04, 0.01, 0.04];
    return {
      bg: "#fff7e8", shadow: 0.14, cam: view(target, 0.30 - 0.010 * u + 0.12 * (1 - k), 0.46, 1.13 + 0.08 * (1 - k), 0.21),
      phone: { pos: [0.215, -0.0008, 0.095], rot: [0.0, 0.42, 0] }, pscreen: 300,
    };
  }

  const SHOTS = { s1, s3, s6, s7 };
  // which 3D shot holds film time t (later shots win where windows overlap: each starts on its bar line)
  window.SHOT_POSE = (t) => {
    let pick = null;
    for (const s of TM.shots3d) if (t >= TM[s][0] - 1e-6 && t < TM[s][1] + 1e-6) pick = s;
    const p = pick ? SHOTS[pick](t) : { bg: BG, cam: { pos: [0, 0.4, 0.9], target: [0, 0, 0] }, phone: { visible: false } };
    p.shot = pick;
    return p;
  };
  window.SHOT_FNS = SHOTS;
})();
