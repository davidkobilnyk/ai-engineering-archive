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

## Audio backfill

`aie backfill` copies each corpus video's best Opus and AAC audio, caption
track, and metadata onto the archive drive at `/Volumes/Archive`, nightly
under launchd. Setup and operations: `docs/ingest/audio-backfill-setup.md`.

## Tests

```bash
.venv/bin/pytest                      # offline, against tests/fixtures
AIE_LIVE_TESTS=1 .venv/bin/pytest tests/test_live.py   # two real requests
```

Design: `docs/superpowers/specs/2026-09-14-aie-archive-design.md`.
