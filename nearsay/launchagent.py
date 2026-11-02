"""The per-user launchd agent that runs the dispatcher.

``QueueDirectories`` makes launchd start the dispatcher whenever the queue
folder is not empty, so nothing runs (and nothing uses battery) between taps.
launchd does not expand ``~`` in these paths, so every path here is absolute.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

from .paths import Paths

LABEL = "com.nearsay.dispatch"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def plist_path(home: Optional[Path] = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def build(paths: Paths, path_env: str) -> Dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [str(paths.dispatch_cmd)],
        "QueueDirectories": [str(paths.queue)],
        "ThrottleInterval": 2,
        "ProcessType": "Interactive",
        "StandardOutPath": str(paths.logs / "launchd.out.log"),
        "StandardErrorPath": str(paths.logs / "launchd.err.log"),
        "EnvironmentVariables": {"PATH": path_env, "NEARSAY_HOME": str(paths.root)},
    }


def write(path: Path, data: Dict) -> None:
    for key in ("ProgramArguments", "QueueDirectories"):
        for p in data[key]:
            if not os.path.isabs(p):
                raise ValueError(f"{key} entries must be absolute paths: {p!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def load(runner: Runner, path: Path) -> "subprocess.CompletedProcess[str]":
    runner(["launchctl", "bootout", f"{_domain()}/{LABEL}"])  # ignore "not loaded"
    return runner(["launchctl", "bootstrap", _domain(), str(path)])


def unload(runner: Runner) -> "subprocess.CompletedProcess[str]":
    return runner(["launchctl", "bootout", f"{_domain()}/{LABEL}"])


def is_loaded(runner: Runner) -> bool:
    try:
        return runner(["launchctl", "print", f"{_domain()}/{LABEL}"]).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def kickstart(runner: Runner) -> "subprocess.CompletedProcess[str]":
    return runner(["launchctl", "kickstart", f"{_domain()}/{LABEL}"])


def default_path_env(extra: Sequence[str] = ()) -> str:
    base = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    seen = []
    for p in list(extra) + base:
        if p and p not in seen:
            seen.append(p)
    return ":".join(seen)
