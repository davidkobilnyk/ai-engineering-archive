# Research brief 03: Stream selection for storage, keyframes, and speech-to-text

Read `00-shared-context.md` first.

## The question

For each new video the job must download (a) the best 1080p video stream
preferring AV1, then VP9, then H.264, (b) the best Opus and the best AAC
audio streams, kept unprocessed as the archive's audio of record and later
sent to hosted speech-to-text services, and (c) the English automatic
caption track. What exact `yt-dlp` invocations achieve this, what verifies
the result, and which audio stream should feed transcription?

## Defaults the owner already accepts

- Keep **both** the best Opus and the best AAC stream (about 40 MB per talk
  total). Exclude dynamic-range-compressed ("DRC") variants and require the
  original-language track (auto-dubbed tracks exist on some videos).
- **"Unprocessed" means no transcoding, ever.** A lossless remux is allowed
  only if the elementary stream is shown to be unchanged. Hash the
  elementary stream, not the container, so the hash survives a remux.
- Prefer DASH over HLS variants; prefer 30 fps over 60 fps where both exist
  at the same resolution and codec; do not infer container from codec (a
  VP9 stream arrived in an mp4 container).
- yt-dlp is called as a subprocess; the deliverable is command-line
  invocations plus the `-J` and `--print` output shapes the Python side
  will parse.
- Speech-to-text vendors: Deepgram, ElevenLabs Scribe, AssemblyAI, a closed
  set. The kept audio must be accepted natively by all three.

## What is already known (measured 2026-09-16)

- Videos since mid-2025 offer AV1 (`av01`), VP9, and H.264 (`avc1`) at 360p
  through 1080p; earlier videos H.264 only. One 81-minute workshop offered
  no 1080p stream at all. Some videos offer 720p or 1080p only at 60 fps.
- The selector `-f "bv*[height<=1080][protocol!*=m3u8]" -S
  "res:1080,vcodec:av01:vp9:h264,fps:30,proto"` chose format 137 (H.264
  1080p30, about 82 MB) on a 2024 talk, 399 (AV1 1080p60, about 42 MB) on
  the Hugging Face talk, and 399 (AV1 1080p60, about 1.36 GB) on the
  8.4-hour Paris 2025 Day 2 stream recording. The `fps:30` preference is
  moot when no 30 fps variant exists at that resolution and codec.
- Audio on the Hugging Face talk: HLS audio variants (233, 234) to exclude;
  DASH Opus at 49, 61, and 113 kbps (249, 250, 251) and AAC at 49 and 129
  kbps (139, 140); all tagged `en-US original (default)`; no DRC variants
  on this video, though they exist on others. The selectors
  `ba[acodec^=opus][format_note!*=DRC]` and
  `ba[acodec^=mp4a][format_note!*=DRC]` returned 251 and 140.
- Fresh uploads: four talks checked 1.2 to 2.8 hours after publication all
  already offered 1080p in all three codecs. The full ladder appears within
  about an hour on this channel; a long hold is not needed, but the
  fetched stream must be verified against the intent.
- Caption tracks are available as `json3` (per-cue timing, sometimes
  per-word offsets), `vtt`, and `srv1`; `json3` was easiest to parse; `en`
  and `en-orig` returned identical text.

## Questions to answer

1. The video selector: confirm or improve the one above, explain each part,
   and note pitfalls (bitrate-first defaults, 60 fps variants, HLS
   variants, videos with no 1080p, the `-S` versus `-f` interaction).
2. Whether to merge video and audio into one container or keep separate
   files, judged against the "no transcoding, remux only with proof" rule.
   Consider keyframe extraction (video only), transcription (audio only),
   disk layout, and future re-processing. Recommend one.
3. Audio selectors that guarantee both the best Opus and the best AAC,
   exclude DRC variants, and require the original-language track. Confirm
   the exact `format_note` and `language` field values yt-dlp exposes for
   DRC and dubbed tracks.
4. Which of the two streams should feed speech-to-text, and why: do
   Deepgram, ElevenLabs Scribe, and AssemblyAI accept Opus/WebM and
   AAC/M4A directly, does either measurably help accuracy, and is there any
   reason to send a decoded WAV or FLAC instead (at what sample rate)?
   Record each vendor's file-size and duration limits for direct upload,
   since 8-hour stream recordings may exceed them.
5. Caption tracks: the options to fetch the English automatic track in
   `json3` without media, whether `json3` word-level offsets are reliable,
   and whether `en` versus `en-orig` ever differ.
6. Metadata: which fields the `-J` or `--write-info-json` output includes
   in current yt-dlp (upload date, duration, description, chapters,
   categories, tags, `heatmap`, view and like counts), which need
   `--write-comments`, and which require the YouTube Data API instead
   (playlist membership, precise publish time). Give the `--print`
   template the job should use for the fields it needs.
7. **Fresh-upload completeness.** How to detect that a just-published
   video's format list is still incomplete, and a wait-or-refetch policy
   that guarantees the archive ends up with the intended stream. The local
   observation suggests "verify the fetched stream matches the intended
   codec and resolution; if not, re-check once after 6 hours." Look for
   documented transcoding delays on long or high-resolution uploads.
   Scheduling of re-checks is brief 01's.
8. **Ended-stream recordings.** Do the same selectors work on a finished
   livestream recording (8 or more hours, a format set that may change for
   a day after the stream ends, possible absence of 1080p), and what
   differs? Brief 04 covers when to fetch them.
9. Verification: `ffprobe` invocations to confirm the file is the
   resolution and codec intended and complete, and how to hash the
   elementary stream.

## Out of scope

Pacing and rate limits (brief 01); tool installation and updates (brief
02); keyframe extraction (brief 09); when to fetch stream recordings (brief
04).

## Deliverable

The exact `yt-dlp` invocations for video, audio, captions, and metadata,
with reasoning; the merge-or-separate decision against the stated rule;
the audio-for-transcription recommendation with vendor documentation
cited; the fresh-upload policy; the verification commands; and the `-J`
and `--print` shapes the Python side parses. Dated citations.

## Suggested sources

The yt-dlp README sections on format selection, sorting, and output
templates at version 2026.08.19; yt-dlp wiki; Deepgram, ElevenLabs, and
AssemblyAI documentation on accepted input formats, limits, and any audio
quality guidance; ffmpeg and ffprobe documentation; community references
for YouTube format IDs (verify currency).
