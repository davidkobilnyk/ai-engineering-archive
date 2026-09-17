"""Seam tests for `aie backfill`. Every test runs the real command in a subprocess
against a temp archive with fake yt-dlp/pmset/route/dig on PATH and real ffmpeg.

Expected values are literals from tests/fixtures/audio/README.md and
tests/fixtures/talks.json.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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


# ---------------------------------------------------------------- guards

NY = ZoneInfo("America/New_York")


def window_excluding_now():
    now = datetime.now(NY)
    return f"{now + timedelta(hours=2):%H:%M}-{now + timedelta(hours=3):%H:%M}"


def window_including_now():
    now = datetime.now(NY)
    return f"{now - timedelta(hours=1):%H:%M}-{now + timedelta(hours=2):%H:%M}"


def assert_skipped(result, archive, reason):
    assert result.returncode == 0, result.stderr
    assert reason in result.stdout
    assert read_status(archive)["last_outcome"] == reason
    assert ytdlp_calls(archive) == []


def test_outside_window_skips(archive):
    r = run_backfill("--window", window_excluding_now(), "--ids", "knDDGYHnnSI", archive=archive)
    assert_skipped(r, archive, "skipped:window")


def test_inside_window_on_mains_runs(archive):
    r = run_backfill("--window", window_including_now(), "--ids", "knDDGYHnnSI", archive=archive)
    assert r.returncode == 0, r.stderr
    assert read_status(archive)["last_outcome"] == "success"
    assert len(ytdlp_calls(archive)) == 1


def test_on_battery_skips_unless_now(archive):
    env = {"FAKE_PMSET_OUTPUT": "Now drawing from 'Battery Power'"}
    r = run_backfill("--window", window_including_now(), "--ids", "knDDGYHnnSI", archive=archive, env=env)
    assert_skipped(r, archive, "skipped:power")

    manual = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive, env=env)
    assert manual.returncode == 0, manual.stderr
    assert len(ytdlp_calls(archive)) == 1


def test_vpn_default_route_skips_even_with_now(archive):
    env = {"FAKE_ROUTE_OUTPUT": "   route to: default\n  interface: utun4"}
    r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive, env=env)
    assert_skipped(r, archive, "skipped:vpn")


def test_foreign_asn_skips(archive):
    env = {"FAKE_DIG_ASN": '"62371 | 185.159.156.0/22 | CH | ripencc | 2015-12-03"'}
    r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive, env=env)
    assert_skipped(r, archive, "skipped:asn")


def test_asn_lookup_failure_fails_closed(archive):
    r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive, env={"FAKE_DIG_IP": ""})
    assert_skipped(r, archive, "skipped:asn-unknown")


def test_unmounted_volume_skips_and_creates_nothing(tmp_path):
    missing = Path("/Volumes/aie-test-not-a-drive")
    r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=missing)
    assert r.returncode == 0, r.stderr
    assert "skipped:drive" in r.stdout
    assert not missing.exists()


def test_second_run_while_locked_skips(archive):
    import fcntl
    import os
    fd = os.open(archive / ".backfill.lock", os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive)
    finally:
        os.close(fd)
    assert_skipped(r, archive, "skipped:lock")


def test_dry_run_lists_queue_and_fetches_nothing(archive):
    r = run_backfill("--now", "--dry-run", "--ids", "knDDGYHnnSI", "yj-wSRJwrrc", archive=archive)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[:2] == ["knDDGYHnnSI", "yj-wSRJwrrc"]
    assert "dry run: 2 of 2 queued videos would be fetched" in r.stdout
    assert ytdlp_calls(archive) == []
    assert not (archive / "status.json").exists()
