# Research brief 09: Extracting slide keyframes from talk videos

Read `00-shared-context.md` first.

## The question

At download time the job extracts still frames from each talk video at the
moments the picture changes, so that slides are preserved as images keyed
by timestamp. The frames are kept forever; text extraction from them is a
later project. Given the measurements below, what detection and
deduplication method produces one clean frame per slide on this channel's
production styles, within the budgets, and how is it validated?

## Defaults the owner already accepts

- **A missed slide is roughly 10x worse than a duplicate.** Target under 2%
  misses on slide-based talks; up to 2 to 3x duplicates is acceptable since
  deduplication can run later.
- **Input is the kept AV1 file, software-decoded.** Hardware decode via
  VideoToolbox is not used (measured 3 to 4x real time for a decode-to-CPU
  workload versus 14 to 17x in software). No second stream is fetched.
- **Compute budget:** the backfill may take up to 4 weeks, running only
  when the laptop is on mains and idle; steady state must clear a 30-talk
  day in under 6 hours; peak resident memory under 2 GB so the laptop stays
  usable. Measured extraction speed makes the backfill about 30 hours of
  CPU and a 30-talk day about one hour, so the budget is loose.
- **Livestream day recordings are excluded** from this brief; they belong
  to the segmentation project.
- **Camera-only talks and panels:** a sparse sample, one frame per 5
  minutes, so the artifact is never empty; the same for camera-only talks
  with slides in the background. Hard cap 400 frames or 150 MB per talk;
  say how sampling degrades gracefully at the cap.
- **Anomalies:** a talk yielding 0 or more than 1,500 detections
  auto-falls back to one frame per 30 seconds and appends a line to a
  weekly review list; never blocks.
- **Timing:** record both detection time and capture time; capture at
  detection plus 500 ms to avoid mid-transition frames; the citation uses
  detection time.
- Storage: JPEG at moderate quality, 1080p, timestamp in milliseconds from
  video start in the filename, plus a manifest per talk.

## What is already known (measured 2026-09-16 on one 21-minute slide talk, 1080p60 AV1, M1 8 GB)

- ffmpeg's `select='gt(scene,T)'` at T=0.3 produced 7 frames, all
  full-frame image swaps in a screenshot-heavy section; every text-slide
  advance in the first 12 minutes was missed.
- At T=0.06 it produced 40 frames in the same 71 seconds. Twelve were
  same-second pairs at slide transitions (crossfade artifacts). Collapsing
  detections within 2 seconds leaves 28 distinct moments spaced 20 to 90
  seconds apart, consistent with a deck. One 2.5-minute gap (3:55 to 6:29)
  may be a missed low-contrast change.
- Full-pass extraction cost was 71 seconds for 1237 seconds of video (17x
  real time) at either threshold; bare decode 87 seconds (14x). Most talks
  are 30 fps and will run faster.
- The channel's production styles: full-screen slides with a small speaker
  inset; alternating cuts between speaker and slides; direct screen
  capture (demos, code); camera-only shots with slides in the background;
  panels are camera-only.
- Slide-deck files are not available as ground truth: a survey found one
  deck link in 205 descriptions (brief 07, retired).
- Tools the owner is aware of: ffmpeg `scene` and `showinfo`;
  PySceneDetect (content and adaptive detectors); perceptual hashing
  (`imagehash`, pHash/dHash); frame differencing on downscaled grayscale.

## Questions to answer

1. Threshold and detector choice for slide decks, given the trade-off
   above: is ffmpeg's `scene` score at about 0.06 the right primary
   detector, or do PySceneDetect's content or adaptive detectors handle
   the low-contrast text-slide case (the 3:55 to 6:29 gap) better? What do
   practitioners and papers on lecture-slide extraction recommend?
2. **Deduplication**, now the main open problem: collapsing crossfade pairs
   (within 2 seconds) and near-duplicates from bullet builds and speaker
   inset motion by perceptual hash. Which hash, what distance threshold,
   and how to keep the final build state of a slide while dropping
   intermediate states without losing a genuinely new slide.
3. Handling speaker cuts and picture-in-picture: is it worth scoring change
   only inside a detected slide region, or classifying frames as slide
   versus camera (text density, edge statistics, a small model) and
   discarding camera frames? Cheapest approach that works.
4. Screen recordings and demos: continuous small changes produce either no
   scene cuts or thousands. What sampling policy works, how a
   screen-recording segment is recognized, and how the 400-frame cap
   degrades gracefully.
5. Memory: does the recommended pipeline stay under 2 GB resident on 1080p
   input, and is downscale-before-detection needed for memory rather than
   speed?
6. Output conventions: frame naming, the per-talk manifest (detection
   time, capture time, hash, scene score, kept or dropped and why), JPEG
   quality for later OCR, and whether to keep a thumbnail strip.
7. Whether any existing open-source tool does lecture-slide extraction end
   to end well enough to adopt rather than assemble.

## Out of scope

OCR and text extraction from frames (later project); decoding strategy
(settled); stream recordings (segmentation project); video download and
format choice (brief 03).

## Deliverable

A recommended detection-plus-deduplication pipeline with parameters, the
reasoning per production style, expected per-hour compute and memory, the
manifest format, and a five-talk validation plan: which kinds of talks to
pick, how the owner hand-labels true slide counts in under 20 minutes per
talk, what to count, and what result would change the parameters. Dated
citations.

## Suggested sources

`ffmpeg` filter documentation (`select`, `scene`, `showinfo`,
`mpdecimate`, `thumbnail`); PySceneDetect documentation and detector
comparisons; perceptual hashing libraries and their threshold guidance;
papers and tools on lecture video slide extraction and slide-transition
detection (education-technology and multimedia venues); practitioner
write-ups from 2023 to 2026.
