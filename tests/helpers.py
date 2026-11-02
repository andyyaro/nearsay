"""Shared fixtures: a throwaway nearsay home with a few projects."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nearsay import config as config_mod  # noqa: E402
from nearsay.paths import Paths  # noqa: E402

FAKE_CLAUDE = """#!{python}
import json, os, sys
with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(),
                        "job": os.environ.get("NEARSAY_JOB_ID")}}) + "\\n")
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
"""


def base_raw(tmp: Path) -> Dict[str, Any]:
    projects = {
        "inbox": {"path": str(tmp / "proj" / "inbox"), "aliases": ["inbox", "scratch"]},
        "orkestra": {"path": str(tmp / "proj" / "orkestra"), "aliases": ["orchestra runtime"]},
        "provalume": {"path": str(tmp / "proj" / "provalume"), "aliases": ["prova loom"],
                      "permission_mode": "acceptEdits"},
        "ev-model": {"path": str(tmp / "proj" / "ev model"), "aliases": ["ev model", "charge ready"],
                     "model": "sonnet"},
        "olympus": {"path": str(tmp / "proj" / "olympus"), "worktree": True},
    }
    raw = config_mod.default_raw()
    raw.update({
        "projects": projects,
        "default_project": "inbox",
        "stickers": {"desk": "orkestra"},
        "linger_seconds": 0,
        "dedupe_seconds": 20,
        "claude_path": str(tmp / "bin" / "claude"),
    })
    return raw


class TapTestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="nearsay-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.paths = Paths(self.tmp / "home" / ".nearsay")
        self.paths.ensure()
        self.raw = base_raw(self.tmp)
        for p in self.raw["projects"].values():
            Path(p["path"]).mkdir(parents=True, exist_ok=True)
        (Path(self.raw["projects"]["olympus"]["path"]) / ".git").mkdir()
        self.write_config(self.raw)
        self.claude_log = self.tmp / "claude-calls.jsonl"
        self.fake_claude = self.tmp / "bin" / "claude"
        self.fake_claude.parent.mkdir(parents=True, exist_ok=True)
        self.fake_claude.write_text(FAKE_CLAUDE.format(python=sys.executable), encoding="utf-8")
        self.fake_claude.chmod(self.fake_claude.stat().st_mode | stat.S_IXUSR)

    def write_config(self, raw: Dict[str, Any]) -> config_mod.Config:
        self.raw = raw
        return config_mod.save(self.paths.config, raw)

    def cfg(self) -> config_mod.Config:
        return config_mod.load(self.paths.config)

    def claude_calls(self) -> List[Dict[str, Any]]:
        if not self.claude_log.exists():
            return []
        return [json.loads(ln) for ln in self.claude_log.read_text(encoding="utf-8").splitlines() if ln.strip()]


class FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class RecordingRunner:
    """Stands in for subprocess.run; records argv and keyword arguments."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "", raise_exc: Optional[BaseException] = None):
        self.calls: List[Dict[str, Any]] = []
        self.returncode, self.stdout, self.stderr, self.raise_exc = returncode, stdout, stderr, raise_exc

    def __call__(self, argv, **kw):
        self.calls.append({"argv": list(argv), **kw})
        if self.raise_exc:
            raise self.raise_exc
        return FakeCompleted(self.returncode, self.stdout, self.stderr)


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None or os.path.exists(cmd)


def run(argv, **kw) -> subprocess.CompletedProcess:
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("timeout", 60)
    return subprocess.run(argv, **kw)
