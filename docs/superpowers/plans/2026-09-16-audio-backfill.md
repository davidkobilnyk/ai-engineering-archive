# Audio Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An `aie backfill` command that fetches, verifies, and records the best Opus and AAC audio, the English caption track, and the metadata snapshot for every corpus video onto the archive drive, unattended, inside the nightly window and its guards.

**Architecture:** A new subpackage `src/aie/ingest/` with one module per concern: `ytdlp.py` builds and runs the one yt-dlp call per video and classifies its outcome; `verify.py` runs ffprobe and streamhash; `records.py` owns the per-video `fetch.json` that doubles as the manifest; `guards.py` runs the fail-closed checks; `status.py` writes `status.json` and pings healthchecks; `backfill.py` is the run loop; `cli.py` gains the subcommand. Every test drives `python -m aie backfill` in a subprocess against a temp archive directory, with fake `yt-dlp`, `pmset`, `route`, and `dig` executables on `PATH` and real `ffprobe` and `ffmpeg` from Homebrew.

**Tech Stack:** Python 3.12+, standard library `subprocess`, `fcntl`, `zoneinfo`, `signal`, `hashlib`, `httpx` (already a dependency), yt-dlp as a subprocess (`yt-dlp[default]` in the project venv), Homebrew ffmpeg 9 and Deno 2.9.

**Spec:** `docs/superpowers/specs/2026-09-16-audio-backfill-design.md`

## Global Constraints

- Python `>=3.12`; the machine runs 3.13.3 in `.venv`. yt-dlp 2026.08.19 is already installed in `.venv` from the calibration run.
- Runtime dependency stays `httpx` only. New optional group `ingest = ["yt-dlp[default]>=2026.8.19"]`. Dev dependency `pytest` only.
- Tests only at the CLI seam via subprocess. No test imports `aie` internals. Expected values are literals: file names from the spec's output templates, hashes from `tests/fixtures/audio/README.md`, ids from `tests/fixtures/talks.json`.
- Every task: write the failing test, run it and see it fail, implement, run it and see it pass, commit. RED then GREEN, always.
- All external binaries are called with `subprocess`. yt-dlp, ffmpeg, ffprobe and Deno by absolute path from CLI options; `pmset`, `route`, `dig` by name on `PATH` (the LaunchAgent sets `PATH`, the tests prepend `tests/fakes`).
- The archive root is `--archive-dir`, default `$AIE_ARCHIVE_DIR` or `/Volumes/Archive`. Video files live in `<archive>/videos/<id>/`. Names come from the templates `%(id)s.f%(format_id)s.%(ext)s`, `%(id)s.en.json3`, `%(id)s.info.json`; the record is `%(id)s.fetch.json`; yt-dlp stderr is saved as `%(id)s.yt-dlp.log`.
- The yt-dlp invocation is exactly spec section 5. Do not add, drop, or reorder flags.
- Exit codes: 0 for a completed run and for every guard skip; 1 when the run stopped on a challenge, the breaker, or a signal; 2 for usage errors.
- Timestamps in records and status are UTC ISO 8601 with seconds. The window is America/New_York.
- Sandbox note for the executor: the sandboxed shell can write to `/Volumes/Archive` but cannot reach YouTube or resolve DNS. Never run the real command against YouTube from the sandbox; the owner does that from the Terminal panel.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Fixture facts used as test literals

| Fact | Value |
|---|---|
| Fixture audio files | `tests/fixtures/audio/silence.f251.webm` (1,010 bytes, Opus 48 kHz stereo, ffprobe duration 1.008 s) and `tests/fixtures/audio/silence.f140.m4a` (1,271 bytes, AAC 44.1 kHz stereo, ffprobe duration 1.000 s) |
| Opus streamhash sha256 | `e80bf0d53e2e9756c2a0dcf16a486493e917cacf4cb57adcadc9394eac2d7eb4` |
| AAC streamhash sha256 | `4025563f21c80dda474e195f5b8d3c8b5165b31a17af5c477114d401dce81957` |
| Opus file sha256 | `04ed4546fe104003e5e71d3edeed135df0ed69b9c77b81ab7a1fac64d2ee8f29` |
| AAC file sha256 | `0ea96d6011b3d8131a93edeb19c18ea33e17b92cca4bb590f04cf980fecfc07b` |
| Video ids in `tests/fixtures/talks.json`, in file order | `knDDGYHnnSI`, `yj-wSRJwrrc`, `am_oeAoUhew` |
| Fake yt-dlp version string | `2026.08.19` |
| Fake yt-dlp rows (ok mode) | format `251`, acodec `opus`, abr `113.488`, note `English (US) original (default), medium`, language `en-US`; format `140`, acodec `mp4a.40.2`, abr `129.479`, same note and language |
| Fake yt-dlp row (dub mode, Opus row only) | format `251-11`, abr `146.859`, note `Malayalam, medium`, language `ml` |
| Fake info.json | `duration` 1, `upload_date` `20240828`, `formats` list matching the rows |
| Fake caption file | one event, so `events` = 1 |
| Charter ASN answer from fake dig | `"20115 | 71.81.192.0/18 | US | arin | 2005-05-19"` |
| Public IP answer from fake dig | `"71.81.249.26"` |

## File structure

```
pyproject.toml                          add the ingest extra
src/aie/ingest/__init__.py
src/aie/ingest/records.py               per-video fetch.json: paths, read, atomic write, done ids, case check, totals
src/aie/ingest/verify.py                ffprobe_audio, streamhash_sha256, sha256_file, VerifyError
src/aie/ingest/ytdlp.py                 Tools, AUDIO_SELECTOR, build_command, Runner, parse_rows, rows_from_files, classify, version
src/aie/ingest/status.py                Status dataclass load/save, utc_now_iso, ping
src/aie/ingest/guards.py                parse_window, in_window, window_end, mains, vpn, asn, drive, lock, check
src/aie/ingest/backfill.py              Config, RunResult, id sources, build_queue, process_video, build_record, run
src/aie/cli.py                          backfill subcommand and cmd_backfill
tests/fakes/yt-dlp                      fake yt-dlp (Python, executable)
tests/fakes/pmset                       prints FAKE_PMSET_OUTPUT
tests/fakes/route                       prints FAKE_ROUTE_OUTPUT
tests/fakes/dig                         prints FAKE_DIG_IP or FAKE_DIG_ASN
tests/fixtures/audio/README.md          generating commands and hash literals
tests/conftest.py                       backfill_command, run_backfill, ytdlp_calls, archive fixture
tests/test_backfill.py                  all backfill seam tests
docs/ingest/com.aie.backfill.plist      LaunchAgent
docs/ingest/audio-backfill-setup.md     owner setup and operations
README.md                               short backfill section
```

---

### Task 1: Scaffold, fakes, and the tracer bullet (fetch, verify, record, skip on rerun)

