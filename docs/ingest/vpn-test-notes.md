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

## Session update, 2026-09-17 ~17:20 UTC (supersedes earlier state above)

### 13:38 run on CO#77 ended (measured, `vpn-test-2026-09-17-0938.log` / `.summary.json`)

- 13:38:08-16:30:55 UTC (~2 h 53 min of `--hours 10`): **58 attempted, 56 ok,
  0 x 429, 0 challenges.** Pace ramped to 20/h by 14:36 and held there. Most
  videos took 57-95 s and 8-12 requests (worst: 195 s; 26 requests).
- It went past home's failure point (42 videos) at about 15:40 UTC and kept
  succeeding for 16 more. This fits a rate limit rather than a nightly count,
  but it was a different address, so it isn't proof.
- Failures:
  - HvMyYLTfvhg 16:21:24 `extractor`: two HTTP 403s on audio pieces
    (`rr3---sn-a5msenes.googlevideo.com`, `Server: gvs 1.0`, no Retry-After), 26 s
    apart. Captions and info.json downloaded; audio didn't. The next videos
    succeeded. Same unexplained 403 pattern as home and decision test 1.
  - zaGyGgLW3SM 16:30:39 `transient`: DNS failed to resolve `www.youtube.com`.
    The script's egress-ASN check then failed and it stopped ("could not look
    up egress ASN"). Likely a Proton connection drop (inferred, not verified).

### Restart at 17:07 UTC (ended 17:55 on a 429; see the 19:30 section below)

- Owner reconnected the VPN; the restart is running in the owner's Terminal
  panel: `.venv/bin/python scripts/vpn_test.py --hours 10`. Log is
  `vpn-test-2026-09-17-1307.log` (the name uses local time). Egress 62.93.177.118. The ASN lookup
  showed AS3257 this time (see the prefix note above). Queue 1044.
- **Owner said to let this run continue as it is**; don't stop or change it.
- No code change was needed for the retries: failed videos aren't "done", so
  `build_queue` put HvMyYLTfvhg and zaGyGgLW3SM first (checked with `--dry-run`),
  followed by the same newest-first order.
- Results so far: HvMyYLTfvhg `failed` (see below); zaGyGgLW3SM ok;
  4loPnxvWWhg ok; _ehJyfHg1Vk ok (as of 17:17).
- Expected end: the 200-per-24-h cap counts today's 58 earlier starts, so about
  142 more starts, roughly 7 h at 20/h (~00:00-01:00 UTC). After that, the 13:38
  run's starts begin aging out of the 24 h window.

### HvMyYLTfvhg retry failed on leftover files, not the network

- Error: `unexpected codec '' for format 140-3.en`
  (`src/aie/ingest/backfill.py:102`). The retry downloaded both audio files
  cleanly (`f140-3.m4a` 12.4 MB, `f251-3.webm` 10.5 MB, no 403). The 16:21
  attempt had left a caption file named `HvMyYLTfvhg.f140-3.en.json3`.
  `ytdlp.rows_from_files` read it as an audio format with an empty codec.
- With owner approval, that file was **moved** (not deleted) to
  `/Volumes/Archive/vpn-test/set-aside/`. The current run won't retry the video;
  the next restart will. Whether it then passes verify using the audio already on
  disk is untested.
- New known gap (not fixed, main code untouched): files left by a failed attempt
  can fail the check on the next retry. It could be logged in
  `next-round-changes.md` if the owner wants it fixed.

### Home nightly job is unloaded

- With owner approval, ran `launchctl bootout gui/$(id -u)/com.aie.backfill`
  (exit 0; `launchctl print` now reports the service not found). The plist is
  still at `~/Library/LaunchAgents/com.aie.backfill.plist`. Re-enable with
  `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aie.backfill.plist`.
- Reason: the VPN route is doing much better than the home line. Home
  `status.json` is unchanged (backoff until 2026-09-18T05:54:34Z,
  `consecutive_challenges: 1`).

### How to check on the run

- The log is on the drive:
  `tail /Volumes/Archive/vpn-test/vpn-test-2026-09-17-1307.log`. The summary
  JSON is written next to it.
