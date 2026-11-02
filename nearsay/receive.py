"""The SSH entry point. This is the only program the iPhone's key may run.

``~/.ssh/authorized_keys`` pins the phone's key to this command with
``command="…/nearsay-receive",restrict``. Whatever the Shortcut puts in its
*Script* field arrives here as the ``SSH_ORIGINAL_COMMAND`` environment variable
and is treated as **data** (a sticker or project name), never executed. The
dictated task arrives on standard input (the Shortcut's *Input* field), so it
never passes through a shell either.

The receiver does as little as possible: validate, route, write one job file,
print one line for the phone's notification, exit. The heavy lifting happens in
the dispatcher, which runs inside your logged-in macOS session.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import IO, List, Mapping, Optional

from . import __version__, jobs
from .config import MODES, Config, ConfigError, ConfigMissing, load
from .logs import log
from .paths import Paths, default_paths
from .router import resolve_name, route
from .text import normalize_task, preview

MAX_STDIN_BYTES = 64 * 1024
MAX_HINT_CHARS = 200
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NOOP_TOKENS = {"tap", "-", "nearsay"}
COMMANDS = {"ping", "status"}
OK = "✓"   # ✓
FAIL = "✗"  # ✗


@dataclass
class Hint:
    project: Optional[str] = None
    mode: Optional[str] = None
    command: Optional[str] = None
    error: Optional[str] = None


def parse_hint(raw: Optional[str], cfg: Config) -> Hint:
    h = Hint()
    if not raw:
        return h
    if len(raw) > MAX_HINT_CHARS:
        h.error = "The Shortcut's Script field is too long. Put only a sticker or project name there."
        return h
    # Tolerate a Script field with extra lines (a stray newline, or a client that adds a
    # preamble): if exactly the kind of line we expect is present, use the last such line.
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    ours = [ln for ln in lines if ln.split()[0].lower() in NOOP_TOKENS | COMMANDS]
    if len(lines) > 1 and ours:
        raw = ours[-1]
    for tok in raw.split():
        low = tok.lower()
        if low in NOOP_TOKENS:
            continue
        if low in COMMANDS:
            h.command = low
            continue
        if low.startswith("mode="):
            value = low.split("=", 1)[1]
            if value not in MODES:
                h.error = f"Unknown mode {value!r}. Use one of: {', '.join(MODES)}."
                return h
            h.mode = value
            continue
        if not TOKEN_RE.match(tok):
            h.error = (f"The Shortcut sent {tok!r}, which is not a valid sticker or project name "
                       "(letters, digits, '.', '_' and '-' only).")
            return h
        project = resolve_name(tok, cfg)
        if project is None:
            known = sorted(set(cfg.projects) | set(cfg.stickers))
            h.error = f"Unknown sticker or project {tok!r}. Known: {', '.join(known)}."
            return h
        if h.project and h.project != project:
            h.error = "The Shortcut named two different projects. Name at most one."
            return h
        h.project = project
    return h


def _client(env: Mapping[str, str]) -> Optional[str]:
    conn = env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or ""
    return conn.split()[0] if conn.split() else None


def _is_duplicate(paths: Paths, digest: str, window: float, now: float) -> bool:
    """True if the same task went to the same project within ``window`` seconds.
    Records this task either way. Locked so two simultaneous taps can't both pass."""
    if window <= 0:
        return False
    paths.root.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(paths.state), os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = json.loads(f.read() or "{}")
        except json.JSONDecodeError:
            data = {}
        dup = data.get("digest") == digest and now - float(data.get("at", 0)) < window
        f.seek(0)
        f.truncate()
        f.write(json.dumps({"digest": digest, "at": now}))
        return dup


def _status_lines(paths: Paths, n: int = 3) -> List[str]:
    lines = []
    for d in jobs.recent(paths, n):
        job = jobs.read_job(d)
        st = jobs.read_status(d)
        if job:
            lines.append(f"{st.get('status', '?')}: {job.project}: {preview(job.task, 40)}")
    queued = len(jobs.list_queue(paths))
    if queued:
        lines.insert(0, f"{queued} waiting in queue")
    return lines or ["No tasks yet."]


