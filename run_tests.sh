#!/bin/bash
# Run the whole test suite. Works on macOS (system Python 3.9+) and Linux.
#   ./run_tests.sh              # uses python3
#   PYTHON=/usr/bin/python3 ./run_tests.sh
# The SSH end-to-end test runs only where sshd, ssh, ssh-keygen and zsh exist
# (on a Mac: all present; sshd is /usr/sbin/sshd). It starts its own sshd on a
# random localhost port with its own config, so it does not touch Remote Login.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/tests"
PY="${PYTHON:-python3}"
export NEARSAY_TEST_PYTHON="${NEARSAY_TEST_PYTHON:-$(command -v "$PY")}"
exec "$PY" -m unittest discover -s . -p 'test_*.py' "$@"
