"""Configuration: one JSON file, validated strictly so mistakes surface early.

Only the Mac's owner can edit this file. Nothing the phone sends can change a
project's folder, permission mode, model or Claude Code binary; the phone can
only pick *which* configured project a task goes to and, optionally, the
launch mode (all three modes are equally or less powerful than "run").
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MODES = ("run", "review", "background")
PERMISSION_MODES = ("default", "manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")
TERMINALS = ("Terminal", "iTerm", "Ghostty", "kitty", "Alacritty", "WezTerm", "custom")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

DEFAULTS: Dict[str, Any] = {
    "version": 1,
    "default_project": "inbox",
    "mode": "run",
    "terminal": "Terminal",
    "terminal_command": None,
    "claude_path": "claude",
    "permission_mode": "default",
    "model": None,
    "remote_control": True,
    "worktree": False,
    "keep_shell": True,
    "notify": True,
    "speak": False,
    "linger_seconds": 15,
    "max_task_chars": 4000,
    "dedupe_seconds": 20,
    "keep_jobs": 200,
    "fuzzy_threshold": 0.84,
    "path_env": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "projects": {
        "inbox": {"path": "~/tapclaude-inbox", "aliases": ["inbox", "scratch"]},
    },
    "stickers": {},
}

# Keys a project may override. Anything else in a project block is an error.
PROJECT_KEYS = ("path", "aliases", "permission_mode", "model", "worktree", "mode", "remote_control")


class ConfigError(Exception):
    """The config file exists but is invalid. ``problems`` lists every issue."""

    def __init__(self, problems: List[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


class ConfigMissing(Exception):
    pass


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    aliases: List[str]
    permission_mode: str
    model: Optional[str]
    worktree: bool
    mode: str
    remote_control: bool


@dataclass(frozen=True)
class Config:
    raw: Dict[str, Any]
    default_project: str
    mode: str
    terminal: str
    terminal_command: Optional[List[str]]
    claude_path: str
    permission_mode: str
    model: Optional[str]
    remote_control: bool
    worktree: bool
    keep_shell: bool
    notify: bool
    speak: bool
    linger_seconds: float
    max_task_chars: int
    dedupe_seconds: float
    keep_jobs: int
    fuzzy_threshold: float
    path_env: str
    projects: Dict[str, Project] = field(default_factory=dict)
    stickers: Dict[str, str] = field(default_factory=dict)

    def project(self, name: str) -> Project:
        return self.projects[name]


def default_raw() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULTS)


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path)))


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def parse(raw: Dict[str, Any]) -> Config:
    """Validate a raw dict and build a typed Config. Collects every problem."""
    problems: List[str] = []
    if not isinstance(raw, dict):
        raise ConfigError(["config must be a JSON object"])

    merged = default_raw()
    merged.pop("projects")
    merged.pop("stickers")
    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        problems.append("unknown setting(s): " + ", ".join(unknown))
    for k, v in raw.items():
        if k in merged:
            merged[k] = v

    def check(cond: bool, msg: str) -> None:
        if not cond:
            problems.append(msg)

    check(merged["mode"] in MODES, f"mode must be one of {', '.join(MODES)} (got {merged['mode']!r})")
    check(merged["terminal"] in TERMINALS, f"terminal must be one of {', '.join(TERMINALS)} (got {merged['terminal']!r})")
    check(
        merged["permission_mode"] in PERMISSION_MODES,
        f"permission_mode must be one of {', '.join(PERMISSION_MODES)} (got {merged['permission_mode']!r})",
    )
    tc = merged["terminal_command"]
    if merged["terminal"] == "custom":
        check(
            isinstance(tc, list) and tc and all(isinstance(x, str) for x in tc) and any("{script}" in x for x in tc),
            'terminal "custom" needs terminal_command: a list of strings containing "{script}"',
        )
    elif tc is not None:
        check(isinstance(tc, list) and all(isinstance(x, str) for x in tc), "terminal_command must be a list of strings or null")
    check(isinstance(merged["claude_path"], str) and merged["claude_path"].strip() != "", "claude_path must be a non-empty string")
    check(merged["model"] is None or (isinstance(merged["model"], str) and merged["model"].strip() != ""), "model must be a string or null")
    for key in ("remote_control", "worktree", "keep_shell", "notify", "speak"):
        check(_is_bool(merged[key]), f"{key} must be true or false")
    for key, lo, hi in (("linger_seconds", 0, 600), ("dedupe_seconds", 0, 3600), ("fuzzy_threshold", 0.5, 1.0)):
        v = merged[key]
        check(isinstance(v, (int, float)) and not _is_bool(v) and lo <= v <= hi, f"{key} must be a number between {lo} and {hi}")
    for key, lo, hi in (("max_task_chars", 20, 100_000), ("keep_jobs", 1, 100_000)):
        v = merged[key]
        check(isinstance(v, int) and not _is_bool(v) and lo <= v <= hi, f"{key} must be a whole number between {lo} and {hi}")
    check(isinstance(merged["path_env"], str), "path_env must be a string")

    projects: Dict[str, Project] = {}
    raw_projects = raw.get("projects", DEFAULTS["projects"])
    if not isinstance(raw_projects, dict) or not raw_projects:
        problems.append("projects must be an object with at least one project")
        raw_projects = {}
    seen_aliases: Dict[str, str] = {}
    for name, p in raw_projects.items():
        where = f"project {name!r}"
        if not isinstance(name, str) or not NAME_RE.match(name):
            problems.append(f"{where}: name must be lowercase letters, digits, '.', '_' or '-' (max 64)")
            continue
        if not isinstance(p, dict):
            problems.append(f"{where}: must be an object with at least a \"path\"")
            continue
        bad = sorted(set(p) - set(PROJECT_KEYS))
        if bad:
            problems.append(f"{where}: unknown key(s) {', '.join(bad)}")
        path = p.get("path")
        if not isinstance(path, str) or not path.strip():
            problems.append(f"{where}: \"path\" is required")
            continue
        expanded = _expand(path)
        if not expanded.is_absolute():
            problems.append(f"{where}: path must be absolute or start with ~ (got {path!r})")
        aliases = p.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) and a.strip() for a in aliases):
            problems.append(f"{where}: aliases must be a list of non-empty strings")
            aliases = []
        perm = p.get("permission_mode", merged["permission_mode"])
        if perm not in PERMISSION_MODES:
            problems.append(f"{where}: permission_mode must be one of {', '.join(PERMISSION_MODES)}")
        mode = p.get("mode", merged["mode"])
        if mode not in MODES:
            problems.append(f"{where}: mode must be one of {', '.join(MODES)}")
        model = p.get("model", merged["model"])
        if model is not None and not (isinstance(model, str) and model.strip()):
            problems.append(f"{where}: model must be a string or null")
        wt = p.get("worktree", merged["worktree"])
        rc = p.get("remote_control", merged["remote_control"])
        if not _is_bool(wt):
            problems.append(f"{where}: worktree must be true or false")
        if not _is_bool(rc):
            problems.append(f"{where}: remote_control must be true or false")
        for spoken in [name] + list(aliases):
            key = " ".join(spoken.lower().split())
            other = seen_aliases.get(key)
            if other and other != name:
                problems.append(f"alias {spoken!r} is used by both {other!r} and {name!r}")
            seen_aliases[key] = name
        projects[name] = Project(
            name=name,
            path=expanded,
            aliases=[a.strip() for a in aliases],
            permission_mode=perm,
            model=model,
            worktree=bool(wt),
            mode=mode,
            remote_control=bool(rc),
        )

    default = merged["default_project"]
    if raw_projects and default not in projects:
        problems.append(f"default_project {default!r} is not one of the projects ({', '.join(sorted(projects)) or 'none'})")

    stickers_raw = raw.get("stickers", {})
    stickers: Dict[str, str] = {}
    if not isinstance(stickers_raw, dict):
        problems.append("stickers must be an object mapping sticker name -> project name")
        stickers_raw = {}
    for s, target in stickers_raw.items():
        if not isinstance(s, str) or not NAME_RE.match(s):
            problems.append(f"sticker {s!r}: name must be lowercase letters, digits, '.', '_' or '-'")
        elif target not in projects:
            problems.append(f"sticker {s!r} points to unknown project {target!r}")
        else:
            stickers[s] = target

    if problems:
        raise ConfigError(problems)

    out = dict(merged)
    out["projects"] = raw_projects
    out["stickers"] = stickers_raw
    return Config(
        raw=out,
        default_project=default,
        mode=merged["mode"],
        terminal=merged["terminal"],
        terminal_command=tc,
        claude_path=os.path.expanduser(merged["claude_path"]),
        permission_mode=merged["permission_mode"],
        model=merged["model"],
        remote_control=merged["remote_control"],
        worktree=merged["worktree"],
        keep_shell=merged["keep_shell"],
        notify=merged["notify"],
        speak=merged["speak"],
        linger_seconds=float(merged["linger_seconds"]),
        max_task_chars=int(merged["max_task_chars"]),
        dedupe_seconds=float(merged["dedupe_seconds"]),
        keep_jobs=int(merged["keep_jobs"]),
        fuzzy_threshold=float(merged["fuzzy_threshold"]),
        path_env=merged["path_env"],
        projects=projects,
        stickers=stickers,
    )


def load_raw(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ConfigMissing(str(path))
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError([f"{path} is not valid JSON (line {e.lineno}, column {e.colno}: {e.msg})"])
    return data


def load(path: Path) -> Config:
    return parse(load_raw(path))


def save(path: Path, raw: Dict[str, Any]) -> Config:
    """Validate first, then write atomically with owner-only permissions."""
    cfg = parse(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".config-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg.raw, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return cfg
