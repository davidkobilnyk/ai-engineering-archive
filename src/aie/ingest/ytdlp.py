"""Build and run the one yt-dlp call per video, and classify what came back."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_SELECTOR = (
    "ba[acodec^=opus][format_note*=original][format_id!$=-drc]/ba[acodec^=opus][format_id!$=-drc],"
    "ba[acodec^=mp4a][format_note*=original][format_id!$=-drc]/ba[acodec^=mp4a][format_id!$=-drc]"
)
ROW_PREFIX = "ROW\t"
PRINT_TEMPLATE = ("after_move:ROW\t%(format_id)s\t%(acodec)s\t%(abr)s\t"
                  "%(format_note)s\t%(language)s\t%(filepath)s")

# Substrings of stderr, checked in this order (spec section 8).
CHALLENGE = ("Sign in to confirm you're not a bot", "HTTP Error 429",
             "This content isn't available, try again later", "reCAPTCHA")
UNAVAILABLE = ("Video unavailable", "Private video", "This video has been removed",
               "members-only", "not available in your country")
EXTRACTOR = ("n challenge solving failed", "nsig extraction failed",
             "Requested format is not available", "Only images are available", "HTTP Error 403")


@dataclass
class Tools:
    yt_dlp: Path
    ffmpeg_dir: Path
    deno: Path

    @property
    def ffmpeg(self) -> Path:
        return self.ffmpeg_dir / "ffmpeg"

    @property
    def ffprobe(self) -> Path:
        return self.ffmpeg_dir / "ffprobe"


@dataclass
class Row:
    format_id: str
    acodec: str
    abr: float | None
    format_note: str
    language: str
    filepath: Path


@dataclass
class Outcome:
    kind: str  # ok | challenge | unavailable | extractor | transient
    exit_code: int
    rows: list[Row] = field(default_factory=list)
    message: str = ""


def build_command(tools: Tools, video_id: str, out_dir: Path, verbose: bool = False) -> list[str]:
    o = str(out_dir)
    cmd = [str(tools.yt_dlp),
           "-4", "--sleep-requests", "3", "--sleep-interval", "10", "--max-sleep-interval", "30",
           "--sleep-subtitles", "5", "--limit-rate", "4M", "--concurrent-fragments", "1",
           "--extractor-retries", "0", "--retries", "10", "--retry-sleep", "http:exp=1:60",
           "--fragment-retries", "10", "--abort-on-unavailable-fragments",
           "--no-playlist", "--no-overwrites", "--newline",
           "--js-runtimes", f"deno:{tools.deno}", "--ffmpeg-location", str(tools.ffmpeg_dir),
           "-f", AUDIO_SELECTOR,
           "--write-info-json", "--write-auto-subs", "--sub-langs", "en", "--sub-format", "json3",
           "-o", f"{o}/%(id)s.f%(format_id)s.%(ext)s",
           "-o", f"subtitle:{o}/%(id)s.%(ext)s",
           "-o", f"infojson:{o}/%(id)s.%(ext)s",
           "--print", PRINT_TEMPLATE]
    if verbose:
        cmd.append("-v")
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")
    return cmd


def parse_rows(stdout: str) -> list[Row]:
    rows = []
    for line in stdout.splitlines():
        if not line.startswith(ROW_PREFIX):
            continue
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        _, format_id, acodec, abr, note, language, path = parts
        try:
            abr_value: float | None = float(abr)
        except ValueError:
            abr_value = None
        rows.append(Row(format_id, acodec, abr_value, note, language, Path(path)))
    return rows


def rows_from_files(out_dir: Path, video_id: str, info: dict) -> list[Row]:
    """Rows for files already on disk (yt-dlp prints no after_move row for a
    file it skipped with --no-overwrites). Format fields come from info.json."""
    by_id = {f.get("format_id"): f for f in info.get("formats", [])}
    rows = []
    prefix = f"{video_id}.f"
    for file in sorted(out_dir.glob(f"{prefix}*")):
        if file.suffix in (".part", ".ytdl"):
            continue
        format_id = file.name[len(prefix):-len(file.suffix)]
        f = by_id.get(format_id, {})
        rows.append(Row(format_id, f.get("acodec", ""), f.get("abr"), f.get("format_note", ""),
                        f.get("language", "") or "", file))
    return rows


def classify(exit_code: int, stderr: str) -> str:
    if any(needle in stderr for needle in CHALLENGE):
        return "challenge"
    if exit_code == 0:
        return "ok"
    if any(needle in stderr for needle in UNAVAILABLE):
        return "unavailable"
    if any(needle in stderr for needle in EXTRACTOR):
        return "extractor"
    return "transient"


def last_error_line(stderr: str) -> str:
    lines = [l for l in stderr.splitlines() if l.strip()]
    for line in reversed(lines):
        if line.startswith("ERROR"):
            return line
    return lines[-1] if lines else ""


class Runner:
    """Runs yt-dlp and keeps the live process so a signal handler can stop it."""

    def __init__(self):
        self.current: subprocess.Popen | None = None

    def run(self, tools: Tools, video_id: str, out_dir: Path, log_path: Path,
            verbose: bool = False) -> Outcome:
        cmd = build_command(tools, video_id, out_dir, verbose)
        self.current = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = self.current.communicate()
        code = self.current.returncode
        self.current = None
        log_path.write_text(stderr)
        return Outcome(classify(code, stderr), code, parse_rows(stdout), last_error_line(stderr))

    def stop(self) -> None:
        if self.current is not None and self.current.poll() is None:
            self.current.terminate()


def version(tools: Tools) -> str:
    proc = subprocess.run([str(tools.yt_dlp), "--version"], capture_output=True, text=True)
    return proc.stdout.strip()
