"""The nearsay soundtrack: Kokoro af_heart, "Funky Triplets" (Michael Ramir C.) as a quiet bed, soft effects.

    <voice-venv>/bin/python -I sound/mix.py

Inputs: assets/audio/music.wav + sound/grid.json (sound/music.py), narration/chosen/<id>.wav + narration/words.json
(narration/pick.py), sound/sfx-src/mixkit-<id>.mp3 (Mixkit free sound effects).
Outputs:
- assets/audio/mix.wav: the soundtrack, -16 LUFS integrated, true peak under -1.5 dBTP; assets/audio/vo.wav, the voice.
- assets/vo.js (window.VO: each line's words and times), assets/timing.js + sound/timing.json (window.TM: scene
  windows, music points, picture cues and the real tap's timeline). Every scene and stage/render.py read these.

Neither screen recording has usable sound (the phone's track is silent, the Mac's is at -56 LUFS of room noise), so
the soundtrack is built: the voice, the bed and one soft effect per picture event.

Levels (the brief: "the sound should not be too loud, just present, the voice should be clear"):
- Speech at -16 LUFS on the spoken stretches. The bed 9 dB under the speech, ducked 4.5 dB more while she speaks.
- Effects: one per picture event, levelled by measurement 3-6 dB over the bed, at least 3 dB under the voice speaking
  around them, peak one frame after the picture.
"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, soundfile as sf, librosa
from scipy.signal import lfilter

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
G = json.loads((ROOT / "sound/grid.json").read_text())
DROP, RETURN, END_CARD, DUR, BAR = G["drop"], G["return"], G["end_card"], G["duration"], G["bar"]
fb = lambda k: round(k * BAR, 3)

# ---- the real tap (the two screen recordings, 2026-11-02; research/TIMELINE.md has how each time was measured)
# Times on the phone recording (s). The phone's clock turns 2:01 -> 2:02 at 2.268 and the Mac's at 185.235 of its
# recording, so Mac time = phone time + 182.967. The job id (20261102T070205078708) is the receiver's own UTC stamp.
REC = {"tap": 0.87,          # the NFC automation starts: the listening panel slides in
       "listening": 1.13,    # "Now listening..."
       "yo": 3.37,           # "Yo" appears
       "stop": 5.95,         # listening stops after the pause: the panel closes (gone at 6.77)
       "job": 7.347,         # the receiver queues the job (2:02:05.079)
       "phone_ok": 7.50,     # the phone: "Tap Claude  ✓ inbox · starting: Yo"
       "term": 7.873,        # Mac: the Terminal window opens (190.840)
       "banner": 8.163,      # Mac: "nearsay ▸ inbox ▸ Yo" (191.130)
       "claude": 8.693,      # Mac: Claude Code starts, "› Yo" (191.660)
       "rc": 9.233,          # Mac: "/remote-control is active" (192.200)
       "think": 11.383,      # Mac: "Moonwalking... thinking with xhigh effort" (194.350)
       "phone_rc": 12.07,    # the phone: "Remote control enabled: inbox: Yo" (from the Claude app)
       "reply": 12.363,      # Mac: "Hey, what are we working on? I'm in ~/nearsay-inbox." (195.330)
       "phone_ready": 15.30} # the phone: the Claude app's second notification (not shown close: it has dashes)
HOLD = 0.75                  # the recording's first frame is held this long at the start of the scene (nothing moves)

# Each line's start in film seconds (film bar k starts at k * 2.4 s; see sound/music.py).
#  hook   v01-v03 over the keys intro (bars 0-1) and the break (bars 2-3)
#  title  v04 just after the drop (9.6)
#  tap    v05 just before the real tap; v06 after "Yo"; v07 on the Terminal opening; v08 on the Remote Control
#  board  v09-v11; routing v12; proof v13 from just after the drums come back (60.0); end card v14
SLOTS = {"v01": 0.90, "v02": 3.00, "v03": 5.30, "v04": 9.75, "v05": None, "v06": None, "v07": None, "v08": None,
         "v09": 34.40, "v10": 39.85, "v11": 42.85, "v12": 51.00, "v13": 60.40, "v14": 67.60}
# Scene windows on bar lines; a scene runs 0.4 s past the next one's start where it fades out over it.
SCENES = {"s1": [0, fb(4)],                    # hook: phone, sticker, the Mac (3D)       bars 0-3
          "s2": [fb(4), fb(6) + 0.4],          # title on the drop (HTML)                  bars 4-5
          "s3": [fb(6), fb(14) + 0.4],         # the real tap, in real time (3D)           bars 6-13
          "s4": [fb(14), fb(21) + 0.4],        # board: how it works (HTML)                bars 14-20
          "s5": [fb(21), RETURN + 0.4],        # routing by voice (HTML)                   bars 21-24
          "s6": [RETURN, END_CARD + 0.4],      # proof (3D)                                bars 25-27
          "s7": [END_CARD, DUR]}               # end card (3D + lockup)                    bars 28-31
SHOTS_3D = ["s1", "s3", "s6", "s7"]
REC0 = SCENES["s3"][0] + HOLD                  # film time of the phone recording's t = 0
rec = lambda k: round(REC0 + REC[k], 3)
SLOTS["v05"] = round(rec("tap") - 0.30, 3)     # "Tap the sticker..." as the phone touches
SLOTS["v06"] = round(rec("yo") + 0.75, 3)      # "When you stop talking..." once "Yo" is on screen
SLOTS["v07"] = round(rec("term") + 0.05, 3)    # "Claude Code opens in a terminal..." as the window opens
SLOTS["v08"] = None                            # after v07, with a breath (set in main)


def lufs(path):
    out = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = out[out.rfind("Summary:"):]
    i = float(summ.split("I:")[1].split("LUFS")[0])
    tp = float(summ.split("Peak:")[1].split("dBFS")[0]) if "Peak:" in summ else 0.0
    return i, tp


def lufs_of(y, tmp, name):
    y = np.asarray(y)
    sf.write(tmp / f"{name}.wav", (y.T if y.ndim == 2 else y).astype(np.float32), SR)
    return lufs(tmp / f"{name}.wav")[0]


def load(path, sr=SR):
    y, s = sf.read(path, always_2d=True)
    y = y.T.astype(np.float64)
    if s != sr:
        y = np.vstack([librosa.resample(ch, orig_sr=s, target_sr=sr) for ch in y])
    return y



def W(meta, k, w, nth=0):
    """Film time of the nth word of line k that matches w (as the scenes' W() helper)."""
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    c = 0
    for x in meta[k]["words"]:
        if norm(x["w"]) == w or norm(x["w"]).startswith(w):
            if c == nth:
                return x["t0"]
            c += 1
    raise KeyError(f"{k}: no word {w!r}")


def picture_cues(meta):
    """Every timed picture event, in film seconds. Scenes read them from window.TM.cues; the effects below use them."""
    c = {f"rec_{k}": rec(k) for k in REC}
    # hook: the phone comes down onto the sticker, the screen shows the real panel; then up to the Mac's display
    c["h_contact"] = 2.85
    c["h_yo"] = round(c["h_contact"] + (REC["yo"] - REC["tap"]), 3)
    c["h_rise"] = W(meta, "v03", "coding")
    c["riser_to"] = DROP; c["mark_title"] = DROP; c["title_line"] = round(meta["v04"]["end"] + 0.25, 3)
    # the tap: camera moves around the real events
    c["t_contact"] = round(rec("tap") - 0.07, 3)
    c["t_to_mac"] = round(rec("stop") + 0.55, 3)      # the camera makes room for the Mac's panel as listening ends
    c["t_wide"] = round(rec("phone_ready") - 1.05, 3)  # out to the wide before the Claude app's second notification
    c["t_closed"] = W(meta, "v08", "closed")          # "...so the lid can stay closed": the stay-awake note
    c["b_sticker"] = SCENES["s4"][0] + 0.55
    c["b_ssh"] = W(meta, "v09", "ssh"); c["b_key"] = W(meta, "v09", "key"); c["b_one"] = W(meta, "v09", "one")
    c["b_nothing"] = W(meta, "v09", "nothing"); c["b_data"] = W(meta, "v10", "data"); c["b_shell"] = W(meta, "v10", "shell")
    c["b_mac"] = W(meta, "v11", "mac"); c["b_folder"] = W(meta, "v11", "folder"); c["b_model"] = W(meta, "v11", "model")
    c["b_perm"] = W(meta, "v11", "permissions"); c["b_pull"] = round(meta["v11"]["end"] + 0.3, 3)
    c["r_start"] = W(meta, "v12", "start"); c["r_name"] = W(meta, "v12", "name"); c["r_there"] = W(meta, "v12", "there")
    c["r_otherwise"] = W(meta, "v12", "otherwise"); c["r_default"] = W(meta, "v12", "default")
    c["p_short"] = W(meta, "v13", "shortcut"); c["p_python"] = W(meta, "v13", "python"); c["p_111"] = W(meta, "v13", "111")
    c["p_chips"] = round(meta["v13"]["end"] + 0.1, 3)
    c["mark_end"] = END_CARD; c["end_line"] = round(meta["v14"]["end"] + 0.25, 3); c["end_url"] = round(meta["v14"]["end"] + 0.7, 3)
    return {k: round(v, 3) for k, v in c.items()}


def main():
    words = json.loads((ROOT / "narration/words.json").read_text())
    music = load(ROOT / "assets/audio/music.wav")
    n = music.shape[1]

    # ---------------------------------------------------------------- the voice
    vo = np.zeros(n)
    meta, prev_end = {}, 0.0
    for key in SLOTS:
        t0 = SLOTS[key]
        if t0 is None:              # v08: after v07 with a 0.45 s breath
            t0 = round(prev_end + 0.45, 3)
        y = load(ROOT / f"narration/chosen/{key}.wav").mean(0)
        if t0 < prev_end + 0.3:
            print(f"warning: {key} starts {prev_end + 0.3 - t0:.2f} s too early (breath under 0.3 s)", file=sys.stderr)
        a = int(round(t0 * SR)); b = min(n, a + len(y))
        vo[a:b] += y[: b - a]
        end = t0 + len(y) / SR
        meta[key] = {"start": round(t0, 3), "end": round(end, 3), "text": words[key]["text"],
                     "words": [{"w": w["w"], "t0": round(t0 + w["t0"], 3), "t1": round(t0 + w["t1"], 3)} for w in words[key]["words"]]}
        prev_end = end
    for k, (a, b) in [("v03", SCENES["s1"]), ("v04", SCENES["s2"]), ("v08", SCENES["s3"]), ("v11", SCENES["s4"]),
                      ("v12", SCENES["s5"]), ("v13", SCENES["s6"]), ("v14", SCENES["s7"])]:
        assert meta[k]["end"] < b - 0.35, f"{k} runs to {meta[k]['end']}, past its scene ({b})"
    tmp = Path(tempfile.mkdtemp())
    sf.write(tmp / "vo_raw.wav", vo.astype(np.float32), SR)
    chain = ("highpass=f=80,equalizer=f=3000:t=q:w=1.2:g=1.5,equalizer=f=250:t=q:w=1.0:g=-1,"
             "deesser=i=0.2:f=0.5,acompressor=threshold=0.1:ratio=2.5:attack=10:release=150:makeup=1.3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "vo_raw.wav"), "-af", chain, "-ar", str(SR),
                    str(ROOT / "assets/audio/vo.wav")], check=True)
    vo = load(ROOT / "assets/audio/vo.wav").mean(0)[:n]
    vo = np.pad(vo, (0, n - len(vo)))
    speech = np.zeros(n, bool)
    for m in meta.values():
        speech[int(m["start"] * SR): int(m["end"] * SR)] = True
    vo *= 10 ** ((-16 - lufs_of(np.vstack([vo, vo])[:, speech], tmp, "speech")) / 20)

    # ---------------------------------------------------------------- the bed
    sf.write(tmp / "m.wav", music.T.astype(np.float32), SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "m.wav"), "-af",
                    "bass=g=-4:f=110:w=0.7,equalizer=f=2500:t=q:w=1.5:g=-2", str(tmp / "m2.wav")], check=True)
    bed = load(tmp / "m2.wav")[:, :n]
    has_music = np.abs(bed).max(0) > 1e-6
    bed *= 10 ** ((-25 - lufs_of(bed[:, has_music], tmp, "bedref")) / 20)
    bed_open = bed.copy()
    hop = SR // 1000
    env = np.sqrt(np.convolve(vo ** 2, np.ones(int(0.05 * SR)) / int(0.05 * SR), "same"))[::hop]
    on = (env > 10 ** (-45 / 20)).astype(float)
    g = np.empty(len(on)); state = 0.0
    att, rel = 1 - np.exp(-1 / (0.04 * 1000)), 1 - np.exp(-1 / (0.45 * 1000))
    for i, target in enumerate(on):
        state += (att if target > state else rel) * (target - state)
        g[i] = state
    g = np.interp(np.arange(n), np.arange(len(g)) * hop, g)
    bed *= 10 ** (-4.5 * g / 20)

    # ---------------------------------------------------------------- timing for the picture
    (ROOT / "assets/vo.js").write_text("window.VO = " + json.dumps(meta) + ";\n")
    cues = picture_cues(meta)
    tm = {"drop": DROP, "return": RETURN, "end_card": END_CARD, "duration": DUR, "bar": BAR, **SCENES,
          "shots3d": SHOTS_3D, "rec0": round(REC0, 3), "rec": REC, "cues": cues}
    (ROOT / "assets/timing.js").write_text("window.TM = " + json.dumps(tm) + ";\n")
    (ROOT / "sound/timing.json").write_text(json.dumps(tm, indent=1))

    # ---------------------------------------------------------------- effects, levelled against the bed
    sfx = np.zeros((2, n))
    vo_k = kpow(np.vstack([vo, vo]))
    bed_p, vo_s = Power(kpow(bed)), Power(vo_k, speech)
    speech_l = Power(vo_k).level(speech)
    placed = []
    for t, name, over, pitch, what in sfx_events(cues):
        placed.append((t, name, what) + place(sfx, name, t, over, pitch, bed_p, vo_s, speech_l))

    # ---------------------------------------------------------------- sum, level, limit
    mix = bed + sfx + np.vstack([vo, vo])
    gm = 10 ** ((-16 - lufs_of(mix, tmp, "mix")) / 20)
    mix *= gm
    sf.write(tmp / "mix2.wav", mix.T.astype(np.float32), SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "mix2.wav"), "-af",
                    "alimiter=limit=0.72:attack=3:release=60:level=disabled", "-ar", str(SR),
                    str(ROOT / "assets/audio/mix.wav")], check=True)
    fi, tp = lufs(ROOT / "assets/audio/mix.wav")

    # ---------------------------------------------------------------- the report
    gap = ~speech & has_music; gap[: int(0.5 * SR)] = False
    v_speech = lufs_of(gm * np.vstack([vo, vo])[:, speech], tmp, "r1")
    b_under = lufs_of(gm * bed[:, speech & has_music], tmp, "r2")
    b_gaps = lufs_of(gm * bed[:, gap], tmp, "r4")
    b_film = lufs_of(gm * bed_open[:, has_music], tmp, "r5")
    print(f"mix.wav {DUR} s: {fi:.1f} LUFS integrated, true peak {tp:.1f} dBTP; voice, bed and {len(placed)} effects")
    print(f"speech {v_speech:.1f} LUFS | bed {b_film:.1f} ({v_speech - b_film:.1f} dB under) | bed under the speech, ducked "
          f"{b_under:.1f} ({v_speech - b_under:.1f} dB under) | bed between lines {b_gaps:.1f}")
    print("lines: " + ", ".join(f"{k} {m['start']:.2f}-{m['end']:.2f}" for k, m in meta.items()))
    sfx_p = Power(kpow(sfx))
    rows = []
    for t, name, what, pk, ob, uv in placed:
        c = int(round(pk * SR)); e = sfx_p.at(c, 0.1)
        rows.append((t, name, ob, uv, e - bed_ref(bed_p, c), voice_ref(vo_s, c, speech_l) - e, what))
    print(f"effects ({len(rows)}): {min(r[2] for r in rows):.1f} to {max(r[2] for r in rows):.1f} dB over the bed, at least "
          f"{min(r[3] for r in rows):.1f} dB under the voice")
    for t, name, ob, uv, ob2, uv2, what in rows:
        flag = "  <-- check" if not (2.95 <= ob <= 6.05) or ob2 > 6.55 or uv2 < 2.95 else ""
        print(f"  {t:6.2f}  {name:11s} +{ob:3.1f} over the bed ({ob2:+4.1f} summed), {uv:4.1f} under the voice ({uv2:4.1f})  {what}{flag}")
    ks = list(meta)
    print("breaths: " + ", ".join(f"{ks[i]}>{ks[i + 1]} {meta[ks[i + 1]]['start'] - meta[ks[i]]['end']:.2f}" for i in range(len(ks) - 1)))
    shutil.rmtree(tmp, ignore_errors=True)


