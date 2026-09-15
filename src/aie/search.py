"""Queries against data/aie.db."""
from __future__ import annotations

import json
import sqlite3
import textwrap
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .index import resolve_event


class MissingIndex(Exception):
    """data/aie.db does not exist."""


class BadQuery(Exception):
    """FTS5 rejected the query text."""


class UnknownTalk(Exception):
    """No talk has the requested slug."""


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


# ---------------------------------------------------------------- basics

def connect(data_dir: Path) -> sqlite3.Connection:
    db = data_dir / "aie.db"
    if not db.exists():
        raise MissingIndex(f"No index found at {db}. Run `aie sync` then `aie index`.")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def format_ts(ms: int) -> str:
    """Milliseconds -> 'MM:SS'; minutes may exceed 59."""
    minutes, seconds = divmod(ms // 1000, 60)
    return f"{minutes:02d}:{seconds:02d}"


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


def yt_url(video_id: str | None, ms: int, fallback: str = "") -> str:
    if not video_id:
        return fallback
    return f"https://www.youtube.com/watch?v={video_id}&t={ms // 1000}"


def talk_url(video_id: str | None, fallback: str = "") -> str:
    """YouTube URL for the talk itself, without a timestamp."""
    return yt_url(video_id, 0, fallback).replace("&t=0", "")


def speaker_names(speakers_json: str) -> list[str]:
    return [s.get("name", "") for s in json.loads(speakers_json or "[]")]


def slugify(value: str) -> str:
    return "-".join(value.lower().split())


def parse_timestamp(value: str) -> int:
    """'MM:SS' -> milliseconds. Minutes may exceed 59 ('65:00')."""
    minutes, seconds = value.split(":")
    if not minutes.isdigit() or not seconds.isdigit() or int(seconds) > 59:
        raise ValueError(f"expected MM:SS, got {value!r}")
    return (int(minutes) * 60 + int(seconds)) * 1000


# ---------------------------------------------------------------- filters

def filter_sql(filters: Filters) -> tuple[str, list]:
    """WHERE fragment and parameters against alias t (talks)."""
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


# ---------------------------------------------------------------- search

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
                        url=talk_url(r["video_id"], r["talk_url"] or ""),
                        text=r["snip"], snippet=r["snip"], kind="metadata", score=r["score"]))
    hits.sort(key=lambda h: h.score)
    return hits[:limit]


def hit_to_dict(hit: Hit) -> dict:
    return asdict(hit)


def format_hits(hits: list[Hit]) -> str:
    if not hits:
        return "No results"
    lines = []
    for i, h in enumerate(hits, 1):
        who = ", ".join(n for n in h.speakers if n) or "unknown speaker"
        when = f" ({format_date_range(h.start_date, h.end_date)})" if h.start_date else ""
        lines.append(f"{i}. {h.title} — {who} · {h.event or 'unknown edition'}{when}")
        lines.append(f"   slug: {h.talk_slug}")
        stamp = "[metadata]" if h.kind == "metadata" else f"[{format_ts(h.start_ms)}]"
        lines.append(f"   {stamp} {h.url}")
        lines.append(textwrap.fill(h.snippet, 76, initial_indent="   ", subsequent_indent="   "))
    return "\n".join(lines)


# ---------------------------------------------------------------- show

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
    """Segments whose start_ms lies in the inclusive range."""
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
        talk_url(talk["video_id"], talk["talk_url"] or ""),
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
            "url": talk_url(talk["video_id"], talk["talk_url"] or ""),
            "duration_ms": talk["duration_ms"], "summary": talk["summary"],
        },
        "chapters": [dict(c) for c in chapters],
        "segments": [dict(s) for s in segments],
    }


# ---------------------------------------------------------------- talks / status

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
            "url": talk_url(row["video_id"], row["talk_url"] or "")}


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
