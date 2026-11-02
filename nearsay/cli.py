"""The ``nearsay`` command."""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

from . import __version__, doctor, jobs, keys, launchagent, receive
from .config import (MODES, PERMISSION_MODES, TERMINALS, ConfigError, ConfigMissing, NAME_RE, default_raw,
                     load, load_raw, save)
from .dispatch import Dispatcher
from .launcher import default_runner
from .paths import Paths, default_paths
from .router import route
from .text import preview

SETTABLE = {
    "mode": "one of " + ", ".join(MODES),
    "terminal": "one of " + ", ".join(TERMINALS),
    "terminal_command": 'JSON list, e.g. ["open","-na","MyTerm","--args","-e","{script}"]',
    "claude_path": "absolute path to the claude binary",
    "permission_mode": "one of " + ", ".join(PERMISSION_MODES),
    "model": "model alias or full name, or none",
    "remote_control": "true/false",
    "worktree": "true/false",
    "keep_shell": "true/false",
    "notify": "true/false",
    "speak": "true/false",
    "linger_seconds": "number",
    "max_task_chars": "whole number",
    "dedupe_seconds": "number",
    "keep_jobs": "whole number",
    "fuzzy_threshold": "number between 0.5 and 1",
    "default_project": "a project name",
    "path_env": "PATH used by the dispatcher",
}


def _print(*a: Any) -> None:
    print(*a)


def _err(msg: str) -> int:
    print(f"✗ {msg}", file=sys.stderr)
    return 1


def _short_home(p: Path) -> str:
    home = str(Path.home())
    s = str(p)
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


def _load_raw_or_default(paths: Paths) -> dict:
    try:
        return load_raw(paths.config)
    except ConfigMissing:
        raise SystemExit(_err("No config yet. Run: nearsay init"))


def _save(paths: Paths, raw: dict) -> int:
    try:
        save(paths.config, raw)
    except ConfigError as e:
        for p in e.problems:
            _err(p)
        return 1
    return 0


def _parse_value(key: str, value: str) -> Any:
    v = value.strip()
    low = v.lower()
    if key == "terminal_command":
        if low in ("none", "null", ""):
            return None
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            raise SystemExit(_err('terminal_command must be a JSON list, e.g. ["open","-na","X","--args","-e","{script}"]'))
    if low in ("true", "on", "yes"):
        return True
    if low in ("false", "off", "no"):
        return False
    if low in ("none", "null"):
        return None
    if key in ("linger_seconds", "dedupe_seconds", "fuzzy_threshold"):
        try:
            return float(v)
        except ValueError:
            raise SystemExit(_err(f"{key} needs a number"))
    if key in ("max_task_chars", "keep_jobs"):
        try:
            return int(v)
        except ValueError:
            raise SystemExit(_err(f"{key} needs a whole number"))
    if key == "claude_path":
        return os.path.abspath(os.path.expanduser(v)) if "/" in v or v.startswith("~") else v
    return v


# ---------------------------------------------------------------- commands

def cmd_init(a, paths: Paths) -> int:
    paths.ensure()
    if paths.config.exists() and not a.force:
        _print(f"✓ Config already exists: {paths.config} (use --force to start over)")
        return 0
    raw = default_raw()
    inbox = Path(os.path.expanduser(a.default_path or "~/nearsay-inbox")).absolute()
    raw["projects"] = {"inbox": {"path": _short_home(inbox), "aliases": ["inbox", "scratch"]}}
    if a.terminal:
        raw["terminal"] = a.terminal
    if a.claude_path:
        raw["claude_path"] = a.claude_path
        claude_dir = os.path.dirname(a.claude_path)
        raw["path_env"] = launchagent.default_path_env([claude_dir])
    if _save(paths, raw):
        return 1
    if not inbox.exists():
        inbox.mkdir(parents=True)
        (inbox / "README.md").write_text(
            "# nearsay inbox\n\nTasks you speak without naming a project start here.\n"
            "Add real projects with `nearsay project add <name> <path>`.\n", encoding="utf-8")
    _print(f"✓ Wrote {paths.config}")
    _print(f"✓ Default project 'inbox' → {inbox}")
    return 0


