"""Opt-in check that the real ai.engineer endpoints still have the shape the archive expects.

Run with: AIE_LIVE_TESTS=1 .venv/bin/pytest tests/test_live.py -v
"""
import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("AIE_LIVE_TESTS"), reason="set AIE_LIVE_TESTS=1 to run")

BASE = "https://ai.engineer"
HEADERS = {"User-Agent": "aie-archive/0.1 (live smoke test)"}


def test_status_endpoint_has_a_corpus_version():
    status = httpx.get(f"{BASE}/api/data/status", headers=HEADERS, timeout=30).json()
    assert isinstance(status.get("corpusVersion"), str) and len(status["corpusVersion"]) == 64
    assert status["counts"]["talks"] >= 1087


def test_one_transcript_is_a_list_of_timestamped_segments():
    url = f"{BASE}/api/data/transcript?slug=harness-engineering&format=json"
    segments = httpx.get(url, headers=HEADERS, timeout=30).json()
    assert isinstance(segments, list) and segments
    assert set(segments[0]) >= {"startMs", "text"}
    assert segments[0]["startMs"] == 15030
