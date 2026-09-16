# Research brief 01: Operating envelope for yt-dlp on a residential connection

Read `00-shared-context.md` first.

## The question

The pipeline downloads video, audio, and caption tracks from the AI Engineer
YouTube channel using `yt-dlp` from one home internet connection. How hard
can it run before YouTube starts challenging or throttling that connection,
and what settings keep it below that line?

## Defaults the owner already accepts

- **Design for the burst first.** The burst (up to about 300 talks over a
  few weeks after each conference, plus two or three stream recordings) is
  what the freshness goal needs. The backfill of about 1,135 talks has no
  deadline, may take months, never runs during an event window or the week
  after it, and within any run new talks are fetched before backfill items.
  Backfill ordering: audio for the whole corpus first (about 20 GB), video
  later (about 220 GB).
- Cadence and guards as in the shared context: nightly window 01:00 to
  07:00 US Eastern plus a midday pass in event weeks; home network, VPN
  off, mains power, or the run is skipped.
- Acceptance criteria: **household YouTube use on the same connection must
  never be affected (zero tolerance)**; a challenge that clears unattended
  within 24 hours and delays a talk by under a day is acceptable; the job
  never retries through a challenge, it backs off 24 hours and alerts after
  two consecutive.
- Prefer DASH variants over HLS (observed: HLS at half the rate and
  hundreds of fragment requests).

## Why it matters

There is no fallback address: cloud acquisition and proxies are out of
scope by decision. If the connection gets a "sign in to confirm you're not
a bot" challenge or a rate limit, the job must have been designed to avoid
it rather than recover by hand, and the household's ordinary YouTube use
shares the address.

## What is already known (measured 2026-09-16)

- Connection: Charter Spectrum residential, about 340 Mbps down, IPv6
  available, no carrier-grade NAT. Use the **sustained rates** for
  arithmetic, not the headline speed: about 6.5 MB/s for DASH streams, 3.2
  MB/s for HLS, with brief stalls at chunk boundaries every 10 MB or so.
  The 240 GB backfill is about 10 hours of transfer; a 300-talk burst about
  2 hours; a stream recording of 1.4 GB a few minutes.
- The same file fetched through the owner's Proton VPN (a datacenter exit)
  showed a burst-then-throttle pattern: 20 to 90 MB/s for a few megabytes,
  then 0.2 to 0.45 MB/s with periodic stalls, 3 minutes 7 seconds for an
  81 MB file versus 12 seconds on the home line. Both logs are available
  as evidence of how YouTube treats a low-trust address versus a
  residential one.
- yt-dlp 2026.08.19 selected the "visionos" player client on its own and
  exposed both HLS and DASH variants of the same stream.
- The owner has fetched, without incident and with the VPN off: three
  video streams, about 60 caption tracks, about 300 metadata-only queries,
  and several channel listings, over one day, one request at a time.
- Stream recordings: per event, two or three recordings of 8 to 10 hours,
  about 1.4 GB each at 1080p AV1, fetched once within 48 hours of each
  conference day as a video-only plus audio-only pair, counting toward the
  same nightly ceiling. They are small compared with the talk burst.
- `yt-dlp` offers `--sleep-interval`, `--max-sleep-interval`,
  `--sleep-requests`, `--sleep-subtitles`, `--limit-rate`, and
  `--concurrent-fragments`. Which values the community has converged on for
  unattended residential use is the question.

## Questions to answer

1. What request rate and daily volume from a single residential address is
   reported as safe in 2026, for (a) media downloads, (b) caption fetches,
   (c) metadata-only queries (`-J`, `--flat-playlist`)? Cite yt-dlp issue
   threads, maintainer guidance, and operator reports with dates. Metadata
   volume can be computed from the cadence: an hourly feed poll (not
   yt-dlp), a daily uploads-playlist listing, and one metadata probe per
   new video.
2. What are the recommended values for the pacing and rate-limit options
   above for an unattended job? Is `--limit-rate` or inter-request sleep
   the more important lever?
3. Whether fetching several artifacts for one video in a single `yt-dlp`
   invocation counts as one contact or several is probably unknowable from
   public sources. Give a conservative default and a calibration test
   rather than a number, and say plainly when evidence is anecdotal.
4. If a residential address does get challenged, what happens: how long
   does it last, does it clear on its own, does it affect the household's
   normal YouTube use, and what is the recommended response for an
   unattended job?
5. IPv6: the connection has it, and prior research reported that YouTube
   scores an entire IPv6 block as one unit. Should the job force IPv4, and
   does that change the pacing advice?
6. How should the backfill be scheduled under the defaults above: how many
   nights, what per-night ceiling, audio first then video, and how does a
   burst pre-empt it?
7. What does a well-behaved downloader look like from YouTube's side that
   the job can emulate cheaply: user agent, client selection
   (`--extractor-args "youtube:player_client=..."`), format probing?

## Out of scope

Cookies, account login, proof-of-origin token providers, proxies, cloud
addresses. Legal questions. Format selection details (brief 03).

## Deliverable

A recommended `yt-dlp` invocation for the nightly job with every pacing
option set and justified; a backfill plan (nights, per-night volume,
ordering, pre-emption by bursts); a table of "signals that mean back off"
with the matching response, distinguishing "succeeding but throttled" from
"challenged"; and the evidence table with dates.

## Suggested sources

yt-dlp GitHub issues and discussions (search: "sign in to confirm", "429",
"rate limit", "residential", "sleep-interval", "throttl"); the yt-dlp README
and wiki at version 2026.08.19 and release notes since June 2026; operator
write-ups from 2025 to 2026 on unattended archiving; the
youtube-transcript-api issue tracker for caption-endpoint behavior.