def cmd_project(a, paths: Paths) -> int:
    raw = _load_raw_or_default(paths)
    projects = raw.setdefault("projects", {})
    if a.action == "list":
        cfg = load(paths.config)
        for name, p in sorted(cfg.projects.items()):
            star = "*" if name == cfg.default_project else " "
            exists = "" if p.path.is_dir() else "  (folder missing!)"
            stickers = [s for s, t in cfg.stickers.items() if t == name]
            bits = [f"mode={p.mode}", f"permissions={p.permission_mode}"]
            if p.model:
                bits.append(f"model={p.model}")
            if p.worktree:
                bits.append("worktree")
            if not p.remote_control:
                bits.append("no-remote-control")
            if p.aliases:
                bits.append("aliases=" + "|".join(p.aliases))
            if stickers:
                bits.append("stickers=" + "|".join(stickers))
            _print(f"{star} {name:<16} {_short_home(p.path)}{exists}\n    {'  '.join(bits)}")
        return 0
    name = a.name.lower()
    if a.action == "add":
        if not NAME_RE.match(name):
            return _err("Project names use lowercase letters, digits, '.', '_' or '-'.")
        path = Path(os.path.expanduser(a.path)).absolute()
        entry = dict(projects.get(name, {}))
        entry["path"] = _short_home(path)
        if a.alias:
            entry["aliases"] = sorted(set(entry.get("aliases", [])) | {x.strip() for x in a.alias if x.strip()})
        for key in ("permission_mode", "model", "mode"):
            val = getattr(a, key)
            if val is not None:
                if key == "model" and val.lower() in ("none", "default"):
                    entry.pop("model", None)
                else:
                    entry[key] = val
        if a.worktree is not None:
            entry["worktree"] = a.worktree
        if a.remote_control is not None:
            entry["remote_control"] = a.remote_control
        projects[name] = entry
        if a.default:
            raw["default_project"] = name
        if _save(paths, raw):
            return 1
        _print(f"✓ Project {name} → {path}" + ("  (default)" if a.default else ""))
        if not path.is_dir():
            _print(f"⚠ {path} does not exist yet; create it before tapping.")
        return 0
    if a.action == "remove":
        if name not in projects:
            return _err(f"No project named {name!r}.")
        if raw.get("default_project", "inbox") == name:
            return _err("That is the default project. Pick another first: nearsay project default <name>")
        projects.pop(name)
        raw["stickers"] = {s: t for s, t in raw.get("stickers", {}).items() if t != name}
        if _save(paths, raw):
            return 1
        _print(f"✓ Removed project {name} (its folder was not touched)")
        return 0
    if a.action == "default":
        raw["default_project"] = name
        if _save(paths, raw):
            return 1
        _print(f"✓ Default project is now {name}")
        return 0
    return _err("unknown action")


def cmd_sticker(a, paths: Paths) -> int:
    raw = _load_raw_or_default(paths)
    stickers = raw.setdefault("stickers", {})
    if a.action == "list":
        if not stickers:
            _print("No named stickers. Any sticker works; name one with: nearsay sticker add desk <project>")
        for s, t in sorted(stickers.items()):
            _print(f"{s:<16} → {t}")
        return 0
    if a.action == "add":
        stickers[a.name.lower()] = a.project.lower()
        if _save(paths, raw):
            return 1
        _print(f"✓ Sticker {a.name.lower()} → {a.project.lower()}. Put \"tap {a.name.lower()}\" in that "
               "sticker's Shortcut Script field (see: nearsay phone).")
        return 0
    if a.action == "remove":
        if stickers.pop(a.name.lower(), None) is None:
            return _err(f"No sticker named {a.name!r}.")
        if _save(paths, raw):
            return 1
        _print(f"✓ Removed sticker {a.name.lower()}")
        return 0
    return _err("unknown action")


