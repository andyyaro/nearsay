# One real tap: how the film's times were measured

Two screen recordings of the same tap, 2026-11-02, about 2:02 AM local time:

- **Phone:** `ScreenRecording_11-02-2026 3.mov` (iPhone 17 Pro, 1206 x 2622, HEVC, variable frame rate, 25.3 s).
- **Mac:** `Screen Recording 2026-11-02 at 1.58.54 AM.mov` (the name has a narrow no-break space, U+202F,
  before "AM").

An earlier phone take (`ScreenRecording_11-02-2026 02-00-44_1.mov`) was not used.

## Method

- Frames were taken with ffmpeg's `fps` filter, and times read from `showinfo` pts. Input seeking (`-ss` before `-i`)
  returned the wrong frames on this variable-frame-rate HEVC file, so it was not used for timing.
- **Clock sync:** both status bars show the minute change 2:01 → 2:02. On the phone it happens at recording time
  2.268 s (pts 1361/600); on the Mac at 185.235 s. So Mac time = phone time + 182.967 s, to about one frame on each side.
- The job file's name agrees: `20261102T070205078708` is 07:02:05.079 UTC = 2:02:05.079 local, phone time 7.35 s.

## The timeline (phone recording time; time after the tap in brackets)

| Phone t | After tap | Where | What |
|---|---|---|---|
| 0.87 | 0.0 | phone | the tap: the listening panel slides in |
| 1.13 | 0.3 | phone | "Now listening…" |
| 3.37 | 2.5 | phone | "Yo" |
| 5.95 | 5.1 | phone | the panel closes (gone by 6.77) |
| 7.347 | 6.5 | Mac | the job is queued (its file name, above) |
| 7.50 | 6.6 | phone | notification "Tap Claude / ✓ inbox · starting: Yo" |
| 7.873 | 7.0 | Mac | a Terminal window opens |
| 8.163 | 7.3 | Mac | "nearsay ▸ inbox ▸ Yo" |
| 8.693 | 7.8 | Mac | Claude Code starts: "› Yo", "/rc connecting…", "Scampering…" |
| 9.233 | 8.4 | Mac | "/remote-control is active · Continue here, on your phone, or at claude.ai/code" |
| 11.383 | 10.5 | Mac | "Moonwalking… (2s · thinking with xhigh effort)" |
| 12.07 | 11.2 | phone | notification "Remote control enabled: inbox: Yo" |
| 12.363 | 11.5 | Mac | Claude's reply "Hey, what are we working on? I'm in ~/nearsay-inbox." and "Brewed for 3s · done 2:02 AM" |
| 15.30 | 14.4 | phone | notification "inbox: Yo — Your Claude Code session is ready…" (gone by 22.2) |

## In the film

- Real-tap scene (s3): recording time r plays at film time 15.15 + r (`sound/timing.json`: `rec0`), so the tap lands
  at 16.02 and the Terminal opens at 23.02. The phone's screen plays the recording unbroken; the Terminal panel and
  the notification callouts switch at the same times; the clock counts real seconds from the tap.
- Hook (s1): the 3D phone touches the sticker at 2.85; the screen holds the recording's first frame until then and
  plays from the tap (0.87) after.
- The narration is placed around these moments (`sound/mix.py`, SLOTS: v05 0.3 s before the tap, v06 0.75 s after
  "Yo", v07 as the Terminal opens), never the other way round.

## Redactions and changes

- Not shown from the Mac recording: the session URL (`claude.ai/code/session_…`), the usage line ("5h n/a | 7d …"),
  the plan name, the user name in the window title and prompt, the job path, the "Last login" lines, the desktop and
  any other window.
- Phone frames: the screen-recording indicator in the Dynamic Island is painted black (520 of 660 frames).
- The third notification has em dashes; it appears only small, on the 3D phone in the wide shot.
- The Mac recording was made with the lid open. The film shows it shut, on purpose; see FACTS.md.
