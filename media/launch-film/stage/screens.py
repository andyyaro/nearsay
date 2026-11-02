"""The iPhone's real screen for the 3D phone: the screen recording of a real tap, one image per film frame.

    <voice-venv>/bin/python -I stage/screens.py "<ScreenRecording_11-02-2026 3.mov>"
        -> assets/screen/pNNNN.jpg (frame NNNN = recording time NNNN / 30 s), assets/screen/index.json

The recording (iPhone 17 Pro, 1206 x 2622, 25.3 s, 2026-11-02 2:01:57 AM) runs from the Shortcuts app through the tap,
the dictation ("Yo"), the Shortcut's reply and Claude's Remote Control notification. Frames are taken at 30 fps
(the film's rate) from 0 to 22.0 s, at half size (603 x 1311, plenty for the phone's size on screen).

One change: iOS draws its screen-recording indicator (a red dot in a red-outlined, widened Dynamic Island) into the
recording. Where it shows, the widened island is filled plain black, as the island itself is; the model's own island
sits in the middle of it. Nothing else is touched. Frames after 22.0 s are not used (the last notification).
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FPS, W, H, END = 30, 603, 1311, 22.0
# the widened island with the indicator, in full-size pixels: x 330-855, y 38-155 (+ its glow); the red dot at (389, 97)
PILL = (322, 29, 864, 164)
DOT = (389, 97)


def main():
    src = sys.argv[1]
    out = ROOT / "assets/screen"; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("p*.jpg"):
        f.unlink()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-t", str(END), "-vf", f"fps={FPS}", "-pix_fmt", "rgb24",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    fw, fh = 1206, 2622
    frames = np.frombuffer(raw, np.uint8).reshape(-1, fh, fw, 3)
    masked = 0
    for i, fr in enumerate(frames):
        im = Image.fromarray(fr)
        r, g, b = (int(v) for v in fr[DOT[1], DOT[0]])
        if r > 150 and g < 90 and b < 90:          # the red indicator is showing
            ImageDraw.Draw(im).rounded_rectangle(PILL, radius=(PILL[3] - PILL[1]) // 2, fill=(0, 0, 0))
            masked += 1
        im.resize((W, H), Image.LANCZOS).save(out / f"p{i:04d}.jpg", quality=92)
    (out / "index.json").write_text(json.dumps({"fps": FPS, "frames": len(frames), "size": [W, H], "masked": masked}))
    print(f"assets/screen: {len(frames)} frames ({len(frames) / FPS:.2f} s), indicator masked on {masked}")


if __name__ == "__main__":
    main()