def cmd_set(a, paths: Paths) -> int:
    if a.key not in SETTABLE:
        return _err(f"Unknown setting {a.key!r}. Settable: {', '.join(sorted(SETTABLE))}")
    raw = _load_raw_or_default(paths)
    raw[a.key] = _parse_value(a.key, a.value)
    if _save(paths, raw):
        return 1
    _print(f"✓ {a.key} = {json.dumps(raw[a.key])}")
    if a.key in ("path_env", "claude_path"):
        _print("  Re-run ./install.sh (or nearsay install-agent) so the dispatcher picks up the new PATH.")
    return 0


def cmd_show_config(a, paths: Paths) -> int:
    raw = _load_raw_or_default(paths)
    _print(json.dumps(raw, indent=2, ensure_ascii=False))
    return 0


def _read_clipboard() -> str:
    try:
        return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        raise SystemExit(_err("Could not read the clipboard (pbpaste). Paste the key as an argument instead."))


def cmd_add_key(a, paths: Paths, home: Optional[Path] = None) -> int:
    if a.from_clipboard:
        text = _read_clipboard()
    elif a.key:
        text = " ".join(a.key)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        return _err("Give the key: nearsay add-key --from-clipboard   (or paste it after add-key)")
    ak = (home or Path.home()) / ".ssh" / "authorized_keys"
    try:
        pk = keys.parse_public_key(text)
        line, warnings = keys.add_key(ak, paths.receive_cmd, pk, a.label, a.allow_from or (), force=a.force)
    except keys.KeyError_ as e:
        return _err(str(e))
    for w in warnings:
        _print(f"⚠ {w}")
    _print(f"✓ Added {pk.type} key as {a.label!r} to {ak}")
    _print("  This key can only queue tasks for nearsay: no shell, no forwarding, no terminal.")
    if a.allow_from:
        _print(f"  Accepted only from: {', '.join(keys.validate_sources(a.allow_from))}")
    return 0


def cmd_remove_key(a, paths: Paths, home: Optional[Path] = None) -> int:
    ak = (home or Path.home()) / ".ssh" / "authorized_keys"
    n = keys.remove_keys(ak, a.label)
    _print(f"✓ Removed {n} nearsay key line(s)" + (f" labelled {a.label!r}" if a.label else ""))
    return 0


def cmd_keys(a, paths: Paths, home: Optional[Path] = None) -> int:
    ak = (home or Path.home()) / ".ssh" / "authorized_keys"
    entries = keys.list_keys(ak)
    if not entries:
        _print("No nearsay keys. Add one: nearsay add-key --from-clipboard")
    for label, ktype, tail in entries:
        _print(f"{label:<12} {ktype:<22} …{tail}")
    return 0


def cmd_route(a, paths: Paths) -> int:
    cfg = load(paths.config)
    hint = receive.parse_hint(a.sticker or "", cfg)
    if hint.error:
        return _err(hint.error)
    from .text import normalize_task
    r = route(normalize_task(a.text), cfg, hint.project)
    _print(f"project : {r.project}")
    _print(f"why     : {r.matched_by}" + (f" (heard “{r.heard_as}”, score {r.score:.2f})" if r.heard_as else ""))
    _print(f"task    : {r.task or '(empty!)'}")
    return 0


