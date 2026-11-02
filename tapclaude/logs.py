"""Append-only JSON-lines logs with simple size-based rotation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_BYTES = 1_000_000


def log(path: Path, event: str, **fields: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            os.replace(path, path.with_suffix(path.suffix + ".1"))
        record = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event}
        record.update(fields)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass  # logging must never break a tap
