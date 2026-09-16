# Research brief 09: Extracting slide keyframes from talk videos

Read `00-shared-context.md` first.

## The question

At download time the job extracts still frames from each talk video at the
moments the picture changes, so that slides are preserved as images keyed
by timestamp. The frames are kept forever; text extraction from them is a
later project. What method and parameters produce one clean frame per slide
on this channel's production styles, with few duplicates and few misses,
at a compute cost the M1 can absorb during a backfill of 463 hours?

## Why it matters

Slides carry correctly spelled names, code, URLs, and numbers that the
speaker never says aloud. Frames are cheap to store (tens of megabytes per
talk at 1080p) and the video is kept anyway, but extracting well is fiddly:
speaker-camera cuts, picture-in-picture layouts, animated bullet builds,
and screen recordings each fool a naive scene-change detector differently.
A survey of what works avoids a long local tuning loop.

## What is already known

- The channel's production styles include: full-screen slides with a small
  speaker inset; alternating cuts between the speaker and the slides;
  direct screen capture (demos, code); and camera-only shots where slides
  are visible in the background at low resolution. Panels are camera-only.
- Tools the owner is aware of: `ffmpeg`'s `select='gt(scene,T)'` filter with
  `showinfo` for timestamps; PySceneDetect (content and adaptive
  detectors); perceptual hashing (`imagehash`, pHash/dHash) to collapse
  near-duplicates; simple frame differencing on downscaled grayscale.
- The M1 decodes H.264 and VP9 in hardware and AV1 only in software. The
  owner will test AV1 decode speed locally; assume the extraction can run
  on either the AV1 or the VP9 stream, whichever is faster.
- Storage target: JPEG at moderate quality, 1080p, with the frame's
  timestamp in milliseconds from video start in the filename or a sidecar
  manifest.

## Questions to answer

1. For slide-based talks specifically, what do practitioners and papers
   recommend: scene-change thresholds for `ffmpeg`'s `scene` score,
   PySceneDetect's content versus adaptive detectors and their parameters,
   or sampling every N seconds plus perceptual-hash deduplication? Compare
   on miss rate (a slide never captured), duplicate rate, and robustness to
   speaker-camera cuts.
2. Handling picture-in-picture and speaker cuts: is it worth detecting the
   slide region and scoring change only inside it, or classifying frames
   as slide versus camera (by OCR text density, edge statistics, or a small
   model) and discarding camera frames? What is the cheapest approach that
   works?
3. Animated builds (a bullet appearing at a time): keep every build state,
   or keep only the final state of each slide? What detection distinguishes
   a build from a new slide?
4. Screen recordings and demos: continuous small changes (cursor, typing)
   produce either no scene cuts or thousands. What sampling policy works
   for these, and how is a screen-recording segment recognized?
5. Compute: expected extraction time per hour of 1080p video on an M1 for
   the recommended pipeline, decoding included, and whether downscaling
   before detection (then extracting the full-resolution frame at the
   chosen timestamps in a second pass) is the standard trick.
6. Output conventions: frame naming with timestamps, a manifest per talk
   (timestamp, hash, scene score, kept or dropped and why), JPEG quality
   versus PNG for later OCR, and whether to keep a downscaled thumbnail
   strip for quick browsing.
7. Whether any existing open-source tool does this end to end for lecture
   or presentation video (lecture-slide extraction is a studied problem in
   education technology) and is worth adopting rather than assembling.

## Out of scope

OCR and text extraction from frames (later project); deck files from
description links (brief 07); video download and format choice (brief 03).

## Deliverable

A recommended extraction pipeline with parameters, the reasoning per
production style, expected per-hour compute and per-talk storage, the
manifest format, and a five-talk local validation plan (which kinds of
talks to pick, what to count, what result would change the parameters).
Dated citations.

## Suggested sources

`ffmpeg` filter documentation (`select`, `scene`, `showinfo`, `mpdecimate`,
`thumbnail`); PySceneDetect documentation and its detector comparisons;
perceptual hashing libraries; papers and tools on lecture video slide
extraction and slide-transition detection (education-technology and
multimedia venues); practitioner write-ups from 2023 to 2026.