**Files:**
- Modify: `pyproject.toml`
- Create: `src/aie/ingest/__init__.py`, `src/aie/ingest/records.py`, `src/aie/ingest/verify.py`, `src/aie/ingest/ytdlp.py`, `src/aie/ingest/status.py`, `src/aie/ingest/guards.py` (drive and lock only in this task), `src/aie/ingest/backfill.py`
- Modify: `src/aie/cli.py`
- Create: `tests/fakes/yt-dlp`, `tests/fixtures/audio/README.md`
- Modify: `tests/conftest.py`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `tests/fixtures/audio/silence.f251.webm` and `silence.f140.m4a` (already on disk, untracked; this task commits them).
- Produces, for later tasks:
  - `records.video_dir(archive: Path, video_id: str) -> Path`, `records.record_path(...)`, `records.read_record(...) -> dict | None`, `records.write_record(archive, video_id, record: dict)`, `records.write_atomic_json(path, data)`, `records.done_ids(archive) -> set[str]`, `records.case_collision(archive, video_id) -> str | None`, `records.summarize(archive) -> tuple[int, int, int]`, `records.SCHEMA_VERSION = 1`, `records.VIDEOS_DIR = "videos"`.
  - `verify.Probe(codec, duration_s, sample_rate, channels)`, `verify.ffprobe_audio(ffprobe: Path, file: Path) -> Probe`, `verify.streamhash_sha256(ffmpeg: Path, file: Path) -> str`, `verify.sha256_file(file) -> str`, `verify.VerifyError`.
  - `ytdlp.Tools(yt_dlp, ffmpeg_dir, deno)` with `.ffmpeg` and `.ffprobe` properties, `ytdlp.Row`, `ytdlp.Outcome(kind, exit_code, rows, message)`, `ytdlp.build_command(tools, video_id, out_dir, verbose=False) -> list[str]`, `ytdlp.Runner().run(tools, video_id, out_dir, log_path, verbose) -> Outcome`, `Runner.stop()`, `ytdlp.parse_rows(stdout) -> list[Row]`, `ytdlp.rows_from_files(out_dir, video_id, info) -> list[Row]`, `ytdlp.classify(exit_code, stderr) -> str`, `ytdlp.version(tools) -> str`.
  - `status.Status` dataclass with `load(archive)` and `save(archive)`, `status.utc_now_iso()`, `status.ping(url, fail=False)`.
  - `guards.drive_ready(archive) -> bool`, `guards.acquire_lock(archive) -> int | None`, `guards.GuardConfig`, `guards.check(cfg, now) -> tuple[str | None, int | None]`.
  - `backfill.Config`, `backfill.RunResult`, `backfill.ids_from_talks_json(path)`, `backfill.ids_from_file(path)`, `backfill.build_queue(archive, ids)`, `backfill.process_video(cfg, runner, video_id, yt_dlp_version) -> tuple[str, str]`, `backfill.build_record(...)`, `backfill.run(cfg, log=print) -> RunResult`.
  - conftest: `backfill_command(*args, archive) -> list[str]`, `backfill_env(archive, data_dir=None, env=None) -> dict`, `run_backfill(*args, archive, data_dir=None, env=None) -> CompletedProcess`, `ytdlp_calls(archive) -> list[list[str]]`, fixture `archive`.

- [ ] **Step 1: Add the ingest extra and commit the fixtures with their README**

Edit `pyproject.toml`, replacing the `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
ingest = ["yt-dlp[default]>=2026.8.19"]
```

Create `tests/fixtures/audio/README.md`:

```markdown
# Audio fixtures

One second of silence in each of the two containers the backfill keeps,
generated on 2026-09-16 with Homebrew ffmpeg 9.0.1:

    ffmpeg -f lavfi -i anullsrc=r=48000:cl=stereo -t 1 -c:a libopus -b:a 64k \
        -metadata:s:a:0 language=eng silence.f251.webm
    ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 1 -c:a aac -b:a 128k \
        -movflags +faststart silence.f140.m4a

Values recorded at generation time; the tests use them as literals.

| file | bytes | ffprobe codec / rate / channels / duration | streamhash sha256 (`ffmpeg -map 0:a:0 -c copy -f streamhash -hash sha256 -`) | file sha256 |
|---|---|---|---|---|
| `silence.f251.webm` | 1010 | opus / 48000 / 2 / 1.008 | `e80bf0d53e2e9756c2a0dcf16a486493e917cacf4cb57adcadc9394eac2d7eb4` | `04ed4546fe104003e5e71d3edeed135df0ed69b9c77b81ab7a1fac64d2ee8f29` |
| `silence.f140.m4a` | 1271 | aac / 44100 / 2 / 1.000 | `4025563f21c80dda474e195f5b8d3c8b5165b31a17af5c477114d401dce81957` | `0ea96d6011b3d8131a93edeb19c18ea33e17b92cca4bb590f04cf980fecfc07b` |

Do not regenerate casually: a different ffmpeg build may encode
differently and change every literal in `tests/test_backfill.py`.
```

Run: `.venv/bin/pip install -e ".[dev,ingest]" -q && .venv/bin/yt-dlp --version`
Expected: `2026.08.19`

Commit:

