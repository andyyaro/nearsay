"""The launchd entry point that actually starts Claude Code.

launchd runs this program (as you, inside your logged-in macOS session) whenever
``~/.tapclaude/queue`` is not empty. Running here rather than in the SSH session
matters: SSH sessions cannot open windows, cannot show permission prompts, and
are blocked by macOS privacy controls from ``~/Documents``, ``~/Desktop`` and
``~/Downloads``, where many projects live.

The dispatcher drains the queue, then waits a few seconds ("lingers") for more
taps before exiting, so a quick second tap starts immediately instead of waiting
for launchd's restart throttle. It always leaves the queue empty, because
launchd would otherwise restart it in a loop.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from . import jobs
from .config import ConfigError, ConfigMissing, load
from .launcher import Launcher, LaunchResult, default_runner
from .logs import log
from .notify import Notifier
from .paths import Paths, default_paths
from .text import preview


class Dispatcher:
    def __init__(self, paths: Paths, launcher: Optional[Launcher] = None,
                 notifier_factory: Optional[Callable[[bool, bool], Notifier]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.paths = paths
        self.launcher = launcher or Launcher()
        self.notifier_factory = notifier_factory or (lambda on, speak: Notifier(default_runner, on, speak))
        self.clock = clock
        self.sleep = sleep
        self.log_path = paths.logs / "dispatch.log"
        self.processed = []  # (job_id, LaunchResult) for tests and `tapclaude test`

    def run(self, linger: Optional[float] = None) -> int:
        self.paths.ensure()
        lock_fd = os.open(str(self.paths.lock), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0  # another dispatcher is draining the queue
            linger_s = linger if linger is not None else self._linger()
            deadline = self.clock() + linger_s
            while True:
                jobs.sweep_strays(self.paths)
                pending = jobs.list_queue(self.paths)
                if pending:
                    for q in pending:
                        self._process(q)
                    deadline = self.clock() + linger_s
                    continue
                if self.clock() >= deadline:
                    break
                self.sleep(0.25)
            self._prune()
            return 0
        finally:
            os.close(lock_fd)

    def _linger(self) -> float:
        try:
            return load(self.paths.config).linger_seconds
        except Exception:
            return 0.0

    def _prune(self) -> None:
        try:
            keep = load(self.paths.config).keep_jobs
        except Exception:
            keep = 200
        jobs.prune(self.paths, keep)

    def _process(self, qfile: Path) -> None:
        job_dir = jobs.claim(self.paths, qfile)
        if job_dir is None:
            return
        job_id = job_dir.name
        try:
            with open(job_dir / "job.json", encoding="utf-8") as f:
                job = jobs.Job.from_dict(json.load(f))
        except (OSError, ValueError, json.JSONDecodeError) as e:
            self._fail(job_dir, job_id, f"unreadable job file: {e}", Notifier(default_runner, True))
            return

        try:
            cfg = load(self.paths.config)
        except ConfigMissing:
            self._fail(job_dir, job_id, "config file missing; run tapclaude init", Notifier(default_runner, True))
            return
        except ConfigError as e:
            self._fail(job_dir, job_id, "config problem: " + e.problems[0], Notifier(default_runner, True))
            return

        notifier = self.notifier_factory(cfg.notify, cfg.speak)
        note = ""
        if job.project not in cfg.projects:
            note = f" (project {job.project!r} no longer configured; used {cfg.default_project!r})"
            job.project = cfg.default_project
        project = cfg.project(job.project)

        try:
            result = self.launcher.launch(cfg, project, job, job_dir)
        except Exception as e:  # keep the queue moving no matter what
            result = LaunchResult(False, f"launcher error: {type(e).__name__}: {e}")

        if result.ok:
            self.processed.append((job_id, result))
            jobs.write_status(job_dir, "launched", result.detail + note, mode=job.mode, project=job.project)
            log(self.log_path, "launched", id=job_id, project=job.project, mode=job.mode, detail=result.detail)
            notifier.notify(f"Claude Code ▸ {job.project}", preview(job.task, 120), subtitle=_mode_label(job.mode))
            notifier.speak(f"Starting in {job.project}")
        else:
            self._fail(job_dir, job_id, result.detail + note, notifier, job=job)

    def _fail(self, job_dir: Path, job_id: str, detail: str, notifier: Notifier, job=None) -> None:
        self.processed.append((job_id, LaunchResult(False, detail)))
        jobs.write_status(job_dir, "failed", detail)
        log(self.log_path, "failed", id=job_id, detail=detail)
        where = f" ({job.project})" if job else ""
        notifier.notify("tapclaude ✗ task not started" + where, detail)
        notifier.speak("Tap Claude could not start the task")


def _mode_label(mode: str) -> str:
    return {"run": "Started", "review": "Typed in — press Enter to send", "background": "Running in background"}.get(mode, mode)


def main() -> int:
    paths = default_paths()
    try:
        return Dispatcher(paths).run()
    except Exception as e:
        log(paths.logs / "dispatch.log", "crash", error=repr(e))
        # Never leave the queue non-empty after a crash, or launchd will loop.
        for q in jobs.list_queue(paths):
            d = jobs.claim(paths, q)
            if d:
                jobs.write_status(d, "failed", f"dispatcher crashed: {e!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
