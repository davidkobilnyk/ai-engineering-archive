# Research brief 04: Capturing conference livestream recordings

Read `00-shared-context.md` first.

## The question

The AI Engineer channel livestreams one stage per conference day, and the
recordings remain on the channel afterward as ordinary videos. The owner
wants to capture each day's recording, starting with AI Engineer Paris on
September 23 and 24, 2026, with the same video and audio policy as talks,
so that a later project can segment it into talks. How should the capture
work, and what is the dry run to prove it before Paris?

## Defaults the owner already accepts

- **Full video, same policy as talks:** best codec at 1080p, video-only
  plus the two audio-only streams, kept unprocessed. Keyframes are
  extracted later by the same pipeline as talks.
- **Download the recording after the day ends, not during.** A missed
  stage-day is tolerable for Paris; prefer the simplest capture, and only
  recommend record-from-start if the channel's history shows recordings
  vanishing within 48 hours (the data below shows they do not).
- Assume the job runs at its scheduled time; scheduling and laptop wake are
  brief 05's problem. The owner is in US Eastern; Paris days end about
  18:00 CEST, which is 12:00 Eastern.
- Segmenting the recording into talks is a later project and out of scope.

## What is already known

Attached: `data/streams-tab-2026-09-16.json`, the channel's Streams tab (32
recordings) with per-video upload date, availability, duration, maximum
resolution, codecs at that resolution, chapter count, and the start of the
description. Findings from it:

- **All 32 recordings back to Summit 2023 are still public.** The channel
  does not unlist or delete stream recordings.
- **One stage per day.** World's Fair 2026 has three recordings of 8.6 to
  9.2 hours (one per day); Europe 2026 two; Singapore 2026 two; Miami 2026
  two; Code 2025 two. Paris 2025 has a full 8.4-hour Day 2 and only a
  1.4-hour "Opening Keynotes" block for Day 1.
- Ended recordings keep 1080p. AV1 is present from Paris 2025 (September
  2025) onward; earlier recordings are H.264 only; one Miami 2026 day has
  VP9 and H.264 but no AV1. The Paris 2025 Day 2 recording is about 1.36 GB
  at 1080p AV1, so an event is roughly 3 to 5 GB.
- `upload_date` equals the stream day and `live_status` is `was_live`. The
  flat Streams listing carries id, title, duration, and live status but
  not dates; a per-video metadata probe adds the date.
- Many recordings carry **YouTube chapters** from the description, 20 to 39
  on recent multi-talk days, which are per-talk boundaries: ground truth
  for the later segmentation project. World's Fair 2026's three recordings
  and Paris 2025 Day 2 have none, so it is not guaranteed.
- Title conventions vary ("AI Engineer Paris 2025 (Day 2)", "AIE Europe
  Keynotes & OpenClaw ft ...", "WF26: Harness Engineering ...").
- As of 2026-09-16 there is **no machine-readable Paris 2026 schedule** in
  the ai.engineer data (the conference registry lists no schedule URL for
  Paris 2026). Do not spend effort confirming this.
- Record-from-start capture exists in `yt-dlp` (`--live-from-start`) but
  requires the machine to be on for the whole stream and is reported as
  fragile.

## Questions to answer

1. After a long livestream ends, how soon is the recording downloadable
   with `yt-dlp`, does it keep the same video ID, and does its format
   ladder match an ordinary upload immediately or lag? Any known limits
   on recording length or availability for very long streams.
2. **Discovery method**, not fixed URLs: list the Streams tab
   (`--flat-playlist` on `/@aiDotEngineer/streams`), filter `live_status`
   equal to `was_live` and upload date within the event window, so the
   same script works unchanged for NYC, Shanghai, and Code. Confirm the
   fields available in flat mode and the cheapest way to get the date.
3. Recommend the capture schedule for Paris: for example "run at 06:00
   Eastern the day after each conference day; if the recording is not yet
   available, retry every 6 hours." Say what "not yet available" looks
   like in yt-dlp output.
4. Schedule ground truth for the later segmentation project, captured now:
   snapshot the web schedule page at T-1 day and T+1 day, plus the stream
   description (and chapters, if present) and comments, all timestamped.
   What does the channel typically put in stream descriptions?
5. The exact `yt-dlp` invocation for a 10-hour recording using the talk
   format policy (brief 03's selectors), handling of very large files
   (resume, partial download), and disk needed per day. Cross-reference
   brief 03's question on ended-stream format sets.
6. Anything about mid-stream restarts producing multiple recordings, or
   per-stage streams appearing in some years, that would confuse a script
   keyed on date.
7. **Dry run.** A command sequence to run this week against the Paris 2025
   Day 2 recording (`wyUdpmj9-64`, 8.4 hours, AV1 available) that exercises
   discovery, download, and verification exactly as the Paris 2026 script
   will, so the script is tested before September 23.

## Out of scope

Segmentation of the stream into talks; pacing (brief 01); tool setup (brief
02); selector details (brief 03); scheduling (brief 05).

## Deliverable

The discovery-plus-capture procedure with exact commands and the schedule,
the "not yet available" retry rule, the schedule-capture step, the disk
budget, and the dry-run sequence. Dated citations.

## Suggested sources

The attached streams file; the channel's Streams tab and past event stream
descriptions; yt-dlp documentation and issues on live recordings and long
VODs at version 2026.08.19; YouTube Help pages on livestream archiving
limits and processing.
