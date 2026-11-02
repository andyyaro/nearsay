# Troubleshooting

Start with `nearsay doctor` on the Mac: it checks each step and prints the fix. Then `nearsay log` shows every tap and what happened to it. Logs are in `~/.nearsay/logs/` (`receive.log`, `dispatch.log`, `launchd.err.log`).

To test the Mac without the phone: `nearsay test "In inbox, say hello"`.
To test the network path without starting anything: set the Shortcut's Script field to `ping` and run it; you should see `✓ nearsay … is reachable.`

## On the phone

| What you see | Likely cause | Fix |
|---|---|---|
| Nothing happens when touching the sticker | Ordinary sticker on aluminum; phone locked; wrong part of the phone | Use an on-metal sticker; unlock the phone; touch with the top edge of the iPhone. Check the automation is on and set to *Run Immediately*. |
| "Could not connect" / timeout | Remote Login off; Mac asleep; different network; wrong Host | `nearsay doctor` (Remote Login check); wake the Mac; same Wi-Fi or Tailscale; re-check Host with `nearsay phone`. If the `.local` name fails, try the Mac's address it prints. |
| Connection refused only from the phone, Mac is fine | Shortcuts lacks Local Network access | iPhone Settings → Privacy & Security → Local Network → Shortcuts → on. |
| "Authentication failed" / "Permission denied" | Key not added, wrong User, or bad permissions on the Mac | `nearsay keys` should list it; User must be your Mac's short account name (`whoami`); `doctor` checks file permissions. If you used `--allow-from`, make sure the phone's address is inside those ranges. |
| `✗ Nothing was heard` | Dictation stopped early or heard silence | Speak right after the panel appears; set *Stop Listening* to *On Tap* for longer tasks. |
| A keyboard appears instead of the listening panel | The trigger opened the Shortcut in text mode | Tap the microphone key on the keyboard, or use *Ask for Input* (see [IPHONE.md](IPHONE.md#part-2-the-nfc-automation)). |
| `✗ Unknown sticker or project 'x'` | Script field names something not in the config | `nearsay sticker list` / `nearsay project list`; fix the Script field. |
| `✗ Same task was just sent` | The sticker was read twice | This is the double-tap guard. Wait 20 s or change `dedupe_seconds`. |
| `✓ … (N tasks already waiting …)` | The dispatcher is not running | See "nothing opens" below. |

## On the Mac

| What you see | Likely cause | Fix |
|---|---|---|
| Phone shows ✓ but nothing opens | Dispatcher agent not loaded or not allowed to run in the background | `nearsay doctor` → *Dispatcher agent*. System Settings → General → Login Items & Extensions → allow the nearsay / python3 background item. Then `nearsay install-agent`. |
| Task went to the wrong project | Dictation spelled the name differently | `nearsay route "exact sentence"` shows the decision; add the spelling with `nearsay project add NAME PATH --alias "what dictation wrote"`. |
| Terminal opens, then `claude: command not found` or exits immediately | `claude_path` is stale (for example after reinstalling Claude Code) | `nearsay set claude_path "$(command -v claude)"` then `nearsay install-agent`. |
| Terminal shows Claude's "trust this folder?" question | First Claude Code session in that folder | Answer it once; later taps go straight in. Background mode needs this done beforehand (run `claude` in the folder once). |
| "Remote Control failed" notice inside Claude | Remote Control needs a claude.ai subscription login (Pro, Max, Team, Enterprise; Team/Enterprise need it enabled by an admin) | Run `claude auth login`, or turn it off: `nearsay set remote_control false`. |
| No macOS notification | Notifications from AppleScript are attributed to *Script Editor* and may be off | System Settings → Notifications → Script Editor → allow. Or `nearsay set notify false`. |
| `review` mode does nothing | Claude Code's `claude-cli://` link handler is registered only after your first interactive prompt | Run `claude` in any terminal, send one prompt, exit. `doctor` checks for `~/Applications/Claude Code URL Handler.app`. |
| iTerm: nothing opens, error mentions "not authorized" | macOS asked whether the dispatcher may control iTerm and it was denied | System Settings → Privacy & Security → Automation → allow it to control iTerm. |
| Ghostty opens a window that closes at once | The script failed before Claude started | `nearsay log`, then `nearsay show <id>`; run the `run.command` in that job folder by hand to see the message. |
| The project folder is in `~/Documents`, `~/Desktop` or `~/Downloads` and Claude cannot read it | Terminal lacks access to that folder | Approve the macOS prompt for Terminal, or System Settings → Privacy & Security → Files and Folders → Terminal. (The dispatcher itself never needs this; Terminal and Claude do, exactly as when you open them yourself.) |
| Tasks queue up and never run after a macOS update | The agent was unloaded | `nearsay install-agent`. |

## Resetting

```bash
nearsay uninstall          # agent + phone key removed, config kept
./install.sh                 # reinstall
nearsay add-key --from-clipboard
```
