"""Manage the iPhone's entry in ``~/.ssh/authorized_keys``.

The line nearsay writes looks like this::

    command="/Users/you/.nearsay/bin/nearsay-receive",restrict ssh-ed25519 AAAA… nearsay:iphone

* ``command=`` forces every login with this key to run the receiver and nothing
  else. Whatever the phone asks to run is ignored as a command and handed to the
  receiver as data in ``SSH_ORIGINAL_COMMAND``.
* ``restrict`` turns off port forwarding, agent forwarding, X11 forwarding,
  terminal (pty) allocation and ``~/.ssh/rc`` for this key.
* ``from=`` (optional) limits the key to addresses you choose, such as your home
  network or your Tailscale network.

The key is validated by decoding it, not just by pattern-matching, and a private
key pasted by mistake is rejected with a clear message.
"""

from __future__ import annotations

import base64
import ipaddress
import os
import re
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

MARK = "nearsay:"
KEY_TYPES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


class KeyError_(ValueError):
    """Raised for keys or options that must not be written."""


@dataclass(frozen=True)
class PublicKey:
    type: str
    blob: str
    comment: str


def parse_public_key(text: str) -> PublicKey:
    t = (text or "").strip()
    if "PRIVATE KEY" in t:
        raise KeyError_("That is a PRIVATE key. Share only the PUBLIC key from the Shortcuts app "
                        "(Run Script Over SSH → SSH Key → Share Public Key).")
    if not t:
        raise KeyError_("No key given. Copy the public key from the Shortcuts app first.")
    lines = [ln for ln in t.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) != 1:
        raise KeyError_("Expected exactly one public key line.")
    parts = lines[0].split(None, 2)
    if len(parts) < 2:
        raise KeyError_("A public key looks like: ssh-ed25519 AAAA… (type, then key data).")
    ktype, blob = parts[0], parts[1]
    comment = parts[2] if len(parts) > 2 else ""
    if ktype not in KEY_TYPES:
        raise KeyError_(f"Unsupported key type {ktype!r}. Supported: {', '.join(KEY_TYPES)}.")
    try:
        raw = base64.b64decode(blob, validate=True)
        (n,) = struct.unpack(">I", raw[:4])
        embedded = raw[4:4 + n].decode("ascii")
    except Exception:
        raise KeyError_("The key data is damaged (not valid base64 SSH key data). Copy it again.")
    if embedded != ktype:
        raise KeyError_(f"Key data says {embedded!r} but the line says {ktype!r}. Copy it again.")
    if len(raw) < 4 + n + 16:
        raise KeyError_("The key data is too short; it was probably cut off while copying.")
    return PublicKey(ktype, blob, comment)


def validate_sources(sources: Sequence[str]) -> List[str]:
    out = []
    for s in sources:
        s = s.strip()
        try:
            out.append(str(ipaddress.ip_network(s, strict=False)))
        except ValueError:
            raise KeyError_(f"{s!r} is not an IP address or network (example: 192.168.1.0/24 or 100.64.0.0/10).")
    return out


def build_line(receive_cmd: Path, key: PublicKey, label: str, sources: Sequence[str] = ()) -> str:
    cmd = str(receive_cmd)
    if any(c in cmd for c in '"\\\n\r'):
        raise KeyError_("The receiver path contains characters that cannot be used in authorized_keys.")
    if not LABEL_RE.match(label):
        raise KeyError_("Label must be letters, digits, '.', '_' or '-' (max 32).")
    opts = [f'command="{cmd}"', "restrict"]
    nets = validate_sources(sources)
    if nets:
        opts.append('from="' + ",".join(nets) + '"')
    return f"{','.join(opts)} {key.type} {key.blob} {MARK}{label}"


def _read(path: Path) -> List[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(prefix=".authorized_keys-", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _contains_blob(line: str, blob: str) -> bool:
    return re.search(r"(^|\s)" + re.escape(blob) + r"(\s|$)", line) is not None


def _label_of(line: str) -> Optional[str]:
    m = re.search(re.escape(MARK) + r"(\S+)\s*$", line)
    return m.group(1) if m else None


def add_key(path: Path, receive_cmd: Path, key: PublicKey, label: str = "iphone",
            sources: Sequence[str] = (), force: bool = False) -> Tuple[str, List[str]]:
    """Add or replace the nearsay line for ``label``. Returns (line, warnings)."""
    new_line = build_line(receive_cmd, key, label, sources)
    lines = _read(path)
    warnings: List[str] = []
    kept: List[str] = []
    for ln in lines:
        mine = _label_of(ln)
        if mine == label:
            continue  # replaced below
        if _contains_blob(ln, key.blob):
            if mine:
                warnings.append(f"Removed the same key from nearsay label {mine!r}.")
                continue
            if not force:
                raise KeyError_(
                    "This exact key is already in authorized_keys WITHOUT restrictions, which would let "
                    "it open a full shell on your Mac. Remove that line or re-run with --force to "
                    "replace it with the restricted nearsay line.")
            warnings.append("Replaced an unrestricted line holding the same key with the restricted line.")
            continue
        kept.append(ln)
    kept.append(new_line)
    _write(path, kept)
    return new_line, warnings


def remove_keys(path: Path, label: Optional[str] = None) -> int:
    lines = _read(path)
    kept = [ln for ln in lines if not (_label_of(ln) and (label is None or _label_of(ln) == label))]
    removed = len(lines) - len(kept)
    if removed:
        _write(path, kept)
    return removed


def list_keys(path: Path) -> List[Tuple[str, str, str]]:
    """(label, key type, short fingerprint-ish id) for each nearsay line."""
    out = []
    for ln in _read(path):
        label = _label_of(ln)
        if not label:
            continue
        m = re.search(r"\s(" + "|".join(re.escape(t) for t in KEY_TYPES) + r")\s(\S+)", ln)
        if m:
            out.append((label, m.group(1), m.group(2)[-12:]))
    return out