SFX = {  # Mixkit free sound effects, the vocabulary of the earlier films
    "pop": "mixkit-2357.mp3",          # soft pop: a part arriving or lighting up; at pitch 0.8 the low pop (refusal only)
    "tick": "mixkit-1120.mp3",         # tick: a step or a counter (a chip, a status dot + word, a row, an end line)
    "whoosh_air": "mixkit-1492.mp3",   # a token travelling along a wire
    "whoosh_wind": "mixkit-1465.mp3",  # the camera gliding between close shots
    "sweep": "mixkit-3115.mp3",        # the two big camera moves (into the board, the pull-back)
    "pop_hard": "mixkit-3005.mp3",     # the soft hit: the mark on the drop, the 14, the mark on the end card
    "riser": "mixkit-2408.mp3",        # swells into the drop
}
# picture kind -> (sound, dB over the bed, default pitch)
KINDS = {"pop": ("pop", 4.0, 1.0), "tick": ("tick", 4.0, 1.0), "whoosh": ("whoosh_air", 3.5, 1.1),
         "glide": ("whoosh_wind", 3.0, 1.0), "sweep": ("sweep", 4.5, 1.0), "lowpop": ("pop", 5.0, 0.8),
         "riser": ("riser", 3.0, 1.0), "hit": ("pop_hard", 4.5, 0.9), "click": ("tick", 2.5, 1.35),
         "chime": ("pop_hard", 4.0, 1.25), "tap": ("pop", 4.5, 0.85)}
