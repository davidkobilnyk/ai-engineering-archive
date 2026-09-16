# Research brief 02: yt-dlp runtime requirements and safe auto-update on macOS

Read `00-shared-context.md` first.

## The question

What does `yt-dlp` need installed on an Apple Silicon Mac in 2026 to keep
working against YouTube for the operations listed below, how should it be
kept up to date without human attention, and how does an unattended job
detect that it has broken?

## Defaults the owner already accepts

- Scheduling is brief 05's problem. Assume: a Python script in a virtual
  environment invoked by launchd; the feed polled hourly while awake; media
  downloads in a nightly window plus a midday pass in event weeks; runs
  skipped when off the home network, on the VPN, or on battery.
- Update policy to evaluate: **reactive update on a detected extractor
  failure, with automatic rollback, as the primary policy; weekly update as
  the fallback.** Homebrew dependencies (ffmpeg, Deno) are pinned and
  updated manually in the owner's weekly hour. Rollback is automatic, and
  the status record states which version is now in use.
- Smoke-test video: `FLUoowDJg4I` ("How I automate my own job at Hugging
  Face using agents", World's Fair 2026, 21 minutes; has an edited upstream
  transcript and was used in every local test).
- Alerting: a glanceable status file on the Mac is the primary signal,
  email secondary. Keep it to a paragraph; it is not a design problem.

## Operations the pipeline runs

One line each with purpose and the flags used so far. Exact format
selectors are brief 03's deliverable; playlist membership is brief 08's
decision; the livestream download is brief 04's.

| Operation | Purpose | Flags used so far |
|---|---|---|
| Metadata probe | Premiere and availability detection before any download; upload date, duration, formats | `-J`, or `--print` of selected fields |
| Uploads listing | Daily complete enumeration of the channel's uploads (and Streams tab) | `--flat-playlist -J` on the channel URL |
| Video-only stream download | The kept video, best codec at 1080p | `-f "bv*[height<=1080][protocol!*=m3u8]" -S "res:1080,vcodec:av01:vp9:h264,fps:30,proto"` |
| Audio-only stream downloads | Best Opus and best AAC, kept unprocessed | `-f "ba[acodec^=opus][format_note!*=DRC]"` and `-f "ba[acodec^=mp4a][format_note!*=DRC]"` |
| Merge | Only if brief 03 decides video and audio should share a container (needs ffmpeg) | none yet |
| Caption fetch | English automatic track as json3 | `--skip-download --write-auto-sub --sub-lang en --sub-format json3` |
| Metadata snapshot | Description, upload date, chapters, heatmap, view and like counts | `--write-info-json` or `-J` |
| Comments fetch | Optional, lower priority | `--write-comments` |
| Livestream recording download | Same as video and audio downloads, on an 8-hour file | as above |
| Update smoke test | One of the real operations (the caption fetch) against the smoke-test video after any update | as caption fetch |

## Why it matters

YouTube changes its player code every few weeks and `yt-dlp` follows with a
release. A pinned version silently stops working mid-burst; an unpinned
auto-update can regress. The owner's budget is one hour a week of attention
across the whole pipeline, so the update policy and the failure signal are
the difference between a pipeline that runs and one that quietly stops.

## What is already known (measured on the owner's machine, 2026-09-16)

- Installed via Homebrew: `yt-dlp 2026.8.19_1`, which the formula installs
  as a pip package into Homebrew's `python@3.14 3.14.7`; `ffmpeg 9.0.1_1`;
  `deno 2.9.6` (pulled in automatically as a yt-dlp dependency). Node
  v24.19.0 exists only through nvm in the user's interactive shell, so a
  scheduled job would not see it. Bun is absent.
- `yt-dlp -v` on a caption fetch reports: `exe versions: ffmpeg 9.0.1,
  ffprobe 9.0.1`; optional libraries including `yt_dlp_ejs-0.8.0`,
  `curl_cffi-0.16.2`, `requests`, `websockets`; `JS runtimes: deno-2.9.6`;
  `JS Challenge Providers: bun (unavailable), deno, node (unavailable),
  quickjs (unavailable)`; `PO Token Providers: none`. It fetched the
  "visionos player API JSON" and logged "Detected experiment to bind GVS PO
  Token to video ID for web client". Caption, metadata, and media fetches
  all succeed in this configuration with no PO token provider.
- `yt-dlp -U` on this install ran without complaint and reported "up to
  date (stable@2026.08.19)". Whether `-U` would overwrite files that
  Homebrew manages when an update exists is unverified; the safer path may
  be `brew upgrade yt-dlp`.
- A prior research report (September 2026) stated: "Current yt-dlp also
  requires an external JavaScript runtime (Deno recommended; Node/Bun work)
  plus the yt_dlp_ejs package to solve challenges and mint tokens. Stable
  releases ship roughly every few weeks (current stable 2026.08.19; nightly
  master builds ship daily). YouTube breaks extractors every few weeks; a
  weekly auto-update in the scheduled job is the recommended pattern, with
  version-pinning as a rollback. Run `yt-dlp -U` (binary) or `pip install
  -U yt-dlp` weekly or before each burst, log the result, and keep a
  last-known-good pin to roll back if an update regresses. One production
  operator (about 8,800 jobs a day) reported that pulling the latest build
  weekly beat pinning, because pinning left them broken mid-week when
  YouTube shipped a player change." Verify these claims; in particular
  whether `yt_dlp_ejs` and a JavaScript runtime are required or merely
  recommended for each operation above.

## Questions to answer

1. **Operation-by-dependency matrix.** For each operation in the table:
   does it need Deno (or another JavaScript runtime), `yt_dlp_ejs`,
   ffmpeg, or any other component, as of yt-dlp 2026.08.19? Which
   operations fail outright without each, which degrade, which are
   unaffected?
2. Installation and update mechanics for a Homebrew install: what `-U`
   does to a Homebrew-managed copy, whether `brew upgrade yt-dlp` lags
   upstream releases and by how much, and whether a separate pip
   installation in the project's own virtual environment would update
   faster and roll back more cleanly. Recommend one, with the exact
   commands for update, verification (the smoke test), and rollback.
3. The reactive-update policy: how the job recognizes "this is an
   extractor failure that an update would fix" versus other failures, how
   it updates, re-runs the smoke test, and rolls back if the smoke test
   fails, all without the owner. Then the weekly fallback.
4. **Operation-by-failure-signature table.** For each operation: what the
   output and exit code look like when YouTube changed something, when the
   network is down, when the video is unavailable or a premiere has not
   aired, and when the download is succeeding but throttled. Which of
   these the job retries, which it updates on, which it alerts on.
5. Any known incompatibilities between recent `yt-dlp` versions and macOS
   15 or Apple Silicon, and any macOS-specific dependency issues (Deno
   updates, ffmpeg from Homebrew).

## Out of scope

Cloud deployment; cookies, tokens, proxies; legal questions; scheduling
(brief 05); pacing (brief 01); selector details (brief 03).

## Deliverable

The dependency matrix; the update-and-rollback procedure with commands;
the failure-signature table with the job's action per row; the status-file
contents in one paragraph. Dated citations.

## Suggested sources

The yt-dlp README, wiki, and release notes on GitHub (version 2026.08.19
and releases since June 2026); the `yt-dlp-ejs` project; PyPI release
history; the Homebrew formula history for yt-dlp; yt-dlp issues tagged with
YouTube extractor changes from 2025 to 2026.
