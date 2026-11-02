# Contributing

## Setup and test

There is nothing to install: nearsay is standard-library Python and runs on the Python 3.9 that
ships with Apple's Command Line Tools.

```bash
./run_tests.sh                          # the whole suite, about 15 s
PYTHON=/usr/bin/python3 ./run_tests.sh  # with Apple's system Python, as installed Macs run it
./run_tests.sh -v                       # one line per test
```

The SSH end-to-end test starts its own `sshd` on a random localhost port with its own config, so
it does not need or touch Remote Login. To try a change on your own Mac, re-run `./install.sh`
(it keeps your config) and use `nearsay test "In inbox, …"` before going back to the phone.

## Rules that keep it safe (non-negotiable)

nearsay lets a phone start an AI coding agent on a computer. Contributions must not weaken that:

- **The phone's key runs the receiver and nothing else.** Never loosen `command=…,restrict` in
  `keys.py`, and keep the end-to-end SSH tests that prove it passing.
- **The task is data, never a command.** It goes from standard input to a file to one argument to
  `claude`. Never pass it through a shell, `eval`, `osascript` string or a URL without the
  escaping the launcher already does, and never build a command line by joining strings.
- **The phone cannot choose what the Mac's config decides**: the folder, permission mode, model
  and `claude` binary. New per-tap options must be validated against a fixed list, like `mode=`.
- **No dependencies.** Standard library only, Python 3.9 compatible, so nothing is `pip install`ed
  on the Mac.
- **Numbers in the docs are what the tests print.** If you change the test count or a timing in
  the README, it must come from a real run.

## Pull requests

Use the checklist in [.github/pull_request_template.md](.github/pull_request_template.md): say
what the change does, whether it touches the path from the phone to `claude`, and confirm the
suite passes. CI runs the same suite on macOS for every pull request.
