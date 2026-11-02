"""Job files: the hand-off between the SSH receiver and the launchd dispatcher.

Lifecycle of one tap::

    incoming/.<id>.tmp  --rename-->  queue/<id>.json  --rename-->  jobs/<id>/job.json
         (receiver writes)              (launchd wakes            (dispatcher claims,
                                         the dispatcher)           launches, records status)

Both moves are ``os.replace`` within one filesystem, so a job is never seen
half-written and is never processed twice.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .paths import Paths


@dataclass
class Job:
    id: str
    created_at: str
    source: str  # "ssh" or "local"
    client: Optional[str]  # phone's IP address from SSH_CONNECTION, if any
    hint: str  # raw text of the Shortcut's Script field
    project: str
    task: str
    matched_by: str
    heard_as: Optional[str]
    mode: str
    version: str = __version__
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        required = ("id", "created_at", "source", "project", "task", "mode")
        missing = [k for k in required if k not in d]
        if missing:
            raise ValueError("job is missing " + ", ".join(missing))
        return cls(
            id=str(d["id"]),
            created_at=str(d["created_at"]),
            source=str(d["source"]),
            client=d.get("client"),
            hint=str(d.get("hint", "")),
            project=str(d["project"]),
            task=str(d["task"]),
            matched_by=str(d.get("matched_by", "default")),
            heard_as=d.get("heard_as"),
            mode=str(d["mode"]),
            version=str(d.get("version", "?")),
            extra=dict(d.get("extra") or {}),
        )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_job_id(now: Optional[datetime] = None) -> str:
    """Sortable by arrival time down to the microsecond, so taps run in the order received."""
    now = now or now_utc()
    return now.strftime("%Y%m%dT%H%M%S") + "%06d" % now.microsecond + "-" + secrets.token_hex(3)


def _write_private(path: Path, data: str) -> None:
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def enqueue(paths: Paths, job: Job) -> Path:
    paths.ensure()
    tmp = paths.incoming / f".{job.id}.tmp"
    _write_private(tmp, job.to_json())
    dest = paths.queue / f"{job.id}.json"
    os.replace(tmp, dest)
    return dest


def list_queue(paths: Paths) -> List[Path]:
    if not paths.queue.exists():
        return []
    return sorted(p for p in paths.queue.iterdir() if p.is_file() and p.suffix == ".json" and not p.name.startswith("."))


def sweep_strays(paths: Paths) -> List[Path]:
    """Move anything in the queue that is not a job file out of the way.

    launchd keeps restarting the dispatcher for as long as the queue folder is
    not empty, so a stray file (``.DS_Store``, a half-copied file, a folder)
    would otherwise cause an endless restart loop.
    """
    moved = []
    if not paths.queue.exists():
        return moved
    for p in paths.queue.iterdir():
        if p.is_file() and p.suffix == ".json" and not p.name.startswith("."):
            continue
        dest = paths.rejected / f"{int(time.time())}-{p.name}"
        try:
            shutil.move(str(p), str(dest))
            moved.append(dest)
        except OSError:
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
            except OSError:
                pass
    return moved


def claim(paths: Paths, qfile: Path) -> Optional[Path]:
    """Atomically move a queued job into its own folder. Returns that folder,
    or None if another dispatcher already claimed it."""
    job_dir = paths.jobs / qfile.stem
    job_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(job_dir, 0o700)
    try:
        os.replace(qfile, job_dir / "job.json")
    except FileNotFoundError:
        return None
    return job_dir


def write_status(job_dir: Path, status: str, detail: str, **extra: Any) -> None:
    payload = {"status": status, "detail": detail, "at": now_utc().isoformat(timespec="seconds")}
    payload.update(extra)
    tmp = job_dir / ".status.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, job_dir / "status.json")


def read_status(job_dir: Path) -> Dict[str, Any]:
    try:
        with open(job_dir / "status.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"status": "pending", "detail": ""}


def read_job(job_dir: Path) -> Optional[Job]:
    try:
        with open(job_dir / "job.json", encoding="utf-8") as f:
            return Job.from_dict(json.load(f))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def job_dirs(paths: Paths) -> List[Path]:
    if not paths.jobs.exists():
        return []
    return sorted(
        (d for d in paths.jobs.iterdir() if d.is_dir() and not d.name.startswith("_")),
        key=lambda d: d.name,
    )


def recent(paths: Paths, n: int = 10) -> List[Path]:
    return list(reversed(job_dirs(paths)[-n:]))


def prune(paths: Paths, keep: int) -> int:
    dirs = job_dirs(paths)
    removed = 0
    for d in dirs[: max(0, len(dirs) - keep)]:
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    rej = sorted(paths.rejected.iterdir()) if paths.rejected.exists() else []
    for p in rej[: max(0, len(rej) - 50)]:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                p.unlink()
            except OSError:
                pass
    return removed
