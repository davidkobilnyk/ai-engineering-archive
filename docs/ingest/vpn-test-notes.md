# First nightly 429 and the VPN rate test: findings and state

Written 2026-09-17 ~14:15 UTC so a later session can pick this up. Files
this relies on:

- `scripts/vpn_test.py`, `scripts/upload_order.py` (new, uncommitted; the
  docstrings describe behaviour and how to run them)
- `docs/ingest/vpn-test-addresses.md` (one row per Proton exit tried)
- `docs/ingest/next-round-changes.md` (owner-requested changes to the job,
  not applied)
- `/Volumes/Archive/logs/backfill-2026-09-17.log`, `/Volumes/Archive/status.json`
- `/Volumes/Archive/vpn-test/` (test archive root: `videos/`, `vpn-test-*.log`,
  `*.summary.json`, `upload-order.txt`, `uploads-not-in-corpus.tsv`)

## Owner decisions in force

- **No changes to the main code or its configuration** (`src/aie/`, tests,
  LaunchAgent, setup doc). The VPN test is separate new files only; it
  reuses the job's code without modifying it. Changes the owner wants for
  the job go in `next-round-changes.md` and wait for approval.
- VPN test pacing: **20 video starts/hour, 200 per rolling 24 h**, counted
  across all runs from the logs.
- Queue order: (1) uploads not in the corpus yet, published in the last 14
  days, 5-60 min long; (2) World's Fair 2026; (3) rest of the corpus; newest
  upload first in each. **No stream recordings** (hard skip over 2 h).
- Owner considers ~55+ nights for the audio backfill unacceptable; that is
  why a faster route (VPN, per-hour pacing) is being explored.
- Owner's browser YouTube on the home line worked the morning after the 429,
  and on Proton CA#620 while yt-dlp was blocked there.

## Home run, night of 2026-09-17 (measured)

- 01:00:14-01:54:34 local: 42 attempted back to back (~77 s each, ~47/h),
  37 ok, 3 `wrong_track`, 1 HTTP 403 on audio (hqHC6Z_lXyo, 01:43:44), then
  HTTP 429 on the **caption** fetch of jVjt-2g8NMY. 8 videos (with captions)
  succeeded between the 403 and the 429. No slowdown before the 429.
- Job reacted as designed: `challenge`, `backoff_until` 2026-09-18T05:54:34Z,
  `consecutive_challenges: 1` (a second challenge alerts).
- `/Volumes/Archive/.backfill.lock` still names PID 73718, which is gone.
  Not checked whether the job treats that as stale (flock should release on
  exit; the file content is just a note).
- Brief 01's report predicted 150-250/night as safe; reality was ~42.

## Facts established (from yt-dlp source and logs, not guesses)

- Per video, yt-dlp writes subtitles **before** info.json and media
  (`YoutubeDL.py` ~3391/3403/3535). The caption fetch is the first request
  after extraction, so a caption 429 does not prove captions have a
  separate, tighter limit.
- In yt-dlp 2026.08.19's YouTube extractor, only caption (timedtext) URLs
  request impersonation (`_video.py:4217`). `curl_cffi` is not installed
  (`yt-dlp[default]` does not include it), so every log warns "no impersonate
  target is available". Effect on limits: unknown.
- A 403 on an audio URL was also seen in decision test 1 (2026-09-16) with no
  volume behind it; cause not established.
- Media downloads are 10 MiB range requests (`CHUNK_SIZE = 10 << 20`), so a
  typical talk is ~8 requests: page, player API, manifest, caption, ~4 audio
  pieces (12 when googlevideo redirects each piece).
- The 3 `wrong_track` failures (and Yyg_BoeB2LU on the VPN) have full audio
  on disk; `format_note` lacks "original". Likely a too-strict check; not
  investigated.

## VPN test results (2026-09-17, all Proton, all AS212238 Datacamp)

- CA#620 149.22.82.105 and CL#40 195.86.38.41: blocked on the first request
  (`/watch` 302 to `google.com/sorry`, 429 there, player `LOGIN_REQUIRED`, no
  Retry-After). Browser on CA#620 worked.
- CO#77 62.93.177.118: works. First run back to back (~55/h, 6 videos, owner
  stopped it). Second run started 13:38 UTC at 20/h, `--hours 10`: 11/11 ok by
  14:11, no 403/429, one throttled AAC download (eZ8WWZzoaR0, 0.13-0.31 MB/s,
  156 s). Home's failure point (42 videos) expected around 15:45 UTC.
- ASN lookups can return several lines (covering prefixes). CO#77 first
  showed AS3257 (GTT /19), later AS212238 (Datacamp /24, the real one). So the
  provider is not what separates working from blocked exits; the address is.
- Proton's server list API needs a login token; finding exits is trial and
  error with `--dry-run` (DNS only) then a real run (a flagged exit fails in
  ~20 s).

## Known gaps in the test script (not fixed)

- Per-video `traffic.log` / `yt-dlp.log` are overwritten when a later run
  retries the same video (CA#620's hqHC6Z trace was overwritten by CL#40's).
  Summary JSONs keep the counts and non-2xx headers per run.
- The speed column is always empty: the job's command uses `--print`, which
  silences yt-dlp progress lines. Time per video is logged instead.
- The `vpn-test-addresses.md` table is updated by hand.
- VPN downloads live under `/Volumes/Archive/vpn-test/videos/`; the home job
  does not see them and would re-fetch them. Moving them into
  `/Volumes/Archive/videos/` has not been decided.
- `upload_order.py` must be re-run to see new uploads; the queue does not
  refresh itself.

## Open questions

- Is YouTube's limit on the home line per hour or per night? (CO#77 at 20/h
  past 42 videos is evidence for a rate limit, on a different address.)
- Does installing `curl_cffi` change caption-fetch behaviour?
- Should the home job adopt the VPN route, per-hour pacing, the new queue
  order, or fetch captions separately? None approved.
- 48 newest corpus talks have `event: null` (mostly voice-agent talks); whether
  they belong to World's Fair 2026 is unknown.
