"""Per-video fetch records on the archive drive. A record present means done."""
from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA_VERSION = 1
VIDEOS_DIR = "videos"


def videos_root(archive: Path) -> Path:
    return archive / VIDEOS_DIR


def video_dir(archive: Path, video_id: str) -> Path:
    return videos_root(archive) / video_id


def record_path(archive: Path, video_id: str) -> Path:
    return video_dir(archive, video_id) / f"{video_id}.fetch.json"


def read_record(archive: Path, video_id: str) -> dict | None:
    path = record_path(archive, video_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def write_record(archive: Path, video_id: str, record: dict) -> None:
    video_dir(archive, video_id).mkdir(parents=True, exist_ok=True)
    write_atomic_json(record_path(archive, video_id), record)


def done_ids(archive: Path) -> set[str]:
    root = videos_root(archive)
    if not root.is_dir():
        return set()
    return {d.name for d in root.iterdir()
            if d.is_dir() and (d / f"{d.name}.fetch.json").exists()}


def case_collision(archive: Path, video_id: str) -> str | None:
    """The name of an existing directory that equals video_id ignoring case only."""
    root = videos_root(archive)
    if not root.is_dir():
        return None
    for d in root.iterdir():
        if d.name != video_id and d.name.lower() == video_id.lower():
            return d.name
    return None


def summarize(archive: Path) -> tuple[int, int, int]:
    """(records_total, unavailable_total, captions_missing_total)."""
    total = unavailable = captions_missing = 0
    for video_id in done_ids(archive):
        record = read_record(archive, video_id) or {}
        total += 1
        if record.get("status") == "unavailable":
            unavailable += 1
        if "captions_missing" in record.get("warnings", []):
            captions_missing += 1
    return total, unavailable, captions_missing
