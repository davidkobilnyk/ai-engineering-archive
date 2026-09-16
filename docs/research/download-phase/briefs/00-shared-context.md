# Shared context for the download-phase research briefs

Date: 2026-09-16 (revised the same day after local measurements and a
review round). This document accompanies the research briefs 01 to 09.
Read it first. It explains the project, what has been decided, what has
been measured, the constraints, and how to write the deliverable. Each
brief is self-contained given this document; no other files are needed.
Brief 07 has been retired (see its file for why).

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
  in batches of 5 to 30 per day after an event; on 2026-09-16 the channel
  posted four in ninety minutes, one every half hour. Conference days are
  also livestreamed, **one stage per day** (the keynote stage), and the
  recordings remain on the channel as ordinary videos afterward: all 32
  stream recordings back to 2023 were still public on 2026-09-16.
- Scheduled **premieres** appear in the channel's upload listing and in the
  RSS feed hours to more than a day before they air, with no duration and no
  downloadable media, and with the feed's `published` time set to when they
  were scheduled, not when they air.
- **Codecs**: every video uploaded since mid-2025 offers AV1, VP9, and H.264
  streams; videos uploaded before that (about 215 talks) offer H.264 only.
  Fresh uploads have the full ladder within about an hour of publication
  (four talks checked at 1.2 to 2.8 hours old all had 1080p in all three
  codecs). Measured sizes: a 21-minute slide talk is about 40 MB at 1080p
  AV1, 135 MB VP9, 470 MB H.264; camera-heavy panels are 5 to 10 times
  larger per minute; an 8.4-hour conference stream recording (slides and a
  podium) is about 1.4 GB at 1080p AV1. Audio-only streams are about 113
  kbps Opus or 129 kbps AAC, about 20 MB per talk each.
- **Automatic captions**: every talk has an English automatic caption track
  (codes `en` and `en-orig`, identical text). Quality varies per video, from
  near-perfect to poor on names. The caption text **drifts over time**: 2 of
  10 tracks re-fetched two weeks apart had changed by a few percent. No
  uploaded (manual) caption tracks were found.
- Descriptions follow a fixed template (talk page on ai.engineer, speakers'
  LinkedIn and X profiles, sometimes a company site). A 205-description
  survey found one slide-deck link and about one GitHub link per five talks.

## 4. Decisions already made (do not reopen)

- **Acquisition runs on the owner's Mac, on a home residential internet
  connection.** Cloud acquisition was researched and rejected: datacenter
  addresses hit YouTube's bot wall, and the mitigations (throwaway account
  cookies, proof-of-origin token providers, residential proxies) need
  ongoing maintenance the owner does not want. **Do not research cloud
  acquisition, cookies, token providers, or proxies.**
- **The owner runs Proton VPN by default, and the job must not run through
  it.** The VPN's exit is a datacenter host, and downloads through it were
  rate-shaped to a fifteenth of the speed. Either the job is excluded from
  the tunnel or it runs in a window with the VPN off. The home-network
  guard must check that the public address belongs to the ISP, not just
  the Wi-Fi name.
- **Run cadence.** The channel feed is polled hourly (a plain RSS fetch, no
  scraping exposure), faster when the last poll found something new. Media
  downloads run in one nightly window, 01:00 to 07:00 US Eastern, plus a
  midday pass during event weeks; no new video starts after the window
  ends, an in-progress download finishes. Nothing runs unless the Mac is on
  the home network, off the VPN, and on mains power; otherwise the run is
  skipped and the queue accumulates.
- Transcription and correction are hosted APIs called from the Mac. The
  transcription vendors under consideration are Deepgram, ElevenLabs
  Scribe, and AssemblyAI, a closed set. Not part of these briefs beyond
  input-format constraints.
- **Keep the full video** at the best codec offered (prefer AV1, then VP9,
  then H.264, at 1080p, prefer 30 fps where both exist, DASH not HLS), on a
  local 2 TB drive. Also keep: the best Opus and the best AAC audio streams
  unprocessed (no transcoding ever; lossless remux only with proof the
  elementary stream is unchanged; hash the elementary stream), keyframes
  extracted on scene changes at 1080p from the stored AV1 file, the caption
  track as json3, and a metadata snapshot at fetch time (title, description
  and every URL in it with status and title, upload date, duration,
  playlist membership, view and like counts, the "most replayed" heatmap,
  comments), a content hash, and an audio fingerprint if brief 06
  recommends one.
