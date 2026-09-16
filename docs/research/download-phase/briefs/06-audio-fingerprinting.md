# Research brief 06: Audio fingerprinting to locate talks inside stream recordings

Read `00-shared-context.md` first.

## The question

A later project will segment each conference day's livestream recording
(8 to 10 hours) into talks and reconcile them with the individually posted
talk videos. The intended mechanism is acoustic fingerprinting. Which open
tools do this well enough, how should the test be run, and is there
anything worth computing at download time given that the unprocessed audio
is kept for every file?

## Defaults the owner already accepts

- **Direction:** index the talk corpus as the database (the canonical use
  for the landmark-style tools; it gives duplicate detection for free) and
  query with sliding windows of the stream recording. Note any tool where
  the inverse also works.
- **Numeric targets:** offset accuracy within ±0.5 s (citations are whole
  seconds); zero talk-level false positives on a test of about 10 talks,
  with a reported confidence score the later project can threshold; recall
  of at least 95% of the talks present.
- **Hard requirement:** the tool returns a **time mapping** (multiple offset
  clusters with match density), not one best offset, because cut talks can
  have removed sections and added intros.
- **Compute-now is optional.** The unprocessed audio is retained, so
  fingerprints can be recomputed later as a background job. The
  deliverable is (a) tool choice plus test, (b) an optional cheap
  compute-now with the chosen tool, schema-versioned and explicitly
  discardable.
- **Environment:** Java or C via Homebrew acceptable, Python preferred; the
  index must run under about 2 GB resident on the 8 GB machine; size for
  2,000 hours of references.

## What is already known

- Candidates the owner is aware of, to be verified and extended:
  Chromaprint (`fpcalc`, the AcoustID fingerprinter, designed for
  whole-track identification), audfprint, Panako, Olaf, dejavu, and the
  landmark approach they implement.
- The stream audio and the cut talk audio are the same recording, but the
  cut version may be trimmed at both ends, re-encoded by YouTube, and
  occasionally edited (removed sections, added intro cards); levels may
  differ.
- Volume: about 1,135 talks now, hundreds per year; two or three 8 to
  10-hour recordings per event.
- **Ground truth exists without manual work.** Several past recordings
  carry YouTube chapters with talk titles and speakers at second
  resolution: Code 2025 Day 2 (`xmbSQz-PNMM`, 9.0 h, 26 chapters, e.g.
  "0:23:41 Stop Building Agents — Barry Zhang & Mahesh Murag") and Europe
  2026 Day 1 (`O_IMsEg91g8`, 9.2 h, 23 chapters), both with their talks in
  the corpus (Code 2025: 67 talks; Europe 2026: 187). Paris 2025 Day 2 has
  no chapters and its talks are not in the corpus under a Paris 2025
  event, so it is a poor ground-truth choice despite being the most
  comparable event. See `data/streams-tab-2026-09-16.json`.
- Both the stream and each talk have a timestamped automatic caption track
  already downloaded, so caption-text alignment is a free, independent
  second method.

## Questions to answer

1. Which open-source fingerprinting tools support **query-in-database
   localization** returning a time mapping robust to re-encoding, level
   changes, and trims? Compare Chromaprint, audfprint, Panako, Olaf, and
   any 2024 to 2026 entrants on: license, language and dependencies,
   maintenance status, macOS installation, documented accuracy, CPU speed,
   index storage and resident memory per hour of reference audio, and
   whether they return multiple offset clusters with density.
2. For the tools that qualify, what parameters and what query window
   length meet the targets, and what is the false-match behaviour when the
   query is not in the reference (a talk not in that day's stream)?
3. Whether any stored intermediate is tool-agnostic enough to be worth
   computing at download time (likely none), and if so its format and
   size per talk and per recording.
4. Duplicate detection and re-edit detection from the same index: how each
   is recognized from the match pattern.
5. Speed: time to index 463 hours of talks on an M1, and to query a 10-hour
   recording against that index.
6. Failure modes with conference audio: music beds, applause, MC segments
   repeated across days, silence, and two talks with the same intro
   jingle.
7. Rank the alternatives (caption-track text alignment, title-slide
   detection in keyframes, schedule times) and say which should run
   **alongside** fingerprinting as a consistency check, not as a fallback.
   Caption alignment is free and independent; say how it would be scored
   against the same targets.

## Out of scope

The segmentation project itself; transcription; keyframe extraction (brief
09) except as a cross-check in question 7.

## Deliverable

A comparison table of tools against the hard requirement and targets; a
recommendation; the confirmation test using a chaptered recording and its
talks, with the chapters as ground truth and three talk starts
cross-checked by caption alignment; expected accuracy, speed, and memory
numbers with sources; and the compute-now decision.

## Suggested sources

The projects' repositories and papers (Chromaprint/AcoustID, audfprint by
Dan Ellis, Panako by Joren Six, Olaf, dejavu); the ISMIR literature on
audio fingerprinting and on query-by-example localization; benchmarks of
landmark-based fingerprinters on robustness to re-encoding and trimming;
any 2024 to 2026 surveys.
