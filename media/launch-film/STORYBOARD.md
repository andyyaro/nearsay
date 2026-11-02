# nearsay launch film: storyboard and build

76.8 s, 1920 × 1080, 30 fps. H.264 with AAC at 256 kb/s; measured on the MP4: -16.2 LUFS
integrated, true peak -1.9 dBTP, loudness range 7.4 LU. Every claim in it and its source is in
[FACTS.md](FACTS.md); how the real tap was timed is in [research/TIMELINE.md](research/TIMELINE.md).

## The film

| Time (s) | Scene | What you see |
|---|---|---|
| 0–9.6 | Hook (3D) | A shut MacBook with a sticker on its lid. An iPhone comes in from the right and touches the sticker; its real screen listens and hears "Yo". "Hold your phone near." / "Say the task." / "A coding session starts on your Mac." |
| 9.6–14.8 | Title | The nearsay lockup on the music's drop, "A voice launcher for Claude Code.", "iPhone Shortcuts and your Mac · open source, MIT". |
| 14.4–34.0 | One real tap (3D) | The tap again, in real time from the screen recordings. A clock counts from the tap. The Mac stays shut; its Terminal is redrawn beside it, each line at the second it appeared: the banner (+7.3 s), Claude Code with "Yo" as its task (+7.8 s), Remote Control (+8.4 s), the reply (+11.5 s). The phone's two notifications, enlarged. "With the lid shut, the Mac must stay awake." |
| 33.6–50.8 | How it works | Sticker → Shortcut → `nearsay-receive` (the only program the key can run) → job queue → `nearsay-dispatch`. What the key cannot do; the words travel stop to stop as data, never through a shell; only the Mac decides folder, model and permission mode. |
| 50.4–60.4 | Routing | Three sentences type in and land in their projects: "In orkestra, …", "Summarize what changed today." (the default, inbox), "Hey Claude, in orchestra …" (a sounds-like match). |
| 60.0–67.6 | Proof (3D) | 3 Shortcut actions, 0 dependencies (standard-library Python 3.9+), 111 tests pass; open source, MIT. |
| 67.2–76.8 | End card | The lockup, "Hold your phone near. Say the task.", github.com/andyyaro/nearsay; the shut Mac and the phone on the right. |

## Look

- **Style:** a UI film: 3D devices on a soft ground, push-ins and orbits, the real screen on the
  device; Montserrat SemiBold capitals for kickers, bold Geist headlines, white chips, subtitles
  burned in on a dark pill.
- **Brand:** nearsay's own: teal #19C7B5, cream #FFF7E8, ink #06292B, and a darker teal #0A7D72
  for teal text on cream. The logo is the repository's (`assets/brand/`).
- **Type:** Geist throughout, the Terminal text included, and Montserrat SemiBold for kickers. No
  monospace and no em dashes on screen. Icons: the HIG Native line glyphs
  (`scripts/vendor/hig-icons.js`, written into `index.html` by `scripts/build-icons.mjs`).
- **The 3D stage** (`stage/`): three.js r186, rendered frame by frame in Chromium on the GPU and
  encoded BT.709. The phone's screen is the recording itself, mapped onto the model's display
  (`stage/screens.py` makes one image per film frame). The camera pans (`view()` in
  `stage/shots.js`) so the devices sit right of centre and the text has the left.

## Sound

- **Voice:** Kokoro-82M, voice af_heart, 14 lines, each take matching the script word for word.
  "nearsay" is voiced NEAR-say (`[nearsay](/nˈɪɹsˌA/)` in `narration/lines-tts.json`), "SSH" as
  "S S H" and 111 as "a hundred and eleven".
- **Music:** "Funky Triplets" by Michael Ramir C. (Mixkit 1141), 100 BPM, cut on its bar lines by
  `sound/music.py`: the real opening under the hook, the drop on the title, the groove under the
  tap and the board, the breakdown under routing, the drums back on the proof, and its own ending
  under the end card.
- **Effects:** soft Mixkit interface sounds: a tap on each touch, ticks and pops on the Mac's and
  the phone's events at their recorded times, a chime on Claude's reply. The list is in
  [assets/audio/SOURCE.md](assets/audio/SOURCE.md).
- **Levels:** speech about -15 LUFS, the music 9 dB under it, master -16.2 LUFS, true peak -1.9 dBTP.

## Build

Get the inputs first: `tools/fetch_vendor.sh` for three.js and GSAP, then the fonts, models,
music and effects listed in [assets/audio/SOURCE.md](assets/audio/SOURCE.md). The Python steps
need numpy, soundfile, scipy, librosa, Pillow and mlx-whisper (`<voice-venv>`), or Playwright
with Chromium (`<playwright-venv>`).

```sh
tools/fetch_vendor.sh
<voice-venv>/bin/python -I stage/screens.py "<phone screen recording>.mov"   # assets/screen/
# Voice each line of narration/lines-tts.json with Kokoro-82M (af_heart) at speeds 1.0 and 1.06,
# as narration/takes/<id>.<k>.wav
<voice-venv>/bin/python -I narration/pick.py takes               # best take per line, words.json
<voice-venv>/bin/python -I sound/music.py                         # assets/audio/music.wav, sound/grid.json
<voice-venv>/bin/python -I sound/mix.py                           # mix.wav, assets/vo.js, assets/timing.js
<playwright-venv>/bin/python -I stage/render.py                   # assets/stage/<shot>.mp4 (s1, s3, s6, s7)
python3 -I build.py                                               # scene windows, subtitles, the .vtt
npx --yes hyperframes@0.8.173 lint && npx --yes hyperframes@0.8.173 check
npx --yes hyperframes@0.8.173 render -o renders/raw.mp4 --fps 30
ffmpeg -y -i renders/raw.mp4 -i assets/audio/mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k \
  -shortest -movflags +faststart renders/nearsay-v1.mp4
```

`stage/render.py --at <t> …` renders stills for checking a pose. The scenes and the 3D shots read
the same timing (`window.TM`, `window.VO`), so a re-voiced line re-times the picture.

## The README preview

`docs/assets/readme/nearsay-in-action.webp` is the real-tap scene, 15.2–31.2 s of the film, at
1200 px and 15 fps, 4.6 MB. The light denoise, a keyframe every 6–12 frames and quality 90 keep
lossy WebP from turning the film's grain on the dark lid and Terminal into blocks, above all
while the camera moves.

```sh
mkdir -p preview
ffmpeg -ss 15.2 -i renders/nearsay-v1.mp4 -t 16 \
  -vf "fps=15,hqdn3d=3:2:4:3,scale=1200:-2:flags=lanczos" preview/p%03d.png
img2webp -loop 0 -kmax 12 -kmin 6 -lossy -q 90 -m 6 -d 67 -mixed -exact preview/p*.png \
  -o ../../docs/assets/readme/nearsay-in-action.webp
```