def cmd_test(a, paths: Paths) -> int:
    captured: List[jobs.Job] = []
    out = io.StringIO()
    env = {"SSH_ORIGINAL_COMMAND": a.sticker or ""}
    receive.run(io.BytesIO(a.text.encode("utf-8")), env, out, paths=paths, source="local", capture=captured)
    _print("Phone would show: " + out.getvalue().strip())
    if not captured:
        return 1
    job = captured[0]
    if a.no_launch:
        # Take it back out of the queue so nothing starts.
        q = paths.queue / f"{job.id}.json"
        d = jobs.claim(paths, q)
        if d:
            jobs.write_status(d, "skipped", "nearsay test --no-launch")
        _print("Not launched (--no-launch).")
        return 0
    if a.now or platform.system() != "Darwin" or not launchagent.is_loaded(default_runner):
        Dispatcher(paths).run(linger=0)
    deadline = time.time() + 15
    while time.time() < deadline:
        st = jobs.read_status(paths.jobs / job.id)
        if st.get("status") not in (None, "pending"):
            mark = "✓" if st["status"] == "launched" else "✗"
            _print(f"Mac result: {mark} {st['status']}: {st.get('detail', '')}")
            return 0 if st["status"] == "launched" else 1
        time.sleep(0.3)
    return _err("No result after 15 s. Is the dispatcher agent loaded? Run: nearsay doctor")


def cmd_log(a, paths: Paths) -> int:
    rows = jobs.recent(paths, a.n)
    if not rows:
        _print("No tasks yet.")
        return 0
    for d in rows:
        job = jobs.read_job(d)
        st = jobs.read_status(d)
        if not job:
            _print(f"{d.name}  (unreadable)")
            continue
        when = job.created_at.replace("T", " ")[:19]
        _print(f"{when}  {st.get('status', '?'):<9} {job.project:<14} {job.mode:<10} {preview(job.task, 60)}")
        if st.get("status") == "failed":
            _print(f"{'':21}└ {st.get('detail', '')}")
    return 0


def cmd_show(a, paths: Paths) -> int:
    matches = [d for d in jobs.job_dirs(paths) if d.name.startswith(a.id) or d.name.endswith(a.id)]
    if not matches:
        return _err(f"No job matching {a.id!r}. See: nearsay log")
    d = matches[-1]
    job = jobs.read_job(d)
    _print(json.dumps({"job": job.__dict__ if job else None, "status": jobs.read_status(d), "folder": str(d)},
                      indent=2, ensure_ascii=False))
    return 0


def _try(argv: List[str]) -> str:
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        return cp.stdout.strip() if cp.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def cmd_phone(a, paths: Paths) -> int:
    user = getpass.getuser()
    local = _try(["scutil", "--get", "LocalHostName"])
    host = f"{local}.local" if local else platform.node()
    lan = _try(["ipconfig", "getifaddr", "en0"]) or _try(["ipconfig", "getifaddr", "en1"])
    ts_cli = shutil.which("tailscale") or "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    ts = _try([ts_cli, "ip", "-4"]).splitlines()[0] if os.path.exists(ts_cli) or shutil.which("tailscale") else ""
    _print("Values for the Shortcut's “Run Script Over SSH” action:\n")
    _print(f"  Host            {host}")
    if lan:
        _print(f"                  (or this Mac's current Wi‑Fi address: {lan})")
    if ts:
        _print(f"                  (or, away from home over Tailscale: {ts})")
    _print("  Port            22")
    _print(f"  User            {user}")
    _print("  Authentication  SSH Key")
    _print("  Input           Dictated Text")
    _print("  Script          tap   (or: tap <sticker-name> to route that sticker to one project)")
    try:
        cfg = load(paths.config)
        if cfg.stickers:
            _print("\nYour named stickers (one NFC automation each):")
            for s, t in sorted(cfg.stickers.items()):
                _print(f"  Script “tap {s}”  → {t}")
        spoken = []
        for name, p in sorted(cfg.projects.items()):
            others = [x for x in p.aliases if x.lower() != name]
            spoken.append(f"“In {name}, …”" + (f"  (also heard as: {', '.join(others)})" if others else ""))
        _print("\nSay one of these at the start to pick a project by voice:")
        for s in spoken:
            _print(f"  {s}")
    except (ConfigMissing, ConfigError):
        pass
    _print("\nFull walkthrough: docs/IPHONE.md")
    return 0


