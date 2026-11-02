# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue.

1. Open the repository's **Security** tab and choose **Report a vulnerability**.
2. If you cannot use that, email **andyyaro25@gmail.com** with "nearsay security" in the subject.

Say what is affected, how to reproduce it and what an attacker could do with it. This is a
one-person project, so a reply can take a few days. Please give a reasonable time for a fix before
you disclose the problem publicly.

## In scope

The code in this repository: the receiver and router (`nearsay/receive.py`, `router.py`,
`text.py`), the queue and dispatcher, the launcher, the `authorized_keys` line written by
`keys.py`, the LaunchAgent, `install.sh` and the GitHub Actions workflow.

What could go wrong, and what stops it, is written down in
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md). Three kinds of report matter most:

- **The phone's key doing anything beyond queueing a task.** It is meant to run the receiver and
  nothing else: no shell, no terminal, no forwarding. Any way around `command=…,restrict` is a
  serious bug.
- **Spoken or typed text reaching a shell.** The task is meant to travel as data only, from
  standard input to a file to one argument to `claude`. Any way for it to be run as a command,
  or to change the folder, permission mode, model or program used, is a serious bug.
- **Anything that lets the phone pick what only the Mac's config should decide.**

## Out of scope

- Someone who already holds your unlocked phone starting a session in a project you configured,
  with the permission mode you chose. That is what nearsay is for; the threat model says how to
  limit it (`default` or `acceptEdits` permission modes, `review` mode, `--allow-from`).
- Problems in Claude Code, iOS Shortcuts or macOS's own SSH server. Please report those to their
  makers.

## Please do not

- Test against a Mac or phone that is not yours.
- Use real personal data while testing.
- Try social engineering or phishing.

## Supported versions

Only the `main` branch receives fixes.
