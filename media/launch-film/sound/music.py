"""Cut "Funky Triplets" (Michael Ramir C., Mixkit 1141, Mixkit Stock Music Free License) to the nearsay film.

    <voice-venv>/bin/python -I sound/music.py     # -> assets/audio/music.wav, sound/grid.json

The brief, 2026-11-01: "calm but not too calm", a new track per film. Funky Triplets is relaxed funk / contemporary R&B
(drum drive 2.63, like Tom's 2.60 on the Flipper film). Measured (librosa, 2026-11-02): exactly 100 BPM in 4/4, the
drums enter at 4.810 s and track bar n starts at 4.810 + 2.4 n (the low-band onsets sit on that grid within 7 ms).
  bars -2..-1   0.01- 4.81  keys only (-28 dB)
  bars  0-19    4.81-52.81  the groove (bar 12 on a little fuller)
  bars 20-21   52.81-57.61  breakdown: the kick and bass drop out
  bar  22      57.61        the drums come back
  bar  30      76.81        it thins; bar 31 (79.21) a break, no kick, no hats
  bar  32      81.61        THE DROP: everything back, fuller (bars 32-41)
  bar  42     105.61        its own ending, a tail to silence by 108.0

The edit (joins on bar lines, 20 ms crossfades); film bar k starts at 2.4 k:
  film  0.0- 4.8  track bars -2..-1  the real opening, keys only             hook
  film  4.8- 9.6  track bars 30-31   the thinning bar and the break           hook
  film  9.6-14.4  track bars 32-33   THE DROP on the title                    title
  film 14.4-50.4  track bars 2-16    the groove, unbroken                     the real tap, the board
  film 50.4-55.2  track bars 17-18                                            routing
  film 55.2-60.0  track bars 20-21   the breakdown                            routing
  film 60.0-67.2  track bars 22-24   the drums come back                      proof
  film 67.2-76.8  track bars 39-42   the full section, then its own ending    end card
"""
import json, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
TRACK = ROOT / "sound/track.mp3"
SR, B0, BAR = 48000, 4.810, 2.4
tb = lambda n: B0 + n * BAR
fb = lambda k: k * BAR
# (film start, track start)
SEGMENTS = [(0.0, tb(-2)), (fb(2), tb(30)), (fb(4), tb(32)), (fb(6), tb(2)), (fb(21), tb(17)), (fb(23), tb(20)),
            (fb(25), tb(22)), (fb(28), tb(39))]
DROP, RETURN, END_CARD = fb(4), fb(25), fb(28)
FILM_END = fb(32)
XF = 0.020


def main():
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(TRACK), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    track = np.frombuffer(raw, np.float32).reshape(-1, 2).T.astype(np.float64)
    n = int(round(FILM_END * SR))
    out = np.zeros((2, n))
    x = int(XF * SR); ramp = np.linspace(0, 1, x)
    for k, (f0s, t0s) in enumerate(SEGMENTS):
        f0 = int(round(f0s * SR)); f1 = int(round(SEGMENTS[k + 1][0] * SR)) if k + 1 < len(SEGMENTS) else n
        t0 = max(0, int(round(t0s * SR)))
        seg = track[:, t0: t0 + (f1 - f0)]
        seg = np.pad(seg, ((0, 0), (0, (f1 - f0) - seg.shape[1])))
        if k > 0:   # equal-gain crossfade over the 20 ms before the bar line
            out[:, f0 - x: f0] = out[:, f0 - x: f0] * (1 - ramp) + track[:, t0 - x: t0] * ramp
        out[:, f0:f1] = seg
    fi = int(0.010 * SR); out[:, :fi] *= np.linspace(0, 1, fi)
    fo = int(0.6 * SR); out[:, -fo:] *= np.linspace(1, 0, fo) ** 2   # the track's own tail is nearly silent by then
    (ROOT / "assets/audio").mkdir(parents=True, exist_ok=True)
    sf.write(ROOT / "assets/audio/music.wav", out.T.astype(np.float32), SR)
    grid = {"track": "Funky Triplets (Michael Ramir C., Mixkit 1141)", "bpm": 100, "bar": BAR, "film_bar_k": "k * bar",
            "drop": round(DROP, 3), "return": round(RETURN, 3), "end_card": round(END_CARD, 3),
            "duration": FILM_END, "segments": [[round(a, 3), round(b, 3)] for a, b in SEGMENTS]}
    (ROOT / "sound/grid.json").write_text(json.dumps(grid, indent=1))
    print(f"music.wav {FILM_END} s; drop {DROP:.3f}, drums back {RETURN:.3f}, end card {END_CARD:.3f}")


if __name__ == "__main__":
    main()