def run(stdin: IO[bytes], env: Mapping[str, str], out: IO[str], paths: Optional[Paths] = None,
        source: str = "ssh", now: Optional[float] = None, capture: Optional[List["jobs.Job"]] = None) -> int:
    paths = paths or default_paths()
    now = time.time() if now is None else now
    log_path = paths.logs / "receive.log"

    def say(line: str) -> int:
        out.write(line + "\n")
        out.flush()
        return 0

    try:
        cfg = load(paths.config)
    except ConfigMissing:
        return say(f"{FAIL} nearsay is not set up on the Mac yet. Run: nearsay doctor")
    except ConfigError as e:
        log(log_path, "config_error", problems=e.problems)
        return say(f"{FAIL} Config problem on the Mac: {e.problems[0]} (run: nearsay doctor)")

    hint_raw = env.get("SSH_ORIGINAL_COMMAND", "")
    hint = parse_hint(hint_raw, cfg)
    if hint.error:
        log(log_path, "bad_hint", hint=hint_raw[:MAX_HINT_CHARS], client=_client(env))
        return say(f"{FAIL} {hint.error}")
    if hint.command == "ping":
        host = os.uname().nodename
        return say(f"{OK} nearsay {__version__} on {host} is reachable.")
    if hint.command == "status":
        return say(" | ".join(_status_lines(paths)))

    data = stdin.read(MAX_STDIN_BYTES + 1)
    if len(data) > MAX_STDIN_BYTES:
        return say(f"{FAIL} That was too long to send (over {MAX_STDIN_BYTES // 1024} KB).")
    task = normalize_task(data.decode("utf-8", errors="replace"))
    if not task:
        return say(f"{FAIL} Nothing was heard, so no task was sent.")
    if len(task) > cfg.max_task_chars:
        return say(f"{FAIL} Task too long ({len(task)} characters; limit {cfg.max_task_chars}).")

    r = route(task, cfg, hint.project)
    if not r.task:
        return say(f"{FAIL} Heard the project “{r.project}” but no task after it.")
    project = cfg.project(r.project)
    mode = hint.mode or project.mode

    digest = hashlib.sha256(f"{r.project}\x00{r.task}".encode("utf-8")).hexdigest()
    if _is_duplicate(paths, digest, cfg.dedupe_seconds, now):
        log(log_path, "duplicate", project=r.project, client=_client(env))
        return say(f"{FAIL} Same task was just sent; ignored the repeat tap.")

    backlog = len(jobs.list_queue(paths))
    job = jobs.Job(
        id=jobs.new_job_id(),
        created_at=jobs.now_utc().isoformat(timespec="seconds"),
        source=source,
        client=_client(env),
        hint=hint_raw[:MAX_HINT_CHARS],
        project=r.project,
        task=r.task,
        matched_by=r.matched_by,
        heard_as=r.heard_as,
        mode=mode,
    )
    jobs.enqueue(paths, job)
    if capture is not None:
        capture.append(job)
    log(log_path, "queued", id=job.id, project=job.project, mode=mode, matched_by=r.matched_by,
        client=job.client, chars=len(job.task))

    verb = {"run": "starting", "review": "ready for review", "background": "starting in background"}[mode]
    line = f"{OK} {r.project} · {verb}: {preview(r.task, 60)}"
    if backlog >= 3:
        line += f" ({backlog} tasks already waiting — is the Mac awake? run: nearsay doctor)"
    return say(line)


def main(argv: Optional[List[str]] = None) -> int:
    try:
        return run(sys.stdin.buffer, os.environ, sys.stdout)
    except Exception as e:  # last-resort message the phone can show
        try:
            log(default_paths().logs / "receive.log", "crash", error=repr(e))
        except Exception:
            pass
        sys.stdout.write(f"{FAIL} nearsay hit an internal error on the Mac: {type(e).__name__}. "
                         "See ~/.nearsay/logs/receive.log\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
