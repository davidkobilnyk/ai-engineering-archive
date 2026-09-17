"""Fail-closed checks that run before any download."""
from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .records import VIDEOS_DIR

LOCAL_TZ = ZoneInfo("America/New_York")
LOCK_NAME = ".backfill.lock"


def parse_window(text: str) -> tuple[time, time]:
    """'01:00-07:00' -> (time(1, 0), time(7, 0)). Raises ValueError."""
    start, end = text.split("-")
    return time.fromisoformat(start), time.fromisoformat(end)


def window_end(now: datetime, start: time, end: time) -> datetime:
    """When the window that contains `now` closes, as an aware local datetime."""
    local = now.astimezone(LOCAL_TZ)
    end_dt = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if end_dt <= local:
        end_dt += timedelta(days=1)
    return end_dt


def drive_ready(archive: Path) -> bool:
    """A path under /Volumes must be a real mount point (an unplugged drive can
    leave a stale folder); any archive dir must be writable."""
    if str(archive).startswith("/Volumes/") and not os.path.ismount(archive):
        return False
    try:
        (archive / VIDEOS_DIR).mkdir(parents=True, exist_ok=True)
        probe = archive / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        return False
    return True


def acquire_lock(archive: Path) -> int | None:
    """flock on <archive>/.backfill.lock; None when another run holds it.
    The lock is released by the kernel when the process exits, however it exits."""
    fd = os.open(archive / LOCK_NAME, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode())
    return fd


@dataclass
class GuardConfig:
    archive: Path
    window: tuple[time, time]
    manual: bool                      # --now: skip the window and mains guards
    backoff_until: datetime | None


def check(cfg: GuardConfig, now: datetime) -> tuple[str | None, int | None]:
    """Return (skip_reason, lock_fd). A None reason means every guard passed
    and the lock is held."""
    if not drive_ready(cfg.archive):
        return "skipped:drive", None
    fd = acquire_lock(cfg.archive)
    if fd is None:
        return "skipped:lock", None
    return None, fd
