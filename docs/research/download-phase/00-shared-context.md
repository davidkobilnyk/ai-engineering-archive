# Shared context for the download-phase research briefs

Date: 2026-09-16. This document accompanies nine research briefs (01 to 09).
Read it first. It explains the project, what has been decided, what has been
measured, the constraints, and how to write the deliverable. Each brief is
self-contained given this document; no other files are needed.

## 1. The project in one paragraph

The owner (a software engineer, working alone, on a Mac) maintains a private,
local, full-text-searchable archive of the AI Engineer conference talk
transcripts. The archive is a Python command-line tool over SQLite with FTS5,
used by an AI coding assistant to answer questions about AI engineering
practice with citations into the talks (timestamped YouTube links). The
transcripts come from a public bulk data feed at https://ai.engineer/data.
The owner is now building an **ingest pipeline** that fetches new talks from
the AI Engineer YouTube channel as soon as they are published, transcribes
them with a hosted speech-to-text service, corrects names with an LLM, and
inserts a provisional transcript that is replaced automatically when the
official edited transcript arrives. These briefs cover the **download phase**
only: watching the channel, fetching video, audio, captions, and metadata,
and storing them.

## 2. Why the pipeline exists (measured, not assumed)

- The upstream feed republishes about every two weeks. A new talk appears in
  it 1 to 16 days after upload, about 8 on average. When it appears, it is a
  **placeholder**: the raw YouTube automatic caption track, a summary, no
  topics, a hash-style slug. The **edited transcript** (verbatim, punctuated,
  names corrected, about 0.4% name error) arrives later: as of 2026-09-16,
  every talk uploaded through 2026-08-21 had an edited transcript and nothing
  uploaded after did, so the edit lag is 3 to 4 weeks and unbounded.
- The owner's goal is a new talk queryable at edited quality within **4 days**
  of upload. AI engineering moves fast; weeks of lag on the newest talks is
  the problem being solved.
- The corpus today: 1,135 talks, about 463 hours of audio, average talk 25
  minutes, some panels and workshops over an hour. Arrival is bursty: one
  conference adds about 300 talks within a few weeks; a trickle otherwise.
- Upcoming events, each producing a burst: AI Engineer Paris (Sept 23 to 24,
  2026), NYC (Oct 12 to 14), Shanghai (Nov 5 to 6), Code in San Francisco
  (Nov 10 to 12).

## 3. The channel and what YouTube offers

- Channel: `https://www.youtube.com/channel/UCLKPca3kwwd-B59HNr-_lvA`
  (handle `@aiDotEngineer`). Talks are posted as individual videos, typically
  in batches of 5 to 30 per day after an event. Conference days are also
  livestreamed per stage; the stream recordings remain as videos afterward.
- Scheduled **premieres** appear in the channel's upload listing hours before
  they air, with no duration and no downloadable media.
- **Codecs**: every video uploaded since mid-2025 offers AV1, VP9, and H.264
  streams; videos uploaded before that (about 215 talks) offer H.264 only.
  Measured sizes for a 21-minute slide talk: 1080p AV1 about 40 MB, 1080p VP9
  about 135 MB, 1080p H.264 about 470 MB. Camera-heavy panels are 5 to 10
  times larger per minute. Audio-only streams are about 129 kbps, about
  20 MB per talk.
- **Automatic captions**: every talk has an English automatic caption track
  (codes `en` and `en-orig`, identical text). Quality varies per video, from
  near-perfect to poor on names. The caption text **drifts over time**: 2 of
  10 tracks re-fetched two weeks apart had changed by a few percent. No
  uploaded (manual) caption tracks were found.
- The `yt-dlp` tool (installed from PyPI into a Python virtual environment)
  has been used successfully from the owner's Mac for audio, video format
  listing, caption tracks (json3, vtt, srv1), channel listings, and upload
  dates. The official YouTube caption download API is owner-only and is a
  dead end.

## 4. Decisions already made (do not reopen)

- **Acquisition runs on the owner's Mac, on a home residential internet
  connection.** Cloud acquisition was researched and rejected: datacenter
  addresses hit YouTube's bot wall, and the mitigations (throwaway account
  cookies, proof-of-origin token providers, residential proxies) need
  ongoing maintenance the owner does not want. **Do not research cloud
  acquisition, cookies, token providers, or proxies.**
- Transcription and correction are hosted APIs called from the Mac. Not
  part of these briefs.
- **Keep the full video** at the best codec offered (prefer AV1, then VP9,
  then H.264, at 1080p), on a local multi-terabyte drive the owner already
  has. Also keep: the audio stream unprocessed, keyframes extracted on scene
  changes at 1080p, the caption track, and a metadata snapshot at fetch time
  (title, description and the links in it, upload date, duration, playlist
  membership, view and like counts, the "most replayed" heatmap, comments),
  a content hash, and an audio fingerprint.
- **The YouTube video ID is the primary key** for everything. Every artifact
  is stored under it with the fetch time and a schema version. Timestamps in
  all artifacts are milliseconds from the video's own start, so that
  citations (`https://www.youtube.com/watch?v=ID&t=SECONDS`) stay correct.
- The owner accepts using `yt-dlp` against YouTube's terms of service for
  this private, non-commercial archive of public conference talks that the
  channel itself transcribes. **Do not re-litigate the terms of service.**
- A livestream capture-and-segmentation project follows this one. For now
  the owner only wants to capture each conference day's stream recording
  and keep its audio and keyframes.

## 5. Constraints and priorities

Priority order: (1) accuracy of names and terms, (2) freshness within 4
days, (3) unattended operation with at most **1 hour per week** of the
owner's attention, (4) cost at most **$40 per month** averaged over the year.
Initial setup should fit in about 5 hours of the owner's time.

Environment: Apple M1 MacBook, 8 GB memory, macOS 15, Homebrew, Python 3.13,
a home broadband connection (assume typical residential upload and download
speeds; the owner has not reported a data cap). The laptop sleeps and is
sometimes closed or away. The M1 has hardware decoders for H.264 and VP9 but
**not for AV1**.

## 6. How to write the deliverable

- Answer the brief's numbered questions in order. Lead with a short summary
  of the recommendation.
- **Date every citation** and every price. Distinguish, explicitly, between
  official documentation, peer-reviewed or measured results, vendor claims,
  and community reports. When sources conflict, say so and say which you
  trust and why.
- **Do not add requirements.** If you think something is missing from scope,
  list it under "suggestions outside scope" at the end; do not fold it into
  the recommendation.
- You cannot run commands or reach the owner's machine. Where a question can
  only be settled by a local test, say so and specify the exact test (tool,
  command shape, inputs, what to measure, what result would change the
  recommendation).
- End with: open uncertainties ranked by how much they would change the
  recommendation, and the cheapest experiment that resolves each; then the
  reference list grouped by source type.
- Length: as long as the evidence needs and no longer. Tables for
  comparisons. Plain language; the reader is a strong engineer who has not
  read the sources.
