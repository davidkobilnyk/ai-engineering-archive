# Research brief 01: Operating envelope for yt-dlp on a residential connection

Read `00-shared-context.md` first.

## The question

The pipeline downloads video, audio, and caption tracks from the AI Engineer
YouTube channel using `yt-dlp` from one home internet connection. How hard
can it run before YouTube starts challenging or throttling that connection,
and what settings keep it below that line?

## Why it matters

Two workloads: a one-time **backfill** of about 1,135 talks (roughly 240 GB
of video at best codec, plus audio and captions), and **bursts** of up to
300 talks over a few weeks after each conference, with a trickle between.
The owner will not babysit it. If the connection gets a "sign in to confirm
you're not a bot" challenge or a rate limit, the job must have been designed
to avoid it rather than recover from it by hand. There is no fallback
address: cloud acquisition and proxies are out of scope by decision.

## What is already known

- Residential addresses are scored far higher than datacenter addresses by
  YouTube's bot detection; challenges on home connections are rare but
  reported, especially under sustained high-volume automated use.
- The owner has fetched, without incident: two audio streams, about 30
  caption tracks, about 60 metadata-only queries, and one 60-item channel
  listing, spread over two days, one request at a time.
- `yt-dlp` offers `--sleep-interval`, `--max-sleep-interval`,
  `--sleep-requests`, `--sleep-subtitles`, `--limit-rate`, and
  `--concurrent-fragments`. Which values the community has converged on for
  unattended residential use is the question.

## Questions to answer

1. What request rate and daily volume from a single residential address is
   reported as safe in 2026, for (a) media downloads, (b) caption fetches,
   (c) metadata-only queries (`-J`, `--flat-playlist`)? Cite yt-dlp issue
   threads, maintainer guidance, and operator reports with dates.
2. What are the recommended values for the pacing and rate-limit options
   above for an unattended job? Is `--limit-rate` (bytes per second) or
   inter-request sleep the more important lever?
3. Does fetching several artifacts for one video in a single `yt-dlp`
   invocation (video, audio, captions, metadata JSON) count as one contact
   or several, from the point of view of bot detection?
4. If a residential address does get challenged, what happens: how long
   does it last, does it clear on its own, does it affect the household's
   normal YouTube use, and what is the recommended response for an
   unattended job (back off and retry after N hours, alert the owner)?
5. Are there time-of-day effects or per-video rate limits worth knowing?
6. How should the backfill of about 240 GB be scheduled: how many nights,
   what per-night ceiling, and should video and audio be fetched in one pass
   or audio first for the whole corpus and video later?
7. What does a well-behaved downloader look like from YouTube's side that
   the job can emulate cheaply: user agent, client selection
   (`--extractor-args "youtube:player_client=..."`), format probing?

## Out of scope

Cookies, account login, proof-of-origin token providers, proxies, cloud
addresses. Legal questions.

## Deliverable

A recommended `yt-dlp` invocation for the nightly job with every pacing
option set and justified; a backfill plan (nights, per-night volume,
ordering); a table of "signals that mean back off" with the matching
response; and the evidence table with dates.

## Suggested sources

yt-dlp GitHub issues and discussions (search: "sign in to confirm", "429",
"rate limit", "residential", "sleep-interval"); the yt-dlp README and wiki;
operator write-ups from 2025 to 2026 on unattended archiving; the
youtube-transcript-api issue tracker for caption-endpoint behavior.
