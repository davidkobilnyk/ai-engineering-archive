"""Seam-test harness: run the aie CLI in a subprocess against a fake ai.engineer."""
import json
import os
import shutil
import subprocess
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
COLLECTIONS = ["talks", "speakers", "topics", "organizations", "chapters", "transcripts"]
SLUGS = ["graphrag", "structured-llm-outputs-with-pydantic", "harness-engineering"]


def fixture_for(path, query):
    """Map a request path to the fixture file that the real site would serve."""
    if path == "/api/data/status":
        return FIXTURES / "status.json"
    if path == "/api/data/transcript":
        slug = query.get("slug", [""])[0]
        return FIXTURES / "transcripts" / f"{slug}.json"
    if path.startswith("/api/data/"):
        return FIXTURES / f"{path.removeprefix('/api/data/')}.json"
    return None


class FakeSite:
    """In-process HTTP server serving the fixtures, with scriptable failures.

    site.fail("/api/data/talks?format=json", 429, 429) makes the next two
    requests for that exact path return those statuses before serving normally.
    site.body(path, b"...") serves that raw body once.
    site.requests records every request path in order.
    """

    def __init__(self):
        self.requests = []
        self.script = {}
        site = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                site.requests.append(self.path)
                parsed = urlparse(self.path)
                queue = site.script.get(self.path)
                if queue:
                    kind, value = queue.popleft()
                    if kind == "status":
                        self.send_response(value)
                        self.end_headers()
                        return
                    body = value
                else:
                    file = fixture_for(parsed.path, parse_qs(parsed.query))
                    if file is None or not file.exists():
                        self.send_response(404)
                        self.end_headers()
                        return
                    body = file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def fail(self, path, *codes):
        self.script.setdefault(path, deque()).extend(("status", c) for c in codes)

    def body(self, path, data):
        self.script.setdefault(path, deque()).append(("body", data))

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake_site():
    site = FakeSite()
    yield site
    site.close()


def run_aie(*args, data_dir, base_url=None, env=None):
    """Run `python -m aie <args>` and return the CompletedProcess."""
    merged = {**os.environ, "AIE_DATA_DIR": str(data_dir), "AIE_RETRY_BASE": "0.01"}
    if base_url:
        merged["AIE_BASE_URL"] = base_url
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "aie", *args], capture_output=True, text=True, env=merged
    )


@pytest.fixture
def synced_dir(tmp_path):
    """A data dir that looks exactly like the result of a successful `aie sync`."""
    raw = tmp_path / "data" / "raw"
    (raw / "transcripts").mkdir(parents=True)
    shutil.copy(FIXTURES / "status.json", raw / "status.json")
    for name in COLLECTIONS:
        shutil.copy(FIXTURES / f"{name}.json", raw / f"{name}.json")
    for slug in SLUGS:
        shutil.copy(FIXTURES / "transcripts" / f"{slug}.json", raw / "transcripts" / f"{slug}.json")
    status = json.loads((FIXTURES / "status.json").read_text())
    (raw / "version.json").write_text(
        json.dumps({"corpusVersion": status["corpusVersion"], "syncedAt": "2026-09-14T00:00:00+00:00"})
    )
    return tmp_path / "data"


@pytest.fixture
def indexed_dir(synced_dir):
    result = run_aie("index", data_dir=synced_dir)
    assert result.returncode == 0, result.stderr
    return synced_dir


FAKES = Path(__file__).parent / "fakes"
FFMPEG_DIR = Path("/opt/homebrew/bin")


def backfill_command(*args, archive):
    """The exact argv the tests run: the CLI with fake yt-dlp and real ffmpeg."""
    return [sys.executable, "-m", "aie", "backfill", "--archive-dir", str(archive),
            "--yt-dlp", str(FAKES / "yt-dlp"), "--ffmpeg-dir", str(FFMPEG_DIR),
            "--deno", str(FFMPEG_DIR / "deno"), *args]


def backfill_env(archive, data_dir=None, env=None):
    merged = {**os.environ,
              "PATH": f"{FAKES}:{os.environ.get('PATH', '')}",
              "FAKE_YTDLP_LOG": str(archive.parent / "ytdlp-calls.jsonl")}
    merged.pop("AIE_HEALTHCHECK_URL", None)
    if data_dir:
        merged["AIE_DATA_DIR"] = str(data_dir)
    if env:
        merged.update(env)
    return merged


def run_backfill(*args, archive, data_dir=None, env=None):
    return subprocess.run(backfill_command(*args, archive=archive), capture_output=True, text=True,
                          env=backfill_env(archive, data_dir, env))


def ytdlp_calls(archive):
    """Every argv the fake yt-dlp received, in order."""
    log = archive.parent / "ytdlp-calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


@pytest.fixture
def archive(tmp_path):
    d = tmp_path / "archive"
    d.mkdir()
    return d
