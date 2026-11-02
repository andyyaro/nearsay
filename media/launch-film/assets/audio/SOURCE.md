# Third-party sounds, pictures and type in the film

These are in the film but not in this repository. Their licences cover using them inside a film,
not handing the files on by themselves, so they are listed here instead. Download each one again
to the path shown to rebuild.

## Music

| Used as | Track | Licence | Put it at |
|---|---|---|---|
| The bed under the whole film, cut on its bar lines by `sound/music.py` | "Funky Triplets" by Michael Ramir C., Mixkit 1141 | [Mixkit Stock Music Free License](https://mixkit.co/license/): free in any project, no credit required, not for use in a music-only track | `sound/track.mp3` |

## Sound effects

All from Mixkit, under the [Mixkit Sound Effects Free License](https://mixkit.co/license/).
The names are the ones `sound/mix.py` uses (`SFX`); each file goes in `sound/sfx-src/` as
`mixkit-<id>.mp3`.

| Name in `mix.py` | Mixkit id | What it marks |
|---|---|---|
| `pop` | 2357 | A part arriving or lighting up; the tap itself, pitched down |
| `tick` | 1120 | A step or a counter: a chip, a status word, a row |
| `whoosh_air` | 1492 | A token travelling along a wire on the board |
| `whoosh_wind` | 1465 | The camera gliding between close shots |
| `sweep` | 3115 | The two big camera moves |
| `pop_hard` | 3005 | The soft hit on the title drop and the end card; Claude's reply, pitched up |
| `riser` | 2408 | The swell into the title drop |

## Voice

Kokoro-82M ([Apache-2.0](https://huggingface.co/hexgrad/Kokoro-82M)), voice af_heart, run
locally. The lines are `narration/lines-tts.json`; the audio is generated, so it is not kept.

## 3D models

| Model | By | Licence | Put it at |
|---|---|---|---|
| [iPhone 17 Pro](https://sketchfab.com/3d-models/iphone-17-pro-4541aa8a28324b33a2baaf81d263aaec) | Ranguel, on Sketchfab | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): credited on the film's end card and its watch page | `assets/models/iphone-17-pro.glb` |
| [MacBook Pro 14-inch M5](https://sketchfab.com/3d-models/macbook-pro-14-inch-m5-652a992f4f244122ae251f9cbb81da1e) | Apple User, on Sketchfab | [Sketchfab Free Standard](https://sketchfab.com/licenses): any media, in derivative works, no credit required | `assets/models/macbook-pro-14.glb` |
| NTAG215 sticker | Made for these films | Same as this repository | `assets/models/ntag215-sticker.glb` (kept here) |

The MacBook model's download did not include its licence. It is identified by its name, file
name and date against the Sketchfab listing above.

## Type

Geist (Regular, Medium, SemiBold, Bold) and Montserrat SemiBold, both under the
[SIL Open Font License 1.1](https://openfontlicense.org/), as `.woff2` files in `assets/fonts/`
with the names `index.html` loads (`Geist-Regular.woff2`, …, `Montserrat-SemiBold.woff2`).

## Pictures

The phone's screen in the film is a screen recording of one real tap, turned into one frame per
film frame by `stage/screens.py`. The recordings are not kept here; `research/TIMELINE.md` says
what is in them and how each moment was timed.
