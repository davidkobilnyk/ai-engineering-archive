"""The glanceable status.json on the archive root, and the healthchecks ping."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .records import write_atomic_json

STATUS_NAME = "status.json"


@dataclass
class Status:
    last_run_start: str | None = None
    last_run_end: str | None = None
    last_outcome: str | None = None
    last_success_time: str | None = None
    videos_completed_last_run: int = 0
    videos_failed_last_run: int = 0
    queue_depth: int = 0
    records_total: int = 0
    unavailable_total: int = 0
    captions_missing_total: int = 0
    yt_dlp_version: str | None = None
    backoff_until: str | None = None
    consecutive_challenges: int = 0
    last_error: str | None = None
    current_video: str | None = None

    @classmethod
    def load(cls, archive: Path) -> "Status":
        path = archive / STATUS_NAME
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()                  # unreadable status starts fresh; records are the truth
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, archive: Path) -> None:
        try:
            write_atomic_json(archive / STATUS_NAME, asdict(self))
        except OSError:
            pass  # the drive is the thing that is missing; nothing to write to


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ping(url: str | None, fail: bool = False) -> None:
    if not url:
        return
    target = url.rstrip("/") + ("/fail" if fail else "")
    try:
        httpx.get(target, timeout=10)
    except httpx.HTTPError:
        pass
