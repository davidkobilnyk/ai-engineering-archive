# AIE Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local CLI, `aie`, that downloads every AI Engineer conference transcript from ai.engineer, indexes it in SQLite full-text search, and answers `search`, `show`, `talks`, and `status` queries so Claude Code can answer questions from the transcripts with citations.

**Architecture:** Three modules under `src/aie/` with one responsibility each: `sync.py` (HTTP to `data/raw`), `index.py` (`data/raw` to `data/aie.db`), `search.py` (queries against `data/aie.db`), wired by `cli.py`. Every test drives the `aie` command in a subprocess against a temporary data directory; network is replaced by an in-test HTTP server serving captured fixtures.

**Tech Stack:** Python 3.12+, standard-library `sqlite3` (FTS5, porter tokenizer) and `argparse`, `httpx` for HTTP, `pytest`, setuptools build backend, plain `venv` + `pip`.

**Spec:** `docs/superpowers/specs/2026-09-14-aie-archive-design.md`

## Global Constraints

- Python `>=3.12`. Machine has 3.13.3 and SQLite 3.49.1 with FTS5.
- `uv` is not installed on this machine. Use `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`. The `pyproject.toml` is standard PEP 621 so `uv sync` works later if desired.
- Runtime dependency: `httpx` only. Dev dependency: `pytest` only.
- Tests only at the CLI seam via subprocess. No test imports `aie` internals. Expected values are literals copied from `tests/fixtures/` (see `tests/fixtures/README.md`), never computed by the code under test.
- Every task: write the failing test, run it and see it fail, implement, run it and see it pass, commit. RED then GREEN, always.
- `data/` is gitignored. Fixtures live in `tests/fixtures/` (already committed).
- Exit codes: 0 success or empty result; 1 missing data or failed operation; 2 usage or query error.
- Sync default delay 2.0 s between requests; retries wait 10, 20, 40 s (scaled by env `AIE_RETRY_BASE`, default 10, tests set 0.01); abort after 3 consecutive failed files.
- Timestamps print as `MM:SS` with two-digit minutes that may exceed 59 (`65:00`).
- YouTube citation URL: `https://www.youtube.com/watch?v=<videoId>&t=<start_ms // 1000>`.
- Environment variables: `AIE_DATA_DIR` (default `./data`), `AIE_BASE_URL` (default `https://ai.engineer`, test hook), `AIE_RETRY_BASE` (test hook).
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Fixture facts used as test literals

| Fact | Value |
|---|---|
| Talks in fixtures, in `talks.json` order | `graphrag`, `structured-llm-outputs-with-pydantic`, `harness-engineering` |
| Transcript index order (`transcripts.json`) | same as above |
| Segment counts | graphrag 20, pydantic 19, harness 69 = 108 |
| Chapter counts | graphrag 8, pydantic 12, harness 11 = 31 |
| Corpus version | `575e4c565354bf07b7d567ab08376f4176910a799bf0ef29ed41868192e0dc24` |
| harness event / videoId / duration | `AI Engineer Europe 2026` / `am_oeAoUhew` / 2781000 |
| graphrag event / videoId / duration | `worldsfair-2024` / `knDDGYHnnSI` / 1155000 |
| pydantic event / videoId / duration | `AI Engineer Summit 2023` / `yj-wSRJwrrc` / 1075000 |
| Speakers | harness: Ryan Lopopolo; graphrag: Emil Eifrem; pydantic: Jason Liu |
| Topics | harness: `agent-engineering`; graphrag and pydantic: `rag-and-knowledge` |
| "strapping my laptop" | only harness segment 10, startMs 681270, next segment startMs 746250 |
| "apples and oranges" | only graphrag segment 10, startMs 660810 |
| `pagerank OR moscone` | graphrag segments 2, 3, 7 (2 and 3 adjacent) |
| `hallucination` (stemmed) | pydantic segments 3 and 16 only; the text says "hallucinations" |
| `urging` | only in graphrag summary, not in any transcript |
| `friction` | only in harness summary, not in any transcript |
| harness chapter 3 | "Scarce Resources", startMs 311000 |
| harness segment 0 | startMs 15030, begins "Our next speaker is here to speak about Harness Engineering" |
| Edition dates | europe 2026: 2026-04-08..10 London; worldsfair 2024: 2024-06-25..27 SF; summit 2023: 2023-10-08..10 SF |

## File structure

```
pyproject.toml
.gitignore                      add data/ and .venv/
src/aie/__init__.py
src/aie/__main__.py             python -m aie -> cli.main
src/aie/cli.py                  argparse, subcommands, exit codes, output formatting calls
src/aie/sync.py                 Fetcher (throttle, retry), sync() -> SyncResult, atomic writes
src/aie/index.py                schema, resolve_event(), build_index() -> IndexResult
src/aie/search.py               connect(), Filters, search(), show helpers, list_talks(), read_status(), formatters
src/aie/editions.json           hand-maintained conference editions
tests/conftest.py               FakeSite HTTP server, run_aie(), synced_dir, indexed_dir fixtures
tests/test_cli.py               all seam tests
tests/test_live.py              opt-in live smoke test
tests/fixtures/                 already committed
.claude/skills/aie-archive/SKILL.md
README.md
```

---

### Task 1: Scaffold and tracer bullet (sync → index → search)

