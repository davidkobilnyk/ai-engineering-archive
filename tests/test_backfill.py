"""Seam tests for `aie backfill`. Every test runs the real command in a subprocess
against a temp archive with fake yt-dlp/pmset/route/dig on PATH and real ffmpeg.

Expected values are literals from tests/fixtures/audio/README.md and
tests/fixtures/talks.json.
"""
import json

from conftest import run_backfill, ytdlp_calls

OPUS_STREAMHASH = "e80bf0d53e2e9756c2a0dcf16a486493e917cacf4cb57adcadc9394eac2d7eb4"
AAC_STREAMHASH = "4025563f21c80dda474e195f5b8d3c8b5165b31a17af5c477114d401dce81957"


def read_status(archive):
    return json.loads((archive / "status.json").read_text())


def read_record(archive, video_id):
    return json.loads((archive / "videos" / video_id / f"{video_id}.fetch.json").read_text())


def watch_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


# ---------------------------------------------------------------- tracer bullet

def test_tracer_two_ids_fetched_verified_recorded_then_skipped(archive):
    first = run_backfill("--now", "--ids", "knDDGYHnnSI", "am_oeAoUhew", archive=archive)
    assert first.returncode == 0, first.stderr

    for vid in ("knDDGYHnnSI", "am_oeAoUhew"):
        d = archive / "videos" / vid
        assert sorted(p.name for p in d.iterdir()) == [
            f"{vid}.en.json3", f"{vid}.f140.m4a", f"{vid}.f251.webm",
            f"{vid}.fetch.json", f"{vid}.info.json", f"{vid}.yt-dlp.log"]
        rec = read_record(archive, vid)
        assert rec["schema_version"] == 1
        assert rec["video_id"] == vid
        assert rec["status"] == "ok"
        assert rec["yt_dlp_version"] == "2026.08.19"
        assert rec["duration_s"] == 1
        assert rec["upload_date"] == "20240828"
        assert rec["audio"]["opus"]["format_id"] == "251"
        assert rec["audio"]["opus"]["file"] == f"{vid}.f251.webm"
        assert rec["audio"]["opus"]["codec"] == "opus"
        assert rec["audio"]["opus"]["bytes"] == 1010
        assert rec["audio"]["opus"]["language"] == "en-US"
        assert rec["audio"]["opus"]["streamhash_sha256"] == OPUS_STREAMHASH
        assert rec["audio"]["aac"]["format_id"] == "140"
        assert rec["audio"]["aac"]["file"] == f"{vid}.f140.m4a"
        assert rec["audio"]["aac"]["codec"] == "aac"
        assert rec["audio"]["aac"]["bytes"] == 1271
        assert rec["audio"]["aac"]["streamhash_sha256"] == AAC_STREAMHASH
        assert rec["captions"]["file"] == f"{vid}.en.json3"
        assert rec["captions"]["events"] == 1
        assert rec["info_json"]["file"] == f"{vid}.info.json"
        assert rec["warnings"] == []

    status = read_status(archive)
    assert status["last_outcome"] == "success"
    assert status["videos_completed_last_run"] == 2
    assert status["videos_failed_last_run"] == 0
    assert status["queue_depth"] == 0
    assert status["records_total"] == 2
    assert status["yt_dlp_version"] == "2026.08.19"
    assert status["current_video"] is None
    calls = ytdlp_calls(archive)
    assert [c[-1] for c in calls] == [watch_url("knDDGYHnnSI"), watch_url("am_oeAoUhew")]
    assert "success: completed 2, failed 0, remaining 0" in first.stdout

    second = run_backfill("--now", "--ids", "knDDGYHnnSI", "am_oeAoUhew", archive=archive)
    assert second.returncode == 0, second.stderr
    assert len(ytdlp_calls(archive)) == 2
    assert read_status(archive)["queue_depth"] == 0
    assert "success: completed 0, failed 0, remaining 0" in second.stdout


def test_invocation_matches_the_spec(archive):
    run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive)
    argv = ytdlp_calls(archive)[0]
    out = str(archive / "videos" / "knDDGYHnnSI")
    assert argv[:26] == [
        "-4", "--sleep-requests", "3", "--sleep-interval", "10", "--max-sleep-interval", "30",
        "--sleep-subtitles", "5", "--limit-rate", "4M", "--concurrent-fragments", "1",
        "--extractor-retries", "0", "--retries", "10", "--retry-sleep", "http:exp=1:60",
        "--fragment-retries", "10", "--abort-on-unavailable-fragments",
        "--no-playlist", "--no-overwrites", "--newline", "--js-runtimes"]
    assert argv[26] == "deno:/opt/homebrew/bin/deno"
    assert argv[27:29] == ["--ffmpeg-location", "/opt/homebrew/bin"]
    assert argv[29:31] == ["-f", (
        "ba[acodec^=opus][format_note*=original][format_id!$=-drc]/ba[acodec^=opus][format_id!$=-drc],"
        "ba[acodec^=mp4a][format_note*=original][format_id!$=-drc]/ba[acodec^=mp4a][format_id!$=-drc]")]
    assert argv[31:38] == ["--write-info-json", "--write-auto-subs", "--sub-langs", "en",
                           "--sub-format", "json3", "-o"]
    assert argv[38] == f"{out}/%(id)s.f%(format_id)s.%(ext)s"
    assert argv[39:41] == ["-o", f"subtitle:{out}/%(id)s.%(ext)s"]
    assert argv[41:43] == ["-o", f"infojson:{out}/%(id)s.%(ext)s"]
    assert argv[43:45] == ["--print", "after_move:ROW\t%(format_id)s\t%(acodec)s\t%(abr)s\t"
                                      "%(format_note)s\t%(language)s\t%(filepath)s"]
    assert argv[45] == watch_url("knDDGYHnnSI")
    assert len(argv) == 46
    assert "-v" not in argv
