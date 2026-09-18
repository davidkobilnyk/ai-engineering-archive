"""Command-line entry point for the aie archive."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import index as index_mod
from . import search as search_mod
from . import sync as sync_mod
from .ingest import backfill as backfill_mod, guards as guards_mod, ytdlp as ytdlp_mod

DEFAULT_BASE_URL = "https://ai.engineer"


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
    add_filter_arguments(p_search)
    p_search.add_argument("--limit", type=int, default=10, help="1-50, default 10")
    p_search.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="print one talk's header, chapters, and transcript")
    p_show.add_argument("talk_slug")
    p_show.add_argument("--from", dest="from_", metavar="MM:SS", help="start of range, inclusive")
    p_show.add_argument("--to", metavar="MM:SS", help="end of range, inclusive")
    p_show.add_argument("--json", action="store_true")

    p_talks = sub.add_parser("talks", help="list talks matching filters")
    add_filter_arguments(p_talks)
    p_talks.add_argument("--json", action="store_true")

    sub.add_parser("status", help="show local corpus version, index time, and counts")
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
    p_bf.add_argument("--subtitles", choices=["on", "off", "only"], default="on",
                      help="on (default): audio and captions; off: audio only, record marks captions "
                           "not_requested; only: fetch captions for records marked not_requested")
    p_audit = sub.add_parser("audit-audio", help="recheck fetched audio files on the archive drive: "
                                                 "full decode, sizes, stream hashes, opus vs aac")
    p_audit.add_argument("--archive-dir", type=Path,
                         default=Path(os.environ.get("AIE_ARCHIVE_DIR", "/Volumes/Archive")))
    p_audit.add_argument("--ffmpeg-dir", type=Path, default=Path("/opt/homebrew/bin"),
                         help="directory holding ffmpeg and ffprobe")
    return parser


def cmd_audit_audio(args) -> int:
    tools = ytdlp_mod.Tools(Path("yt-dlp"), args.ffmpeg_dir, Path("deno"))
    return backfill_mod.audit(tools, args.archive_dir.resolve())


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
        print(f"aborted after {sync_mod.MAX_CONSECUTIVE_FAILURES} consecutive failures; "
              f"last error: {result.last_error}")
    return 0 if result.ok else 1


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
        verbose=args.verbose, healthcheck_url=os.environ.get("AIE_HEALTHCHECK_URL"),
        subtitles=args.subtitles)
    result = backfill_mod.run(cfg)
    print(f"{result.outcome}: completed {result.completed}, failed {result.failed}, "
          f"remaining {result.remaining}")
    return result.exit_code


COMMANDS = {
    "sync": cmd_sync, "index": cmd_index, "search": cmd_search,
    "show": cmd_show, "talks": cmd_talks, "status": cmd_status, "backfill": cmd_backfill,
    "audit-audio": cmd_audit_audio,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (search_mod.MissingIndex, index_mod.MissingRawData, search_mod.UnknownTalk) as e:
        print(e, file=sys.stderr)
        return 1
    except search_mod.BadQuery as e:
        print(f"invalid query syntax: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
