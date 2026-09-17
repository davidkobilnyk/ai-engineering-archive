"""The audio backfill run: queue, guards, per-video fetch and verify, status."""
from __future__ import annotations

import json
import os
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import guards, records, verify, ytdlp
from .status import Status, ping, utc_now_iso

DURATION_TOLERANCE_S = 2.0
MAX_CONSECUTIVE_FAILURES = 3


@dataclass
class Config:
    archive: Path
    ids: list[str]
    tools: ytdlp.Tools
    limit: int = 200
    manual: bool = False
    window: str = "01:00-07:00"
    dry_run: bool = False
    verbose: bool = False
    healthcheck_url: str | None = None


@dataclass
class RunResult:
    outcome: str  # success | skipped:<reason> | dry-run | challenge | error | interrupted
    completed: int = 0
    failed: int = 0
    remaining: int = 0
    exit_code: int = 0


def ids_from_talks_json(path: Path) -> list[str]:
    seen: set[str] = set()
    ids = []
    for talk in json.loads(path.read_text()):
        video_id = talk.get("videoId")
        if video_id and video_id not in seen:
            seen.add(video_id)
            ids.append(video_id)
    return ids


def ids_from_file(path: Path) -> list[str]:
    ids = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    return ids


def build_queue(archive: Path, ids: list[str]) -> list[str]:
    done = records.done_ids(archive)
    return [i for i in ids if i not in done]


def append_run_log(archive: Path, line: str) -> None:
    logs = archive / "logs"
    logs.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc)
    with (logs / f"backfill-{stamp:%Y-%m-%d}.log").open("a") as f:
        f.write(f"{stamp.isoformat(timespec='seconds')}\t{line}\n")


def audio_role(acodec: str) -> str | None:
    if acodec.startswith("opus"):
        return "opus"
    if acodec.startswith("mp4a"):
        return "aac"
    return None


def build_record(cfg: Config, video_id: str, out_dir: Path, rows: list[ytdlp.Row],
                 yt_dlp_version: str) -> dict:
    """Spec section 7: every check, then the record. Raises VerifyError."""
    info_path = out_dir / f"{video_id}.info.json"
    if not info_path.exists():
        raise verify.VerifyError("info.json missing")
    info = json.loads(info_path.read_text())
    duration = info.get("duration")
    if duration is None:
        raise verify.VerifyError("info.json has no duration")
    if not rows:
        rows = ytdlp.rows_from_files(out_dir, video_id, info)

    audio: dict[str, dict] = {}
    for row in rows:
        role = audio_role(row.acodec)
        if role is None:
            raise verify.VerifyError(f"unexpected codec {row.acodec!r} for format {row.format_id}")
        if role in audio:
            raise verify.VerifyError(f"two {role} rows")
        if not row.language.lower().startswith("en") or "original" not in row.format_note.lower():
            raise verify.VerifyError(
                f"wrong_track: format {row.format_id} is {row.language!r} {row.format_note!r}")
        file = row.filepath if row.filepath.is_absolute() else out_dir / row.filepath
        if not file.exists():
            raise verify.VerifyError(f"missing file {file.name}")
        if file.with_name(file.name + ".part").exists():
            raise verify.VerifyError(f"partial file beside {file.name}")
        probe = verify.ffprobe_audio(cfg.tools.ffprobe, file)
        if probe.codec != role:
            raise verify.VerifyError(f"{file.name}: codec {probe.codec}, expected {role}")
        if abs(probe.duration_s - float(duration)) > DURATION_TOLERANCE_S:
            raise verify.VerifyError(
                f"{file.name}: duration {probe.duration_s:.1f}s vs metadata {duration}s")
        audio[role] = {
            "format_id": row.format_id, "file": file.name, "bytes": file.stat().st_size,
            "codec": probe.codec, "abr_kbps": row.abr, "language": row.language,
            "format_note": row.format_note, "probe_duration_s": round(probe.duration_s, 3),
            "streamhash_sha256": verify.streamhash_sha256(cfg.tools.ffmpeg, file)}
    missing = {"opus", "aac"} - audio.keys()
    if missing:
        raise verify.VerifyError(f"missing audio: {', '.join(sorted(missing))}")

    warnings: list[str] = []
    captions = None
    caption_path = out_dir / f"{video_id}.en.json3"
    if caption_path.exists():
        events = json.loads(caption_path.read_text()).get("events")
        if not isinstance(events, list):
            raise verify.VerifyError("caption file has no events list")
        captions = {"file": caption_path.name, "bytes": caption_path.stat().st_size,
                    "sha256": verify.sha256_file(caption_path), "events": len(events)}
    else:
        warnings.append("captions_missing")

    return {
        "schema_version": records.SCHEMA_VERSION, "video_id": video_id, "status": "ok",
        "fetched_at": utc_now_iso(), "yt_dlp_version": yt_dlp_version,
        "duration_s": duration, "upload_date": info.get("upload_date"),
        "audio": audio, "captions": captions,
        "info_json": {"file": info_path.name, "bytes": info_path.stat().st_size,
                      "sha256": verify.sha256_file(info_path)},
        "warnings": warnings}