def cmd_install_agent(a, paths: Paths) -> int:
    try:
        cfg = load(paths.config)
        path_env = cfg.path_env
        claude_dir = os.path.dirname(cfg.claude_path) if "/" in cfg.claude_path else ""
    except (ConfigMissing, ConfigError):
        path_env, claude_dir = launchagent.default_path_env(), ""
    if claude_dir and claude_dir not in path_env.split(":"):
        path_env = claude_dir + ":" + path_env
    plist = launchagent.plist_path()
    launchagent.write(plist, launchagent.build(paths, path_env))
    _print(f"✓ Wrote {plist}")
    if os.environ.get("NEARSAY_SKIP_LAUNCHD") == "1" or platform.system() != "Darwin":
        _print("  (launchd step skipped)")
        return 0
    cp = launchagent.load(default_runner, plist)
    if cp.returncode != 0:
        return _err(f"launchctl bootstrap failed: {(cp.stderr or cp.stdout).strip()}")
    _print("✓ Dispatcher agent loaded (it sleeps until a task arrives)")
    return 0


def cmd_uninstall(a, paths: Paths) -> int:
    if not a.yes:
        ans = input("Remove the nearsay agent and phone key? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            _print("Cancelled.")
            return 1
    if platform.system() == "Darwin":
        launchagent.unload(default_runner)
    plist = launchagent.plist_path()
    if plist.exists():
        plist.unlink()
        _print(f"✓ Removed {plist}")
    n = keys.remove_keys(Path.home() / ".ssh" / "authorized_keys")
    _print(f"✓ Removed {n} phone key line(s) from ~/.ssh/authorized_keys")
    link = Path.home() / ".local" / "bin" / "nearsay"
    if link.is_symlink() and os.path.realpath(link) == os.path.realpath(paths.cli_cmd):
        link.unlink()
        _print(f"✓ Removed {link}")
    if a.purge:
        shutil.rmtree(paths.root, ignore_errors=True)
        _print(f"✓ Deleted {paths.root}")
    else:
        _print(f"  Kept {paths.root} (config and task history). Delete it with --purge.")
    _print("  Your projects were not touched. Turn Remote Login off in System Settings if you no longer need it,")
    _print("  and delete the NFC automation in the Shortcuts app on your phone.")
    return 0


def cmd_doctor(a, paths: Paths) -> int:
    checks = doctor.run_checks(paths, default_runner)
    _print(doctor.format_checks(checks))
    return 1 if any(c.status == doctor.FAIL for c in checks) else 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nearsay",
                                description="Tap an NFC sticker, speak a task, start Claude Code on this Mac.")
    p.add_argument("--version", action="version", version=f"nearsay {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    s = sub.add_parser("init", help="create the config and the default 'inbox' project")
    s.add_argument("--default-path", help="folder for the default project (default ~/nearsay-inbox)")
    s.add_argument("--terminal", choices=TERMINALS)
    s.add_argument("--claude-path", help="absolute path to claude")
    s.add_argument("--force", action="store_true", help="overwrite an existing config")

    s = sub.add_parser("project", help="add, remove, list projects or pick the default")
    ps = s.add_subparsers(dest="action", metavar="action", required=True)
    ps.add_parser("list", help="list projects")
    pa = ps.add_parser("add", help="add or update a project")
    pa.add_argument("name")
    pa.add_argument("path")
    pa.add_argument("--alias", action="append", help="another spoken name (repeatable), e.g. how dictation spells it")
    pa.add_argument("--permission-mode", choices=PERMISSION_MODES)
    pa.add_argument("--model")
    pa.add_argument("--mode", choices=MODES)
    pa.add_argument("--worktree", dest="worktree", action="store_true", default=None,
                    help="start each tapped task in its own git worktree")
    pa.add_argument("--no-worktree", dest="worktree", action="store_false")
    pa.add_argument("--remote-control", dest="remote_control", action="store_true", default=None)
    pa.add_argument("--no-remote-control", dest="remote_control", action="store_false")
    pa.add_argument("--default", action="store_true", help="make this the default project")
    pr = ps.add_parser("remove", help="remove a project from the config (folder untouched)")
    pr.add_argument("name")
    pd = ps.add_parser("default", help="set the default project")
    pd.add_argument("name")

    s = sub.add_parser("sticker", help="name a sticker and pin it to a project")
    ss = s.add_subparsers(dest="action", metavar="action", required=True)
    ss.add_parser("list")
    sa = ss.add_parser("add")
    sa.add_argument("name")
    sa.add_argument("project")
    sr = ss.add_parser("remove")
    sr.add_argument("name")

    s = sub.add_parser("set", help="change a setting (see: nearsay set --help)",
                       epilog="\n".join(f"  {k:<16} {v}" for k, v in SETTABLE.items()),
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    s.add_argument("key")
    s.add_argument("value")
    sub.add_parser("config", help="print the current config")

    s = sub.add_parser("add-key", help="authorize the iPhone's public key (restricted to nearsay)")
    s.add_argument("key", nargs="*", help="the public key line (or use --from-clipboard)")
    s.add_argument("--from-clipboard", action="store_true", help="read the key from the clipboard (pbpaste)")
    s.add_argument("--label", default="iphone", help="name for this device (default: iphone)")
    s.add_argument("--allow-from", action="append", metavar="CIDR",
                   help="only accept this key from these addresses, e.g. 192.168.1.0/24 (repeatable)")
    s.add_argument("--force", action="store_true", help="replace an unrestricted line holding the same key")
    s = sub.add_parser("remove-key", help="remove nearsay key lines")
    s.add_argument("--label")
    sub.add_parser("keys", help="list authorized nearsay keys")

    s = sub.add_parser("route", help="show which project a sentence would go to (nothing is launched)")
    s.add_argument("text")
    s.add_argument("--sticker", help="pretend this sticker was tapped")

    s = sub.add_parser("test", help="send a task through the whole Mac-side pipeline, as if from the phone")
    s.add_argument("text")
    s.add_argument("--sticker", help="pretend this sticker was tapped")
    s.add_argument("--now", action="store_true", help="dispatch in this process instead of via launchd")
    s.add_argument("--no-launch", action="store_true", help="route and queue only; start nothing")

    s = sub.add_parser("log", help="recent tasks")
    s.add_argument("-n", type=int, default=15)
    s = sub.add_parser("show", help="details of one task")
    s.add_argument("id")
    sub.add_parser("doctor", help="check the whole setup and say how to fix problems")
    sub.add_parser("phone", help="print the values to type into the iPhone Shortcut")
    sub.add_parser("install-agent", help="(re)write and load the launchd dispatcher agent")
    s = sub.add_parser("uninstall", help="remove the agent and phone key")
    s.add_argument("--purge", action="store_true", help="also delete ~/.nearsay")
    s.add_argument("--yes", action="store_true")
    sub.add_parser("receive", help=argparse.SUPPRESS)
    sub.add_parser("dispatch", help=argparse.SUPPRESS)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["receive"]:
        return receive.main()
    if argv[:1] == ["dispatch"]:
        from .dispatch import main as dispatch_main
        return dispatch_main()
    parser = build_parser()
    a = parser.parse_args(argv)
    if not a.cmd:
        parser.print_help()
        return 0
    paths = default_paths()
    handlers = {
        "init": cmd_init, "project": cmd_project, "sticker": cmd_sticker, "set": cmd_set,
        "config": cmd_show_config, "add-key": cmd_add_key, "remove-key": cmd_remove_key, "keys": cmd_keys,
        "route": cmd_route, "test": cmd_test, "log": cmd_log, "show": cmd_show, "doctor": cmd_doctor,
        "phone": cmd_phone, "install-agent": cmd_install_agent, "uninstall": cmd_uninstall,
    }
    try:
        return handlers[a.cmd](a, paths)
    except ConfigMissing:
        return _err("No config yet. Run: nearsay init")
    except ConfigError as e:
        for prob in e.problems:
            _err(prob)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
