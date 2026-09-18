"""VPN rate-limit test for the audio backfill (2026-09-17).

Runs the backfill's own per-video fetch and verify (aie.ingest.backfill.process_video,
same yt-dlp command and pacing flags) back to back through Proton VPN, into a
separate archive root, and stops on the first challenge. It never touches the
home archive's status.json, queue records, lock, or backoff.

Differences from the nightly job, all deliberate:
- Requires the VPN: refuses to start, and stops mid-run, if the default route is
  the physical interface or the egress ASN is Charter's.
- yt-dlp gets -v and --print-traffic; stdout is saved per video so the status
  line and headers (e.g. Retry-After) of any 403/429 are on disk. Request counts
  read both streams: subtitles go through curl_cffi when it is installed, and
  its trace is on stderr, not in --print-traffic. The two dig lookups per video
  are counted too.
- Skips the three videos that failed last night on the wrong_track check (a
  verify issue, not a network one) to save transfer time.
- Queue order, newest upload first within each group (order file and report from
  scripts/upload_order.py): (1) uploads not in the corpus yet, published in the
  last 14 days and 5-60 min long; (2) World's Fair 2026 talks; (3) the rest of the
  corpus. Nothing over 2 h (stream recordings) is ever queued from the report.
- Paced: video starts at least 3600/--per-hour s apart (default 20/h), and stops
  once --max-per-day videos (default 200) started in the last 24 h. Both count
  every run into the test root, read back from its logs, so a restart does not
  reset them.

Run from the repo root with the VPN on:
    .venv/bin/python scripts/vpn_test.py --hours 4
    .venv/bin/python scripts/vpn_test.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from aie.ingest import backfill, guards, records, ytdlp

HOME_ARCHIVE = Path("/Volumes/Archive")
DEFAULT_OUT = HOME_ARCHIVE / "vpn-test"
TALKS = Path("data/raw/talks.json")
# New uploads not in the corpus yet (queued first): talk-length and recent.
RECENT_DAYS = 14
RECENT_MIN_S = 5 * 60
RECENT_MAX_S = 60 * 60
NEVER_OVER_S = 2 * 60 * 60
# Queued next, still newest upload first within the group.
FIRST_EVENTS = {"AI Engineer World's Fair 2026", "worldsfair-2026-online-track"}
WRONG_TRACK_LAST_NIGHT =["kQmXtrmQ5Zg", "OkEGJ5G3foU", "OimPoLxioYg"]

SEND = re.compile(r"^send: b['\"](GET|POST|HEAD) (\S+) HTTP/[\d.]+(?:.*?\\r\\nHost: ([^\\]+))?")
REPLY = re.compile(r"^reply: 'HTTP/[\d.]+ (\d{3})")
HEADER = re.compile(r"^header: (.+)$")
CURL_SEND = re.compile(r"^> (?:GET|POST|HEAD) (\S+) HTTP/[\d.]+")
CURL_REPLY = re.compile(r"^< HTTP/[\d.]+ (\d{3})")
DONE = re.compile(r"^\[download\] 100% of\s+~?\s*([\d.]+)(KiB|MiB|GiB) in \S+ at\s+([\d.]+)(KiB|MiB)/s")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def endpoint(path: str, host: str) -> str:
    p = path.split("?", 1)[0]
    if "timedtext" in p:
        return "caption"
    if p.startswith("/api/manifest/"):
        return "manifest"
    if p.startswith("/videoplayback") or "googlevideo" in host:
        return "media"
    if p.startswith("/youtubei/"):
        return "api:" + p.rsplit("/", 1)[-1]
    if p.startswith("/watch"):
        return "webpage"
    if p.startswith("/s/player"):
        return "player_js"
    return p


def parse_traffic(stdout: str, stderr: str = "") -> tuple[Counter, list[dict]]:
    """(requests by endpoint and status, non-2xx replies with their headers).
    stdout holds --print-traffic from yt-dlp's urllib/requests handlers; stderr
    holds the curl_cffi trace (-v), which is how subtitles are fetched when
    curl_cffi is installed. URLs are cut at '?' so tokens are not copied into
    the summary."""
    counts: Counter = Counter()
    problems: list[dict] = []
    last_send = ("?", "?")
    current: dict | None = None
    for line in stdout.splitlines():
        m = SEND.match(line)
        if m:
            current = None
            host = m.group(3) or "?"
            last_send = (endpoint(m.group(2), host), host)
            continue
        m = REPLY.match(line)
        if m:
            code = int(m.group(1))
            counts[f"{last_send[0]} {code}"] += 1
            current = None
            if code >= 300 and code not in (301, 302, 303, 307, 308):
                current = {"endpoint": last_send[0], "host": last_send[1], "status": code, "headers": []}
                problems.append(current)
            continue
        m = HEADER.match(line)
        if m and current is not None:
            current["headers"].append(m.group(1))
    path = None
    current = None
    for line in stderr.splitlines():
        m = CURL_SEND.match(line)
        if m:
            path, current = m.group(1), None
            continue
        if path is not None and line.startswith("Host: "):
            last_send = (endpoint(path, line[6:].strip()), line[6:].strip())
            path = None
            continue
        m = CURL_REPLY.match(line)
        if m:
            code = int(m.group(1))
            counts[f"{last_send[0]} {code}"] += 1
            current = None
            if code >= 300 and code not in (301, 302, 303, 307, 308):
                current = {"endpoint": last_send[0], "host": last_send[1], "status": code, "headers": []}
                problems.append(current)
            continue
        if current is not None and line.startswith("< ") and line[2:].strip():
            current["headers"].append(line[2:].strip())
        elif not line.startswith("< "):
            current = None
    return counts, problems


def speeds(stdout: str) -> list[str]:
    out = []
    for line in stdout.splitlines():
        m = DONE.match(line.strip())
        if m:
            out.append(f"{m.group(1)}{m.group(2)}@{m.group(3)}{m.group(4)}/s")
    return out


class TrafficRunner(ytdlp.Runner):
    """ytdlp.Runner with --print-traffic added and stdout saved beside the stderr log."""

    def run(self, tools, video_id, out_dir, log_path, verbose=False, subtitles="on"):
        cmd = ytdlp.build_command(tools, video_id, out_dir, verbose=True, subtitles=subtitles)
        cmd.insert(-1, "--print-traffic")
        self.current = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = self.current.communicate()
        code = self.current.returncode
        self.current = None
        log_path.write_text(stderr)
        log_path.with_name(f"{video_id}.traffic.log").write_text(stdout)
        self.last_stdout = stdout
        self.last_stderr = stderr
        return ytdlp.Outcome(ytdlp.classify(code, stderr), code, ytdlp.parse_rows(stdout),
                             ytdlp.last_error_line(stderr))


def ordered_ids(talk_ids: list[str], upload_order: list[str]) -> list[str]:
    """Talk IDs in upload order (newest first); talks missing from the uploads
    playlist keep their talks.json order at the end."""
    talks = set(talk_ids)
    seen: set[str] = set()
    out = []
    for i in upload_order:
        if i in talks and i not in seen:
            seen.add(i)
            out.append(i)
    return out + [i for i in talk_ids if i not in seen]


def recent_uploads_not_in_corpus(tsv: Path, today: date | None = None) -> list[str]:
    """Talk-length uploads the corpus does not have yet, newest first, from the
    report scripts/upload_order.py writes: published in the last RECENT_DAYS days,
    RECENT_MIN_S to RECENT_MAX_S long, and never over NEVER_OVER_S (stream recordings)."""
    if not tsv.exists():
        return []
    today = today or date.today()
    rows = []
    for text in tsv.read_text().splitlines()[1:]:
        f = text.split("\t")
        if len(f) < 5 or not f[4].isdigit() or not f[2]:
            continue
        position, video_id, published, seconds = int(f[0]), f[1], date.fromisoformat(f[2]), int(f[4])
        if seconds > NEVER_OVER_S:
            continue
        if (today - published).days <= RECENT_DAYS and RECENT_MIN_S <= seconds <= RECENT_MAX_S:
            rows.append((position, video_id))
    return [video_id for _, video_id in sorted(rows)]


def video_starts(out: Path) -> list[datetime]:
    """Start times of every video attempted by any run into this test root,
    read back from the logs (line time is the finish; field 5 is elapsed '61s')."""
    starts = []
    for log in out.glob("vpn-test-*.log"):
        for text in log.read_text().splitlines():
            f = text.split("\t")
            if len(f) < 5 or f[1] in ("start", "end", "stop", "ip-change") or not re.fullmatch(r"\d+s", f[4]):
                continue
            starts.append(datetime.fromisoformat(f[0]) - timedelta(seconds=int(f[4][:-1])))
    return sorted(starts)


def wait_for_slot(history: list[datetime], per_hour: float, stopping: dict, deadline: float) -> bool:
    """Sleep until 3600/per_hour s after the last start. False if interrupted or past the deadline."""
    if not history:
        return True
    ready = history[-1] + timedelta(seconds=3600 / per_hour)
    wait = (ready - datetime.now(timezone.utc)).total_seconds()
    if wait > 0:
        print(f"{now_iso()}\twaiting {round(wait)}s for the next {per_hour:g}/h slot")
    while datetime.now(timezone.utc) < ready:
        if stopping["flag"] or time.monotonic() >= deadline:
            return False
        time.sleep(1)
    return True


def network() -> tuple[bool, str | None, int | None]:
    """(tunnel_up, public_ipv4, asn)."""
    tunnel = not guards.default_route_is_physical()
    ip = guards.public_ipv4()
    return tunnel, ip, guards.asn_of(ip) if ip else None


def vpn_problem(tunnel: bool, asn: int | None) -> str | None:
    if not tunnel:
        return "default route is the physical interface (VPN off?)"
    if asn is None:
        return "could not look up egress ASN"
    if asn in guards.CHARTER_ASNS:
        return f"egress ASN {asn} is Charter (home address)"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=4.0, help="no new video starts after this (default 4)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"test archive root (default {DEFAULT_OUT})")
    ap.add_argument("--dry-run", action="store_true", help="check the VPN and print the queue; fetch nothing")
    ap.add_argument("--per-hour", type=float, default=20.0,
                    help="most video starts per hour; starts are spaced 3600/N s apart (default 20)")
    ap.add_argument("--max-per-day", type=int, default=200,
                    help="stop when this many videos started in the last 24 h, across runs (default 200)")
    ap.add_argument("--subtitles", choices=["on", "off", "only"], default="on",
                    help="on (default): audio and captions; off: audio only, record marks captions "
                         "not_requested; only: captions for records marked not_requested")
    ap.add_argument("--order-file", type=Path, default=DEFAULT_OUT / "upload-order.txt",
                    help="video IDs newest upload first, from scripts/upload_order.py")
    args = ap.parse_args()

    tunnel, ip, asn = network()
    problem = vpn_problem(tunnel, asn)
    print(f"route via tunnel: {tunnel}; egress {ip} AS{asn}")
    if problem:
        print(f"refusing to run: {problem}", file=sys.stderr)
        return 2

    talk_ids = backfill.ids_from_talks_json(TALKS)
    if not args.order_file.exists():
        print(f"no upload order at {args.order_file}; run scripts/upload_order.py first", file=sys.stderr)
        return 2
    ids = ordered_ids(talk_ids, backfill.ids_from_file(args.order_file))
    events = {t.get("videoId"): t.get("event") for t in json.loads(TALKS.read_text())}
    ids = [i for i in ids if events.get(i) in FIRST_EVENTS] + [i for i in ids if events.get(i) not in FIRST_EVENTS]
    new_uploads = recent_uploads_not_in_corpus(args.order_file.with_name("uploads-not-in-corpus.tsv"))
    ids = new_uploads + [i for i in ids if i not in set(new_uploads)]
    skip = records.done_ids(HOME_ARCHIVE) | set(WRONG_TRACK_LAST_NIGHT)
    queue = [i for i in backfill.build_queue(args.out, ids, args.subtitles) if i not in skip]
    print(f"queue: {len(queue)} videos: {len(new_uploads)} new uploads not in the corpus, then World's Fair 2026, "
          f"then the rest; newest upload first in each (home records and last night's "
          f"wrong_track IDs excluded); pace {args.per_hour}/h, cap {args.max_per_day} per 24 h")
    if args.dry_run:
        print("first 10:", " ".join(queue[:10]))
        return 0

    tools = ytdlp.Tools(Path(sys.executable).with_name("yt-dlp"), Path("/opt/homebrew/bin"),
                        Path("/opt/homebrew/bin/deno"))
    cfg = backfill.Config(archive=args.out, ids=ids, tools=tools, verbose=True, subtitles=args.subtitles)
    version = ytdlp.version(tools)
    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out / f"vpn-test-{datetime.now():%Y-%m-%d-%H%M}.log"
    summary_path = log_path.with_suffix(".summary.json")

    runner = TrafficRunner()
    stopping = {"flag": False}

    def on_signal(signum, frame):
        stopping["flag"] = True
        runner.stop()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    summary = {"started": now_iso(), "subtitles": args.subtitles, "yt_dlp_version": version,
               "start_ip": ip, "start_asn": asn,
               "ip_changes": [], "attempted": 0, "outcomes": {}, "requests": {}, "non_2xx": [],
               "stopped_because": None, "ended": None}
    totals: Counter = Counter()
    outcomes: Counter = Counter()

    def write_summary():
        summary["outcomes"] = dict(outcomes)
        summary["requests"] = dict(sorted(totals.items()))
        summary_path.write_text(json.dumps(summary, indent=1))

    with log_path.open("a") as log:
        def line(*fields):
            text = "\t".join(str(f) for f in (now_iso(), *fields))
            log.write(text + "\n")
            log.flush()
            print(text)

        line("start", f"ip {ip}", f"AS{asn}", f"queue {len(queue)}", f"yt-dlp {version}",
             f"subtitles {args.subtitles}")
        deadline = time.monotonic() + args.hours * 3600
        consecutive_failures = 0
        current_ip = ip
        for video_id in queue:
            if stopping["flag"]:
                summary["stopped_because"] = "interrupted"
                break
            if time.monotonic() >= deadline:
                summary["stopped_because"] = f"{args.hours} h limit"
                break
            tunnel, ip, asn = network()
            # Two dig TXT lookups per video: public IP (ns1.google.com), then ASN (Cymru).
            totals[f"dns:public-ip {'ok' if ip else 'fail'}"] += 1
            if ip:
                totals[f"dns:asn {'ok' if asn is not None else 'fail'}"] += 1
            problem = vpn_problem(tunnel, asn)
            if problem:
                summary["stopped_because"] = f"vpn check: {problem}"
                line("stop", problem)
                break
            if ip != current_ip:
                summary["ip_changes"].append({"at": now_iso(), "from": current_ip, "to": ip, "asn": asn})
                line("ip-change", f"{current_ip} -> {ip}", f"AS{asn}")
                current_ip = ip

            history = video_starts(args.out)
            day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
            if sum(1 for s in history if s > day_ago) >= args.max_per_day:
                summary["stopped_because"] = f"daily cap: {args.max_per_day} videos started in the last 24 h"
                break
            if not wait_for_slot(history, args.per_hour, stopping, deadline):
                continue  # interrupted or past the hours limit; the loop top records which

            history.append(datetime.now(timezone.utc))
            hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            pace = sum(1 for s in history if s > hour_ago)
            started = time.monotonic()
            runner.last_stdout = runner.last_stderr = ""
            kind, detail = backfill.process_video(cfg, runner, video_id, version)
            elapsed = round(time.monotonic() - started)
            counts, problems = parse_traffic(runner.last_stdout, runner.last_stderr)
            totals.update(counts)
            for p in problems:
                summary["non_2xx"].append({"at": now_iso(), "video_id": video_id, **p})
            summary["attempted"] += 1
            outcomes[kind] += 1
            reqs = sum(counts.values())
            codes = ",".join(f"{k}x{v}" for k, v in sorted(counts.items()) if not k.endswith(" 200") and not k.endswith(" 206"))
            line(video_id, kind, detail, f"{elapsed}s", f"{reqs} req", " ".join(speeds(runner.last_stdout)),
                 codes, f"ip {ip}", f"pace {pace}/h")
            write_summary()

            if kind == "challenge":
                summary["stopped_because"] = f"challenge on {video_id}: {detail}"
                break
            if kind in ("ok", "unavailable"):
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= backfill.MAX_CONSECUTIVE_FAILURES:
                    summary["stopped_because"] = f"{consecutive_failures} failures in a row"
                    break
        else:
            summary["stopped_because"] = "queue empty"

        summary["ended"] = now_iso()
        write_summary()
        line("end", summary["stopped_because"], f"attempted {summary['attempted']}", dict(outcomes))
    print(f"log: {log_path}\nsummary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