def process_video(cfg: Config, runner: ytdlp.Runner, video_id: str,
                  yt_dlp_version: str) -> tuple[str, str]:
    """Fetch and verify one video. Returns (kind, detail) where kind is
    ok | unavailable | challenge | extractor | transient | failed."""
    collision = records.case_collision(cfg.archive, video_id)
    if collision:
        return "failed", f"case_collision with existing directory {collision}"
    out_dir = records.video_dir(cfg.archive, video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    outcome = runner.run(cfg.tools, video_id, out_dir, out_dir / f"{video_id}.yt-dlp.log", cfg.verbose)
    if outcome.kind == "unavailable":
        records.write_record(cfg.archive, video_id, {
            "schema_version": records.SCHEMA_VERSION, "video_id": video_id,
            "status": "unavailable", "unavailable_reason": outcome.message,
            "fetched_at": utc_now_iso(), "yt_dlp_version": yt_dlp_version})
        return "unavailable", outcome.message
    if outcome.kind != "ok":
        return outcome.kind, outcome.message
    try:
        record = build_record(cfg, video_id, out_dir, outcome.rows, yt_dlp_version)
    except verify.VerifyError as e:
        return "failed", str(e)
    records.write_record(cfg.archive, video_id, record)
    return "ok", ""


def finish(cfg: Config, st: Status, result: RunResult) -> None:
    st.current_video = None
    result.remaining = len(build_queue(cfg.archive, cfg.ids))
    st.queue_depth = result.remaining
    st.records_total, st.unavailable_total, st.captions_missing_total = records.summarize(cfg.archive)
    st.last_run_end = utc_now_iso()
    st.last_outcome = result.outcome
    st.videos_completed_last_run = result.completed
    st.videos_failed_last_run = result.failed
    st.save(cfg.archive)


def run(cfg: Config, log=print) -> RunResult:
    now = datetime.now(timezone.utc)
    st = Status.load(cfg.archive) if cfg.archive.is_dir() else Status()
    window = guards.parse_window(cfg.window)
    backoff = datetime.fromisoformat(st.backoff_until) if st.backoff_until else None
    reason, lock_fd = guards.check(guards.GuardConfig(cfg.archive, window, cfg.manual, backoff), now)
    if reason:
        log(reason)
        st.last_run_start = st.last_run_end = utc_now_iso()
        st.last_outcome = reason
        st.save(cfg.archive)
        return RunResult(outcome=reason)

    try:
        st.yt_dlp_version = ytdlp.version(cfg.tools)
        queue = build_queue(cfg.archive, cfg.ids)
        batch = queue[:cfg.limit]
        if cfg.dry_run:
            for video_id in batch:
                log(video_id)
            log(f"dry run: {len(batch)} of {len(queue)} queued videos would be fetched")
            return RunResult(outcome="dry-run", remaining=len(queue))

        st.last_run_start = utc_now_iso()
        st.last_outcome = "running"
        st.videos_completed_last_run = st.videos_failed_last_run = 0
        st.queue_depth = len(queue)
        st.save(cfg.archive)
        append_run_log(cfg.archive, f"run start\tqueue {len(queue)}\tbatch {len(batch)}")

        runner = ytdlp.Runner()
        stop = {"requested": False}

        def on_signal(signum, frame):
            stop["requested"] = True
            runner.stop()

        previous = {s: signal.signal(s, on_signal) for s in (signal.SIGTERM, signal.SIGINT)}
        result = RunResult(outcome="success")
        consecutive_failures = 0
        end = None if cfg.manual else guards.window_end(now, *window)
        try:
            for i, video_id in enumerate(batch, 1):
                if stop["requested"]:
                    break
                if end is not None and datetime.now(guards.LOCAL_TZ) >= end:
                    log("window ended; not starting another video")
                    break
                st.current_video = video_id
                st.save(cfg.archive)
                log(f"[{i}/{len(batch)}] {video_id}")
                kind, detail = process_video(cfg, runner, video_id, st.yt_dlp_version)
                append_run_log(cfg.archive, f"{video_id}\t{kind}\t{detail}")
                if stop["requested"]:
                    result.outcome = "interrupted"
                    result.exit_code = 1
                    if kind not in ("ok", "unavailable"):
                        break
                if kind in ("ok", "unavailable"):
                    result.completed += 1
                    consecutive_failures = 0
                    st.consecutive_challenges = 0
                    st.last_success_time = utc_now_iso()
                else:
                    result.failed += 1
                    consecutive_failures += 1
                    st.last_error = f"{video_id}: {detail}"
                    log(f"  {kind}: {detail}")
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        result.outcome, result.exit_code = "error", 1
                        ping(cfg.healthcheck_url, fail=True)
                        break
                st.videos_completed_last_run = result.completed
                st.videos_failed_last_run = result.failed
                st.save(cfg.archive)
                if result.outcome == "interrupted":
                    break
        finally:
            for s, handler in previous.items():
                signal.signal(s, handler)
        finish(cfg, st, result)
        append_run_log(cfg.archive, f"run end\t{result.outcome}\tcompleted {result.completed}\tfailed {result.failed}")
        if result.outcome == "success":
            ping(cfg.healthcheck_url)
        return result
    finally:
        os.close(lock_fd)
