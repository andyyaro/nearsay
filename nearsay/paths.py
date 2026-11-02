"""Where nearsay keeps its files.

Everything lives under one folder (``~/.nearsay`` by default, or the folder
named by the ``NEARSAY_HOME`` environment variable). The folder is outside
``~/Documents``, ``~/Desktop`` and ``~/Downloads`` on purpose: macOS privacy
controls (TCC) block a process started by the SSH server from those folders,
and the receiver must be able to write here without any extra permission.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_HOME = "NEARSAY_HOME"


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    @property
    def queue(self) -> Path:
        """Watched by launchd (QueueDirectories). Must be empty when idle."""
        return self.root / "queue"

    @property
    def incoming(self) -> Path:
        """Scratch area for atomic writes. Same filesystem as ``queue``."""
        return self.root / "incoming"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def rejected(self) -> Path:
        return self.root / "jobs" / "_rejected"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def bin(self) -> Path:
        return self.root / "bin"

    @property
    def app(self) -> Path:
        return self.root / "app"

    @property
    def lock(self) -> Path:
        return self.root / "dispatch.lock"

    @property
    def state(self) -> Path:
        """Small state file used to ignore accidental double taps."""
        return self.root / "last-task.json"

    @property
    def receive_cmd(self) -> Path:
        return self.bin / "nearsay-receive"

    @property
    def dispatch_cmd(self) -> Path:
        return self.bin / "nearsay-dispatch"

    @property
    def cli_cmd(self) -> Path:
        return self.bin / "nearsay"

    def ensure(self) -> None:
        for d in (self.root, self.queue, self.incoming, self.jobs, self.rejected, self.logs, self.bin):
            d.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(d, 0o700)
            except OSError:
                pass


def default_paths() -> Paths:
    env = os.environ.get(ENV_HOME)
    root = Path(env).expanduser() if env else Path.home() / ".nearsay"
    return Paths(root.absolute())