```bash
git add pyproject.toml tests/fixtures/audio
git commit -m "Audio fixtures and the ingest extra

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the fake yt-dlp**

Create `tests/fakes/yt-dlp` (no extension) and `chmod +x` it:

```python
#!/usr/bin/env python3
"""Fake yt-dlp for the backfill seam tests.

Mimics the parts of the real contract the backfill relies on: the -o
templates, the after_move print rows on stdout, ERROR lines on stderr,
exit codes, --no-overwrites, .part files, and --version.

Environment:
  FAKE_YTDLP_LOG     argv is appended to this file as one JSON line per call
  FAKE_YTDLP_SCRIPT  JSON object mapping video id to a mode:
                     ok (default), challenge, unavailable, fail, dub
  FAKE_YTDLP_SLEEP   seconds to hold each .part file before finishing it
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
IMPERSONATION_WARNING = ("WARNING: The extractor specified to use impersonation for this download, "
                         "but no impersonate target is available.")

argv = sys.argv[1:]
if argv == ["--version"]:
    print("2026.08.19")
    sys.exit(0)

if os.environ.get("FAKE_YTDLP_LOG"):
    with open(os.environ["FAKE_YTDLP_LOG"], "a") as f:
        f.write(json.dumps(argv) + "\n")

url = argv[-1]
video_id = url.split("v=")[-1]
templates = [argv[i + 1] for i, a in enumerate(argv) if a == "-o"]
main_template = next(t for t in templates if not t.startswith(("subtitle:", "infojson:")))
out_dir = Path(main_template).parent
mode = json.loads(os.environ.get("FAKE_YTDLP_SCRIPT", "{}")).get(video_id, "ok")

if mode == "challenge":
    print(f"ERROR: [youtube] {video_id}: Sign in to confirm you're not a bot. "
          "This helps protect our community.", file=sys.stderr)
    sys.exit(1)
if mode == "unavailable":
    print(f"ERROR: [youtube] {video_id}: Video unavailable", file=sys.stderr)
    sys.exit(1)
if mode == "fail":
    print("ERROR: Unable to download webpage: <urlopen error [Errno 8] "
          "nodename nor servname provided, or not known>", file=sys.stderr)
    sys.exit(1)

formats = [
    {"format_id": "251", "acodec": "opus", "abr": 113.488, "ext": "webm", "language": "en-US",
     "format_note": "English (US) original (default), medium", "fixture": "silence.f251.webm"},
    {"format_id": "140", "acodec": "mp4a.40.2", "abr": 129.479, "ext": "m4a", "language": "en-US",
     "format_note": "English (US) original (default), medium", "fixture": "silence.f140.m4a"},
]
if mode == "dub":
    formats[0] = {**formats[0], "format_id": "251-11", "abr": 146.859,
                  "format_note": "Malayalam, medium", "language": "ml"}

out_dir.mkdir(parents=True, exist_ok=True)
hold = float(os.environ.get("FAKE_YTDLP_SLEEP", "0"))
for fmt in formats:
    target = out_dir / f"{video_id}.f{fmt['format_id']}.{fmt['ext']}"
    if target.exists():
        print(f"[download] {target} has already been downloaded", file=sys.stderr)
        continue
    part = target.with_name(target.name + ".part")
    shutil.copy(FIXTURES / fmt["fixture"], part)
    if hold:
        time.sleep(hold)
    os.replace(part, target)
    print("\t".join(["ROW", fmt["format_id"], fmt["acodec"], str(fmt["abr"]),
                     fmt["format_note"], fmt["language"], str(target)]))

caption = out_dir / f"{video_id}.en.json3"
if not caption.exists():
    caption.write_text(json.dumps(
        {"events": [{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "silence"}]}]}))
info = out_dir / f"{video_id}.info.json"
if not info.exists():
    info.write_text(json.dumps({
        "id": video_id, "title": "fixture talk", "duration": 1, "upload_date": "20240828",
        "formats": [{k: v for k, v in fmt.items() if k != "fixture"} for fmt in formats]}))
print(IMPERSONATION_WARNING, file=sys.stderr)
```

Run: `chmod +x tests/fakes/yt-dlp && tests/fakes/yt-dlp --version`
Expected: `2026.08.19`

- [ ] **Step 3: Add the backfill harness to conftest**

Append to `tests/conftest.py`:

```python
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
```

- [ ] **Step 4: Write the failing tracer-bullet test**

Create `tests/test_backfill.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_backfill.py -v`
Expected: both FAIL; stderr of the subprocess contains `invalid choice: 'backfill'`.

- [ ] **Step 6: Create `src/aie/ingest/__init__.py` and `records.py`**

`src/aie/ingest/__init__.py`:

```python
"""Download-phase ingest: fetch YouTube artifacts onto the archive drive."""
```

`src/aie/ingest/records.py`:

```python
"""Per-video fetch records on the archive drive. A record present means done."""
from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA_VERSION = 1
VIDEOS_DIR = "videos"


def videos_root(archive: Path) -> Path:
    return archive / VIDEOS_DIR


def video_dir(archive: Path, video_id: str) -> Path:
    return videos_root(archive) / video_id


def record_path(archive: Path, video_id: str) -> Path:
    return video_dir(archive, video_id) / f"{video_id}.fetch.json"


def read_record(archive: Path, video_id: str) -> dict | None:
    path = record_path(archive, video_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def write_record(archive: Path, video_id: str, record: dict) -> None:
    video_dir(archive, video_id).mkdir(parents=True, exist_ok=True)
    write_atomic_json(record_path(archive, video_id), record)


def done_ids(archive: Path) -> set[str]:
    root = videos_root(archive)
    if not root.is_dir():
        return set()
    return {d.name for d in root.iterdir()
            if d.is_dir() and (d / f"{d.name}.fetch.json").exists()}


def case_collision(archive: Path, video_id: str) -> str | None:
    """The name of an existing directory that equals video_id ignoring case only."""
    root = videos_root(archive)
    if not root.is_dir():
        return None
    for d in root.iterdir():
        if d.name != video_id and d.name.lower() == video_id.lower():
            return d.name
    return None


def summarize(archive: Path) -> tuple[int, int, int]:
    """(records_total, unavailable_total, captions_missing_total)."""
    total = unavailable = captions_missing = 0
    for video_id in done_ids(archive):
        record = read_record(archive, video_id) or {}
        total += 1
        if record.get("status") == "unavailable":
            unavailable += 1
        if "captions_missing" in record.get("warnings", []):
            captions_missing += 1
    return total, unavailable, captions_missing
```

- [ ] **Step 7: Create `verify.py`**

```python
"""ffprobe, elementary-stream hash, and file hash checks on fetched files."""
from __future__ import annotations

import hashlib
import json
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
```

- [ ] **Step 8: Create `ytdlp.py`**

```python
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
```

- [ ] **Step 9: Create `status.py`**

```python
"""The glanceable status.json on the archive root, and the healthchecks ping."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .records import write_atomic_json

STATUS_NAME = "status.json"


@dataclass
class Status:
    last_run_start: str | None = None
    last_run_end: str | None = None
    last_outcome: str | None = None
    last_success_time: str | None = None
    videos_completed_last_run: int = 0
    videos_failed_last_run: int = 0
    queue_depth: int = 0
    records_total: int = 0
    unavailable_total: int = 0
    captions_missing_total: int = 0
    yt_dlp_version: str | None = None
    backoff_until: str | None = None
    consecutive_challenges: int = 0
    last_error: str | None = None
    current_video: str | None = None

    @classmethod
    def load(cls, archive: Path) -> "Status":
        path = archive / STATUS_NAME
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, archive: Path) -> None:
        try:
            write_atomic_json(archive / STATUS_NAME, asdict(self))
        except OSError:
            pass  # the drive is the thing that is missing; nothing to write to


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ping(url: str | None, fail: bool = False) -> None:
    if not url:
        return
    target = url.rstrip("/") + ("/fail" if fail else "")
    try:
        httpx.get(target, timeout=10)
    except httpx.HTTPError:
        pass
```

- [ ] **Step 10: Create `guards.py` with the drive check and the lock only**

```python
"""Fail-closed checks that run before any download."""
from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .records import VIDEOS_DIR

LOCAL_TZ = ZoneInfo("America/New_York")
LOCK_NAME = ".backfill.lock"


def parse_window(text: str) -> tuple[time, time]:
    """'01:00-07:00' -> (time(1, 0), time(7, 0)). Raises ValueError."""
    start, end = text.split("-")
    return time.fromisoformat(start), time.fromisoformat(end)


def window_end(now: datetime, start: time, end: time) -> datetime:
    """When the window that contains `now` closes, as an aware local datetime."""
    local = now.astimezone(LOCAL_TZ)
    end_dt = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if end_dt <= local:
        end_dt += timedelta(days=1)
    return end_dt


def drive_ready(archive: Path) -> bool:
    """A path under /Volumes must be a real mount point (an unplugged drive can
    leave a stale folder); any archive dir must be writable."""
    if str(archive).startswith("/Volumes/") and not os.path.ismount(archive):
        return False
    try:
        (archive / VIDEOS_DIR).mkdir(parents=True, exist_ok=True)
        probe = archive / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        return False
    return True


