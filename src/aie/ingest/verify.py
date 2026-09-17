"""ffprobe, elementary-stream hash, and file hash checks on fetched files."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class VerifyError(Exception):
    """A fetched file failed a check; the video gets no record."""


@dataclass
class Probe:
    codec: str
    duration_s: float
    sample_rate: int
    channels: int


def ffprobe_audio(ffprobe: Path, file: Path) -> Probe:
    cmd = [str(ffprobe), "-v", "error", "-select_streams", "a:0",
           "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
           "-of", "json", str(file)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise VerifyError(f"ffprobe failed on {file.name}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    if not streams or "format" not in data:
        raise VerifyError(f"no audio stream in {file.name}")
    stream = streams[0]
    return Probe(codec=stream.get("codec_name", ""),
                 duration_s=float(data["format"].get("duration", "nan")),
                 sample_rate=int(stream.get("sample_rate", 0)),
                 channels=int(stream.get("channels", 0)))


def streamhash_sha256(ffmpeg: Path, file: Path) -> str:
    """sha256 of the elementary audio stream, invariant to a lossless remux."""
    cmd = [str(ffmpeg), "-v", "error", "-i", str(file), "-map", "0:a:0", "-c", "copy",
           "-f", "streamhash", "-hash", "sha256", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise VerifyError(f"streamhash failed on {file.name}: {proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        if "SHA256=" in line:
            return line.split("SHA256=", 1)[1].strip().lower()
    raise VerifyError(f"streamhash printed no hash for {file.name}")


def sha256_file(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