VOICE_MARGIN = 3.0   # an effect stays at least this far under the voice speaking around it (or the speech level)
_cache = {}

# K-weighting (ITU-R BS.1770 at 48 kHz): levels below are in LUFS-like units, comparable with the speech's -16
_KB1, _KA1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
_KB2, _KA2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]


def kpow(y):
    """K-weighted power per sample, summed over channels."""
    y = np.atleast_2d(y)
    z = lfilter(_KB2, _KA2, lfilter(_KB1, _KA1, y, axis=-1), axis=-1)
    return (z ** 2).sum(0)


class Power:
    """Window levels of a K-weighted power signal (cumulative sums, so each lookup is O(1)). With a mask, a window's
    level counts only the masked samples (the voice: what she says around a moment, not the pauses)."""
    def __init__(self, p, mask=None):
        self.p = p; self.c = np.concatenate([[0.0], np.cumsum(p if mask is None else p * mask)])
        self.k = np.concatenate([[0.0], np.cumsum(np.ones(len(p)) if mask is None else mask.astype(float))])

    def at(self, centre, half_s):
        h = int(half_s * SR); a = max(0, centre - h); b = min(len(self.p), centre + h)
        k = self.k[b] - self.k[a]
        return None if k < 1 else -0.691 + 10 * np.log10((self.c[b] - self.c[a]) / k + 1e-12)

    def level(self, mask):
        return -0.691 + 10 * np.log10(self.p[mask].mean() + 1e-12)