def acquire_lock(archive: Path) -> int | None:
    """flock on <archive>/.backfill.lock; None when another run holds it.
    The lock is released by the kernel when the process exits, however it exits."""
    fd = os.open(archive / LOCK_NAME, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode())
    return fd


@dataclass
class GuardConfig:
    archive: Path
    window: tuple[time, time]
    manual: bool                      # --now: skip the window and mains guards
    backoff_until: datetime | None


def check(cfg: GuardConfig, now: datetime) -> tuple[str | None, int | None]:
    """Return (skip_reason, lock_fd). A None reason means every guard passed
    and the lock is held."""
    if not drive_ready(cfg.archive):
        return "skipped:drive", None
    fd = acquire_lock(cfg.archive)
    if fd is None:
        return "skipped:lock", None
    return None, fd
```

- [ ] **Step 11: Create `backfill.py`**

```python
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
```

- [ ] **Step 12: Wire the CLI**

In `src/aie/cli.py`, add `from .ingest import backfill as backfill_mod, guards as guards_mod, ytdlp as ytdlp_mod` next to the other imports, then in `build_parser()` before `return parser`:

```python
    p_bf = sub.add_parser("backfill", help="fetch audio, captions and metadata for corpus videos "
                                           "onto the archive drive")
    p_bf.add_argument("--archive-dir", type=Path,
                      default=Path(os.environ.get("AIE_ARCHIVE_DIR", "/Volumes/Archive")),
                      help="archive root (default /Volumes/Archive or $AIE_ARCHIVE_DIR)")
    source = p_bf.add_mutually_exclusive_group()
    source.add_argument("--ids-file", type=Path, help="one video ID per line, # comments")
    source.add_argument("--ids", nargs="+", metavar="ID", help="video IDs to fetch")
    p_bf.add_argument("--limit", type=int, default=200, help="videos started per run (default 200)")
    p_bf.add_argument("--now", action="store_true", help="manual run: skip the window and mains guards")
    p_bf.add_argument("--window", default="01:00-07:00",
                      help="nightly window in America/New_York (default 01:00-07:00)")
    p_bf.add_argument("--dry-run", action="store_true", help="run the guards, print the queue, fetch nothing")
    p_bf.add_argument("--yt-dlp", type=Path, default=Path(sys.executable).with_name("yt-dlp"),
                      help="yt-dlp binary (default: the one beside this Python)")
    p_bf.add_argument("--ffmpeg-dir", type=Path, default=Path("/opt/homebrew/bin"),
                      help="directory holding ffmpeg and ffprobe")
    p_bf.add_argument("--deno", type=Path, default=Path("/opt/homebrew/bin/deno"))
    p_bf.add_argument("--verbose", action="store_true", help="pass -v to yt-dlp")
```

Add the command and register it:

```python
def cmd_backfill(args) -> int:
    if args.limit < 1:
        print("--limit must be at least 1", file=sys.stderr)
        return 2
    try:
        guards_mod.parse_window(args.window)
    except ValueError:
        print("--window must look like HH:MM-HH:MM", file=sys.stderr)
        return 2
    if args.ids:
        ids = args.ids
    elif args.ids_file:
        ids = backfill_mod.ids_from_file(args.ids_file)
    else:
        talks = args.data_dir / "raw" / "talks.json"
        if not talks.exists():
            print(f"no talks file at {talks}; run `aie sync` or pass --ids-file", file=sys.stderr)
            return 1
        ids = backfill_mod.ids_from_talks_json(talks)
    cfg = backfill_mod.Config(
        archive=args.archive_dir.resolve(), ids=ids,
        tools=ytdlp_mod.Tools(args.yt_dlp, args.ffmpeg_dir, args.deno),
        limit=args.limit, manual=args.now, window=args.window, dry_run=args.dry_run,
        verbose=args.verbose, healthcheck_url=os.environ.get("AIE_HEALTHCHECK_URL"))
    result = backfill_mod.run(cfg)
    print(f"{result.outcome}: completed {result.completed}, failed {result.failed}, "
          f"remaining {result.remaining}")
    return result.exit_code
```

```python
COMMANDS = {
    "sync": cmd_sync, "index": cmd_index, "search": cmd_search,
    "show": cmd_show, "talks": cmd_talks, "status": cmd_status, "backfill": cmd_backfill,
}
```

- [ ] **Step 13: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_backfill.py -v`
Expected: both PASS.

Run: `.venv/bin/pytest -q`
Expected: every existing test still passes.

- [ ] **Step 14: Commit**

```bash
git add src/aie/ingest src/aie/cli.py tests/fakes/yt-dlp tests/conftest.py tests/test_backfill.py
git commit -m "aie backfill: fetch, verify, and record audio for corpus videos (tracer bullet)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Guards, window, backoff, and dry run

**Files:**
- Modify: `src/aie/ingest/guards.py`
- Create: `tests/fakes/pmset`, `tests/fakes/route`, `tests/fakes/dig`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `guards.GuardConfig`, `guards.check`, `guards.parse_window` from Task 1; `run_backfill`, `ytdlp_calls`, `archive` from conftest.
- Produces: `guards.in_window(now, start, end) -> bool`, `guards.window_end(now, start, end) -> datetime`, `guards.on_mains() -> bool`, `guards.default_route_is_physical() -> bool`, `guards.public_ipv4() -> str | None`, `guards.asn_of(ip) -> int | None`, `guards.CHARTER_ASNS`, `guards.LOCAL_TZ`. `check` now runs the full order: window, backoff, mains, drive, vpn, asn, lock.

- [ ] **Step 1: Write the fake pmset, route, and dig**

`tests/fakes/pmset` (`chmod +x`):

```python
#!/usr/bin/env python3
"""Fake pmset: prints FAKE_PMSET_OUTPUT (default: on mains)."""
import os
print(os.environ.get("FAKE_PMSET_OUTPUT", "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t80%; charged"))
```

`tests/fakes/route` (`chmod +x`):

```python
#!/usr/bin/env python3
"""Fake route: prints FAKE_ROUTE_OUTPUT (default: default route on en0)."""
import os
print(os.environ.get("FAKE_ROUTE_OUTPUT", "   route to: default\ndestination: default\n   gateway: 192.168.1.1\n  interface: en0"))
```

`tests/fakes/dig` (`chmod +x`):

```python
#!/usr/bin/env python3
"""Fake dig: the public-IP TXT lookup prints FAKE_DIG_IP, the Cymru ASN lookup
prints FAKE_DIG_ASN. Defaults are the values measured on 2026-09-16.
An empty value prints nothing, which is what a failed lookup looks like."""
import os
import sys
if any("myaddr" in a for a in sys.argv):
    print(os.environ.get("FAKE_DIG_IP", '"71.81.249.26"'))
else:
    print(os.environ.get("FAKE_DIG_ASN", '"20115 | 71.81.192.0/18 | US | arin | 2005-05-19"'))
