"""Seam test for scripts/vpn_test.py: parse_traffic(stdout, stderr).

Fixtures are trimmed copies of real yt-dlp output from 2026-09-18 (queries cut,
cookies dropped). Expected counts were read off the raw logs by hand.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "vpn_test"

spec = importlib.util.spec_from_file_location("vpn_test", ROOT / "scripts" / "vpn_test.py")
vpn_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vpn_test)


def streams(video_id):
    return ((FIXTURES / f"{video_id}.stdout").read_text(),
            (FIXTURES / f"{video_id}.stderr").read_text())


def test_subtitle_429_from_curl_trace_is_counted_and_reported():
    counts, problems = vpn_test.parse_traffic(*streams("2bvtay8wGYI"))

    assert counts["caption 429"] == 1
    assert [(p["endpoint"], p["host"], p["status"]) for p in problems] == [("caption", "www.youtube.com", 429)]
    assert "content-length: 1103" in problems[0]["headers"]


def test_ok_video_counts_every_request_by_endpoint():
    # ewtOo0scUh0: watch page, player API, HLS manifest, subtitles (curl), then
    # two ~10 MB chunks for each of 2 formats, each a 302 then a 206.
    counts, problems = vpn_test.parse_traffic(*streams("ewtOo0scUh0"))

    assert dict(counts) == {"webpage 200": 1, "api:player 200": 1, "manifest 200": 1,
                            "caption 200": 1, "media 302": 4, "media 206": 4}
    assert problems == []
