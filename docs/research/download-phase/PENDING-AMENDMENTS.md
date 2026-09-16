# Pending amendments to the download-phase briefs

Collected 2026-09-16 from local tests and the research-prep agent's reviews.
Not yet applied to the briefs. Apply on the owner's go.

## 00-shared-context.md

- Replace "assume typical residential speeds" with measured values (VPN off):
  Charter Spectrum residential; ~340 Mbps down, ~39 Mbps up; idle latency
  ~33 ms; IPv6 yes; CGNAT no (hop 2 is a private ISP address, public IP has
  a residential hostname); data cap: Spectrum residential historically none,
  owner to confirm on account page.
- Add: the owner runs Proton VPN by default. Its exit is a datacenter host
  (DataPacket, Atlanta). **The download job must not run through the VPN.**
  Either exclude the job via split tunnelling or run in a window with the
  VPN off. The home-network guard must check that the public address
  belongs to the ISP, not just the Wi-Fi name.
- Add: run cadence. Channel feed polled hourly (plain RSS fetch, no
  scraping exposure). Media downloads in one nightly window, plus a midday
  pass during event weeks. Nothing runs unless on the home network, off the
  VPN, and on mains power; otherwise the run is skipped and the queue
  accumulates.
- Add: yt-dlp 2026.08.19 installed via Homebrew; it pulled in Deno as its
  JavaScript runtime. ffmpeg 9.0.1 via Homebrew with libdav1d.
- Add: measured sustained download rates on the home line: ~6.5 MB/s for
  DASH streams, ~3.2 MB/s for HLS variants, with brief stalls at chunk
  boundaries every ~10 MB. Through the VPN: 0.2 to 0.45 MB/s, rate-shaped.
  240 GB backfill is therefore about 10 hours of transfer.

## 01-residential-ip-operating-envelope.md

From the prep agent's review (all accepted):

1. State: "Design for the burst first. The backfill has no deadline, may
   take months, never runs during an event window or the week after, and
   within any run new talks are fetched before backfill items." Backfill
   ordering: audio for the whole corpus first (~20 GB), video later
   (~220 GB).
2. Use the measured connection numbers above; the arithmetic should use the
   ~6.5 MB/s sustained rate, not the headline speed.
3. State the cadence and the home-network/VPN-off rule (see 00).
4. Add stream recordings to the volume estimate: per event, 2 to 3 days x
   2 to 4 stages x 8 to 10 hours, so 40 to 100 hours of camera-heavy video,
   roughly 25 to 55 GB at 1080p AV1; fetched once within 48 hours of each
   day, as a video-only plus audio-only pair, counting toward the same
   nightly ceiling.
5. Staleness: cite yt-dlp 2026.08.19; require flags verified against the
   README at that version and release notes for the last 90 days. Replace
   question 3 ("one contact or several") with "give a conservative default
   plus a calibration test; say when evidence is anecdotal or unknowable."
6. Acceptance criteria: household YouTube use on the same connection must
   never be affected (zero tolerance); a challenge that clears unattended
   within 24 h and delays a talk under a day is acceptable; the job never
   retries through a challenge, backs off 24 h, alerts after two
   consecutive.

Observed behaviour to include as evidence: yt-dlp selected the "visionos"
player client on its own; it exposes HLS and DASH variants of the same
stream, HLS slower and many more requests, so prefer DASH; the two download
logs (VPN on versus off) for the same file. Also address IPv6: the
connection has it, and prior research said YouTube scores an IPv6 block as
one unit; recommend whether to force IPv4 for the job.

## 02-ytdlp-runtime-and-update-strategy.md

From the prep agent's review (accepted with refinements):

- Add an "Operations the pipeline runs" table, one line each with purpose
  and the flags currently used: metadata-only probe (premiere and
  availability detection); flat listing of the uploads playlist; video-only
  stream download; audio-only stream download (kept unprocessed); merge
  only if brief 03 decides so; caption track fetch as json3; metadata JSON
  including heatmap and counts; comments fetch (optional, lower priority);
  livestream recording download (conditional on brief 04); the update
  smoke test (one of the real operations against a known video). Playlist
  membership is conditional on brief 08. Exact selectors are brief 03's
  deliverable.
- Question 1 becomes an operation-by-dependency matrix (Deno, ffmpeg,
  companion packages); question 4 an operation-by-failure-signature table,
  including "succeeding but throttled" as a state distinct from "failed."
- Note Deno was installed automatically as a dependency by Homebrew.

## 03-format-selection-and-audio-for-stt.md

- Add: prefer DASH over HLS variants explicitly (observed: HLS at half the
  rate and hundreds of fragment requests). The 1080p H.264 stream selected
  by default was 60 fps (format 299); the selector must prefer 30 fps where
  both exist.
- The VP9 file was delivered in an mp4 container, not webm; the job should
  not assume container by codec.

## 05-unattended-jobs-on-a-laptop.md

- Add: Proton VPN on macOS 15. Can a scheduled command-line job (yt-dlp
  under launchd) be excluded from the tunnel by app-based split tunnelling?
  Can the tunnel be connected and disconnected from a script (no official
  macOS CLI; check scutil or app automation)? What is the reliable guard
  if neither works (public-IP check before running)?

## 09-keyframe-extraction-for-slides.md

Observed on 2026-09-16, one 21-minute slide talk, 1080p60 AV1, M1 8 GB:

- ffmpeg `scene` threshold 0.3 produced 7 frames, all full-frame image
  swaps in the screenshot-heavy section; every text-slide advance in the
  first 12 minutes was missed.
- Threshold 0.06 produced 40 frames in the same 71 seconds; 12 were
  same-second pairs at slide transitions (crossfade artifacts). Collapsing
  detections within 2 s leaves 28 distinct moments spaced 20 to 90 s
  apart, consistent with a deck. One 2.5-minute gap (3:55 to 6:29) may be a
  missed low-contrast change.
- Full-pass extraction cost is 14 to 17x real time on the AV1 stream; the
  backfill is about 30 hours of CPU. Hardware decode via VideoToolbox was
  3 to 4x real time for this workload (frames copied back to CPU) and is
  not to be used. So: extract from the stored AV1 file in software; the
  two-pass low-resolution trick is unnecessary.
- Research focus shifts to deduplication (perceptual hash) and the missed
  low-contrast case rather than decode strategy.

## 10-av1-decode-speed-test.md

Fill the results table:

| Measurement | Seconds | Real-time factor |
|---|---|---|
| AV1 1080p60 software decode | 87.4 (repeat 91.1) | 14.2x (13.6x) |
| VP9 1080p60 software decode | 44.3 | 27.9x |
| H.264 1080p60 software decode | 32.2 | 38.4x |
| VP9 1080p60 hardware decode | 287.9 | 4.3x |
| H.264 1080p60 hardware decode | 355.2 | 3.5x |
| AV1 keyframe extraction, scene 0.3 | 70.9 | 17.4x (7 frames) |
| AV1 keyframe extraction, scene 0.06 | 70.9 | 17.4x (40 frames) |

Note: all three files were 60 fps; most talks are 30 fps and will run
faster. Verdict: store AV1, extract from AV1 in software.
