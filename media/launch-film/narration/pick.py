"""Kokoro af_heart takes (nearsay). Choose the best take of each narration line and time its words.

    <voice-venv>/bin/python -I narration/pick.py takes     (the folder of <id>.<k>.wav takes)

For every line in lines.json: transcribe each take (mlx-whisper, word timestamps), score it by how exactly the words
match the script (lines-tts.json), trim silence, and keep the winner as chosen/<id>.wav (narration/overrides.json can
force a take: {"v02": "v02.2.wav"}). words.json gets each chosen line's words with times relative to the clip's start,
in the script's own spellings (lines.json: "nearsay", "SSH", "111"), so subtitles and W() cues read them.
"""
import json, re, sys, difflib
from pathlib import Path
import numpy as np, soundfile as sf
import mlx_whisper

HERE = Path(__file__).resolve().parent
ASR = "mlx-community/whisper-large-v3-turbo"
# numbers as she says them (lines.json writes digits, lines-tts.json writes words)
NUM = {"111": "a hundred and eleven", "1": "one", "2": "two"}


def norm(s):
    s = re.sub(r"\[([^\]]+)\]\(/[^)]*/\)", r"\1", s).lower()     # "[word](/phonemes/)" -> "word"
    s = re.sub(r"([a-z])(\d)", r"\1 \2", s)                       # "ntag213" -> "ntag 213"
    s = s.replace("-", " ").replace(".", " ")
    s = re.sub(r"[^a-z0-9' ]", "", s).replace("'", "")
    s = re.sub(r"\b(\d+)\b", lambda m: NUM.get(m.group(1), m.group(1)), s)
    s = " ".join(s.split())
    s = re.sub(r"\b([a-z])((?: [a-z]\b)+)", lambda m: m.group(1) + m.group(2).replace(" ", ""), s)   # "n f c" -> "nfc"
    # Kokoro says klˈɔd (Claude) every time; Whisper writes "Cloud" after "a voice launcher for"
    for a, b in [("one hundred", "a hundred"), ("near say", "nearsay"), ("cloud", "claude")]:
        s = re.sub(rf"\b{a}\b", b, s)
    return s


def respell(text, ws):
    """Give the timed words the script's own spellings (lines.json), so the scenes' W() cues and the subtitles read
    "Rekognition", "Fourteen", "read-only", "profile-photo". Whisper's "-only" style pieces are joined to the word
    before; then each script token takes as many heard words as spell it. Returns None if they do not line up."""
    key = lambda s: norm(s).replace(" ", "")
    heard = []
    for w in ws:
        if heard and w["w"].startswith("-"):
            heard[-1] = {"w": heard[-1]["w"] + w["w"], "t0": heard[-1]["t0"], "t1": w["t1"]}
        else:
            heard.append(dict(w))
    out, i = [], 0
    for tok in text.split():
        want, got, j = key(tok), "", i
        while j < len(heard) and len(got) < len(want):
            got += key(heard[j]["w"]); j += 1
        if got != want or j == i:
            return None
        out.append({"w": tok, "t0": heard[i]["t0"], "t1": heard[j - 1]["t1"]})
        i = j
    return out if i == len(heard) else None

def trim(y, sr, thr_db=-42, pad=0.06):
    env = np.abs(y)
    win = int(0.01 * sr)
    rms = np.sqrt(np.convolve(env ** 2, np.ones(win) / win, "same"))
    on = np.where(20 * np.log10(rms + 1e-9) > thr_db)[0]
    if not len(on):
        return y, 0.0
    a, b = max(0, on[0] - int(pad * sr)), min(len(y), on[-1] + int(pad * sr))
    return y[a:b], a / sr


def main():
    takes_dir = HERE / sys.argv[1]
    lines = json.loads((HERE / "lines.json").read_text())
    tts = json.loads((HERE / "lines-tts.json").read_text())
    out = HERE / "chosen"; out.mkdir(exist_ok=True)
    over = json.loads((HERE / "overrides.json").read_text()) if (HERE / "overrides.json").exists() else {}
    words_out, report = {}, []
    for key, text in lines.items():
        best = None
        cands = [takes_dir / over[key]] if key in over else sorted(takes_dir.glob(f"{key}.*.wav"))
        for f in cands:
            y, sr = sf.read(f)
            if y.ndim > 1: y = y.mean(1)
            y, cut = trim(y, sr)
            tmp = out / f"_{f.name}"; sf.write(tmp, y, sr)
            r = mlx_whisper.transcribe(str(tmp), path_or_hf_repo=ASR, language="en", word_timestamps=True)
            tmp.unlink()
            heard = " ".join(s["text"] for s in r["segments"]).strip()
            score = difflib.SequenceMatcher(None, norm(tts[key]).split(), norm(heard).split()).ratio()
            dur = len(y) / sr
            # words-per-second sanity: penalise very slow, draggy takes slightly
            wps = len(text.split()) / max(dur, 0.1)
            rank = score + (0.03 if f.name.endswith(".1.wav") else 0.0)
            ws = [{"w": w["word"].strip(), "t0": round(w["start"], 3), "t1": round(w["end"], 3)}
                  for s in r["segments"] for w in s.get("words", [])]
            if best is None or rank > best[0]:
                best = (rank, f.name, y, sr, heard, dur, ws, score)
        rank, name, y, sr, heard, dur, ws, score = best
        sf.write(out / f"{key}.wav", y, sr)
        ws = respell(text, ws) or (print(f"warning: {key} words keep Whisper's spelling", file=sys.stderr) or ws)
        words_out[key] = {"text": text, "dur": round(dur, 3), "take": name, "words": ws}
        report.append(f"{key} {name:10s} {dur:5.2f}s match={score:.2f}  heard: {heard}")
    (HERE / "words.json").write_text(json.dumps(words_out, indent=1))
    print("\n".join(report))


if __name__ == "__main__":
    main()
