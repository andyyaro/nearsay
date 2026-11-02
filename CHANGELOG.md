# Changelog

## Unreleased - Renamed to nearsay (November 2026)

The project is now **nearsay**. Nothing about how it works has changed: the phone still sends
`tap`, the key is still locked to the receiver, and the whole suite passes: 109 tests, the original 108 plus one for a fix below.

### Changed
- **The name, everywhere.** The command is `nearsay` (was `tapclaude`); the install folder is
  `~/.nearsay`; the programs are `nearsay-receive` and `nearsay-dispatch`; the LaunchAgent is
  `com.nearsay.dispatch`; the default project folder is `~/nearsay-inbox`; environment variables
  start with `NEARSAY_`; phone key lines end in `nearsay:<label>`; the Shortcut in the guide is
  called **nearsay**. The repository moved to `github.com/andyyaro/nearsay` (the old address
  redirects).
- The security model moved from `docs/SECURITY.md` to [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md),
  so that [SECURITY.md](SECURITY.md) can be the policy for reporting a problem.
- README: the nearsay logo, badges, a flow diagram and a list of known limitations.

### Added
- CI: the full suite on macOS with Apple's system Python and a current one, on every push to
  `main` and every pull request ([tests.yml](.github/workflows/tests.yml)).
- [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md),
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and a pull request template.

### Fixed
- **The SSH end-to-end test now runs on macOS.** It created `/run/sshd`, a folder only Linux's
  sshd needs; on a Mac `/run` is read-only, so the whole end-to-end class errored before it
  started. It now does that on Linux only, and all six end-to-end tests pass against Apple's sshd.
- **`nearsay uninstall` honours `NEARSAY_SKIP_LAUNCHD=1`**, as `install-agent` already did. A
  LaunchAgent label belongs to the user, not to a `HOME` folder, so an uninstall run in a test or
  a sandbox could unload the real dispatcher. A test now holds this.

### Moving from tapclaude

Your existing install keeps working until you move. To move, run this on the Mac. It keeps the
phone's key, so you do not need to touch the phone:

```bash
# 1. Save the phone's key, then remove the old agent, key line and PATH link (keeps ~/.tapclaude)
KEY=$(grep -E ' tapclaude:[A-Za-z0-9._-]+$' ~/.ssh/authorized_keys | head -1 | awk '{print $(NF-2), $(NF-1)}')
~/.tapclaude/bin/tapclaude uninstall --yes

# 2. Install nearsay and bring your projects and settings across
git clone https://github.com/andyyaro/nearsay.git ~/code/nearsay
cd ~/code/nearsay && ./install.sh
cp ~/.tapclaude/config.json ~/.nearsay/config.json

# 3. Authorize the same phone key for nearsay, then check everything
nearsay add-key "$KEY"
nearsay doctor
```

If you had limited the key with `--allow-from`, add the same option to `nearsay add-key`. Once
`nearsay doctor` is happy and a tap works, delete `~/.tapclaude` and `~/tapclaude-inbox` if you
no longer need their task history.

## 1.0.0 - First release, as tapclaude (October 2026)

- Tap an NFC sticker with an iPhone, speak a task, and a Claude Code session starts on the Mac in
  the right project.
- The phone's SSH key is locked to one program (`command=…,restrict`); the words travel as data
  and never pass through a shell.
- Project chosen by voice ("In orkestra, …", with aliases and sounds-like matching) or by sticker.
- Three launch modes: `run`, `review` (prompt filled in but not sent) and `background`.
- Remote Control on by default, so the session also appears in the Claude app on the phone.
- `doctor`, `phone`, `route`, `test`, `log` and `show` commands; a validated config file.
- A test suite covering routing, the receiver, the launcher, the dispatcher, keys, the installer
  and an end-to-end run through a real OpenSSH server.
