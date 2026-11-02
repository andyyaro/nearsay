"""Turn a job into a running Claude Code session.

Three launch modes:

``run`` (default)
    Opens a terminal window in the project folder and starts an interactive
    ``claude`` session with your task already sent. Uses your configured
    permission mode, model, optional git worktree, and (by default) Remote
    Control, so the same session also shows up in the Claude app on your phone.

``review``
    Opens Claude Code's own deep link (``claude-cli://open?cwd=…&q=…``). The task
    is typed into the prompt box but **not sent** until you press Enter, and
    Claude Code shows a "Prompt from an external link" warning. Safest mode.

``background``
    Starts ``claude --bg``: no window; the session runs as a background agent you
    can watch with ``claude agents`` or attach to with ``claude attach``.

Every value that ends up in a shell script is quoted with ``shlex.quote``. The
task text itself is never placed in the script: it is stored in ``prompt.txt``
and read into a variable, then passed to ``claude`` as one argument.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence
from urllib.parse import quote

from .config import Config, Project
from .jobs import Job
from .text import preview

DEEP_LINK_MAX_Q = 5000  # documented limit for the q parameter

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def default_runner(argv: Sequence[str], **kw) -> "subprocess.CompletedProcess[str]":
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("timeout", 60)
    return subprocess.run(list(argv), **kw)


@dataclass
class LaunchResult:
    ok: bool
    detail: str
    argv: Optional[List[str]] = None


def session_name(project: str, task: str, limit: int = 60) -> str:
    words = " ".join(task.split()).replace('"', "'")
    name = f"{project}: {words}"
    return preview(name, limit)


def claude_args(cfg: Config, project: Project, job: Job, name: str, background: bool = False) -> List[str]:
    args = [cfg.claude_path, "--name", name]
    if project.remote_control and not background:
        # --remote-control takes an optional session name; we always pass one so the
        # task that follows can never be mistaken for the name.
        args += ["--remote-control", name]
    if project.permission_mode not in ("default", "manual"):
        args += ["--permission-mode", project.permission_mode]
    if project.model:
        args += ["--model", project.model]
    if project.worktree:
        args += ["--worktree", "tap-" + job.id.split("-")[-1]]
    return args


def render_run_script(job: Job, project: Project, argv: List[str], prompt_file: Path,
                      title: str, keep_shell: bool) -> str:
    q = shlex.quote
    claude_cmd = " ".join(q(a) for a in argv)
    banner = "tapclaude ▸ " + project.name + " ▸ " + preview(job.task, 100)
    missing = "tapclaude: cannot open " + str(project.path)
    lines = [
        "#!/bin/zsh -l",
        f"# tapclaude job {job.id}. Generated file; safe to delete.",
        f"export TAPCLAUDE_JOB_ID={q(job.id)}",
        f"export TAPCLAUDE_PROJECT={q(project.name)}",
        f"printf '\\033]0;%s\\007' {q(title)}",
        f"cd -- {q(str(project.path))} || {{ print -r -- {q(missing)}; read -k 1 -s; exit 1; }}",
        f"TAPCLAUDE_TASK=\"$(<{q(str(prompt_file))})\"",
        f"print -r -- {q(banner)}",
        "print",
        f"{claude_cmd} \"$TAPCLAUDE_TASK\"",
        "code=$?",
        "if (( code != 0 )); then",
        "  print -r -- \"tapclaude: claude exited with status $code. Press any key to close.\"",
        "  read -k 1 -s",
        "  exit $code",
        "fi",
    ]
    if keep_shell:
        lines.append('exec "${SHELL:-/bin/zsh}" -l')
    return "\n".join(lines) + "\n"


def opener_argv(cfg: Config, script: Path) -> List[str]:
    s = str(script)
    t = cfg.terminal
    if t == "Terminal":
        return ["open", "-a", "Terminal", s]
    if t == "iTerm":
        return [
            "osascript",
            "-e", "on run argv",
            "-e", 'tell application "iTerm" to create window with default profile command (item 1 of argv)',
            "-e", 'tell application "iTerm" to activate',
            "-e", "end run",
            shlex.quote(s),
        ]
    if t == "Ghostty":
        return ["open", "-na", "Ghostty", "--args", "-e", s]
    if t == "kitty":
        return ["open", "-na", "kitty", "--args", s]
    if t == "Alacritty":
        return ["open", "-na", "Alacritty", "--args", "-e", s]
    if t == "WezTerm":
        return ["open", "-na", "WezTerm", "--args", "start", "--", s]
    if t == "custom":
        return [part.replace("{script}", s) for part in (cfg.terminal_command or [])]
    raise ValueError(f"unknown terminal {t!r}")


def review_url(project_path: Path, task: str) -> str:
    q = task
    if len(q) > DEEP_LINK_MAX_Q:
        note = "\n\n[tapclaude: task truncated to fit a deep link]"
        q = q[: DEEP_LINK_MAX_Q - len(note)] + note
    return "claude-cli://open?cwd=" + quote(str(project_path), safe="/") + "&q=" + quote(q, safe="")


def _env(cfg: Config) -> dict:
    env = dict(os.environ)
    claude_dir = str(Path(cfg.claude_path).expanduser().parent) if "/" in cfg.claude_path else ""
    parts = [p for p in [claude_dir, cfg.path_env, env.get("PATH", "")] if p]
    env["PATH"] = ":".join(parts)
    return env


class Launcher:
    def __init__(self, runner: Runner = default_runner):
        self.runner = runner

    def launch(self, cfg: Config, project: Project, job: Job, job_dir: Path) -> LaunchResult:
        if not project.path.is_dir():
            return LaunchResult(False, f"project folder not found: {project.path}")
        prompt_file = job_dir / "prompt.txt"
        fd = os.open(str(prompt_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(job.task)

        name = session_name(project.name, job.task)
        mode = job.mode

        if mode == "review":
            argv = ["open", review_url(project.path, job.task)]
            return self._run(argv, "opened Claude Code with your task typed in (press Enter to send)", env=_env(cfg))

        if mode == "background":
            argv = claude_args(cfg, project, job, name, background=True) + ["--bg", job.task]
            res = self._run(argv, "started as a background agent (see: claude agents)",
                            cwd=str(project.path), env=_env(cfg))
            return res

        argv = claude_args(cfg, project, job, name)
        script = job_dir / "run.command"
        body = render_run_script(job, project, argv, prompt_file, f"tap ▸ {name}", cfg.keep_shell)
        fd = os.open(str(script), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o700)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(script, 0o700)
        return self._run(opener_argv(cfg, script), f"opened {cfg.terminal} and started Claude Code", env=_env(cfg))

    def _run(self, argv: List[str], success: str, **kw) -> LaunchResult:
        try:
            cp = self.runner(argv, **kw)
        except FileNotFoundError as e:
            return LaunchResult(False, f"command not found: {e.filename or argv[0]}", argv)
        except subprocess.TimeoutExpired:
            return LaunchResult(False, f"timed out running {argv[0]}", argv)
        if cp.returncode != 0:
            err = (cp.stderr or cp.stdout or "").strip().splitlines()
            return LaunchResult(False, f"{argv[0]} failed ({cp.returncode}): {err[-1] if err else 'no output'}", argv)
        out = (cp.stdout or "").strip()
        detail = success + (f" — {out.splitlines()[0]}" if out and argv[0] != "open" and argv[0] != "osascript" else "")
        return LaunchResult(True, detail, argv)
