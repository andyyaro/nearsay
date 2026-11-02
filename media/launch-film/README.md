# nearsay launch film

The 77-second film at the top of the [repository README](../../README.md), published at
https://andyyaro.github.io/nearsay/film.html. It shows one real tap from an iPhone to a Mac, then
how the words get there safely and how they find their project. The phone's screen in it is a
screen recording of that tap, played in real time; the Mac's Terminal is redrawn line by line at
the second each line appeared, with private details left out.

[STORYBOARD.md](STORYBOARD.md) has the scenes, the look, the sound and every build step.
[FACTS.md](FACTS.md) has every claim in the film and where it comes from.

## What is here

| Path | What it is |
|---|---|
| `index.html`, `compositions/` | The composition (HyperFrames 0.8.173, GSAP): one file per scene, plus the burned-in subtitles |
| `build.py` | Writes the scene windows and subtitles into the composition, and the captions file |
| `stage/` | The 3D shots: `stage.html` and `shots.js` (three.js), `render.py` (frame by frame in Chromium), `screens.py` (the phone's real screen, one image per frame), `look.py` |
| `sound/` | The music edit (`music.py`) and the mix (`mix.py`): narration, music and effects, placed on the tap's recorded times |
| `narration/` | The script (`lines.json`), the script as voiced (`lines-tts.json`) and `pick.py`, which chooses the best take of each line and times its words |
| `research/TIMELINE.md` | How each moment of the real tap was measured from the two screen recordings |
| `FACTS.md` | Every line of narration and every on-screen claim, with its source |
| `scripts/` | The HIG Native line icons and the script that writes them into `index.html` |
| `tools/fetch_vendor.sh` | Fetches three.js and GSAP at the pinned versions and checks each file's SHA-256 |
| `deploy/film.html`, `deploy/index.html` | The watch page, and a redirect to it from the site's root |
| `assets/brand/` | The nearsay logo files the film uses |
| `assets/models/ntag215-sticker.glb` | The sticker model, made for these films |
| `assets/audio/SOURCE.md` | Every third-party sound, model and font in the film, with its licence and where it goes |

## What is not here, and why

The working folder for the film is about 600 MB. This folder keeps the source and leaves out
everything that is generated or that its licence does not let us hand on by itself:

- **Generated:** the phone's screen frames, the 3D renders, the narration takes and word times,
  the music edit, the mix, the timing files and the renders. The build steps make them again.
- **The screen recordings** of the real tap. [research/TIMELINE.md](research/TIMELINE.md) says what
  is in them and how each time was read.
- **Third-party media:** the music ("Funky Triplets" by Michael Ramir C., Mixkit), seven Mixkit
  sound effects and the iPhone and MacBook models from Sketchfab.
  [assets/audio/SOURCE.md](assets/audio/SOURCE.md) lists each one with its licence and the path it
  goes to.
- **Libraries and fonts:** three.js r186 and GSAP 3.14.2 are fetched by `tools/fetch_vendor.sh`.
  The Geist and Montserrat fonts (SIL OFL 1.1) go in `assets/fonts/`.

## Publishing

The MP4, its captions and its poster are assets of the
[`film-v1` release](https://github.com/andyyaro/nearsay/releases/tag/film-v1), so the 26.5 MB
film is not in the repository's history. The
[film page workflow](../../.github/workflows/film.yml) puts them on GitHub Pages with
`deploy/film.html`, `deploy/index.html` and the logo. It runs when anything in `deploy/` changes
on `main`. After replacing a release asset, run it by hand:

```sh
gh release upload film-v1 nearsay-launch.mp4 --clobber
gh workflow run film.yml
```

## Credits

Narration: Kokoro-82M (Apache-2.0), voice af_heart. Music: "Funky Triplets" by Michael Ramir C.
(Mixkit). Sound effects: Mixkit. 3D models: "iPhone 17 Pro" by Ranguel (Sketchfab, CC BY 4.0) and
"MacBook Pro 14-inch M5" by Apple User (Sketchfab), drawn with three.js. Type: Geist and Montserrat
(SIL OFL 1.1).