- **The YouTube video ID is the primary key** for everything. Every artifact
  is stored under it with the fetch time and a schema version. Timestamps in
  all artifacts are milliseconds from the video's own start, so that
  citations (`https://www.youtube.com/watch?v=ID&t=SECONDS`) stay correct.
- The pipeline calls yt-dlp as a **subprocess** (command line), not through
  its Python API, so that yt-dlp's frequent releases stay isolated and its
  documented stdout and JSON contract is what the code parses.
- The owner accepts using `yt-dlp` against YouTube's terms of service for
  this private, non-commercial archive of public conference talks that the
  channel itself transcribes. **Do not re-litigate the terms of service.**
- A livestream capture-and-segmentation project follows this one. In this
  phase each conference day's stream recording is captured after the day
  ends, with the same video and audio policy as talks; segmenting it into
  talks is not in scope.

## 5. Constraints and priorities

Priority order: (1) accuracy of names and terms, (2) freshness within 4
days, (3) unattended operation with at most **1 hour per week** of the
owner's attention, (4) cost at most **$40 per month** averaged over the year.
Initial setup should fit in about 5 hours of the owner's time.

Environment, measured on 2026-09-16:

- Apple M1 MacBook, 8 GB memory, macOS 15.4.1, FileVault on, owner stays
  logged in. Homebrew present. Python 3.13 for the archive; Homebrew's
  Python 3.14 hosts yt-dlp.
- Installed: yt-dlp 2026.08.19 (Homebrew formula, which pulled in Deno
  2.9.6 as the JavaScript runtime and carries `yt_dlp_ejs` 0.8.0), ffmpeg
  9.0.1 with libdav1d. Node 24 exists only in the user's interactive shell
  via nvm; no Bun.
- The M1 has hardware decoders for H.264 and VP9 but not AV1. Measured:
  software AV1 decode of 1080p60 runs at about 14x real time; hardware
  decode through VideoToolbox was 3 to 4x real time for a decode-to-CPU
  workload and is not to be used.
- Home connection: Charter Spectrum residential, about 340 Mbps down and 39
  Mbps up, idle latency 33 ms, IPv6 available, no carrier-grade NAT, no
  known data cap (owner to confirm on the account page). Sustained
  download from YouTube on this line: about 6.5 MB/s for DASH streams, 3.2
  MB/s for HLS variants, with brief stalls at chunk boundaries every 10 MB
  or so. Through the VPN: 0.2 to 0.45 MB/s. The 240 GB backfill is about
  10 hours of transfer on the home line.
- Archive drive: WD Elements 2 TB, USB, APFS, about 1.76 TB free; treat as
  a spinning disk powered from the cable, desk-only, spins down when idle.
- Overnight default for the project: laptop on the desk, on mains, lid
  open, display asleep, awake all night, drive attached. The owner is
  willing to keep this routine; closed-lid operation is a secondary case.
- Timezone: US Eastern (America/New_York).

## 6. How to write the deliverable

- Answer the brief's numbered questions in order. Lead with a short summary
  of the recommendation.
- **Date every citation** and every price. Distinguish, explicitly, between
  official documentation, peer-reviewed or measured results, vendor claims,
  and community reports. When sources conflict, say so and say which you
  trust and why. yt-dlp's YouTube extractor changes monthly: verify every
  flag against the README at version 2026.08.19 and check release notes for
  the last 90 days; where evidence is anecdotal or unknowable, say so and
  give a conservative default plus a calibration test rather than a number.
- **Do not add requirements.** If you think something is missing from scope,
  list it under "suggestions outside scope" at the end; do not fold it into
  the recommendation. Each brief opens with the defaults the owner already
  accepts; work within them.
- You cannot run commands or reach the owner's machine. Where a question can
  only be settled by a local test, say so and specify the exact test (tool,
  command shape, inputs, what to measure, what result would change the
  recommendation). Public URLs (the channel's RSS feed, its playlists page)
  may be fetched during research; report what was actually observed.
- End with: open uncertainties ranked by how much they would change the
  recommendation, and the cheapest experiment that resolves each; then the
  reference list grouped by source type.
- Length: as long as the evidence needs and no longer. Tables for
  comparisons. Plain language; the reader is a strong engineer who has not
  read the sources.