def bed_ref(bed_p, c):
    """The bed's level at sample c: the louder of its 400 ms momentary and 3 s short-term levels, so an effect in a
    pause between the intro's chords sits over the music's level in that bar, not over the silence."""
    return max(bed_p.at(c, 0.2), bed_p.at(c, 1.5))


def voice_ref(vo_s, c, speech_l):
    """The voice's level around sample c: her speech within 0.5 s (pauses not counted), else the film's speech level."""
    v = vo_s.at(c, 0.5)
    return speech_l if v is None or v < speech_l - 15 else v


def clip(name):
    if name not in _cache:
        y = load(ROOT / "sound/sfx-src" / SFX[name])
        if name == "riser":    # let it swell in from nothing (as secure-data-hub)
            f = int(1.2 * SR); y[:, :f] *= np.linspace(0, 1, f) ** 2
        _cache[name] = y
    return _cache[name]


def place(out, name, t, over_db, pitch, bed_p, vo_s, speech_l):
    """Put one effect in: its peak one frame after the picture at t, over_db over the bed there (K-weighted: the
    effect over 200 ms around its peak against bed_ref), capped VOICE_MARGIN under voice_ref.
    Returns (peak time, dB over the bed, dB under the voice), the effect alone."""
    y = clip(name)
    if pitch != 1.0:   # small pitch steps rotate repeated sounds (resampling also shortens or lengthens them)
        y = np.vstack([librosa.resample(ch, orig_sr=SR, target_sr=int(SR / pitch)) for ch in y])
    pk = int(np.argmax(np.convolve(np.abs(y).mean(0), np.ones(240) / 240, "same")))
    pad = int(0.2 * SR)                         # silence around the clip, so its 200 ms window is never cut short
    own = Power(kpow(np.pad(y, ((0, 0), (pad, pad))))).at(pk + pad, 0.1)
    c = int(round((t + 1 / 30) * SR))          # the peak lands one frame after the picture
    b_ref, v_ref = bed_ref(bed_p, c), voice_ref(vo_s, c, speech_l)
    target = min(b_ref + over_db, v_ref - VOICE_MARGIN)
    y = y * 10 ** ((target - own) / 20)
    a = c - pk
    s0 = max(0, -a); a = max(0, a)
    b = min(out.shape[1], a + y.shape[1] - s0)
    out[:, a:b] += y[:, s0: s0 + (b - a)]
    return (c / SR, target - b_ref, v_ref - target)



