# Research brief 02: yt-dlp runtime requirements and safe auto-update on macOS

Read `00-shared-context.md` first.

## The question

What does `yt-dlp` need installed on an Apple Silicon Mac in 2026 to keep
working against YouTube, how should it be kept up to date without human
attention, and how does an unattended job detect that it has broken?

## Why it matters

YouTube changes its player code every few weeks and `yt-dlp` follows with a
release. A pinned version silently stops working mid-burst; an unpinned
auto-update can regress. The owner's budget is one hour a week of attention
across the whole pipeline, so the update policy and the failure alert are
the difference between a pipeline that runs and one that quietly stops.

## What is already known

- `yt-dlp` is currently installed from PyPI into a Python 3.13 virtual
  environment and works for audio, captions, and metadata as of
  2026-09-16 (version from PyPI at that date).
- A recent research report stated that current `yt-dlp` requires an external
  JavaScript runtime (Deno recommended; Node or Bun also work) plus a
  companion package to solve YouTube's challenges, and that stable releases
  ship every few weeks with nightly builds daily. The owner's installation
  has not yet needed a JavaScript runtime for the operations tried; whether
  it will for video downloads or under challenge is unknown.
- Homebrew is available. The machine is macOS 15 on an M1.

## Questions to answer

1. As of now, exactly what does `yt-dlp` require on macOS for reliable
   YouTube downloads: JavaScript runtime (which, which version, how
   detected), `ffmpeg` (for merging separate video and audio streams and
   for post-processing), any companion Python packages? Which operations
   fail without each?
2. Installation method for unattended use: PyPI in a virtual environment,
   the standalone binary, or Homebrew. Which updates most safely and which
   lags YouTube changes least? Cite release cadence data.
3. Update policy: the report recommended a weekly auto-update plus a pinned
   last-known-good rollback. Confirm or improve: exact commands, how to
   verify an update worked before relying on it (a smoke test against a
   known video), how to roll back, and whether nightly builds are advisable.
4. Breakage detection: what do failures look like in `yt-dlp` output and
   exit codes when YouTube has changed something versus when the network
   is down versus when a video is unavailable? How should the job classify
   these so it retries the right ones and alerts on the others?
5. Alerting on a laptop: the lightest reliable way for a scheduled job to
   tell the owner "downloads have failed for two nights" (macOS
   notification, email, a message to a chat app, a status file the owner
   checks weekly). Recommend one.
6. Any known incompatibilities between recent `yt-dlp` versions and macOS
   15 or Apple Silicon.

## Out of scope

Cloud deployment; cookies, tokens, proxies; legal questions.

## Deliverable

A setup checklist for the Mac (packages, versions, verification commands),
an update-and-rollback procedure with commands, a failure classification
table (symptom, likely cause, job action), and the alerting recommendation,
with dated citations.

## Suggested sources

The yt-dlp README, wiki, and release notes on GitHub; PyPI release history;
yt-dlp issues tagged with YouTube extractor changes from 2025 to 2026;
Homebrew formula history; operator write-ups on unattended yt-dlp.
