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