def sfx_events(c):
    """(picture time, sound, dB over the bed, pitch, what). A whoosh peaks at its fastest point (the middle of a move)."""
    e = []
    add = lambda t, kind, what, **kw: e.append((t, *KINDS[kind][:1], kw.get("over", KINDS[kind][1]), kw.get("pitch", KINDS[kind][2]), what))
    add(c["h_contact"] - 0.55, "whoosh", "the phone comes down")
    add(c["h_contact"], "tap", "the phone touches the sticker")
    add(c["h_yo"], "pop", "Yo", pitch=1.15)
    add(c["h_rise"] + 0.6, "sweep", "up to the Mac's display")
    add(DROP - 2.2, "riser", "into the drop")
    add(c["mark_title"], "hit", "the lockup on the drop")
    add(c["title_line"] + 0.6, "tick", "the title chip")
    add(c["t_contact"] - 0.5, "whoosh", "the phone comes down (real tap)")
    add(c["t_contact"], "tap", "the real tap")
    add(c["rec_yo"], "pop", "Yo", pitch=1.15)
    add(c["t_to_mac"] + 0.5, "glide", "camera makes room for the Mac")
    add(c["rec_phone_ok"], "tick", "phone: ✓ starting")
    add(c["rec_term"], "pop", "the Terminal opens", pitch=0.95)
    add(c["rec_claude"], "tick", "Claude Code starts", pitch=1.1)
    add(c["rec_rc"], "tick", "remote control active", pitch=1.2)
    add(c["rec_reply"], "chime", "Claude replies")
    add(c["t_wide"] + 0.5, "sweep", "out to the wide")
    add(c["t_closed"], "tick", "lid closed: the Mac stays awake")
    for k, what in [("b_sticker", "sticker card"), ("b_ssh", "SSH card"), ("b_key", "key card"), ("b_data", "data chip"),
                    ("b_mac", "Mac card"), ("b_folder", "folder"), ("b_model", "model"), ("b_perm", "permissions")]:
        add(c[k], "pop" if k in ("b_sticker", "b_ssh", "b_key", "b_mac") else "tick", what)
    add(c["b_shell"], "lowpop", "never through a shell")
    add(c["b_pull"] + 0.5, "sweep", "pull back")
    add(c["r_start"], "tick", "the sentence types")
    add(c["r_there"], "pop", "routed to orkestra", pitch=1.1)
    add(c["r_default"], "pop", "routed to the default project", pitch=1.0)
    add(RETURN, "hit", "the drums come back", over=3.0)
    for k, p in [("p_short", 1.0), ("p_python", 1.06), ("p_111", 1.12)]:
        add(c[k], "pop", f"proof {k[2:]}", pitch=p)
    add(c["p_chips"], "tick", "proof chips")
    add(c["mark_end"], "hit", "the lockup on the end card"); add(c["end_url"], "tick", "the URL")
    return e


if __name__ == "__main__":
    main()