```

Run: `chmod +x tests/fakes/pmset tests/fakes/route tests/fakes/dig && PATH=tests/fakes:$PATH dig +short TXT x.origin.asn.cymru.com`
Expected: `"20115 | 71.81.192.0/18 | US | arin | 2005-05-19"`

- [ ] **Step 2: Write the failing guard tests**

Append to `tests/test_backfill.py` (add `from datetime import datetime, timedelta` and `from zoneinfo import ZoneInfo` at the top):

```python
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
```

Add `from pathlib import Path` to the imports.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_backfill.py -v -k "window or battery or vpn or asn or unmounted or locked or dry_run"`
Expected: `test_outside_window_skips`, `test_on_battery_skips_unless_now`, `test_vpn_default_route_skips_even_with_now`, `test_foreign_asn_skips`, `test_asn_lookup_failure_fails_closed` FAIL (the run proceeds and calls yt-dlp). `test_unmounted_volume_skips_and_creates_nothing`, `test_second_run_while_locked_skips`, `test_dry_run_lists_queue_and_fetches_nothing`, `test_inside_window_on_mains_runs` PASS already.

- [ ] **Step 4: Implement the remaining guards**

Replace `guards.py` in full:

```python
"""Fail-closed checks that run before any download (spec section 9)."""
from __future__ import annotations

import fcntl
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .records import VIDEOS_DIR

LOCAL_TZ = ZoneInfo("America/New_York")
CHARTER_ASNS = {20115, 11351, 7843, 20001, 12271}
LOCK_NAME = ".backfill.lock"


def parse_window(text: str) -> tuple[time, time]:
    """'01:00-07:00' -> (time(1, 0), time(7, 0)). Raises ValueError."""
    start, end = text.split("-")
    return time.fromisoformat(start), time.fromisoformat(end)


def in_window(now: datetime, start: time, end: time) -> bool:
    t = now.astimezone(LOCAL_TZ).time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end          # a window that crosses midnight


def window_end(now: datetime, start: time, end: time) -> datetime:
    """When the window that contains `now` closes, as an aware local datetime."""
    local = now.astimezone(LOCAL_TZ)
    end_dt = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if end_dt <= local:
        end_dt += timedelta(days=1)
    return end_dt


def run_text(cmd: list[str]) -> str | None:
    """stdout of a successful command, else None."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def on_mains() -> bool:
    out = run_text(["pmset", "-g", "batt"])
    return bool(out) and "AC Power" in out


def default_route_is_physical() -> bool:
    out = run_text(["route", "-n", "get", "default"])
    if not out:
        return False
    for line in out.splitlines():
        if line.strip().startswith("interface:"):
            return not line.split(":", 1)[1].strip().startswith("utun")
    return False


def public_ipv4() -> str | None:
    out = run_text(["dig", "-4", "+short", "TXT", "o-o.myaddr.l.google.com", "@ns1.google.com"])
    if not out:
        return None
    ip = out.strip().strip('"')
    return ip if ip.count(".") == 3 and ip.replace(".", "").isdigit() else None


def asn_of(ip: str) -> int | None:
    reversed_ip = ".".join(reversed(ip.split(".")))
    out = run_text(["dig", "+short", "TXT", f"{reversed_ip}.origin.asn.cymru.com"])
    if not out:
        return None
    try:
        return int(out.strip().strip('"').split("|")[0].strip())
    except ValueError:
        return None


def drive_ready(archive: Path) -> bool:
    """A path under /Volumes must be a real mount point (an unplugged drive can
    leave a stale folder); any archive dir must be writable."""
    if str(archive).startswith("/Volumes/") and not os.path.ismount(archive):
        return False
    try:
        (archive / VIDEOS_DIR).mkdir(parents=True, exist_ok=True)
        probe = archive / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        return False
    return True


def acquire_lock(archive: Path) -> int | None:
    """flock on <archive>/.backfill.lock; None when another run holds it.
    The lock is released by the kernel when the process exits, however it exits."""
    fd = os.open(archive / LOCK_NAME, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode())
    return fd


@dataclass
class GuardConfig:
    archive: Path
    window: tuple[time, time]
    manual: bool                      # --now: skip the window and mains guards
    backoff_until: datetime | None


def check(cfg: GuardConfig, now: datetime) -> tuple[str | None, int | None]:
    """Return (skip_reason, lock_fd). A None reason means every guard passed
    and the lock is held. Order and names follow spec section 9."""
    if not cfg.manual and not in_window(now, *cfg.window):
        return "skipped:window", None
    if cfg.backoff_until and now < cfg.backoff_until:
        return "skipped:backoff", None
    if not cfg.manual and not on_mains():
        return "skipped:power", None
    if not drive_ready(cfg.archive):
        return "skipped:drive", None
    if not default_route_is_physical():
        return "skipped:vpn", None
    ip = public_ipv4()
    asn = asn_of(ip) if ip else None
    if asn is None:
        return "skipped:asn-unknown", None
    if asn not in CHARTER_ASNS:
        return "skipped:asn", None
    fd = acquire_lock(cfg.archive)
    if fd is None:
        return "skipped:lock", None
    return None, fd
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_backfill.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/aie/ingest/guards.py tests/fakes tests/test_backfill.py
git commit -m "aie backfill: window, mains, drive, VPN, ASN, and lock guards

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Outcomes: challenge stop and backoff, unavailable records, breaker, dub guard, fail ping

**Files:**
- Modify: `src/aie/ingest/backfill.py`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `fake_site` fixture from conftest (records request paths; any path returns 404, which is fine for a ping); `FAKE_YTDLP_SCRIPT` modes from the fake.
- Produces: `backfill.BACKOFF_HOURS = 24`, `backfill.CHALLENGE_ALERT_STRIKES = 2`. `run` now handles the `challenge` kind.

- [ ] **Step 1: Write the failing outcome tests**

Append to `tests/test_backfill.py` (add `from datetime import timezone` to the datetime import):

```python
# ---------------------------------------------------------------- outcomes

def test_challenge_stops_run_backs_off_24h_and_next_run_skips(archive, fake_site):
    env = {"FAKE_YTDLP_SCRIPT": json.dumps({"yj-wSRJwrrc": "challenge"}),
           "AIE_HEALTHCHECK_URL": fake_site.url + "/hc/abc"}
    ids = ["knDDGYHnnSI", "yj-wSRJwrrc", "am_oeAoUhew"]
    before = datetime.now(timezone.utc)

    r = run_backfill("--now", "--ids", *ids, archive=archive, env=env)

    assert r.returncode == 1
    assert "challenge: completed 1, failed 0, remaining 2" in r.stdout
    assert (archive / "videos" / "knDDGYHnnSI" / "knDDGYHnnSI.fetch.json").exists()
    assert not (archive / "videos" / "yj-wSRJwrrc" / "yj-wSRJwrrc.fetch.json").exists()
    assert [c[-1] for c in ytdlp_calls(archive)] == [watch_url("knDDGYHnnSI"), watch_url("yj-wSRJwrrc")]
    status = read_status(archive)
    assert status["last_outcome"] == "challenge"
    assert status["consecutive_challenges"] == 1
    assert "Sign in to confirm you're not a bot" in status["last_error"]
    until = datetime.fromisoformat(status["backoff_until"])
    assert timedelta(hours=23, minutes=59) < until - before < timedelta(hours=24, minutes=1)
    assert fake_site.requests == []          # the first strike does not alert

    again = run_backfill("--now", "--ids", *ids, archive=archive, env=env)
    assert again.returncode == 0
    assert "skipped:backoff" in again.stdout
    assert len(ytdlp_calls(archive)) == 2


