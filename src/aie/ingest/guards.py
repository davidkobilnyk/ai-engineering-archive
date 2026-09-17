"""Fail-closed checks that run before any download (spec section 9)."""
from __future__ import annotations

import fcntl
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .records import VIDEOS_DIR

LOCAL_TZ = ZoneInfo("America/New_York")
CHARTER_ASNS = {20115, 11351, 7843, 20001, 12271}
LOCK_NAME = ".backfill.lock"


def parse_window(text: str) -> tuple[time, time]:
    """'01:00-07:00' -> (time(1, 0), time(7, 0)). Raises ValueError."""
    start, end = text.split("-")
    return time.fromisoformat(start), time.fromisoformat(end)


def in_window(now: datetime, start: time, end: time) -> bool:
    t = now.astimezone(LOCAL_TZ).time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end          # a window that crosses midnight


def window_end(now: datetime, start: time, end: time) -> datetime:
    """When the window that contains `now` closes, as an aware local datetime."""
    local = now.astimezone(LOCAL_TZ)
    end_dt = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if end_dt <= local:
        end_dt += timedelta(days=1)
    return end_dt


def run_text(cmd: list[str]) -> str | None:
    """stdout of a successful command, else None."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def on_mains() -> bool:
    out = run_text(["pmset", "-g", "batt"])
    return bool(out) and "AC Power" in out


def default_route_is_physical() -> bool:
    out = run_text(["route", "-n", "get", "default"])
    if not out:
        return False
    for line in out.splitlines():
        if line.strip().startswith("interface:"):
            return not line.split(":", 1)[1].strip().startswith("utun")
    return False


def public_ipv4() -> str | None:
    out = run_text(["dig", "-4", "+short", "TXT", "o-o.myaddr.l.google.com", "@ns1.google.com"])
    if not out:
        return None
    ip = out.strip().strip('"')
    return ip if ip.count(".") == 3 and ip.replace(".", "").isdigit() else None


def asn_of(ip: str) -> int | None:
    reversed_ip = ".".join(reversed(ip.split(".")))
    out = run_text(["dig", "+short", "TXT", f"{reversed_ip}.origin.asn.cymru.com"])
    if not out:
        return None
    try:
        return int(out.strip().strip('"').split("|")[0].strip())
    except ValueError:
        return None


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
    and the lock is held. Order and names follow spec section 9."""
    if not cfg.manual and not in_window(now, *cfg.window):
        return "skipped:window", None
    if cfg.backoff_until and now < cfg.backoff_until:
        return "skipped:backoff", None
    if not cfg.manual and not on_mains():
        return "skipped:power", None
    if not drive_ready(cfg.archive):
        return "skipped:drive", None
    if not default_route_is_physical():
        return "skipped:vpn", None
    ip = public_ipv4()
    asn = asn_of(ip) if ip else None
    if asn is None:
        return "skipped:asn-unknown", None
    if asn not in CHARTER_ASNS:
        return "skipped:asn", None
    fd = acquire_lock(cfg.archive)
    if fd is None:
        return "skipped:lock", None
    return None, fd
