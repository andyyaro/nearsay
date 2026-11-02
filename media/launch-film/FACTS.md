# nearsay film: every claim and its source

The app repo is `andyyaro/nearsay` at [`7612285`](https://github.com/andyyaro/nearsay/blob/7612285/README.md)
("Stop logging a phone that hangs up early as a crash"); README line numbers below are at that commit.
"Recorded" means the two screen recordings of one real tap on 2026-11-02, about
2:02 AM: the iPhone's (`ScreenRecording_11-02-2026 3.mov`) and the Mac's (`Screen Recording 2026-11-02 at 1.58.54 AM.mov`).
How each moment was timed is in `research/TIMELINE.md`.

## The narration

| # | Line (as subtitled) | Source |
|---|---|---|
| v01-v03 | "Hold your phone near. Say the task. A coding session starts on your Mac." | README line 18, the tagline, word for word. |
| v04 | "nearsay. A voice launcher for Claude Code." | README line 30: "nearsay is a voice launcher for Claude Code." |
| v05 | "Tap the sticker, and say what you want done." | README 30-31: "Hold your iPhone to an NFC sticker on your Mac, say what you want done". Recorded: the tap, "Now listening…", "Yo". |
| v06 | "When you stop talking, the phone sends it to your Mac." | README 41 ("dictation noticing that you stopped talking"); diagram 48-49 (Dictate Text, then Run Script Over SSH, words on stdin). Recorded: the listening panel closes at 5.95 s, the job is queued on the Mac at 7.35 s. |
| v07 | "Claude Code opens in a terminal, in the right project, with your words as the task." | README 31 and 132-133. Recorded: Terminal opens at 7.87 s; Claude Code starts in `~/nearsay-inbox` with "Yo" as its prompt at 8.69 s. |
| v08 | "And the same session shows up in the Claude app on your phone, so the lid can stay closed." | README 73 and 134 (Remote Control: the same session in the Claude app, Code tab). Recorded: "/remote-control is active" on the Mac at 9.23 s; the phone's "Remote control enabled" notification at 12.07 s. "The lid can stay closed": a choice for the film; see the note below. |
| v09 | "The words go over SSH, with a key that can start one program, and nothing else." | README 57 ("The phone's key can start one program and nothing else"), 69, 228 (`command="…/nearsay-receive",restrict`: no shell, no terminal, no port or agent forwarding). |
| v10 | "They travel as data, never through a shell." | README 57-58 and 229. |
| v11 | "And only the Mac decides the folder, the model and the permissions." | README 230: "The phone cannot change which folder, permission mode, model or program is used; only the config file on the Mac decides." |
| v12 | "Start with a project's name, and the task goes there. Otherwise, it goes to your default project." | README "Choosing the project by voice", 140-147 and its table. |
| v13 | "Three Shortcut actions on the phone. Standard-library Python on the Mac. 111 tests." | README 119 (three actions), 37 and 81 (standard-library Python 3.9+, nothing installed with pip), 245 and 310 (111 tests). Run here on 2026-11-02: `./run_tests.sh` gave "Ran 111 tests in 12.506s, OK" (HOME isolated; the SSH test starts its own sshd). |
| v14 | "nearsay. Hold your phone near, and say the task." | The tagline again. |

## On screen

| Text | Source |
|---|---|
| "Since the tap" clock, "+7.3 s", "+7.8 s", "+8.4 s", "+11.5 s" | Recorded; times relative to the tap, rounded to 0.1 s (`research/TIMELINE.md`). The clock runs in real time from the tap to Claude's reply (11.5 s) and holds. |
| The Terminal panel ("nearsay › inbox › Yo", "Claude Code", "Opus 5.5 with xhigh effort", "~/nearsay-inbox · /rc connecting…", "› Yo", "/remote-control is active · Continue here, on your phone, or at claude.ai/code", "Scampering…", "Moonwalking… (2s · thinking with xhigh effort)", "Hey, what are we working on? I'm in ~/nearsay-inbox.", "Brewed for 3s · done 2:02 AM") | Recorded on the Mac, redrawn in Geist, each line at the time it appeared. Left out on purpose: the session URL, the usage limits line, the plan name, the user name, the job path and the "Last login" lines. |
| Phone notifications "Tap Claude / ✓ inbox · starting: Yo" and "Remote control enabled: inbox: Yo / Your Claude Code session is ready to control from your phone." | Recorded on the phone at 7.50 s and 12.07 s, redrawn larger. "Tap Claude" was the Shortcut's name when this was recorded (the README calls it "nearsay"). The third notification (15.30 s) contains em dashes and is only seen small, on the 3D phone. |
| "With the lid shut, the Mac must stay awake / Closed-display mode works: an external display, keyboard and power." | README 271, limitation 6. |
| Board: "NFC sticker, on the Mac's lid" | README 124 lists "the lid's back" as a sticker place. |
| Board: Shortcut, nearsay-receive, Job queue, nearsay-dispatch | README diagram 47-54 and table 67-72. |
| Board: "written with command = nearsay-receive, restrict"; "No shell", "No terminal", "No port or agent forwarding" | README 228 and 283. |
| Board: "dictated words → standard input → a job file → one argument to claude" | README 58 and 229. |
| Board: "Folder ~/nearsay-inbox" | The default project in the recording. |
| Routing rows | README table 140-147, rows 1, 5 and 4. "inbox" is the default project (recorded). |
| "3 Shortcut actions: Dictate Text, Run Script Over SSH, Show Notification" | README 119. |
| "0 dependencies on the Mac: standard-library Python 3.9 or newer, nothing installed with pip" | README badges 11 and 14 ("dependencies: none"), 37, 81. |
| "111 tests pass: SSH tested end to end, against a real OpenSSH server" | README 249-259; run here (above). |
| "Open source, MIT"; "iPhone Shortcuts and your Mac · open source, MIT" | `LICENSE` (copied to `research/repo-LICENSE.txt`). |
| "github.com/andyyaro/nearsay" | The repo's `origin`. |

## What is real and what is reconstructed

- **Real:** the phone's screen on the 3D iPhone is the recording itself, frame for frame (0 to 22.0 s, 30 fps), in
  real time from the tap. The Terminal text and the notifications are what the recordings show, at the times they show it.
- **Reconstructed:** the 3D scene. The Mac recording was made with the lid open (a screen recording needs the screen);
  the film shows the MacBook shut with the sticker on its lid, on purpose: the point of nearsay is not having to
  open the Mac. That only works while the Mac stays awake (README limitation 6), which is why the lid card is there.
- **Changed in the phone frames:** iOS draws its screen-recording indicator into the Dynamic Island; it is painted
  plain black where it shows (`stage/screens.py`). In the hook (s1), the phone's first frame is held until the 3D
  phone touches the sticker, then the recording plays from the tap.
- **The Mac's Terminal is redrawn**, not shown: Geist instead of the Terminal's monospace font (these films use no
  monospace) and the private parts removed (above).
