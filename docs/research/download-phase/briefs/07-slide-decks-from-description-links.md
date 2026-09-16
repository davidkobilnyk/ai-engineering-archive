# Brief 07: Slide decks from description links — RETIRED

Retired 2026-09-16 before any research was run. Not for handoff.

## Why

The brief's premise was that talk descriptions often link the speaker's
slide deck, which would be a better source of correctly spelled names than
OCR of video frames. A survey settled it before research was needed:
`data/description-links-2026-09-16.md` tallies 205 talk descriptions
fetched with yt-dlp, stratified by edition and weighted to 2025 and 2026
plus 30 recent placeholder talks. **One of 205 links a deck** (a Google
Slides link on a single World's Fair 2026 talk); one of 180 in the 2025 to
2026 subset; only 8 of 205 mention the word "slides" at all. Descriptions
follow a fixed template: the ai.engineer talk page, the speakers' LinkedIn
and X profiles, sometimes a company site. The build threshold the owner
set (15% of recent talks with a fetchable deck) is missed by an order of
magnitude.

## What survives, and where it lives

- The download job records every URL in a description with fetch time,
  HTTP status, and page title, as part of the metadata snapshot (brief 03,
  question 6). This is nearly free and preserves whatever is there.
- About one talk in five links a GitHub repository (44 links across 205
  talks). A repository's README is a cheap source of correctly spelled
  names and identifiers for the correction stage. This is a note for the
  correction-stage research, not this phase.
- Slides come from keyframes: brief 09.
