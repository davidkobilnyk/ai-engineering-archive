"""Write the channel's upload order (newest first) for scripts/vpn_test.py (2026-09-17).

Walks the uploads playlist with the YouTube Data API (playlistItems.list, 1 quota
unit per page of 50). The key is read from the login Keychain and sent only as
an X-Goog-Api-Key header. No yt-dlp and no youtube.com scraping.

Run from the repo root in the Terminal (the sandboxed shell cannot read the Keychain):
    .venv/bin/python scripts/upload_order.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UPLOADS_PLAYLIST = "UULKPca3kwwd-B59HNr-_lvA"
API = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
OUT = Path("/Volumes/Archive/vpn-test/upload-order.txt")
TALKS = Path("data/raw/talks.json")


def api_key() -> str:
    proc = subprocess.run(["security", "find-generic-password", "-a", "ingest", "-s",
                           "youtube-data-api-key", "-w"], capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        sys.exit("could not read youtube-data-api-key from the login Keychain")
    return proc.stdout.strip()


def main() -> int:
    key = api_key()
    ids: list[str] = []
    token = None
    pages = 0
    while True:
        query = {"part": "contentDetails", "playlistId": UPLOADS_PLAYLIST, "maxResults": 50}
        if token:
            query["pageToken"] = token
        req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(query)}",
                                     headers={"X-Goog-Api-Key": key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            page = json.load(resp)
        pages += 1
        ids += [item["contentDetails"]["videoId"] for item in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            break

    talks = {t.get("videoId") for t in json.loads(TALKS.read_text())} - {None}
    in_corpus = sum(1 for i in ids if i in talks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("# uploads playlist, newest first; written by scripts/upload_order.py\n"
                   + "\n".join(ids) + "\n")
    print(f"{pages} pages, {len(ids)} uploads; {in_corpus} of {len(talks)} corpus talks found in the playlist")
    print(f"wrote {OUT}")
    report_not_in_corpus(key, ids, talks)
    return 0


def iso_duration_s(text: str) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text or "")
    if not m:
        return None
    d, h, mi, s = (int(g or 0) for g in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def report_not_in_corpus(key: str, ids: list[str], talks: set[str]) -> None:
    """Report only: the uploads with no corpus talk, with title, date, duration, livestream flag.
    videos.list, 1 quota unit per 50 IDs."""
    missing = [(pos, i) for pos, i in enumerate(ids) if i not in talks]
    details: dict[str, dict] = {}
    for start in range(0, len(missing), 50):
        batch = [i for _, i in missing[start:start + 50]]
        query = {"part": "snippet,contentDetails,liveStreamingDetails", "id": ",".join(batch), "maxResults": 50}
        req = urllib.request.Request(f"{VIDEOS_API}?{urllib.parse.urlencode(query)}",
                                     headers={"X-Goog-Api-Key": key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            for item in json.load(resp).get("items", []):
                details[item["id"]] = item

    rows = []
    for pos, video_id in missing:
        item = details.get(video_id, {})
        snippet = item.get("snippet", {})
        seconds = iso_duration_s(item.get("contentDetails", {}).get("duration", ""))
        rows.append({
            "position": pos, "video_id": video_id,
            "published": (snippet.get("publishedAt") or "")[:10],
            "duration": f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds is not None else "?",
            "duration_s": seconds,
            "livestream": "yes" if "liveStreamingDetails" in item else "no",
            "live_now": snippet.get("liveBroadcastContent", "?"),
            "title": snippet.get("title", "(not returned: private or removed?)")})

    tsv = OUT.with_name("uploads-not-in-corpus.tsv")
    cols = ["position", "video_id", "published", "duration", "duration_s", "livestream", "live_now", "title"]
    tsv.write_text("\t".join(cols) + "\n" + "".join(
        "\t".join(str(r[c]) for c in cols) + "\n" for r in rows))
    print(f"\n{len(rows)} uploads not in the corpus (position 0 = newest):")
    print(f"{'pos':>4}  {'video_id':<11}  {'published':<10}  {'duration':>8}  live  title")
    for r in rows:
        print(f"{r['position']:>4}  {r['video_id']:<11}  {r['published']:<10}  {r['duration']:>8}  "
              f"{r['livestream']:<4}  {r['title'][:70]}")
    print(f"wrote {tsv}")


if __name__ == "__main__":
    sys.exit(main())
