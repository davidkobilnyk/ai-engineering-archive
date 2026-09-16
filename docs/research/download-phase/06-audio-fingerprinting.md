# Research brief 06: Audio fingerprinting to locate talks inside stream recordings

Read `00-shared-context.md` first.

## The question

A later project will segment each conference day's livestream recording
(8 to 10 hours) into talks and reconcile them with the individually posted
talk videos. The intended mechanism is acoustic fingerprinting: fingerprint
every audio file at download time, then find where a 20-minute talk's audio
sits inside the day's stream. Which open tools do this well, how accurate
and fast are they, and what should be computed and stored now so the later
project has what it needs?

## Why it matters

Fingerprints are cheap to compute at download time and awkward to add
later for files already processed. They solve three problems: locating a
cut talk inside a stream (so timestamps can be remapped between the two),
confirming that a re-uploaded or re-edited video is the same recording, and
deduplicating. Text matching could do the first, but fingerprints are
independent of transcription quality.

## What is already known

- The candidates the owner is aware of, to be verified and extended:
  Chromaprint (`fpcalc`, the AcoustID fingerprinter), audfprint, Panako,
  Olaf, dejavu, and the landmark approach (Shazam-style) they implement.
  Chromaprint is designed for whole-track identification, not for locating
  a segment inside a long recording; whether it can be used that way is a
  question.
- The stream audio and the cut talk audio are the same recording, but the
  cut version may be trimmed at both ends, have different encoding
  (YouTube re-encodes), and occasionally have edits (removed sections,
  added intro cards). Audio levels may differ.
- Volume: about 1,135 talks now, hundreds per year; a handful of 10-hour
  streams per event. Fingerprints must be computed on the M1 in the
  background.

## Questions to answer

1. Which open-source fingerprinting tools support **query-in-database
   localization**: given a long reference and a short query, return the
   offset where the query occurs, robust to re-encoding, level changes, and
   trims? Compare Chromaprint, audfprint, Panako, Olaf, and any 2024 to 2026
   entrants, on: license, language and dependencies, maintenance status,
   macOS installation, documented accuracy, speed on CPU, and index storage
   size per hour of audio.
2. For the tools that qualify, what parameters and what query length give
   reliable localization, and what is the false-match behaviour when the
   query is not in the reference (a talk not in that day's stream)?
3. What exactly should be computed and stored **now**, at download time, so
   it does not have to be recomputed: the raw fingerprint data per file in
   the tool's native format, an index, or both? Format and size estimates
   per talk and per 10-hour stream.
4. Can the same fingerprints serve duplicate detection (same recording
   re-uploaded under a new video ID) and detection of re-edits (same talk,
   sections removed)? How would each be recognized from the match pattern?
5. Speed: for the backfill, how long to fingerprint 463 hours of audio on an
   M1 with the recommended tool, and for each event, a few 10-hour streams?
6. Failure modes with conference audio: music beds, applause, MC segments
   repeated across days, two stages with overlapping audio, silence.
7. If no fingerprinting tool is satisfactory, what is the best alternative
   for locating a talk inside a stream: transcript alignment, title-slide
   detection in keyframes, schedule times? Rank them.

## Out of scope

The segmentation project itself; transcription; keyframe extraction (brief
09) except as an alternative in question 7.

## Deliverable

A comparison table of tools; a recommendation for what to compute and store
at download time with the command or library call; expected accuracy,
speed, and storage numbers with sources; and the test the owner should run
on one stream and its cut talks to confirm before relying on it.

## Suggested sources

The projects' repositories and papers (Chromaprint/AcoustID, audfprint by
Dan Ellis, Panako by Joren Six, Olaf, dejavu); the ISMIR literature on
audio fingerprinting; benchmarks comparing landmark-based fingerprinters
on robustness to re-encoding and trimming; any 2024 to 2026 surveys.