def test_second_consecutive_challenge_pings_fail(archive, fake_site):
    (archive / "status.json").write_text(json.dumps({
        "consecutive_challenges": 1,
        "backoff_until": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")}))
    env = {"FAKE_YTDLP_SCRIPT": json.dumps({"knDDGYHnnSI": "challenge"}),
           "AIE_HEALTHCHECK_URL": fake_site.url + "/hc/abc"}

    r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive, env=env)

    assert r.returncode == 1
    assert read_status(archive)["consecutive_challenges"] == 2
    assert fake_site.requests == ["/hc/abc/fail"]


def test_unavailable_video_gets_a_permanent_record(archive):
    env = {"FAKE_YTDLP_SCRIPT": json.dumps({"yj-wSRJwrrc": "unavailable"})}
    r = run_backfill("--now", "--ids", "yj-wSRJwrrc", "am_oeAoUhew", archive=archive, env=env)
    assert r.returncode == 0, r.stderr
    rec = read_record(archive, "yj-wSRJwrrc")
    assert rec["status"] == "unavailable"
    assert "Video unavailable" in rec["unavailable_reason"]
    assert "audio" not in rec
    assert read_status(archive)["unavailable_total"] == 1
    assert read_status(archive)["records_total"] == 2

    again = run_backfill("--now", "--ids", "yj-wSRJwrrc", "am_oeAoUhew", archive=archive, env=env)
    assert again.returncode == 0
    assert len(ytdlp_calls(archive)) == 2


def test_three_consecutive_failures_trip_the_breaker(archive, fake_site):
    env = {"FAKE_YTDLP_SCRIPT": json.dumps({"a1": "fail", "a2": "fail", "a3": "fail"}),
           "AIE_HEALTHCHECK_URL": fake_site.url + "/hc/abc"}
    r = run_backfill("--now", "--ids", "a1", "a2", "a3", "knDDGYHnnSI", archive=archive, env=env)
    assert r.returncode == 1
    assert "error: completed 0, failed 3, remaining 4" in r.stdout
    assert [c[-1] for c in ytdlp_calls(archive)] == [watch_url("a1"), watch_url("a2"), watch_url("a3")]
    status = read_status(archive)
    assert status["last_outcome"] == "error"
    assert status["videos_failed_last_run"] == 3
    assert status["last_error"].startswith("a3: ERROR: Unable to download webpage")
    assert fake_site.requests == ["/hc/abc/fail"]
    assert not (archive / "videos" / "a1" / "a1.fetch.json").exists()


def test_failure_between_successes_does_not_trip_the_breaker(archive):
    env = {"FAKE_YTDLP_SCRIPT": json.dumps({"b1": "fail", "b2": "fail", "b3": "fail"})}
    r = run_backfill("--now", "--ids", "b1", "b2", "knDDGYHnnSI", "b3", "am_oeAoUhew", archive=archive, env=env)
    assert r.returncode == 0, r.stderr
    assert "success: completed 2, failed 3, remaining 3" in r.stdout


def test_dubbed_track_is_refused(archive):
    env = {"FAKE_YTDLP_SCRIPT": json.dumps({"knDDGYHnnSI": "dub"})}
    r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive, env=env)
    assert r.returncode == 0, r.stderr
    d = archive / "videos" / "knDDGYHnnSI"
    assert not (d / "knDDGYHnnSI.fetch.json").exists()
    assert (d / "knDDGYHnnSI.f251-11.webm").exists()      # left for inspection
    status = read_status(archive)
    assert status["videos_failed_last_run"] == 1
    assert "wrong_track" in status["last_error"]
    assert "251-11" in status["last_error"]
```


- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_backfill.py -v -k "challenge or unavailable or breaker or dubbed"`
Expected: `test_challenge_stops_run_backs_off_24h_and_next_run_skips` and `test_second_consecutive_challenge_pings_fail` FAIL (the challenge is counted as a plain failure and the run continues). `test_unavailable_video_gets_a_permanent_record`, `test_three_consecutive_failures_trip_the_breaker`, `test_failure_between_successes_does_not_trip_the_breaker`, `test_dubbed_track_is_refused` PASS already from Task 1.

- [ ] **Step 3: Handle the challenge kind in the run loop**

In `backfill.py`, add the constants under `MAX_CONSECUTIVE_FAILURES`:

```python
BACKOFF_HOURS = 24
CHALLENGE_ALERT_STRIKES = 2
```

Add `timedelta` to the datetime import. In `run`, replace the branch

```python
                if kind in ("ok", "unavailable"):
```

with

```python
                if kind == "challenge":
                    st.consecutive_challenges += 1
                    st.backoff_until = (datetime.now(timezone.utc)
                                        + timedelta(hours=BACKOFF_HOURS)).isoformat(timespec="seconds")
                    st.last_error = f"{video_id}: {detail}"
                    log(f"  challenge: {detail}; backing off until {st.backoff_until}")
                    result.outcome, result.exit_code = "challenge", 1
                    if st.consecutive_challenges >= CHALLENGE_ALERT_STRIKES:
                        ping(cfg.healthcheck_url, fail=True)
                    break
                if kind in ("ok", "unavailable"):
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_backfill.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/aie/ingest/backfill.py tests/test_backfill.py
git commit -m "aie backfill: challenge stop with 24h backoff, second-strike alert

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Queue sources and order, limit, case collision, resume without a record, success ping, SIGTERM

**Files:**
- Modify: `src/aie/ingest/backfill.py` (only if a test in this task fails; the code from Task 1 is expected to cover most of it)
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `synced_dir` fixture (a data dir whose `raw/talks.json` lists `knDDGYHnnSI`, `yj-wSRJwrrc`, `am_oeAoUhew` in that order), `backfill_command`, `backfill_env`.
- Produces: nothing new; this task pins behaviour already specified.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backfill.py` (add `import os`, `import signal`, `import subprocess`, `import time` and `from conftest import backfill_command, backfill_env` to the imports):

```python
# ---------------------------------------------------------------- queue, limit, resume, signals

def test_default_queue_is_talks_json_order_and_limit_caps_it(archive, synced_dir):
    r = run_backfill("--now", "--limit", "2", archive=archive, data_dir=synced_dir)
    assert r.returncode == 0, r.stderr
    assert [c[-1] for c in ytdlp_calls(archive)] == [watch_url("knDDGYHnnSI"), watch_url("yj-wSRJwrrc")]
    assert "success: completed 2, failed 0, remaining 1" in r.stdout
    assert read_status(archive)["queue_depth"] == 1

    rest = run_backfill("--now", "--limit", "2", archive=archive, data_dir=synced_dir)
    assert rest.returncode == 0, rest.stderr
    assert [c[-1] for c in ytdlp_calls(archive)][2:] == [watch_url("am_oeAoUhew")]
    assert read_status(archive)["queue_depth"] == 0


def test_missing_talks_json_is_an_error(archive, tmp_path):
    r = run_backfill("--now", archive=archive, data_dir=tmp_path / "empty")
    assert r.returncode == 1
    assert "no talks file" in r.stderr


def test_ids_file_with_comments(archive, tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("# uploads walk\nam_oeAoUhew\n\nknDDGYHnnSI  # graphrag\n")
    r = run_backfill("--now", "--ids-file", str(ids), archive=archive)
    assert r.returncode == 0, r.stderr
    assert [c[-1] for c in ytdlp_calls(archive)] == [watch_url("am_oeAoUhew"), watch_url("knDDGYHnnSI")]


def test_limit_must_be_positive(archive):
    r = run_backfill("--now", "--limit", "0", "--ids", "knDDGYHnnSI", archive=archive)
    assert r.returncode == 2
    assert "--limit" in r.stderr


def test_bad_window_is_a_usage_error(archive):
    r = run_backfill("--window", "1am-7am", "--ids", "knDDGYHnnSI", archive=archive)
    assert r.returncode == 2
    assert "--window" in r.stderr


def test_case_collision_is_refused_without_calling_ytdlp(archive):
    (archive / "videos" / "abcdefghijk").mkdir(parents=True)
    r = run_backfill("--now", "--ids", "ABCDEFGHIJK", archive=archive)
    assert r.returncode == 0, r.stderr
    assert ytdlp_calls(archive) == []
    assert "case_collision" in read_status(archive)["last_error"]
    assert not (archive / "videos" / "abcdefghijk" / "abcdefghijk.fetch.json").exists()


def test_files_present_without_record_are_verified_and_recorded(archive):
    run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive)
    record = archive / "videos" / "knDDGYHnnSI" / "knDDGYHnnSI.fetch.json"
    record.unlink()

    r = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive)

    assert r.returncode == 0, r.stderr
    assert len(ytdlp_calls(archive)) == 2            # yt-dlp is asked again, skips the files
    rec = read_record(archive, "knDDGYHnnSI")
    assert rec["audio"]["opus"]["format_id"] == "251"
    assert rec["audio"]["opus"]["language"] == "en-US"
    assert rec["audio"]["opus"]["streamhash_sha256"] == OPUS_STREAMHASH
    assert rec["audio"]["aac"]["streamhash_sha256"] == AAC_STREAMHASH


def test_success_pings_healthcheck_and_skips_do_not(archive, fake_site):
    env = {"AIE_HEALTHCHECK_URL": fake_site.url + "/hc/abc"}
    ok = run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive, env=env)
    assert ok.returncode == 0, ok.stderr
    assert fake_site.requests == ["/hc/abc"]

    skipped = run_backfill("--window", window_excluding_now(), "--ids", "am_oeAoUhew", archive=archive, env=env)
    assert "skipped:window" in skipped.stdout
    assert fake_site.requests == ["/hc/abc"]


def test_run_log_records_each_video(archive):
    run_backfill("--now", "--ids", "knDDGYHnnSI", archive=archive)
    logs = list((archive / "logs").glob("backfill-*.log"))
    assert len(logs) == 1
    lines = logs[0].read_text().splitlines()
    assert any("\tknDDGYHnnSI\tok\t" in line for line in lines)
    assert lines[0].split("\t")[1] == "run start"
    assert lines[-1].split("\t")[1] == "run end"


def test_sigterm_stops_after_the_current_video_and_leaves_no_record(archive):
    env = backfill_env(archive, env={"FAKE_YTDLP_SLEEP": "5"})
    proc = subprocess.Popen(backfill_command("--now", "--ids", "knDDGYHnnSI", "am_oeAoUhew", archive=archive),
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    part = archive / "videos" / "knDDGYHnnSI" / "knDDGYHnnSI.f251.webm.part"
    deadline = time.time() + 10
    while not part.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert part.exists(), "the fake never started downloading"

    proc.send_signal(signal.SIGTERM)
    stdout, stderr = proc.communicate(timeout=15)

    assert proc.returncode == 1, stderr
    assert "interrupted" in stdout
    assert part.exists()                                                     # left for resume
    assert not (archive / "videos" / "knDDGYHnnSI" / "knDDGYHnnSI.fetch.json").exists()
    assert not (archive / "videos" / "am_oeAoUhew").exists()
    status = read_status(archive)
    assert status["last_outcome"] == "interrupted"
    assert status["current_video"] is None
    assert len(ytdlp_calls(archive)) == 1
```

- [ ] **Step 2: Run the tests to verify which fail**

Run: `.venv/bin/pytest tests/test_backfill.py -v`
Expected: every test in this task PASSES against the Task 1 code except possibly `test_sigterm_stops_after_the_current_video_and_leaves_no_record`. If it fails because the process exits 0 or `last_outcome` is `success`, the signal handler is not marking the run interrupted: check that `on_signal` sets `stop["requested"]` before `runner.stop()` and that the loop turns `stop["requested"]` into `result.outcome = "interrupted"` right after `process_video` returns (the code in Task 1 step 11 does this). If it fails because the record for the first video exists, the fake finished before the signal arrived: raise `FAKE_YTDLP_SLEEP` to `8`.

- [ ] **Step 3: Fix anything that failed, re-run, and confirm all green**

Run: `.venv/bin/pytest -q`
Expected: all tests pass, including the pre-existing `tests/test_cli.py`.

- [ ] **Step 4: Commit**

```bash
git add src/aie/ingest tests/test_backfill.py
git commit -m "aie backfill: queue sources, limit, case guard, resume, healthcheck ping, SIGTERM

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: LaunchAgent, setup doc, README

**Files:**
- Create: `docs/ingest/com.aie.backfill.plist`, `docs/ingest/audio-backfill-setup.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the `aie backfill` options from Task 1, the guard names from Task 2, `status.json` fields from Task 1.
- Produces: nothing for code; this is the owner-facing handoff. No test: docs have no seam.

- [ ] **Step 1: Write the LaunchAgent**

`docs/ingest/com.aie.backfill.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.aie.backfill</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string><string>-m</string><string>-s</string>
    <string>/Users/davidkobilnyk/Documents/code/ai-engineering-archive/.venv/bin/python</string>
    <string>-m</string><string>aie</string><string>backfill</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>1</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>AIE_DATA_DIR</key>
    <string>/Users/davidkobilnyk/Documents/code/ai-engineering-archive/data</string>
    <key>AIE_ARCHIVE_DIR</key>
    <string>/Volumes/Archive</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>/Users/davidkobilnyk/Documents/code/ai-engineering-archive</string>
  <key>StandardOutPath</key>
  <string>/Users/davidkobilnyk/Library/Logs/aie-backfill.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/davidkobilnyk/Library/Logs/aie-backfill.err.log</string>
  <key>ProcessType</key>
  <string>Background</string>
  <key>LowPriorityIO</key>
  <true/>
  <key>Nice</key>
  <integer>5</integer>
  <key>ExitTimeOut</key>
  <integer>240</integer>
</dict>
</plist>
```

Run: `plutil -lint docs/ingest/com.aie.backfill.plist`
Expected: `docs/ingest/com.aie.backfill.plist: OK`

- [ ] **Step 2: Write the setup and operations doc**

`docs/ingest/audio-backfill-setup.md`:

```markdown
# Audio backfill: setup and operations

`aie backfill` fetches the best Opus and AAC audio, the English caption
track, and the yt-dlp metadata snapshot for every corpus video onto
`/Volumes/Archive/videos/<id>/`, verifies each file with ffprobe, hashes the
elementary streams, and writes `<id>.fetch.json` when everything checks out.
Design: `docs/superpowers/specs/2026-09-16-audio-backfill-design.md`.

## One-time setup (about an hour)

1. Install the tools into the project venv:

       .venv/bin/pip install -e ".[dev,ingest]"
       .venv/bin/yt-dlp --version        # 2026.08.19 or newer

   ffmpeg and Deno stay Homebrew: `/opt/homebrew/bin/ffmpeg`,
   `/opt/homebrew/bin/deno`.

2. Refresh the corpus so the queue has every talk:

       .venv/bin/aie sync

3. First manual run from the Terminal, VPN off, drive attached:

       .venv/bin/aie backfill --now --ids FLUoowDJg4I --limit 1
       cat /Volumes/Archive/status.json
       cat /Volumes/Archive/videos/FLUoowDJg4I/FLUoowDJg4I.fetch.json

   `--now` skips only the window and mains guards. The drive, VPN, ASN and
   lock guards still run. A manual run on a hotspot or through Proton VPN
   ends in `skipped:asn` or `skipped:vpn`.

4. Grant Full Disk Access to the Python that launchd will run, so it can
   write to the USB volume. The venv binary is a symlink, so grant the
   resolved path: `readlink -f .venv/bin/python`. System Settings, Privacy
   and Security, Full Disk Access, add that file.

5. Install the LaunchAgent:

       cp docs/ingest/com.aie.backfill.plist ~/Library/LaunchAgents/
       launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aie.backfill.plist

   Then fire it once by hand during the day to prove the wiring:

       launchctl kickstart gui/$(id -u)/com.aie.backfill
       sleep 5; cat /Volumes/Archive/status.json

   Expect `"last_outcome": "skipped:window"`. Anything else in
   `~/Library/Logs/aie-backfill.err.log` is a setup problem.

6. Optional dead-man alert: create a check at healthchecks.io with a 2-day
   period, then add its URL to the plist's `EnvironmentVariables` as
   `AIE_HEALTHCHECK_URL` and re-bootstrap (`launchctl bootout` then
   `bootstrap`). A completed run pings it; a second consecutive challenge
   or a tripped breaker pings `/fail`.

7. Delete the calibration scratch folder: `rm -r /Volumes/Archive/_calibration`.

## What a night looks like

At 01:00 ET launchd starts the job under `caffeinate`. The guards run in
order: window, backoff, mains, drive, VPN, ASN, lock. Any failure writes
`status.json` with `skipped:<guard>` and exits 0. Otherwise the job takes
the first 200 videos without a record, in `talks.json` order, and fetches
them one at a time: about 55 to 80 s each with the pacing sleeps, so a
full night is 3 to 4.5 hours. No new video starts after 07:00 ET.

Outcomes per video: `ok` (record written), `unavailable` (record written
with `status: unavailable`, never retried), `challenge` (run stops, 24 h
backoff, alert on the second consecutive strike), anything else (no
record, retried the next night; three in a row stop the run).

## Reading status

    cat /Volumes/Archive/status.json

| field | meaning |
|---|---|
| `last_outcome` | `success`, `skipped:<guard>`, `challenge`, `error`, `interrupted` |
| `queue_depth` | videos still without a record |
| `records_total`, `unavailable_total`, `captions_missing_total` | counts over all records |
| `backoff_until` | set after a challenge; the job skips until then |
| `consecutive_challenges` | resets on the next successful video |
| `last_error` | the last per-video failure, with its video id |
| `yt_dlp_version` | from `yt-dlp --version` at run start |

Per-run lines are appended to `/Volumes/Archive/logs/backfill-YYYY-MM-DD.log`;
the last yt-dlp stderr for a video is `videos/<id>/<id>.yt-dlp.log`.

## Manual runs

    aie backfill --now --dry-run                 # guards plus the queue, no fetch
    aie backfill --now --limit 5                 # five videos, right now
    aie backfill --now --ids-file uploads.txt    # a different id list
    aie backfill --now --verbose --ids <id>      # yt-dlp -v into <id>.yt-dlp.log

## When yt-dlp breaks

Symptoms: `last_error` mentions `n challenge solving failed`, `Requested
format is not available`, or `HTTP Error 403`, and the breaker trips.
Update in the venv and re-run one talk:

    .venv/bin/pip install -U "yt-dlp[default]"
    .venv/bin/aie backfill --now --ids FLUoowDJg4I --limit 1

Roll back with `pip install "yt-dlp==2026.08.19"` if the new one is worse.
```

- [ ] **Step 3: Add a README section**

Append to `README.md` after the "Use" section:

```markdown
## Audio backfill

`aie backfill` copies each corpus video's best Opus and AAC audio, caption
track, and metadata onto the archive drive at `/Volumes/Archive`, nightly
under launchd. Setup and operations: `docs/ingest/audio-backfill-setup.md`.
```

- [ ] **Step 4: Run the whole suite one last time and commit**

Run: `.venv/bin/pytest -q`
Expected: all pass.

```bash
git add docs/ingest README.md
git commit -m "Audio backfill: LaunchAgent, setup doc, README section

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage: section 4 options (Task 1 step 12), section 5 invocation (Task 1 step 8, pinned by `test_invocation_matches_the_spec`), section 6 layout and record (Task 1 steps 6 and 11), section 7 checks (Task 1 step 11 `build_record`; dub guard pinned in Task 3), section 8 outcomes (Task 1 classify, Task 3 challenge branch, breaker in Task 1 loop pinned in Task 3), section 9 guards (Task 2), section 10 status and ping (Task 1 step 9, pinned in Tasks 3 and 4), section 11 scheduling (Task 5), section 12 tests (Tasks 1 to 4), section 13 owner setup (Task 5 doc).
- Not covered by a test, by design: stopping at window end mid-run needs a clock that can be moved. The check is three lines at the top of the loop body in `run` (Task 1 step 11) reading `guards.window_end`, which Task 1 step 10 defines and Task 2 keeps verbatim.
- Type consistency: `process_video` returns `(kind, detail)` strings everywhere; `RunResult.remaining` is what the CLI prints as `remaining`; `Status` field names match the spec's status JSON exactly; `Tools.ffprobe` is used by `build_record` and `Tools.ffmpeg` by `streamhash_sha256`.
