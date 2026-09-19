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


# Network check before the run and before every video. ASNs: 20115 is one of
# Charter's (the home line); 212238 is a Proton exit seen on 09-17.

def test_home_mode_accepts_a_direct_route_on_charter():
    assert vpn_test.network_problem(tunnel=False, asn=20115, home=True) is None


def test_home_mode_refuses_the_vpn_or_a_non_charter_address():
    assert vpn_test.network_problem(tunnel=True, asn=20115, home=True) is not None
    assert vpn_test.network_problem(tunnel=False, asn=212238, home=True) is not None
    assert vpn_test.network_problem(tunnel=False, asn=None, home=True) is not None


def test_vpn_mode_still_requires_the_tunnel_and_a_non_charter_address():
    assert vpn_test.network_problem(tunnel=True, asn=212238) is None
    assert vpn_test.network_problem(tunnel=False, asn=212238) is not None
    assert vpn_test.network_problem(tunnel=True, asn=20115) is not None
    assert vpn_test.network_problem(tunnel=True, asn=None) is not None