**Files:**
- Create: `pyproject.toml`, `src/aie/__init__.py`, `src/aie/__main__.py`, `src/aie/cli.py`, `src/aie/sync.py`, `src/aie/index.py`, `src/aie/search.py`, `src/aie/editions.json`, `tests/conftest.py`, `tests/test_cli.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `aie.sync.sync(data_dir: Path, base_url: str, delay: float, force: bool, log) -> SyncResult` with fields `corpus_version, up_to_date, fetched, skipped, failed: list[str], aborted, last_error` and property `ok`.
- Produces: `aie.index.build_index(data_dir: Path, log) -> IndexResult` with fields `talks, segments, chapters, editions, unresolved_events: list[str], skipped_files: list[str]`; raises `MissingRawData`.
- Produces: `aie.search.connect(data_dir) -> sqlite3.Connection` (raises `MissingIndex`), `Filters` dataclass, `search(con, query, filters, limit) -> list[Hit]`, `format_hits(hits) -> str`, `format_ts(ms) -> str`, `yt_url(video_id, ms) -> str`.
- Produces: `aie.cli.main(argv=None) -> int`.
- Test helpers in `tests/conftest.py`: `FakeSite` (`.url`, `.requests`, `.fail(path, *codes)`, `.body(path, data)`), `run_aie(*args, data_dir, base_url=None, env=None) -> CompletedProcess`, fixtures `fake_site`, `synced_dir`, `indexed_dir`.

- [ ] **Step 1: Create the package skeleton and install it**

`pyproject.toml`:

```toml
[project]
name = "aie"
version = "0.1.0"
description = "Local searchable archive of AI Engineer conference transcripts"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
aie = "aie.cli:main"

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
aie = ["editions.json"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`src/aie/__init__.py`: empty file.

`src/aie/__main__.py`:

```python
import sys

from .cli import main

sys.exit(main())
```

`src/aie/editions.json`:

```json
[
  {"series": "summit", "year": 2023, "title": "AI Engineer Summit 2023", "start_date": "2023-10-08", "end_date": "2023-10-10", "location": "San Francisco"},
  {"series": "worldsfair", "year": 2024, "title": "AI Engineer World's Fair 2024", "start_date": "2024-06-25", "end_date": "2024-06-27", "location": "San Francisco"},
  {"series": "summit", "year": 2025, "title": "AI Engineer Summit 2025", "start_date": "2025-02-19", "end_date": "2025-02-22", "location": "New York"},
  {"series": "worldsfair", "year": 2025, "title": "AI Engineer World's Fair 2025", "start_date": "2025-06-03", "end_date": "2025-06-05", "location": "San Francisco"},
  {"series": "paris", "year": 2025, "title": "AI Engineer Paris 2025", "start_date": "2025-09-23", "end_date": "2025-09-24", "location": "Paris"},
  {"series": "code", "year": 2025, "title": "AI Engineer Code 2025", "start_date": "2025-11-19", "end_date": "2025-11-22", "location": "New York"},
  {"series": "europe", "year": 2026, "title": "AI Engineer Europe 2026", "start_date": "2026-04-08", "end_date": "2026-04-10", "location": "London"},
  {"series": "miami", "year": 2026, "title": "AI Engineer Miami 2026", "start_date": "2026-04-20", "end_date": "2026-04-21", "location": "Miami"},
  {"series": "singapore", "year": 2026, "title": "AI Engineer Singapore 2026", "start_date": "2026-05-15", "end_date": "2026-05-17", "location": "Singapore"},
  {"series": "worldsfair", "year": 2026, "title": "AI Engineer World's Fair 2026", "start_date": "2026-06-29", "end_date": "2026-07-02", "location": "San Francisco"}
]
```

Append to `.gitignore`:

```
# aie archive data and venv
data/
.venv/
```

Create empty placeholders so the package imports: `src/aie/cli.py`, `src/aie/sync.py`, `src/aie/index.py`, `src/aie/search.py` each containing only a module docstring for now (they are filled in Step 4).

Install:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Expected: `Successfully installed aie-0.1.0 httpx ... pytest ...`

- [ ] **Step 2: Write the test harness and the failing tracer-bullet test**

`tests/conftest.py`:

```python
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
```

`tests/test_cli.py`:

```python
"""Seam tests for the aie CLI. Every test runs the real command in a subprocess."""
from conftest import run_aie


def test_tracer_sync_index_search(fake_site, tmp_path):
    data = tmp_path / "data"

    synced = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    assert synced.returncode == 0, synced.stderr

    indexed = run_aie("index", data_dir=data)
    assert indexed.returncode == 0, indexed.stderr

    found = run_aie("search", '"strapping my laptop"', data_dir=data)
    assert found.returncode == 0, found.stderr
    assert "slug: harness-engineering" in found.stdout
    assert "[11:21] https://www.youtube.com/watch?v=am_oeAoUhew&t=681" in found.stdout
```

- [ ] **Step 3: Run the tracer test and watch it fail**

```bash
.venv/bin/pytest tests/test_cli.py::test_tracer_sync_index_search -v
```

Expected: FAIL. `synced.returncode` is non-zero because `python -m aie` has no `main` yet (stderr shows `ImportError: cannot import name 'main'`).

- [ ] **Step 4: Write the minimal implementation**

`src/aie/sync.py`:

```python
"""Download the ai.engineer public corpus into data/raw."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

COLLECTIONS = ["talks", "speakers", "topics", "organizations", "chapters", "transcripts"]
USER_AGENT = "aie-archive/0.1 (local transcript archive)"


class FetchError(Exception):
    """A file could not be fetched."""


@dataclass
class SyncResult:
    corpus_version: str | None = None
    up_to_date: bool = False
    fetched: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    aborted: bool = False
    last_error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failed and not self.aborted


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def fetch_json_bytes(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    if response.status_code != 200:
        raise FetchError(f"HTTP {response.status_code}")
    return response.content


def sync(data_dir: Path, base_url: str, delay: float = 2.0, force: bool = False, log=print) -> SyncResult:
    raw = data_dir / "raw"
    (raw / "transcripts").mkdir(parents=True, exist_ok=True)
    result = SyncResult()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        status_bytes = fetch_json_bytes(client, f"{base_url}/api/data/status")
        result.corpus_version = json.loads(status_bytes).get("corpusVersion")
        write_atomic(raw / "status.json", status_bytes)
        for name in COLLECTIONS:
            log(f"fetching {name}")
            write_atomic(raw / f"{name}.json", fetch_json_bytes(client, f"{base_url}/api/data/{name}?format=json"))
            result.fetched += 1
        entries = json.loads((raw / "transcripts.json").read_text())
        for i, entry in enumerate(entries, 1):
            slug = entry["talkSlug"]
            log(f"[{i}/{len(entries)}] transcript {slug}")
            url = f"{base_url}/api/data/transcript?slug={slug}&format=json"
            write_atomic(raw / "transcripts" / f"{slug}.json", fetch_json_bytes(client, url))
            result.fetched += 1
        version = {"corpusVersion": result.corpus_version,
                   "syncedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        write_atomic(raw / "version.json", json.dumps(version).encode())
    return result
```

`src/aie/index.py`:

```python
"""Build data/aie.db from data/raw."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class MissingRawData(Exception):
    """data/raw is absent or has no talks file."""


SCHEMA = """
CREATE TABLE editions(series TEXT, year INTEGER, title TEXT, start_date TEXT, end_date TEXT,
                      location TEXT, PRIMARY KEY(series, year));
CREATE TABLE talks(slug TEXT PRIMARY KEY, title TEXT, event_raw TEXT, series TEXT, year INTEGER,
                   start_date TEXT, end_date TEXT, url TEXT, video_id TEXT, duration_ms INTEGER,
                   summary TEXT, speakers_json TEXT, topics_json TEXT);
CREATE TABLE chapters(talk_slug TEXT, title TEXT, start_ms INTEGER, end_ms INTEGER);
CREATE TABLE segments(id INTEGER PRIMARY KEY, talk_slug TEXT, seq INTEGER, start_ms INTEGER,
                      end_ms INTEGER, text TEXT);
CREATE INDEX segments_talk ON segments(talk_slug, seq);
CREATE VIRTUAL TABLE segments_fts USING fts5(text, content='segments', content_rowid='id',
                                             tokenize='porter unicode61');
CREATE VIRTUAL TABLE talk_docs_fts USING fts5(title, summary, slug UNINDEXED,
                                              tokenize='porter unicode61');
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""


@dataclass
class IndexResult:
    talks: int = 0
    segments: int = 0
    chapters: int = 0
    editions: int = 0
    unresolved_events: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)


def build_index(data_dir: Path, log=print) -> IndexResult:
    raw = data_dir / "raw"
    talks_file = raw / "talks.json"
    if not talks_file.exists():
        raise MissingRawData(f"No raw data found at {raw}. Run `aie sync` first.")
    db_path = data_dir / "aie.db"
    result = IndexResult()
    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA)
        talks = json.loads(talks_file.read_text())
        for t in talks:
            con.execute(
                "INSERT INTO talks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (t["slug"], t.get("title"), t.get("event"), None, None, None, None, t.get("url"),
                 t.get("videoId"), t.get("durationMs"), t.get("summary"),
                 json.dumps(t.get("speakers", [])), json.dumps(t.get("topics", []))),
            )
            segs = json.loads((raw / "transcripts" / f"{t['slug']}.json").read_text())
            rows = []
            for i, s in enumerate(segs):
                end = segs[i + 1]["startMs"] if i + 1 < len(segs) else (t.get("durationMs") or s["startMs"])
                rows.append((t["slug"], i, s["startMs"], end, s["text"]))
            con.executemany("INSERT INTO segments(talk_slug, seq, start_ms, end_ms, text) VALUES (?,?,?,?,?)", rows)
            result.segments += len(rows)
        con.execute("INSERT INTO segments_fts(rowid, text) SELECT id, text FROM segments")
        result.talks = len(talks)
        con.execute("INSERT INTO meta VALUES ('indexed_at', ?)",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
        con.commit()
    finally:
        con.close()
    return result
```

`src/aie/search.py`:

```python
"""Queries against data/aie.db."""
from __future__ import annotations

import json
import sqlite3
import textwrap
from dataclasses import dataclass
from pathlib import Path


class MissingIndex(Exception):
    """data/aie.db does not exist."""


@dataclass
class Filters:
    event: str | None = None
    speaker: str | None = None
    topic: str | None = None
    talk: str | None = None
    after: str | None = None
    before: str | None = None


@dataclass
class Hit:
    talk_slug: str
    title: str
    speakers: list[str]
    event: str | None
    start_date: str | None
    end_date: str | None
    start_ms: int
    end_ms: int
    url: str
    text: str
    snippet: str
    kind: str
    score: float


def connect(data_dir: Path) -> sqlite3.Connection:
    db = data_dir / "aie.db"
    if not db.exists():
        raise MissingIndex(f"No index found at {db}. Run `aie sync` then `aie index`.")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def format_ts(ms: int) -> str:
    minutes, seconds = divmod(ms // 1000, 60)
    return f"{minutes:02d}:{seconds:02d}"


def yt_url(video_id: str | None, ms: int, fallback: str = "") -> str:
    if not video_id:
        return fallback
    return f"https://www.youtube.com/watch?v={video_id}&t={ms // 1000}"


def speaker_names(speakers_json: str) -> list[str]:
    return [s.get("name", "") for s in json.loads(speakers_json or "[]")]


def search(con: sqlite3.Connection, query: str, filters: Filters, limit: int = 10) -> list[Hit]:
    rows = con.execute(
        """
        SELECT s.talk_slug, s.seq, s.start_ms, s.end_ms, s.text,
               snippet(segments_fts, 0, '', '', '…', 64) AS snip, bm25(segments_fts) AS score,
               t.title, t.speakers_json, t.video_id, t.url AS talk_url, t.event_raw,
               t.start_date, t.end_date
        FROM segments_fts
        JOIN segments s ON s.id = segments_fts.rowid
        JOIN talks t ON t.slug = s.talk_slug
        WHERE segments_fts MATCH ?
        ORDER BY score LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    return [
        Hit(
            talk_slug=r["talk_slug"], title=r["title"] or "", speakers=speaker_names(r["speakers_json"]),
            event=r["event_raw"], start_date=r["start_date"], end_date=r["end_date"],
            start_ms=r["start_ms"], end_ms=r["end_ms"],
            url=yt_url(r["video_id"], r["start_ms"], r["talk_url"] or ""),
            text=r["text"], snippet=r["snip"], kind="segment", score=r["score"],
        )
        for r in rows
    ]


def format_hits(hits: list[Hit]) -> str:
    if not hits:
        return "No results"
    lines = []
    for i, h in enumerate(hits, 1):
        who = ", ".join(n for n in h.speakers if n) or "unknown speaker"
        lines.append(f"{i}. {h.title} — {who} · {h.event or 'unknown edition'}")
        lines.append(f"   slug: {h.talk_slug}")
        lines.append(f"   [{format_ts(h.start_ms)}] {h.url}")
        lines.append(textwrap.fill(h.snippet, 76, initial_indent="   ", subsequent_indent="   "))
    return "\n".join(lines)
```

`src/aie/cli.py`:

```python
"""Command-line entry point for the aie archive."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import index as index_mod
from . import search as search_mod
from . import sync as sync_mod

DEFAULT_BASE_URL = "https://ai.engineer"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aie", description="Local searchable archive of AI Engineer talks.")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("AIE_DATA_DIR", "data")),
                        help="where raw files and the index live (default ./data or $AIE_DATA_DIR)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="download the corpus into data/raw")
    p_sync.add_argument("--force", action="store_true", help="re-download everything")
    p_sync.add_argument("--delay", type=float, default=2.0, help="seconds between requests (default 2)")

    sub.add_parser("index", help="rebuild data/aie.db from data/raw")

    p_search = sub.add_parser("search", help="full-text search over transcripts and talk metadata")
    p_search.add_argument("query", help="FTS5 query: words, \"phrases\", OR, NEAR(...)")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--json", action="store_true")
    return parser


def cmd_sync(args) -> int:
    base_url = os.environ.get("AIE_BASE_URL", DEFAULT_BASE_URL)
    result = sync_mod.sync(args.data_dir, base_url, delay=args.delay, force=args.force)
    print(f"fetched {result.fetched}, skipped {result.skipped}, failed {len(result.failed)}, "
          f"corpus {result.corpus_version}")
    return 0 if result.ok else 1


def cmd_index(args) -> int:
    result = index_mod.build_index(args.data_dir)
    print(f"talks {result.talks} · segments {result.segments} · chapters {result.chapters} · "
          f"editions {result.editions}")
    return 0


def cmd_search(args) -> int:
    con = search_mod.connect(args.data_dir)
    hits = search_mod.search(con, args.query, search_mod.Filters(), limit=args.limit)
    print(search_mod.format_hits(hits))
    return 0


COMMANDS = {"sync": cmd_sync, "index": cmd_index, "search": cmd_search}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (search_mod.MissingIndex, index_mod.MissingRawData) as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tracer test and watch it pass**

```bash
.venv/bin/pytest tests/test_cli.py::test_tracer_sync_index_search -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/aie tests/conftest.py tests/test_cli.py
git commit -m "feat: scaffold aie package with tracer bullet sync/index/search

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Sync skips when up to date, resumes, honours --force, and never claims completion after a failure

**Files:**
- Modify: `src/aie/sync.py` (replace `sync()`)
- Modify: `src/aie/cli.py` (`cmd_sync` prints failures)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `FakeSite.requests`, `FakeSite.fail(path, *codes)`, `run_aie` from Task 1.
- Produces: `SyncResult.up_to_date`, `.skipped`, `.failed` populated as the spec describes; `aie sync` exit 1 when any file failed; stdout contains `up to date` when nothing to do and `failed: <names>` when files failed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
STATUS_PATH = "/api/data/status"
GRAPHRAG_PATH = "/api/data/transcript?slug=graphrag&format=json"
PYDANTIC_PATH = "/api/data/transcript?slug=structured-llm-outputs-with-pydantic&format=json"
HARNESS_PATH = "/api/data/transcript?slug=harness-engineering&format=json"


def test_sync_second_run_is_up_to_date_and_only_checks_status(fake_site, tmp_path):
    data = tmp_path / "data"
    first = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    assert first.returncode == 0, first.stderr
    fake_site.requests.clear()

    second = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert second.returncode == 0
    assert "up to date" in second.stdout
    assert fake_site.requests == [STATUS_PATH]


def test_sync_force_redownloads_every_transcript(fake_site, tmp_path):
    data = tmp_path / "data"
    run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    fake_site.requests.clear()

    forced = run_aie("sync", "--delay", "0", "--force", data_dir=data, base_url=fake_site.url)

    assert forced.returncode == 0
    assert {GRAPHRAG_PATH, PYDANTIC_PATH, HARNESS_PATH} <= set(fake_site.requests)


def test_sync_failed_transcript_means_exit_1_and_no_version_file(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(PYDANTIC_PATH, 404)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 1
    assert "failed: transcript:structured-llm-outputs-with-pydantic" in result.stdout
    assert not (data / "raw" / "version.json").exists()
    assert (data / "raw" / "transcripts" / "graphrag.json").exists()
    assert (data / "raw" / "transcripts" / "harness-engineering.json").exists()
    assert not (data / "raw" / "transcripts" / "structured-llm-outputs-with-pydantic.json").exists()


def test_sync_resumes_by_fetching_only_the_missing_transcript(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(PYDANTIC_PATH, 404)
    run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    fake_site.requests.clear()

    resumed = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert resumed.returncode == 0, resumed.stderr
    transcript_requests = [p for p in fake_site.requests if "/api/data/transcript?" in p]
    assert transcript_requests == [PYDANTIC_PATH]
    assert "skipped 2" in resumed.stdout
    assert (data / "raw" / "version.json").exists()
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
.venv/bin/pytest tests/test_cli.py -v -k "up_to_date or force or failed_transcript or resumes"
```

Expected: 4 FAIL. The up-to-date test fails because the second run re-fetches everything (`requests` has 10 entries); the 404 test fails with an unhandled `FetchError` traceback and exit 1 but no `failed:` line and no other transcripts written (the exception aborts the loop before harness is fetched); the resume test fails for the same reason.

- [ ] **Step 3: Replace `sync()` in `src/aie/sync.py`**

Keep everything above `def sync` unchanged. Replace `sync` with:

```python
def sync(data_dir: Path, base_url: str, delay: float = 2.0, force: bool = False, log=print) -> SyncResult:
    raw = data_dir / "raw"
    (raw / "transcripts").mkdir(parents=True, exist_ok=True)
    result = SyncResult()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        try:
            status_bytes = fetch_json_bytes(client, f"{base_url}/api/data/status")
        except FetchError as e:
            result.failed.append("status")
            result.last_error = str(e)
            result.aborted = True
            return result
        result.corpus_version = json.loads(status_bytes).get("corpusVersion")

        version_file = raw / "version.json"
        if not force and version_file.exists():
            local = json.loads(version_file.read_text()).get("corpusVersion")
            if local == result.corpus_version:
                result.up_to_date = True
                log(f"up to date (corpus {str(result.corpus_version)[:12]})")
                return result
        write_atomic(raw / "status.json", status_bytes)

        def download(name: str, url: str, dest: Path) -> None:
            try:
                write_atomic(dest, fetch_json_bytes(client, url))
                result.fetched += 1
            except FetchError as e:
                result.failed.append(name)
                result.last_error = str(e)
                log(f"  failed: {name} ({e})")

        for name in COLLECTIONS:
            log(f"fetching {name}")
            download(name, f"{base_url}/api/data/{name}?format=json", raw / f"{name}.json")

        index_file = raw / "transcripts.json"
        if not index_file.exists():
            return result
        entries = json.loads(index_file.read_text())
        for i, entry in enumerate(entries, 1):
            slug = entry["talkSlug"]
            dest = raw / "transcripts" / f"{slug}.json"
            if dest.exists() and not force:
                result.skipped += 1
                continue
            log(f"[{i}/{len(entries)}] transcript {slug}")
            download(f"transcript:{slug}", f"{base_url}/api/data/transcript?slug={slug}&format=json", dest)

        if result.ok:
            version = {"corpusVersion": result.corpus_version,
                       "syncedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            write_atomic(version_file, json.dumps(version).encode())
    return result
```

Note the transcript URL is built from `base_url` and the slug, never from the index entry's `jsonUrl`, which always points at the real site.

- [ ] **Step 4: Update `cmd_sync` in `src/aie/cli.py`**

```python
def cmd_sync(args) -> int:
    base_url = os.environ.get("AIE_BASE_URL", DEFAULT_BASE_URL)
    result = sync_mod.sync(args.data_dir, base_url, delay=args.delay, force=args.force)
    if result.up_to_date:
        return 0
    print(f"fetched {result.fetched}, skipped {result.skipped}, failed {len(result.failed)}, "
          f"corpus {result.corpus_version}")
    if result.failed:
        print("failed: " + ", ".join(result.failed))
    if result.aborted:
        print(f"aborted: {result.last_error}")
    return 0 if result.ok else 1
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: 5 PASS (tracer plus the four new ones).

- [ ] **Step 6: Commit**

```bash
git add src/aie/sync.py src/aie/cli.py tests/test_cli.py
git commit -m "feat(sync): up-to-date skip, resume, --force, version written last

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Sync throttles, retries with backoff, rejects truncated bodies, and trips a circuit breaker

**Files:**
- Modify: `src/aie/sync.py` (replace `fetch_json_bytes` with `Fetcher`, add breaker to `download`)
- Modify: `src/aie/cli.py` (abort message names the rule)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `FakeSite.fail`, `FakeSite.body`, `FakeSite.requests`.
- Produces: `sync.RETRY_BASE_SECONDS` (from env `AIE_RETRY_BASE`, default 10.0), `sync.MAX_CONSECUTIVE_FAILURES = 3`, `sync.Fetcher(client, delay, log).get_json_bytes(url) -> bytes`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_sync_retries_after_429_then_succeeds(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(GRAPHRAG_PATH, 429, 429)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 0, result.stderr
    assert fake_site.requests.count(GRAPHRAG_PATH) == 3
    assert (data / "raw" / "transcripts" / "graphrag.json").exists()


def test_sync_retries_a_truncated_body(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.body(HARNESS_PATH, b'[{"startMs": 15030, "text": "Our next spea')

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 0, result.stderr
    assert fake_site.requests.count(HARNESS_PATH) == 2
    saved = (data / "raw" / "transcripts" / "harness-engineering.json").read_text()
    assert saved.startswith("[") and saved.rstrip().endswith("]")


def test_sync_gives_up_on_a_file_after_three_retries(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(GRAPHRAG_PATH, 500, 500, 500, 500)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 1
    assert fake_site.requests.count(GRAPHRAG_PATH) == 4
    assert "failed: transcript:graphrag" in result.stdout
    assert (data / "raw" / "transcripts" / "harness-engineering.json").exists()


def test_sync_aborts_after_three_consecutive_failed_files(fake_site, tmp_path):
    data = tmp_path / "data"
    for name in ["talks", "speakers", "topics"]:
        fake_site.fail(f"/api/data/{name}?format=json", 503, 503, 503, 503)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 1
    assert "aborted after 3 consecutive failures" in result.stdout
    assert "failed: talks, speakers, topics" in result.stdout
    assert not any("organizations" in p for p in fake_site.requests)
    assert not (data / "raw" / "version.json").exists()


def test_sync_waits_delay_between_requests(fake_site, tmp_path):
    import time

    data = tmp_path / "data"
    started = time.monotonic()
    result = run_aie("sync", "--delay", "0.2", data_dir=data, base_url=fake_site.url)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert len(fake_site.requests) == 10
    assert elapsed >= 10 * 0.2
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
.venv/bin/pytest tests/test_cli.py -v -k "retries or gives_up or aborts or waits_delay"
```

Expected: 5 FAIL. The 429 test sees `requests.count == 1` and exit 1 (no retry); the truncated test saves the bad body and exits 0; the give-up test sees one request; the abort test sees organizations requested and no `aborted after` line; the delay test finishes in well under 2 s.

- [ ] **Step 3: Replace `src/aie/sync.py` wholesale with the final version**

```python
"""Download the ai.engineer public corpus into data/raw."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

COLLECTIONS = ["talks", "speakers", "topics", "organizations", "chapters", "transcripts"]
USER_AGENT = "aie-archive/0.1 (local transcript archive)"
RETRY_BASE_SECONDS = float(os.environ.get("AIE_RETRY_BASE", "10"))
MAX_ATTEMPTS = 4  # one try plus three retries
MAX_CONSECUTIVE_FAILURES = 3


class FetchError(Exception):
    """A file could not be fetched after all retries."""


@dataclass
class SyncResult:
    corpus_version: str | None = None
    up_to_date: bool = False
    fetched: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    aborted: bool = False
    last_error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failed and not self.aborted


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class Fetcher:
    """One request at a time, a pause after each, retries with exponential backoff."""

    def __init__(self, client: httpx.Client, delay: float, log):
        self.client = client
        self.delay = delay
        self.log = log

    def get_json_bytes(self, url: str) -> bytes:
        """Return the body of a 200 response that parses as JSON, or raise FetchError.

        Retries on 429, 529, any 5xx, transport errors, and bodies that are not
        valid JSON. Does not retry other statuses such as 404.
        """
        last_error = "unknown error"
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                wait = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                self.log(f"  retry {attempt}/{MAX_ATTEMPTS - 1} in {wait:g}s ({last_error})")
                time.sleep(wait)
            try:
                response = self.client.get(url)
            except httpx.TransportError as e:
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(self.delay)
                continue
            time.sleep(self.delay)
            if response.status_code == 200:
                try:
                    json.loads(response.content)
                except ValueError:
                    last_error = "body is not valid JSON"
                    continue
                return response.content
            if response.status_code in (429, 529) or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                continue
            raise FetchError(f"HTTP {response.status_code}")
        raise FetchError(last_error)


def sync(data_dir: Path, base_url: str, delay: float = 2.0, force: bool = False, log=print) -> SyncResult:
    raw = data_dir / "raw"
    (raw / "transcripts").mkdir(parents=True, exist_ok=True)
    result = SyncResult()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        fetcher = Fetcher(client, delay, log)
        try:
            status_bytes = fetcher.get_json_bytes(f"{base_url}/api/data/status")
        except FetchError as e:
            result.failed.append("status")
            result.last_error = str(e)
            result.aborted = True
            return result
        result.corpus_version = json.loads(status_bytes).get("corpusVersion")

        version_file = raw / "version.json"
        if not force and version_file.exists():
            local = json.loads(version_file.read_text()).get("corpusVersion")
            if local == result.corpus_version:
                result.up_to_date = True
                log(f"up to date (corpus {str(result.corpus_version)[:12]})")
                return result
        write_atomic(raw / "status.json", status_bytes)

        consecutive_failures = 0

        def download(name: str, url: str, dest: Path) -> bool:
            """Fetch one file. Return False when the circuit breaker has tripped."""
            nonlocal consecutive_failures
            try:
                write_atomic(dest, fetcher.get_json_bytes(url))
                result.fetched += 1
                consecutive_failures = 0
                return True
            except FetchError as e:
                result.failed.append(name)
                result.last_error = str(e)
                consecutive_failures += 1
                log(f"  failed: {name} ({e})")
                return consecutive_failures < MAX_CONSECUTIVE_FAILURES

        for name in COLLECTIONS:
            log(f"fetching {name}")
            if not download(name, f"{base_url}/api/data/{name}?format=json", raw / f"{name}.json"):
                result.aborted = True
                return result

        index_file = raw / "transcripts.json"
        if not index_file.exists():
            return result
        entries = json.loads(index_file.read_text())
        for i, entry in enumerate(entries, 1):
            slug = entry["talkSlug"]
            dest = raw / "transcripts" / f"{slug}.json"
            if dest.exists() and not force:
                result.skipped += 1
                continue
            log(f"[{i}/{len(entries)}] transcript {slug}")
            if not download(f"transcript:{slug}", f"{base_url}/api/data/transcript?slug={slug}&format=json", dest):
                result.aborted = True
                return result

        if result.ok:
            version = {"corpusVersion": result.corpus_version,
                       "syncedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            write_atomic(version_file, json.dumps(version).encode())
    return result
```

- [ ] **Step 4: Update the abort line in `cmd_sync` (`src/aie/cli.py`)**

Replace the `if result.aborted:` branch with:

```python
    if result.aborted:
        print(f"aborted after {sync_mod.MAX_CONSECUTIVE_FAILURES} consecutive failures; "
              f"last error: {result.last_error}")
```

- [ ] **Step 5: Run the whole file and watch it pass**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: 10 PASS. The delay test takes about 2 s; everything else is sub-second.

- [ ] **Step 6: Commit**

```bash
git add src/aie/sync.py src/aie/cli.py tests/test_cli.py
git commit -m "feat(sync): throttle, retry with backoff, reject truncated JSON, circuit breaker

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Index resolves editions and dates, builds atomically, reports problems

**Files:**
- Modify: `src/aie/index.py` (replace wholesale)
- Modify: `src/aie/search.py` (join editions, show date range)
- Modify: `src/aie/cli.py` (`cmd_index` output, error handling)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `synced_dir`, `indexed_dir`, `run_aie`.
- Produces: `index.resolve_event(event_raw: str | None) -> tuple[str, int] | None`, `index.load_editions() -> list[dict]`, `index.SERIES_ALIASES`. `talks.series/year/start_date/end_date` populated. `search.format_date_range(start: str, end: str) -> str` (e.g. `Apr 8-10, 2026`, `Jun 29 – Jul 2, 2026`, `Apr 20, 2026`). `Hit.event` is the edition title when resolved, else the raw event string.
- `aie index` stdout: `talks N · segments N · chapters N · editions N`, then optional `unresolved events: <slug>: '<raw>'[, ...]` and `skipped files: <name>: <reason>[, ...]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
import json


def test_index_reports_counts(synced_dir):
    result = run_aie("index", data_dir=synced_dir)

    assert result.returncode == 0, result.stderr
    assert "talks 3 · segments 108 · chapters 31 · editions 10" in result.stdout


def test_index_resolves_both_event_string_styles_to_edition_dates(indexed_dir):
    display_style = run_aie("search", '"strapping my laptop"', data_dir=indexed_dir)
    slug_style = run_aie("search", '"apples and oranges"', data_dir=indexed_dir)

    assert "AI Engineer Europe 2026 (Apr 8-10, 2026)" in display_style.stdout
    assert "AI Engineer World's Fair 2024 (Jun 25-27, 2024)" in slug_style.stdout


def test_index_reports_unresolved_event_strings(synced_dir):
    talks_file = synced_dir / "raw" / "talks.json"
    talks = json.loads(talks_file.read_text())
    next(t for t in talks if t["slug"] == "graphrag")["event"] = "mystery-conf"
    talks_file.write_text(json.dumps(talks))

    result = run_aie("index", data_dir=synced_dir)

    assert result.returncode == 0, result.stderr
    assert "unresolved events: graphrag: 'mystery-conf'" in result.stdout
    found = run_aie("search", '"apples and oranges"', data_dir=synced_dir)
    assert "slug: graphrag" in found.stdout
    assert "unknown edition" in found.stdout


def test_index_skips_a_malformed_transcript_and_continues(synced_dir):
    bad = synced_dir / "raw" / "transcripts" / "structured-llm-outputs-with-pydantic.json"
    bad.write_text('[{"startMs": 14790, "text": "Hey guys')

    result = run_aie("index", data_dir=synced_dir)

    assert result.returncode == 0, result.stderr
    assert "talks 3 · segments 89 · chapters 31 · editions 10" in result.stdout
    assert "skipped files: structured-llm-outputs-with-pydantic.json" in result.stdout
    found = run_aie("search", '"apples and oranges"', data_dir=synced_dir)
    assert "slug: graphrag" in found.stdout


def test_index_failure_leaves_previous_index_intact(indexed_dir):
    (indexed_dir / "raw" / "talks.json").write_text("{not json")

    result = run_aie("index", data_dir=indexed_dir)

    assert result.returncode == 1
    assert "talks.json" in result.stderr
    assert not (indexed_dir / "aie.db.tmp").exists()
    found = run_aie("search", '"strapping my laptop"', data_dir=indexed_dir)
    assert found.returncode == 0
    assert "slug: harness-engineering" in found.stdout


def test_index_without_raw_data_exits_1(tmp_path):
    result = run_aie("index", data_dir=tmp_path / "data")

    assert result.returncode == 1
    assert "Run `aie sync` first" in result.stderr
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
.venv/bin/pytest tests/test_cli.py -v -k index
```

Expected: 5 FAIL, 1 PASS. `reports_counts` fails (chapters and editions print 0); `resolves_both` fails (no dates printed); `unresolved` fails (no such line); `malformed` fails with a traceback exit 1; `failure_leaves_previous` fails because the second build corrupts `aie.db` in place (the search afterwards errors); `without_raw_data` already passes from Task 1.

- [ ] **Step 3: Replace `src/aie/index.py` wholesale**

```python
"""Build data/aie.db from data/raw."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path


class MissingRawData(Exception):
    """data/raw is absent or has no talks file."""


SCHEMA = """
CREATE TABLE editions(series TEXT, year INTEGER, title TEXT, start_date TEXT, end_date TEXT,
                      location TEXT, PRIMARY KEY(series, year));
CREATE TABLE talks(slug TEXT PRIMARY KEY, title TEXT, event_raw TEXT, series TEXT, year INTEGER,
                   start_date TEXT, end_date TEXT, url TEXT, video_id TEXT, duration_ms INTEGER,
                   summary TEXT, speakers_json TEXT, topics_json TEXT);
CREATE TABLE chapters(talk_slug TEXT, title TEXT, start_ms INTEGER, end_ms INTEGER);
CREATE INDEX chapters_talk ON chapters(talk_slug, start_ms);
CREATE TABLE segments(id INTEGER PRIMARY KEY, talk_slug TEXT, seq INTEGER, start_ms INTEGER,
                      end_ms INTEGER, text TEXT);
CREATE INDEX segments_talk ON segments(talk_slug, seq);
CREATE VIRTUAL TABLE segments_fts USING fts5(text, content='segments', content_rowid='id',
                                             tokenize='porter unicode61');
CREATE VIRTUAL TABLE talk_docs_fts USING fts5(title, summary, slug UNINDEXED,
                                              tokenize='porter unicode61');
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""

# Checked in order; the first alias found as a whole word wins.
SERIES_ALIASES = [
    ("world's fair", "worldsfair"), ("worlds fair", "worldsfair"), ("worldsfair", "worldsfair"),
    ("summit", "summit"), ("code", "code"), ("paris", "paris"), ("europe", "europe"),
    ("miami", "miami"), ("singapore", "singapore"), ("new york", "nyc"), ("nyc", "nyc"),
    ("shanghai", "shanghai"), ("asia", "asia"), ("india", "india"),
]


def resolve_event(event_raw: str | None) -> tuple[str, int] | None:
    """Map a raw event string to (series, year).

    Handles both styles the site uses: "AI Engineer World's Fair 2025" and
    "worldsfair-2024" or "worldsfair-2026-online-track". Returns None when no
    four-digit year or no known series is present.
    """
    if not event_raw:
        return None
    lowered = event_raw.lower()
    match = re.search(r"\b(20\d\d)\b", lowered)
    if not match:
        return None
    year = int(match.group(1))
    words = re.sub(r"[^a-z']+", " ", lowered.replace(match.group(1), " "))
    padded = f" {' '.join(words.split())} "
    for alias, series in SERIES_ALIASES:
        if f" {alias} " in padded:
            return series, year
    return None


def load_editions() -> list[dict]:
    return json.loads(resources.files("aie").joinpath("editions.json").read_text())


@dataclass
class IndexResult:
    talks: int = 0
    segments: int = 0
    chapters: int = 0
    editions: int = 0
    unresolved_events: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)


def read_segments(path: Path) -> list[dict]:
    """Parse a transcript file; raise ValueError if it is not a list of segments."""
    segs = json.loads(path.read_text())
    if not isinstance(segs, list) or any("startMs" not in s or "text" not in s for s in segs):
        raise ValueError("not a list of {startMs, text} segments")
    return segs


def build_index(data_dir: Path, log=print) -> IndexResult:
    """Rebuild data/aie.db into a temp file and rename it into place on success."""
    raw = data_dir / "raw"
    talks_file = raw / "talks.json"
    if not talks_file.exists():
        raise MissingRawData(f"No raw data found at {raw}. Run `aie sync` first.")
    db_path = data_dir / "aie.db"
    tmp_path = data_dir / "aie.db.tmp"
    if tmp_path.exists():
        tmp_path.unlink()
    result = IndexResult()
    try:
        con = sqlite3.connect(tmp_path)
        try:
            con.executescript(SCHEMA)
            editions = load_editions()
            con.executemany(
                "INSERT INTO editions VALUES (?,?,?,?,?,?)",
                [(e["series"], e["year"], e["title"], e["start_date"], e["end_date"], e["location"])
                 for e in editions],
            )
            by_key = {(e["series"], e["year"]): e for e in editions}

            try:
                talks = json.loads(talks_file.read_text())
            except ValueError as e:
                raise ValueError(f"talks.json is not valid JSON: {e}") from e
            chapters_file = raw / "chapters.json"
            chapters = json.loads(chapters_file.read_text()) if chapters_file.exists() else []

            for t in talks:
                key = resolve_event(t.get("event"))
                edition = by_key.get(key) if key else None
                if edition is None:
                    result.unresolved_events.append(f"{t['slug']}: {t.get('event')!r}")
                con.execute(
                    "INSERT INTO talks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (t["slug"], t.get("title"), t.get("event"),
                     edition["series"] if edition else None, edition["year"] if edition else None,
                     edition["start_date"] if edition else None, edition["end_date"] if edition else None,
                     t.get("url"), t.get("videoId"), t.get("durationMs"), t.get("summary"),
                     json.dumps(t.get("speakers", [])), json.dumps(t.get("topics", []))),
                )
                con.execute("INSERT INTO talk_docs_fts(title, summary, slug) VALUES (?,?,?)",
                            (t.get("title") or "", t.get("summary") or "", t["slug"]))
                tfile = raw / "transcripts" / f"{t['slug']}.json"
                if not tfile.exists():
                    result.skipped_files.append(f"{tfile.name}: missing")
                    continue
                try:
                    segs = read_segments(tfile)
                except ValueError as e:
                    result.skipped_files.append(f"{tfile.name}: {e}")
                    continue
                rows = []
                for i, s in enumerate(segs):
                    end = segs[i + 1]["startMs"] if i + 1 < len(segs) else (t.get("durationMs") or s["startMs"])
                    rows.append((t["slug"], i, s["startMs"], end, s["text"]))
                con.executemany(
                    "INSERT INTO segments(talk_slug, seq, start_ms, end_ms, text) VALUES (?,?,?,?,?)", rows)
                result.segments += len(rows)

            con.executemany("INSERT INTO chapters VALUES (?,?,?,?)",
                            [(c["talkSlug"], c["title"], c["startMs"], c["endMs"]) for c in chapters])
            con.execute("INSERT INTO segments_fts(rowid, text) SELECT id, text FROM segments")
            result.talks, result.chapters, result.editions = len(talks), len(chapters), len(editions)

            version_file = raw / "version.json"
            version = json.loads(version_file.read_text()) if version_file.exists() else {}
            counts = {"talks": result.talks, "segments": result.segments,
                      "chapters": result.chapters, "editions": result.editions}
            con.executemany("INSERT INTO meta VALUES (?,?)", [
                ("corpus_version", version.get("corpusVersion") or ""),
                ("synced_at", version.get("syncedAt") or ""),
                ("indexed_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                ("counts", json.dumps(counts)),
            ])
            con.commit()
            indexed = con.execute("SELECT count(*) FROM talks").fetchone()[0]
            if indexed != len(talks):
                raise RuntimeError(f"sanity check failed: {indexed} talks indexed, {len(talks)} in raw")
        finally:
            con.close()
        os.replace(tmp_path, db_path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return result
```

- [ ] **Step 4: Teach search about editions (`src/aie/search.py`)**

Add `from datetime import date` to the imports at the top of the file, then add after `format_ts`:

```python
def format_date_range(start: str | None, end: str | None) -> str:
    """'2026-04-08','2026-04-10' -> 'Apr 8-10, 2026'; across months -> 'Jun 29 – Jul 2, 2026'."""
    if not start:
        return ""
    a = date.fromisoformat(start)
    b = date.fromisoformat(end) if end else a
    if a == b:
        return f"{a:%b} {a.day}, {a.year}"
    if a.month == b.month:
        return f"{a:%b} {a.day}-{b.day}, {a.year}"
    return f"{a:%b} {a.day} – {b:%b} {b.day}, {b.year}"
```

Replace the SQL in `search()` so it left-joins editions and exposes the title, and set `Hit.event` from it:

```python
    rows = con.execute(
        """
        SELECT s.talk_slug, s.seq, s.start_ms, s.end_ms, s.text,
               snippet(segments_fts, 0, '', '', '…', 64) AS snip, bm25(segments_fts) AS score,
               t.title, t.speakers_json, t.video_id, t.url AS talk_url, t.event_raw,
               t.start_date, t.end_date, e.title AS edition_title
        FROM segments_fts
        JOIN segments s ON s.id = segments_fts.rowid
        JOIN talks t ON t.slug = s.talk_slug
        LEFT JOIN editions e ON e.series = t.series AND e.year = t.year
        WHERE segments_fts MATCH ?
        ORDER BY score LIMIT ?
        """,
        (query, limit),
    ).fetchall()
```

and in the `Hit(...)` construction use `event=r["edition_title"] or r["event_raw"]`.

In `format_hits`, replace the first appended line with:

```python
        when = f" ({format_date_range(h.start_date, h.end_date)})" if h.start_date else ""
        lines.append(f"{i}. {h.title} — {who} · {h.event or 'unknown edition'}{when}")
```

- [ ] **Step 5: Update `cmd_index` and error handling in `src/aie/cli.py`**

```python
def cmd_index(args) -> int:
    try:
        result = index_mod.build_index(args.data_dir)
    except (ValueError, RuntimeError, OSError) as e:
        print(f"index failed: {e}", file=sys.stderr)
        return 1
    print(f"talks {result.talks} · segments {result.segments} · chapters {result.chapters} · "
          f"editions {result.editions}")
    if result.unresolved_events:
        print("unresolved events: " + ", ".join(result.unresolved_events))
    if result.skipped_files:
        print("skipped files: " + ", ".join(result.skipped_files))
    return 0
```

- [ ] **Step 6: Run the tests and watch them pass**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: 16 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/aie/index.py src/aie/search.py src/aie/cli.py tests/test_cli.py
git commit -m "feat(index): editions, event normalization, atomic build, problem reporting

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Search filters, JSON output, metadata hits, adjacent collapsing, errors and hints

**Files:**
- Modify: `src/aie/search.py` (replace `search`, add `filter_sql`, `collapse_adjacent`, `filter_hints`, `BadQuery`)
- Modify: `src/aie/cli.py` (filters, `--json`, limit validation, exit 2 on bad query)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `indexed_dir`, `run_aie`, `index.resolve_event`.
- Produces: `search.BadQuery`, `search.filter_sql(filters) -> tuple[str, list]` (fragment against alias `t`), `search.filter_hints(con, filters) -> list[str]`, `search.hit_to_dict(hit) -> dict`. `search()` now takes filters into account, merges metadata hits (`kind="metadata"`, `start_ms=0`, `end_ms=0`, URL without `&t=`), collapses adjacent segments, and raises `BadQuery` on FTS5 syntax errors. CLI: `--event --speaker --topic --talk --after --before --limit --json`; `add_filter_arguments(parser)` and `filters_from_args(args)` helpers reused by `talks` in Task 7.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def search_json(data_dir, *args):
    result = run_aie("search", *args, "--json", data_dir=data_dir)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_search_json_carries_every_documented_field(indexed_dir):
    hits = search_json(indexed_dir, '"strapping my laptop"')

    assert len(hits) == 1
    hit = hits[0]
    assert set(hit) >= {"talk_slug", "title", "speakers", "event", "start_date", "end_date",
                        "start_ms", "end_ms", "url", "text", "kind", "score"}
    assert hit["talk_slug"] == "harness-engineering"
    assert hit["speakers"] == ["Ryan Lopopolo"]
    assert hit["event"] == "AI Engineer Europe 2026"
    assert hit["start_date"] == "2026-04-08"
    assert hit["end_date"] == "2026-04-10"
    assert hit["start_ms"] == 681270
    assert hit["end_ms"] == 746250
    assert hit["url"] == "https://www.youtube.com/watch?v=am_oeAoUhew&t=681"
    assert hit["kind"] == "segment"
    assert "strapping my laptop" in hit["text"]


def test_search_surfaces_summary_only_matches_as_metadata_hits(indexed_dir):
    plain = run_aie("search", "urging", data_dir=indexed_dir)
    hits = search_json(indexed_dir, "urging")

    assert "slug: graphrag" in plain.stdout
    assert "[metadata] https://www.youtube.com/watch?v=knDDGYHnnSI" in plain.stdout
    assert [h["kind"] for h in hits] == ["metadata"]
    assert hits[0]["start_ms"] == 0


def test_search_collapses_adjacent_matching_segments(indexed_dir):
    hits = search_json(indexed_dir, "pagerank OR moscone")

    segment_hits = [h for h in hits if h["kind"] == "segment"]
    assert {h["talk_slug"] for h in segment_hits} == {"graphrag"}
    assert sorted((h["start_ms"], h["end_ms"]) for h in segment_hits) == [(115050, 259350), (460050, 533910)]


def test_search_stems_query_terms(indexed_dir):
    hits = search_json(indexed_dir, "hallucination")

    assert {h["talk_slug"] for h in hits} == {"structured-llm-outputs-with-pydantic"}
    assert sorted(h["start_ms"] for h in hits) == [184710, 928770]


def test_search_filters_by_speaker_topic_and_talk(indexed_dir):
    by_speaker = search_json(indexed_dir, "prompts", "--speaker", "jason liu")
    by_topic = search_json(indexed_dir, "prompts", "--topic", "agent-engineering")
    by_talk = search_json(indexed_dir, "knowledge", "--talk", "graphrag")

    assert by_speaker and {h["talk_slug"] for h in by_speaker} == {"structured-llm-outputs-with-pydantic"}
    assert by_topic and {h["talk_slug"] for h in by_topic} == {"harness-engineering"}
    assert by_talk and {h["talk_slug"] for h in by_talk} == {"graphrag"}


def test_search_filters_by_edition_and_date(indexed_dir):
    by_series = search_json(indexed_dir, '"knowledge graph"', "--event", "worldsfair")
    by_title = search_json(indexed_dir, '"knowledge graph"', "--event", "AI Engineer Summit 2023")
    after = search_json(indexed_dir, '"knowledge graph"', "--after", "2024-01-01")
    before = search_json(indexed_dir, '"knowledge graph"', "--before", "2024-01-01")

    assert by_series and {h["talk_slug"] for h in by_series} == {"graphrag"}
    assert by_title and {h["talk_slug"] for h in by_title} == {"structured-llm-outputs-with-pydantic"}
    assert after and {h["talk_slug"] for h in after} == {"graphrag"}
    assert before and {h["talk_slug"] for h in before} == {"structured-llm-outputs-with-pydantic"}


def test_search_limit_is_honoured_and_capped(indexed_dir):
    two = search_json(indexed_dir, "prompts", "--limit", "2")
    too_many = run_aie("search", "prompts", "--limit", "51", data_dir=indexed_dir)

    assert len(two) == 2
    assert too_many.returncode == 2


def test_search_with_no_hits_says_so_and_exits_0(indexed_dir):
    result = run_aie("search", "zzqxv", data_dir=indexed_dir)

    assert result.returncode == 0
    assert result.stdout.strip() == "No results"


def test_search_bad_syntax_exits_2(indexed_dir):
    result = run_aie("search", "AND", data_dir=indexed_dir)

    assert result.returncode == 2
    assert "invalid query syntax" in result.stderr


def test_search_unknown_speaker_gets_a_hint(indexed_dir):
    result = run_aie("search", "prompts", "--speaker", "Ryan", data_dir=indexed_dir)

    assert result.returncode == 0
    assert "No results" in result.stdout
    assert "Ryan Lopopolo" in result.stdout
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
.venv/bin/pytest tests/test_cli.py -v -k search
```

Expected: the four search tests from earlier tasks still pass; the ten new ones FAIL. `--json` and the filter flags are unrecognised (argparse exit 2), so most fail on `returncode == 0`; the bad-syntax test fails with a traceback exit 1 instead of 2.

- [ ] **Step 3: Replace `search()` and add helpers in `src/aie/search.py`**

Add `BadQuery` next to `MissingIndex`:

```python
class BadQuery(Exception):
    """FTS5 rejected the query text."""
```

Add these functions (replace the existing `search`):

```python
from dataclasses import asdict


def slugify(value: str) -> str:
    return "-".join(value.lower().split())


def filter_sql(filters: Filters) -> tuple[str, list]:
    """WHERE fragment and parameters against alias t (talks)."""
    from .index import resolve_event

    clauses: list[str] = []
    params: list = []
    if filters.event:
        key = resolve_event(filters.event)
        if key:
            clauses.append("t.series = ? AND t.year = ?")
            params += list(key)
        else:
            clauses.append("(t.series = ? OR instr(lower(t.event_raw), ?) > 0)")
            params += [filters.event.lower(), filters.event.lower()]
    if filters.speaker:
        clauses.append("EXISTS (SELECT 1 FROM json_each(t.speakers_json) j "
                       "WHERE lower(json_extract(j.value, '$.name')) = ? OR json_extract(j.value, '$.slug') = ?)")
        params += [filters.speaker.lower(), slugify(filters.speaker)]
    if filters.topic:
        clauses.append("EXISTS (SELECT 1 FROM json_each(t.topics_json) j "
                       "WHERE lower(json_extract(j.value, '$.name')) = ? OR json_extract(j.value, '$.slug') = ?)")
        params += [filters.topic.lower(), slugify(filters.topic)]
    if filters.talk:
        clauses.append("t.slug = ?")
        params.append(filters.talk)
    if filters.after:
        clauses.append("t.start_date >= ?")
        params.append(filters.after)
    if filters.before:
        clauses.append("t.start_date <= ?")
        params.append(filters.before)
    return (" AND ".join(clauses) or "1=1"), params


TALK_COLUMNS = """t.title, t.speakers_json, t.video_id, t.url AS talk_url, t.event_raw,
                  t.start_date, t.end_date, e.title AS edition_title"""


def _talk_fields(r) -> dict:
    return dict(title=r["title"] or "", speakers=speaker_names(r["speakers_json"]),
                event=r["edition_title"] or r["event_raw"], start_date=r["start_date"], end_date=r["end_date"])


def _run_hit(run: list) -> Hit:
    """Merge a run of consecutive matching segments from one talk into one hit."""
    best = min(run, key=lambda r: r["score"])
    return Hit(talk_slug=best["talk_slug"], **_talk_fields(best),
               start_ms=run[0]["start_ms"], end_ms=run[-1]["end_ms"],
               url=yt_url(best["video_id"], run[0]["start_ms"], best["talk_url"] or ""),
               text=best["text"], snippet=best["snip"], kind="segment", score=best["score"])


def collapse_adjacent(rows: list) -> list[Hit]:
    by_talk: dict[str, list] = {}
    for r in rows:
        by_talk.setdefault(r["talk_slug"], []).append(r)
    hits = []
    for talk_rows in by_talk.values():
        talk_rows.sort(key=lambda r: r["seq"])
        run = [talk_rows[0]]
        for r in talk_rows[1:]:
            if r["seq"] == run[-1]["seq"] + 1:
                run.append(r)
            else:
                hits.append(_run_hit(run))
                run = [r]
        hits.append(_run_hit(run))
    return hits


def search(con: sqlite3.Connection, query: str, filters: Filters, limit: int = 10) -> list[Hit]:
    where, params = filter_sql(filters)
    try:
        segment_rows = con.execute(
            f"""
            SELECT s.talk_slug, s.seq, s.start_ms, s.end_ms, s.text,
                   snippet(segments_fts, 0, '', '', '…', 64) AS snip, bm25(segments_fts) AS score,
                   {TALK_COLUMNS}
            FROM segments_fts
            JOIN segments s ON s.id = segments_fts.rowid
            JOIN talks t ON t.slug = s.talk_slug
            LEFT JOIN editions e ON e.series = t.series AND e.year = t.year
            WHERE segments_fts MATCH ? AND {where}
            ORDER BY score LIMIT ?
            """,
            [query, *params, limit * 5],
        ).fetchall()
        doc_rows = con.execute(
            f"""
            SELECT d.slug AS talk_slug, snippet(talk_docs_fts, 1, '', '', '…', 64) AS snip,
                   bm25(talk_docs_fts) AS score, {TALK_COLUMNS}
            FROM talk_docs_fts d
            JOIN talks t ON t.slug = d.slug
            LEFT JOIN editions e ON e.series = t.series AND e.year = t.year
            WHERE talk_docs_fts MATCH ? AND {where}
            ORDER BY score LIMIT ?
            """,
            [query, *params, limit],
        ).fetchall()
    except sqlite3.OperationalError as e:
        raise BadQuery(str(e)) from e
    hits = collapse_adjacent(segment_rows)
    for r in doc_rows:
        hits.append(Hit(talk_slug=r["talk_slug"], **_talk_fields(r), start_ms=0, end_ms=0,
                        url=yt_url(r["video_id"], 0, r["talk_url"] or "").replace("&t=0", ""),
                        text=r["snip"], snippet=r["snip"], kind="metadata", score=r["score"]))
    hits.sort(key=lambda h: h.score)
    return hits[:limit]


def hit_to_dict(hit: Hit) -> dict:
    return asdict(hit)


def filter_hints(con: sqlite3.Connection, filters: Filters) -> list[str]:
    """For each filter value that matches nothing, suggest values that share a word with it."""
    def nearest(values, needle):
        words = [w for w in needle.lower().split() if len(w) > 2]
        return sorted({v for v in values if v and any(w in v.lower() for w in words)})[:5]

    hints = []
    checks = [
        ("speaker", filters.speaker,
         "SELECT DISTINCT json_extract(j.value, '$.name') FROM talks t, json_each(t.speakers_json) j",
         lambda v, names: v.lower() in {n.lower() for n in names} or slugify(v) in {slugify(n) for n in names}),
        ("topic", filters.topic,
         "SELECT DISTINCT json_extract(j.value, '$.name') || ' (' || json_extract(j.value, '$.slug') || ')' "
         "FROM talks t, json_each(t.topics_json) j",
         lambda v, names: any(v.lower() == n.lower() or slugify(v) in n for n in names)),
        ("event", filters.event,
         "SELECT DISTINCT coalesce(e.title, t.event_raw) FROM talks t "
         "LEFT JOIN editions e ON e.series = t.series AND e.year = t.year",
         lambda v, names: any(v.lower() in n.lower() for n in names)),
        ("talk", filters.talk, "SELECT slug FROM talks", lambda v, names: v in names),
    ]
    for label, value, sql, matches in checks:
        if not value:
            continue
        names = [r[0] for r in con.execute(sql).fetchall() if r[0]]
        if not matches(value, names):
            near = nearest(names, value)
            suffix = f"; nearest: {', '.join(near)}" if near else ""
            hints.append(f"no {label} matches {value!r}{suffix}")
    return hints
```

Also update `format_hits` so metadata hits print `[metadata]` in place of the timestamp:

```python
        stamp = "[metadata]" if h.kind == "metadata" else f"[{format_ts(h.start_ms)}]"
        lines.append(f"   {stamp} {h.url}")
```

- [ ] **Step 4: Update `src/aie/cli.py`**

Add helpers and rewrite the search parser and command:

```python
import json


def add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event", help="edition: series like worldsfair, or a title like 'AI Engineer Code 2025'")
    parser.add_argument("--speaker", help="speaker name or slug")
    parser.add_argument("--topic", help="topic name or slug")
    parser.add_argument("--talk", help="restrict to one talk slug")
    parser.add_argument("--after", metavar="YYYY-MM-DD", help="edition start date on or after")
    parser.add_argument("--before", metavar="YYYY-MM-DD", help="edition start date on or before")


def filters_from_args(args) -> search_mod.Filters:
    return search_mod.Filters(event=args.event, speaker=args.speaker, topic=args.topic,
                              talk=args.talk, after=args.after, before=args.before)
```

In `build_parser`, the search subparser becomes:

```python
    p_search = sub.add_parser("search", help="full-text search over transcripts and talk metadata")
    p_search.add_argument("query", help="FTS5 query: words, \"phrases\", OR, NEAR(...)")
    add_filter_arguments(p_search)
    p_search.add_argument("--limit", type=int, default=10, help="1-50, default 10")
    p_search.add_argument("--json", action="store_true")
```

`cmd_search` becomes:

```python
def cmd_search(args) -> int:
    if not 1 <= args.limit <= 50:
        print("--limit must be between 1 and 50", file=sys.stderr)
        return 2
    con = search_mod.connect(args.data_dir)
    filters = filters_from_args(args)
    hits = search_mod.search(con, args.query, filters, limit=args.limit)
    if args.json:
        print(json.dumps([search_mod.hit_to_dict(h) for h in hits], ensure_ascii=False))
        return 0
    print(search_mod.format_hits(hits))
    if not hits:
        for hint in search_mod.filter_hints(con, filters):
            print(hint)
    return 0
```

In `main`, add a handler for bad queries:

```python
    except search_mod.BadQuery as e:
        print(f"invalid query syntax: {e}", file=sys.stderr)
        return 2
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: 26 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/aie/search.py src/aie/cli.py tests/test_cli.py
git commit -m "feat(search): filters, JSON, metadata hits, adjacent collapsing, hints, exit codes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `aie show` prints a talk header, chapters, and a transcript range

**Files:**
- Modify: `src/aie/search.py` (add `UnknownTalk`, `parse_timestamp`, `get_talk`, `chapters_for`, `segments_for`, `format_show`, `show_to_dict`)
- Modify: `src/aie/cli.py` (`show` subcommand)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `connect`, `format_ts`, `format_date_range`, `yt_url`, `speaker_names`.
- Produces: `search.UnknownTalk`, `search.parse_timestamp("MM:SS") -> int` (ms; raises `ValueError`), `search.get_talk(con, slug) -> sqlite3.Row`, `search.chapters_for(con, slug) -> list[Row]`, `search.segments_for(con, slug, from_ms=None, to_ms=None) -> list[Row]` (segments whose `start_ms` lies in the inclusive range), `search.format_show(talk, chapters, segments) -> str`, `search.show_to_dict(talk, chapters, segments) -> dict`.
- CLI: `aie show TALK_SLUG [--from MM:SS] [--to MM:SS] [--json]`; unknown slug exit 1 with `no talk with slug '<slug>'` on stderr; `--from` after `--to` or unparsable time exit 2.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_show_prints_header_chapters_and_the_requested_range(indexed_dir):
    result = run_aie("show", "harness-engineering", "--from", "11:00", "--to", "12:30", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert out.startswith("Harness Engineering: How to Build Software When Humans Steer, Agents Execute")
    assert "Ryan Lopopolo · AI Engineer Europe 2026 (Apr 8-10, 2026) · 46:21" in out
    assert "slug: harness-engineering" in out
    assert "https://www.youtube.com/watch?v=am_oeAoUhew" in out
    assert "[05:11] Scarce Resources" in out
    assert "\n[11:21] " in out
    assert "\n[12:26] " in out
    assert "[00:15] Our next speaker" not in out


def test_show_without_a_range_returns_the_whole_talk_as_json(indexed_dir):
    result = run_aie("show", "harness-engineering", "--json", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["talk"]["slug"] == "harness-engineering"
    assert payload["talk"]["video_id"] == "am_oeAoUhew"
    assert payload["talk"]["duration_ms"] == 2781000
    assert len(payload["chapters"]) == 11
    assert len(payload["segments"]) == 69
    assert payload["segments"][0]["start_ms"] == 15030
    assert payload["segments"][0]["text"].startswith("Our next speaker is here to speak about Harness Engineering")


def test_show_accepts_minutes_past_59(indexed_dir):
    result = run_aie("show", "harness-engineering", "--from", "65:00", "--json", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["segments"] == []


def test_show_unknown_slug_exits_1(indexed_dir):
    result = run_aie("show", "no-such-talk", data_dir=indexed_dir)

    assert result.returncode == 1
    assert "no talk with slug 'no-such-talk'" in result.stderr


def test_show_from_after_to_is_a_usage_error(indexed_dir):
    result = run_aie("show", "harness-engineering", "--from", "20:00", "--to", "10:00", data_dir=indexed_dir)

    assert result.returncode == 2
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
.venv/bin/pytest tests/test_cli.py -v -k show
```

Expected: 5 FAIL, all with argparse `invalid choice: 'show'` (exit 2), so the two tests expecting exit 2 fail on their stdout/stderr assertions being unreachable only if you assert output; the range test as written expects exactly exit 2 and will pass by accident. That is fine: it still fails to prove anything until Step 3, and the other four fail.

- [ ] **Step 3: Add show helpers to `src/aie/search.py`**

```python
class UnknownTalk(Exception):
    """No talk has the requested slug."""


def parse_timestamp(value: str) -> int:
    """'MM:SS' -> milliseconds. Minutes may exceed 59 ('65:00')."""
    minutes, seconds = value.split(":")
    if not minutes.isdigit() or not seconds.isdigit() or int(seconds) > 59:
        raise ValueError(f"expected MM:SS, got {value!r}")
    return (int(minutes) * 60 + int(seconds)) * 1000


def get_talk(con: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row = con.execute(
        f"SELECT t.slug, t.duration_ms, t.summary, {TALK_COLUMNS} FROM talks t "
        "LEFT JOIN editions e ON e.series = t.series AND e.year = t.year WHERE t.slug = ?",
        (slug,),
    ).fetchone()
    if row is None:
        raise UnknownTalk(f"no talk with slug {slug!r}")
    return row


def chapters_for(con: sqlite3.Connection, slug: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT title, start_ms, end_ms FROM chapters WHERE talk_slug = ? ORDER BY start_ms", (slug,)
    ).fetchall()


def segments_for(con: sqlite3.Connection, slug: str, from_ms: int | None = None,
                 to_ms: int | None = None) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT seq, start_ms, end_ms, text FROM segments WHERE talk_slug = ? "
        "AND start_ms >= ? AND start_ms <= ? ORDER BY seq",
        (slug, from_ms or 0, to_ms if to_ms is not None else 2**62),
    ).fetchall()


def format_show(talk: sqlite3.Row, chapters: list, segments: list) -> str:
    who = ", ".join(n for n in speaker_names(talk["speakers_json"]) if n) or "unknown speaker"
    edition = talk["edition_title"] or talk["event_raw"] or "unknown edition"
    when = f" ({format_date_range(talk['start_date'], talk['end_date'])})" if talk["start_date"] else ""
    lines = [
        talk["title"] or talk["slug"],
        f"{who} · {edition}{when} · {format_ts(talk['duration_ms'] or 0)}",
        f"slug: {talk['slug']}",
        yt_url(talk["video_id"], 0, talk["talk_url"] or "").replace("&t=0", ""),
        "",
        "Chapters",
    ]
    lines += [f"  [{format_ts(c['start_ms'])}] {c['title']}" for c in chapters]
    lines += ["", "Transcript"]
    lines += [f"[{format_ts(s['start_ms'])}] {s['text']}" for s in segments]
    return "\n".join(lines)


def show_to_dict(talk: sqlite3.Row, chapters: list, segments: list) -> dict:
    return {
        "talk": {
            "slug": talk["slug"], "title": talk["title"], "speakers": speaker_names(talk["speakers_json"]),
            "event": talk["edition_title"] or talk["event_raw"], "start_date": talk["start_date"],
            "end_date": talk["end_date"], "video_id": talk["video_id"],
            "url": yt_url(talk["video_id"], 0, talk["talk_url"] or "").replace("&t=0", ""),
            "duration_ms": talk["duration_ms"], "summary": talk["summary"],
        },
        "chapters": [dict(c) for c in chapters],
        "segments": [dict(s) for s in segments],
    }
```

- [ ] **Step 4: Add the `show` subcommand to `src/aie/cli.py`**

In `build_parser`:

```python
    p_show = sub.add_parser("show", help="print one talk's header, chapters, and transcript")
    p_show.add_argument("talk_slug")
    p_show.add_argument("--from", dest="from_", metavar="MM:SS", help="start of range, inclusive")
    p_show.add_argument("--to", metavar="MM:SS", help="end of range, inclusive")
    p_show.add_argument("--json", action="store_true")
```

Command:

```python
def cmd_show(args) -> int:
    try:
        from_ms = search_mod.parse_timestamp(args.from_) if args.from_ else None
        to_ms = search_mod.parse_timestamp(args.to) if args.to else None
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if from_ms is not None and to_ms is not None and from_ms > to_ms:
        print("--from must not be after --to", file=sys.stderr)
        return 2
    con = search_mod.connect(args.data_dir)
    talk = search_mod.get_talk(con, args.talk_slug)
    chapters = search_mod.chapters_for(con, args.talk_slug)
    segments = search_mod.segments_for(con, args.talk_slug, from_ms, to_ms)
    if args.json:
        print(json.dumps(search_mod.show_to_dict(talk, chapters, segments), ensure_ascii=False))
    else:
        print(search_mod.format_show(talk, chapters, segments))
    return 0
```

Register it: `COMMANDS = {"sync": cmd_sync, "index": cmd_index, "search": cmd_search, "show": cmd_show}`. In `main`, add `search_mod.UnknownTalk` to the tuple of exceptions that print to stderr and return 1.

- [ ] **Step 5: Run the tests and watch them pass**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: 31 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/aie/search.py src/aie/cli.py tests/test_cli.py
git commit -m "feat(show): talk header, chapters, transcript ranges, JSON output

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `aie talks`, `aie status`, and missing-data messages

**Files:**
- Modify: `src/aie/search.py` (add `list_talks`, `format_talks`, `talk_to_dict`, `read_status`, `format_status`)
- Modify: `src/aie/cli.py` (`talks` and `status` subcommands)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `filter_sql`, `filters_from_args`, `add_filter_arguments`, `connect`, `MissingIndex`.
- Produces: `search.list_talks(con, filters) -> list[Row]` ordered by `start_date` then slug, nulls last; `search.read_status(data_dir) -> dict` with keys `synced` (bool), `corpus_version`, `synced_at`, `indexed` (bool), `indexed_at`, `counts` (dict); `search.format_status(status) -> str`.
- CLI: `aie talks [filters] [--json]`, `aie status`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_talks_lists_every_talk_oldest_edition_first(indexed_dir):
    plain = run_aie("talks", data_dir=indexed_dir)
    as_json = run_aie("talks", "--json", data_dir=indexed_dir)

    assert plain.returncode == 0, plain.stderr
    lines = plain.stdout.strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("structured-llm-outputs-with-pydantic")
    assert "AI Engineer Summit 2023 (Oct 8-10, 2023)" in lines[0]
    assert lines[1].startswith("graphrag")
    assert lines[2].startswith("harness-engineering")
    assert [t["slug"] for t in json.loads(as_json.stdout)] == [
        "structured-llm-outputs-with-pydantic", "graphrag", "harness-engineering"]


def test_talks_accepts_the_search_filters(indexed_dir):
    by_speaker = run_aie("talks", "--speaker", "emil eifrem", "--json", data_dir=indexed_dir)
    after = run_aie("talks", "--after", "2026-01-01", "--json", data_dir=indexed_dir)

    assert [t["slug"] for t in json.loads(by_speaker.stdout)] == ["graphrag"]
    assert [t["slug"] for t in json.loads(after.stdout)] == ["harness-engineering"]


def test_status_reports_version_and_counts(indexed_dir):
    result = run_aie("status", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    assert "corpus version: 575e4c565354bf07b7d567ab08376f4176910a799bf0ef29ed41868192e0dc24" in result.stdout
    assert "synced: 2026-09-14T00:00:00+00:00" in result.stdout
    assert "indexed:" in result.stdout
    assert "talks: 3 · segments: 108 · chapters: 31 · editions: 10" in result.stdout


def test_status_on_an_empty_data_dir(tmp_path):
    result = run_aie("status", data_dir=tmp_path / "data")

    assert result.returncode == 0
    assert "not synced" in result.stdout
    assert "not indexed" in result.stdout


def test_query_commands_without_an_index_exit_1(synced_dir):
    for command in (["search", "prompts"], ["show", "graphrag"], ["talks"]):
        result = run_aie(*command, data_dir=synced_dir)
        assert result.returncode == 1, command
        assert "Run `aie sync` then `aie index`" in result.stderr, command
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
.venv/bin/pytest tests/test_cli.py -v -k "talks or status or without_an_index"
```

Expected: `talks` and `status` tests FAIL with argparse `invalid choice` (exit 2). `without_an_index` FAILS on the `talks` command for the same reason (search and show already behave).

- [ ] **Step 3: Add listing and status helpers to `src/aie/search.py`**

```python
def list_talks(con: sqlite3.Connection, filters: Filters) -> list[sqlite3.Row]:
    where, params = filter_sql(filters)
    return con.execute(
        f"SELECT t.slug, t.duration_ms, {TALK_COLUMNS} FROM talks t "
        "LEFT JOIN editions e ON e.series = t.series AND e.year = t.year "
        f"WHERE {where} ORDER BY t.start_date IS NULL, t.start_date, t.slug",
        params,
    ).fetchall()


def talk_to_dict(row: sqlite3.Row) -> dict:
    return {"slug": row["slug"], "title": row["title"], "speakers": speaker_names(row["speakers_json"]),
            "event": row["edition_title"] or row["event_raw"], "start_date": row["start_date"],
            "end_date": row["end_date"], "duration_ms": row["duration_ms"],
            "url": yt_url(row["video_id"], 0, row["talk_url"] or "").replace("&t=0", "")}


def format_talks(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "No results"
    lines = []
    for r in rows:
        who = ", ".join(n for n in speaker_names(r["speakers_json"]) if n) or "unknown speaker"
        edition = r["edition_title"] or r["event_raw"] or "unknown edition"
        when = f" ({format_date_range(r['start_date'], r['end_date'])})" if r["start_date"] else ""
        lines.append(f"{r['slug']}  {r['title']} — {who} · {edition}{when}")
    return "\n".join(lines)


def read_status(data_dir: Path) -> dict:
    status = {"synced": False, "corpus_version": None, "synced_at": None,
              "indexed": False, "indexed_at": None, "counts": {}}
    version_file = data_dir / "raw" / "version.json"
    if version_file.exists():
        version = json.loads(version_file.read_text())
        status.update(synced=True, corpus_version=version.get("corpusVersion"), synced_at=version.get("syncedAt"))
    db = data_dir / "aie.db"
    if db.exists():
        con = connect(data_dir)
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        con.close()
        status.update(indexed=True, indexed_at=meta.get("indexed_at"),
                      counts=json.loads(meta.get("counts") or "{}"))
    return status


def format_status(status: dict) -> str:
    lines = []
    if status["synced"]:
        lines.append(f"corpus version: {status['corpus_version']}")
        lines.append(f"synced: {status['synced_at']}")
    else:
        lines.append("not synced (run `aie sync`)")
    if status["indexed"]:
        c = status["counts"]
        lines.append(f"indexed: {status['indexed_at']}")
        lines.append(f"talks: {c.get('talks', 0)} · segments: {c.get('segments', 0)} · "
                     f"chapters: {c.get('chapters', 0)} · editions: {c.get('editions', 0)}")
    else:
        lines.append("not indexed (run `aie index`)")
    return "\n".join(lines)
```

- [ ] **Step 4: Add the subcommands to `src/aie/cli.py`**

In `build_parser`:

```python
    p_talks = sub.add_parser("talks", help="list talks matching filters")
    add_filter_arguments(p_talks)
    p_talks.add_argument("--json", action="store_true")

    sub.add_parser("status", help="show local corpus version, index time, and counts")
```

Commands:

```python
def cmd_talks(args) -> int:
    con = search_mod.connect(args.data_dir)
    rows = search_mod.list_talks(con, filters_from_args(args))
    if args.json:
        print(json.dumps([search_mod.talk_to_dict(r) for r in rows], ensure_ascii=False))
    else:
        print(search_mod.format_talks(rows))
    return 0


def cmd_status(args) -> int:
    print(search_mod.format_status(search_mod.read_status(args.data_dir)))
    return 0
```

Register both in `COMMANDS`.

- [ ] **Step 5: Run the tests and watch them pass**

```bash
.venv/bin/pytest tests/test_cli.py -v
```

Expected: 36 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/aie/search.py src/aie/cli.py tests/test_cli.py
git commit -m "feat: talks listing, status command, missing-index messages

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Claude Code skill, README, and opt-in live smoke test

**Files:**
- Create: `.claude/skills/aie-archive/SKILL.md`, `README.md`, `tests/test_live.py`

**Interfaces:**
- Consumes: the finished CLI from Tasks 1-7.
- Produces: the skill Claude Code loads for archive questions; a live test that runs only with `AIE_LIVE_TESTS=1`.

- [ ] **Step 1: Write the live test (it is skipped by default, so RED here means "skipped", then GREEN means it passes when enabled)**

`tests/test_live.py`:

```python
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
```

Run without the flag:

```bash
.venv/bin/pytest tests/test_live.py -v
```

Expected: 2 SKIPPED. Then run once with the flag to confirm the upstream shape:

```bash
AIE_LIVE_TESTS=1 .venv/bin/pytest tests/test_live.py -v
```

Expected: 2 PASS (needs network; two requests).

- [ ] **Step 2: Write the skill**

`.claude/skills/aie-archive/SKILL.md`:

```markdown
---
name: aie-archive
description: Answer questions about AI engineering practice, tools, models, and vendors from the local archive of AI Engineer conference transcripts. Use for any question where conference speakers would have opinions or experience to share.
---

# AIE archive

A local, full-text-searchable copy of every AI Engineer conference transcript,
queried through the `aie` CLI (run it as `.venv/bin/aie` from the repo root,
or `aie` if the venv is active).

## Before answering

Run `aie status`. If it says "not synced" or "not indexed", stop and tell the
user to run `aie sync` (about 36 minutes the first time) and then `aie index`.
Do not answer from anything but the archive.

## How to search

The query language is SQLite FTS5: bare words are ANDed, `"quoted phrases"`
match exactly, `OR` works, `NEAR(a b, 10)` finds words close together, and
`term*` matches prefixes. Words are stemmed, so `prompting` finds `prompt`.
Hyphenated words must be quoted: `"auto-compaction"`.

1. Write two or three phrasings of the question in the words a speaker would
   use, not the user's words. Cover the product name, the generic term, and a
   concrete symptom. Example for "pitfalls of Claude research mode":
   `aie search '"research mode" OR "deep research"'`,
   `aie search 'research agent pitfalls OR mistakes OR failure'`,
   `aie search 'claude research citations wrong OR hallucinated'`.
2. Run at least three distinct searches before concluding the archive has
   nothing. Use `--after YYYY-MM-DD` to prefer recent editions on fast-moving
   questions such as model comparisons, and `--speaker`, `--topic`, `--event`,
   `--talk` to narrow. `aie talks --topic <slug>` lists what exists.
3. Use `--json` when you need to process many hits; the plain output is for
   reading a few.

## Before quoting

A hit is one transcript segment and often cuts mid-thought. For every hit you
intend to use, run `aie show <slug> --from MM:SS --to MM:SS` with a window of
two to three minutes around the hit's timestamp, and read it before quoting.

## How to answer

- Group findings by claim, not by talk.
- Attribute every claim to the speaker and talk, with the timestamped YouTube
  link from the hit (`https://www.youtube.com/watch?v=...&t=...`).
- Say whether the speaker asserted something or demonstrated it.
- Note the edition date; a 2026 talk outweighs a 2023 talk on anything that
  changes fast.
- Automated transcripts contain errors. Quote short passages and say when a
  word is likely a transcription mistake.

## Never

- Never quote the `summary` field or a metadata hit as if it were something
  the speaker said. Metadata hits (`[metadata]`) only tell you which talk to
  open.
- Never answer from general knowledge, web search, or any source other than
  this archive. When the archive has nothing, say exactly that and list the
  queries you tried.
```

- [ ] **Step 3: Write the README**

`README.md`:

```markdown
# AI Engineer transcript archive

A local, searchable archive of the AI Engineer conference transcripts from
https://ai.engineer/data, built so Claude Code can answer questions from what
speakers actually said, with citations.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/aie sync      # downloads ~1,100 files, one every 2 s, about 36 minutes
.venv/bin/aie index     # builds data/aie.db in a few seconds
.venv/bin/aie status
```

## Use

```bash
aie search '"research mode" OR "deep research"' --after 2026-01-01
aie show harness-engineering --from 11:00 --to 13:00
aie talks --speaker "Ryan Lopopolo"
```

`aie search --help` lists the filters. Queries use SQLite FTS5 syntax.
In Claude Code, the `aie-archive` skill in `.claude/skills` tells Claude how
to use these commands and to answer only from the archive.

## Tests

```bash
.venv/bin/pytest                      # offline, against tests/fixtures
AIE_LIVE_TESTS=1 .venv/bin/pytest tests/test_live.py   # two real requests
```

Design: `docs/superpowers/specs/2026-09-14-aie-archive-design.md`.
```

- [ ] **Step 4: Run the whole suite**

```bash
.venv/bin/pytest -v
```

Expected: 36 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/aie-archive/SKILL.md README.md tests/test_live.py
git commit -m "docs: aie-archive skill, README, opt-in live smoke test

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Spec coverage check

| Spec section | Task |
|---|---|
| 2 Data source endpoints, shapes, event inconsistency | 1 (sync URLs), 4 (`resolve_event`) |
| 3 Layout and stack | 1 |
| 4 Data model, normalization, ranking, collapsing | 1, 4, 5 |
| 5 Sync: order, throttle, tmp writes, resume, retries, breaker, version last, editions.json | 1, 2, 3 |
| 6 Index: tmp build and rename, sanity check, malformed skip, counts, exit 1 | 4 |
| 7 CLI: sync, index, search, show, talks, status, `--data-dir`, env | 1, 5, 6, 7 |
| 8 Skill | 8 |
| 9 Errors and exit codes | 4, 5, 6, 7 |
| 10 Tests: fake site, fixtures, tracer bullet, live test, seams | 1 (harness, tracer), 2-7, 8 (live) |