- In the Bash sandbox, the egress/ASN lookup fails ("could not look up egress
  ASN") even when the VPN works. Run `vpn_test.py` (including `--dry-run`) from
  the Terminal panel, not sandboxed Bash.

### Still open

- The earlier open questions above still stand.
- Whether VPN downloads move into `/Volumes/Archive/videos/`, and whether the
  home job switches to the VPN route or per-hour pacing: undecided, owner's call.

## Session update, 2026-09-17 ~19:30 UTC (latest; supersedes the 17:20 section)

### The 17:07 run on CO#77 ended on a 429 at 17:55 UTC

`vpn-test-2026-09-17-1307.log` / `.summary.json`:

- 17:07:17-17:55:34 UTC (48 min of `--hours 10`): 17 attempted, 15 ok, 1 failed
  (HvMyYLTfvhg, see below), **1 challenge: HTTP 429 on the caption fetch of
  u6q-byPWUuo** from `www.youtube.com`, no `Retry-After`. The 15 before it were
  clean (59-89 s, 8-12 requests, no 403s). No slowdown first - the same
  signature as the home line's 429.
- So 20/h did not prevent the 429; it delayed it. The earlier "this fits a rate
  limit" reading in the 17:20 section is **wrong as stated** - see the counts below.

### Starts before each 429 (measured from the logs, by egress address)

| Trailing window before the 429 | Home (429 05:54) | CO#77 (429 17:55) |
|---|---|---|
| 1 h | 42 | 16 |
| 2 h | 42 | 28 |
| 3 h | 42 | 48 |
| 4 h | 45 | 68 |
| 5 h | 45 | 80 |
| whole session | 45 (03:06-05:54) | 81 (13:06-17:55) |

Home's 45 includes a single-video test run at 03:06. CO#77's 81 is the three runs
on 62.93.177.118 (6 + 58 + 17); the 12:54/13:00 rows in the log dir are the
blocked CA#620 and CL#40 exits and are not on this address.

**No single window gives the same threshold for both addresses.** Neither "N per
hour" nor "N per rolling window" fits.

### Working hypothesis: a token bucket (unproven, 2 points / 2 parameters)

A budget that spends one per video start and refills steadily fits both failures
with **refill ~10 starts/h and bucket ~33**:

- home: 42 starts in 54 min - fast enough that refill barely matters
- CO#77: 81 starts in 4 h 50 min (avg ~16.8/h), ~7/h above refill, so the same
  bucket took ~5 h to drain

Caveat, important: two failures and two unknowns, so the fit is exact by
construction and is **not evidence**. The two addresses need not share a budget.
Its sharp prediction is what makes it worth testing: a sustained rate below the
refill should never trip, however long it runs.

### Test running now: 8/h on a new exit CR#4 (started 18:51:34 UTC)

- Owner runs it in their own terminal tab (not Claude's):
  `.venv/bin/python scripts/vpn_test.py --per-hour 8 --hours 16 --max-per-day 300`
- Egress **195.177.92.62** AS212238 (new today; not CO#77, CA#620 or CL#40).
  Log `vpn-test-2026-09-17-1451.log`. Queue 1028.
- Cap raised to 300 so it does not bind (81 used today + ~128 at 8/h). `--hours 16`
  is the limiter: no new starts after ~10:51 UTC on 2026-09-18.
- As of 19:23: 5 attempted, 5 ok (u6q-byPWUuo - the 429 casualty - 5dCAmSDOAjI,
  byn9PURoBNY, Xln-On3syJk, z1dqv74SpUs). No 403s, no 429s.
- **What counts as a result**: no 429 through the whole run supports the bucket
  (refill >= 8/h). A 429 refutes it as stated; the count and time then give a
  better refill estimate.

### HvMyYLTfvhg is fixed; the leftover-file failure is understood

- The stray `HvMyYLTfvhg.f140-3.en.json3` (written by the 16:21 attempt, read by
  `ytdlp.rows_from_files` as an audio format with an empty codec) was moved to
  `/Volumes/Archive/vpn-test/set-aside/`. Nothing was deleted.
- On the next run the video verified in **9 s with 3 requests** using the audio
  already on disk. Confirms the diagnosis: a leftover file, not the network.
- Still a real gap in the job: files left by a failed attempt can fail the check
  on the next retry. Not fixed, main code untouched; candidate for
  `next-round-changes.md` if the owner wants it.

### Other state

- Home nightly LaunchAgent `com.aie.backfill` is **unloaded** (`launchctl bootout`,
  exit 0; plist still in `~/Library/LaunchAgents`). Nothing else touches YouTube
  overnight. Re-enable with `launchctl bootstrap gui/$(id -u) <plist>`.
- Home `status.json` untouched: backoff until 2026-09-18T05:54:34Z,
  `consecutive_challenges: 1`.
- Two duplicate runs were started by accident at 18:41/18:42 (owner's and
  Claude's, same args). Claude's `pkill -f` pattern then matched both and killed
  the owner's too. Lesson for a later session: check for a running process first,
  target by PID, and leave the owner's processes to the owner.
- `docs/ingest/vpn-test-notes.md` is on branch `vpn-audio-test`;
  PR is davidkobilnyk/ai-engineering-archive#6.
