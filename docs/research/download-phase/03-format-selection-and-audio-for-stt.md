# Research brief 03: Stream selection for storage, keyframes, and speech-to-text

Read `00-shared-context.md` first.

## The question

For each new video the job must download (a) the best 1080p video stream
preferring AV1, then VP9, then H.264, (b) the best audio stream, kept
unprocessed as the archive's audio of record and later sent to hosted
speech-to-text services, and (c) the English automatic caption track. What
exact `yt-dlp` format selection achieves this, and which audio stream is
the right one to keep for transcription?

## Why it matters

The video is kept forever on a local drive, so codec choice sets storage
size by a factor of ten. The audio is the input to every transcription now
and in the future, so the wrong container or codec could cost accuracy or
force conversions. Getting the selector wrong silently, for example
downloading a 720p stream because 1080p was named differently, would only
be noticed months later.

## What is already known

- Measured on the channel: videos since mid-2025 offer AV1 (`av01`), VP9,
  and H.264 (`avc1`) at 360p through 1080p; earlier videos H.264 only. One
  81-minute workshop offered no 1080p stream at all. Some videos offer
  720p at 60 fps.
- Audio streams observed: about 129 kbps, in both Opus/WebM and AAC/M4A
  containers. Which is better for speech-to-text is unknown.
- Video and audio are separate streams on YouTube; merging into one file
  needs `ffmpeg`. The archive may prefer to keep them as separate files
  keyed by video ID.
- Caption tracks are available as `json3` (with per-cue timing and, in some
  cases, per-word offsets), `vtt`, and `srv1`; `json3` was the easiest to
  parse. Codes `en` and `en-orig` returned identical text.

## Questions to answer

1. The `yt-dlp` format selector (`-f` with `-S` sort options) that expresses
   "1080p if available else the highest below it; AV1 preferred, then VP9,
   then H.264; avoid 60 fps if a 30 fps stream of the same resolution and
   codec exists" and downloads it as video-only. Give the exact string and
   explain each part. Note pitfalls (e.g. `bestvideo` preferring bitrate
   over codec).
2. Whether to merge video and audio into one container or keep separate
   files. Consider: keyframe extraction (video only), transcription (audio
   only), disk layout, and future re-processing. Recommend one.
3. Audio for speech-to-text: Opus/WebM versus AAC/M4A at the bitrates
   YouTube offers. Do the major hosted transcription services (Deepgram,
   ElevenLabs Scribe, AssemblyAI) accept both directly? Does either
   measurably help accuracy? Is there any reason to transcode to WAV or
   FLAC before upload (and if so, at what sample rate), or to keep the
   original and let each service decode it?
4. Caption tracks: the `yt-dlp` options to fetch the English automatic
   track in `json3` without downloading media, whether `json3` word-level
   offsets are reliable, and whether `en` versus `en-orig` ever differ.
5. Metadata: the `-J` or `--write-info-json` output includes upload date,
   duration, description, chapters, categories, tags, and a `heatmap` (most
   replayed) field. Confirm which fields exist in current `yt-dlp` output,
   which need the extra `--write-comments` option, and which require the
   YouTube Data API instead (playlist membership, precise publish time).
6. Verification: how to confirm after download that the file is the
   resolution and codec intended (`ffprobe` invocation) and complete
   (`yt-dlp`'s own checks, content hash), so the job can reject a bad fetch.

## Out of scope

Pacing and rate limits (brief 01); tool installation (brief 02); keyframe
extraction method (brief 09).

## Deliverable

The exact `yt-dlp` invocations for video, audio, captions, and metadata
(one invocation or several, with reasoning), the audio-format
recommendation with evidence from transcription vendors' documentation, the
merge-or-separate decision, and the verification commands. Dated citations.

## Suggested sources

The yt-dlp README sections on format selection and sorting; yt-dlp wiki;
Deepgram, ElevenLabs, and AssemblyAI documentation on accepted input formats
and any guidance on audio quality; ffmpeg and ffprobe documentation; YouTube
format ID references maintained by the community (verify currency).
