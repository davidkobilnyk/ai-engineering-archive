# Research brief 04: Capturing conference livestream recordings

Read `00-shared-context.md` first.

## The question

The AI Engineer channel livestreams each conference day, one stream per
stage, and the recordings remain on the channel afterward. The individual
talk videos are cut and posted days to weeks later. The owner wants to
capture each day's stream recording, starting with AI Engineer Paris on
September 23 and 24, 2026, and keep its audio and keyframes, so that a
later project can segment it into talks. How should the capture work?

## Why it matters

The stream is the earliest possible copy of every talk from an event; the
cut videos close the gap only partially. If the recording is captured
within a day or two it exists regardless of what happens to it on YouTube
later. The first event is one week from the date of this brief, so the
answer must be actionable immediately with a simple script, not a system.

## What is already known

- Streams are long: a conference day is 8 to 10 hours per stage. At 1080p
  best codec that is a few gigabytes per stage per day; audio about 500 MB.
- Recorded-from-start capture exists in `yt-dlp` (`--live-from-start`) but
  requires the machine to be on for the whole stream and is reported as
  fragile. The owner's laptop is not reliably on all day.
- After a stream ends YouTube publishes the recording as an ordinary video,
  after some processing time. Whether it keeps the same video ID as the
  live event, how long processing takes for a 10-hour stream, and whether
  the channel later unlists or trims its stream recordings are unknown.
- The later segmentation project will match cut talks to positions in the
  stream (brief 06 covers audio fingerprinting for that); this brief covers
  only capture.

## Questions to answer

1. After a long livestream ends, how soon is the recording downloadable
   with `yt-dlp`, does it keep the same video ID, and does its quality
   ladder (AV1/VP9/H.264, 1080p) match an ordinary upload or lag it? Any
   known limits on recording length or availability for very long streams.
2. What has this channel historically done with its stream recordings:
   left public, unlisted, trimmed, or deleted? Check past events (World's
   Fair 2025 and 2026, Europe 2026, Code 2025) for stream recordings still
   on the channel and their state.
3. Given an unreliable laptop, compare: (a) download the recording the
   morning after each day; (b) `--live-from-start` during the stream; (c)
   both, with (b) as a bonus. Recommend one for Paris and say what to do if
   the recording is not yet available when the job runs.
4. The recording carries the whole day: how to capture the schedule that
   maps stream time to talk (the event's published schedule, chapters in
   the stream's description, timestamps in comments) at the same time, so
   the segmentation project has ground truth. What does the channel put in
   stream descriptions?
5. Specific `yt-dlp` invocation for a 10-hour recording: format selection
   (same policy as talks), whether to fetch audio separately, handling of
   very large files (resume, partial download), and disk needed per day.
6. Anything about DVR windows, mid-stream restarts producing multiple
   recordings, or per-stage streams that would confuse a naive script.

## Out of scope

Segmentation of the stream into talks (a later project); pacing (brief 01);
tool setup (brief 02).

## Deliverable

A recommendation for the Paris capture with the exact commands and a
schedule ("run at 06:00 the day after each conference day; if not
available, retry every 6 hours"), the channel's historical behavior with
stream recordings, the disk budget, and the schedule-capture step. Dated
citations.

## Suggested sources

The channel itself (past event streams and their descriptions); yt-dlp
documentation and issues on `--live-from-start` and long VODs; YouTube Help
pages on livestream archiving limits and processing; community reports on
downloading multi-hour stream recordings.
