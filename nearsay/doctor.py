"""``nearsay doctor``: check every link in the chain and say how to fix it."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from . import jobs, keys, launchagent
from .config import Config, ConfigError, ConfigMissing, load
from .paths import Paths

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"
ICON = {OK: "✓", WARN: "⚠", FAIL: "✗", INFO: "•"}


@dataclass
class Check:
    status: str
    title: str
    detail: str = ""
    fix: str = ""


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_claude(cfg: Config) -> Optional[str]:
    p = cfg.claude_path
    if "/" in p:
        return p if os.path.isfile(p) and os.access(p, os.X_OK) else None
    search = ":".join([str(Path.home() / ".local/bin"), cfg.path_env, os.environ.get("PATH", "")])
    return shutil.which(p, path=search)


def _bad_perms(path: Path) -> bool:
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & (stat.S_IWGRP | stat.S_IWOTH))


def run_checks(paths: Paths, runner: Callable, home: Optional[Path] = None,
               is_macos: Optional[bool] = None, port_probe: Callable[[str, int], bool] = tcp_open) -> List[Check]:
    home = home or Path.home()
    is_macos = (platform.system() == "Darwin") if is_macos is None else is_macos
    out: List[Check] = []
    add = out.append

    add(Check(OK if is_macos else WARN, "macOS", platform.platform(),
              "" if is_macos else "nearsay launches Mac apps; only the tests run elsewhere."))
    add(Check(OK if sys.version_info >= (3, 9) else FAIL, "Python", sys.version.split()[0],
              "" if sys.version_info >= (3, 9) else "Python 3.9 or newer is required."))

    try:
        cfg: Optional[Config] = load(paths.config)
        add(Check(OK, "Config", str(paths.config)))
    except ConfigMissing:
        cfg = None
        add(Check(FAIL, "Config", f"{paths.config} does not exist", "Run: nearsay init"))
    except ConfigError as e:
        cfg = None
        add(Check(FAIL, "Config", "; ".join(e.problems), f"Edit {paths.config}, then run nearsay doctor again."))

    if cfg:
        for name, p in sorted(cfg.projects.items()):
            tag = " (default)" if name == cfg.default_project else ""
            if not p.path.is_dir():
                add(Check(FAIL, f"Project {name}{tag}", f"folder not found: {p.path}",
                          f"Create it, or: nearsay project add {name} /correct/path"))
                continue
            extras = []
            if p.worktree and not (p.path / ".git").exists():
                add(Check(FAIL, f"Project {name}{tag}", "worktree is on but the folder is not a git repository",
                          f"Run git init there, or: nearsay project add {name} {p.path} (without --worktree)"))
                continue
            if p.permission_mode == "bypassPermissions":
                add(Check(WARN, f"Project {name}{tag}", "permission mode is bypassPermissions",
                          "A tap can start a session that runs commands without asking. Consider acceptEdits or auto."))
                continue
            extras.append(f"mode={p.mode}")
            if p.permission_mode != "default":
                extras.append(f"permissions={p.permission_mode}")
            if p.aliases:
                extras.append("aliases: " + ", ".join(p.aliases))
            add(Check(OK, f"Project {name}{tag}", f"{p.path} ({'; '.join(extras)})"))

        claude = find_claude(cfg)
        if not claude:
            add(Check(FAIL, "Claude Code", f"cannot find {cfg.claude_path!r}",
                      "Install Claude Code, then: nearsay set claude_path \"$(command -v claude)\""))
        else:
            try:
                cp = runner([claude, "--version"], timeout=20)
                ver = (cp.stdout or "").strip().splitlines()[0] if cp.returncode == 0 and cp.stdout else ""
                add(Check(OK if cp.returncode == 0 else WARN, "Claude Code", f"{claude} {ver}".strip(),
                          "" if cp.returncode == 0 else "`claude --version` failed; run claude once in a terminal."))
            except Exception as e:
                add(Check(WARN, "Claude Code", f"{claude} (could not run: {e})"))

        if cfg.mode == "run" or any(p.mode == "run" for p in cfg.projects.values()):
            app = {"Terminal": "Terminal", "iTerm": "iTerm", "Ghostty": "Ghostty", "kitty": "kitty",
                   "Alacritty": "Alacritty", "WezTerm": "WezTerm"}.get(cfg.terminal)
            if app and is_macos:
                places = [Path("/Applications"), home / "Applications", Path("/System/Applications/Utilities"),
                          Path("/Applications/Utilities")]
                found = next((pl / f"{app}.app" for pl in places if (pl / f"{app}.app").exists()), None)
                add(Check(OK if found else FAIL, "Terminal app", str(found or f"{app}.app not found"),
                          "" if found else "Install it or: nearsay set terminal Terminal"))
        if cfg.mode == "review" or any(p.mode == "review" for p in cfg.projects.values()):
            handler = home / "Applications" / "Claude Code URL Handler.app"
            add(Check(OK if handler.exists() else FAIL, "Review mode link handler", str(handler),
                      "" if handler.exists() else "Open a terminal, run claude, send any prompt once, then exit."))

    if is_macos:
        up = port_probe("127.0.0.1", 22)
        add(Check(OK if up else FAIL, "Remote Login (SSH)", "listening on port 22" if up else "not listening",
                  "" if up else "System Settings → General → Sharing → Remote Login: on, "
                  "Allow access for: Only these users (just you)."))

    ak = home / ".ssh" / "authorized_keys"
    entries = keys.list_keys(ak)
    if entries:
        labels = ", ".join(f"{lab} ({kt})" for lab, kt, _ in entries)
        add(Check(OK, "Phone key", labels))
        text = ak.read_text(encoding="utf-8") if ak.exists() else ""
        if f'command="{paths.receive_cmd}"' not in text:
            add(Check(FAIL, "Phone key target", "the key points to a different receiver path",
                      "Re-run: nearsay add-key --from-clipboard (after copying the phone's public key)"))
    else:
        add(Check(FAIL, "Phone key", f"no nearsay key in {ak}",
                  "Copy the public key from the Shortcut's SSH action, then: nearsay add-key --from-clipboard"))
    for p, what in ((home, "home folder"), (home / ".ssh", "~/.ssh"), (ak, "authorized_keys")):
        if p.exists() and _bad_perms(p):
            add(Check(FAIL, f"Permissions on {what}", f"{p} is writable by group/others; sshd will refuse keys",
                      f"chmod go-w {p}"))

    for f in (paths.receive_cmd, paths.dispatch_cmd, paths.cli_cmd):
        if not (f.exists() and os.access(f, os.X_OK)):
            add(Check(FAIL, "Installed files", f"missing {f}", "Re-run ./install.sh"))
            break
    else:
        add(Check(OK, "Installed files", str(paths.bin)))

    if is_macos:
        plist = launchagent.plist_path(home)
        loaded = launchagent.is_loaded(runner)
        if not plist.exists():
            add(Check(FAIL, "Dispatcher agent", f"{plist} missing", "Re-run ./install.sh"))
        else:
            add(Check(OK if loaded else FAIL, "Dispatcher agent", "loaded" if loaded else "not loaded",
                      "" if loaded else f"launchctl bootstrap gui/$(id -u) {plist}"))

    waiting = jobs.list_queue(paths)
    add(Check(WARN if waiting else OK, "Queue", f"{len(waiting)} waiting" if waiting else "empty",
              "The dispatcher is not picking tasks up; see ~/.nearsay/logs/launchd.err.log" if waiting else ""))

    last = jobs.recent(paths, 1)
    if last:
        st = jobs.read_status(last[0])
        if st.get("status") == "failed":
            add(Check(WARN, "Last task", f"{last[0].name}: {st.get('detail', '')}", "See: nearsay log"))
        else:
            add(Check(OK, "Last task", f"{last[0].name}: {st.get('status')}"))
    return out


def format_checks(checks: List[Check]) -> str:
    lines = []
    for c in checks:
        line = f"{ICON[c.status]} {c.title}: {c.detail}".rstrip(": ")
        lines.append(line)
        if c.fix and c.status in (FAIL, WARN):
            lines.append(f"    fix: {c.fix}")
    fails = sum(c.status == FAIL for c in checks)
    warns = sum(c.status == WARN for c in checks)
    lines.append("")
    lines.append("All good." if not fails and not warns else f"{fails} problem(s), {warns} warning(s).")
    return "\n".join(lines)
