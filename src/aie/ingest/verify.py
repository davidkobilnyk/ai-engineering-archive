"""ffprobe, elementary-stream hash, and file hash checks on fetched files."""
from __future__ import annotations

import hashlib
import json
import re
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


@dataclass
class Decoded:
    duration_s: float  # from the decoded samples, not the container header
    mean_volume_db: float
    errors: list[str]  # ffmpeg error lines; any means damaged data somewhere


def decode_audio(ffmpeg: Path, file: Path, sample_rate: int, channels: int) -> Decoded:
    """Decode the whole first audio stream. ffprobe reads only the header, so a
    file cut short or damaged mid-way can still report its full duration."""
    cmd = [str(ffmpeg), "-nostats", "-hide_banner", "-loglevel", "level+info", "-i", str(file),
           "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    lines = proc.stderr.splitlines()
    errors = [l for l in lines if "[error]" in l or "[fatal]" in l]
    if proc.returncode != 0 and not errors:
        errors = [f"ffmpeg exit {proc.returncode}"]
    samples = [int(m.group(1)) for l in lines if (m := re.search(r"n_samples: (\d+)", l))]
    volumes = [float(m.group(1)) for l in lines if (m := re.search(r"mean_volume: (-?[\d.]+|-inf) dB", l))]
    if not samples or not volumes or not sample_rate or not channels:
        raise VerifyError(f"decode of {file.name} gave no sample count: {errors[:1]}")
    return Decoded(duration_s=round(samples[-1] / (sample_rate * channels), 3),
                   mean_volume_db=volumes[-1], errors=errors)


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
