# Research brief 07: Fetching speakers' slide decks from video description links

Read `00-shared-context.md` first.

## The question

Talk descriptions on the channel sometimes link to the speaker's slides
(Google Slides, PDF on a personal site, Speaker Deck, Notion, a GitHub
repository) and related resources. A deck as a file is a far better source
of correctly spelled names, code, and URLs than OCR of video frames. At
download time the job should resolve and fetch those links before they rot.
How common are such links on this channel, what hosts are used, and what can
be fetched automatically without an account?

## Why it matters

Names and technical terms are the top accuracy priority, and the deck is
the one place the speaker wrote them down. Links rot, drives get locked,
and repositories move, so the fetch must happen at download time or not at
all. But if only a small fraction of talks link a deck, or most links need
a login, the step is not worth building now. The answer decides that.

## What is already known

- The owner has looked at a few descriptions; the pattern includes links to
  the ai.engineer talk page, speaker social profiles, and sometimes a deck
  or repository. No systematic count has been done. The channel has about
  1,135 talk videos.
- The ai.engineer talk pages themselves (for example
  `https://ai.engineer/talks/<videoId>-<slug>`) show chapters and an article
  form of the talk; whether they link decks is unknown.
- Google Slides decks shared publicly can be exported as PDF through an
  export URL without signing in, as far as the owner knows; whether that is
  still true and rate-limited is a question.

## Questions to answer

1. Survey the channel: across a sample of at least 60 talk descriptions
   spanning 2023 to 2026, what fraction link a deck, and on which hosts?
   Also what other resource types appear (repositories, papers, demo sites,
   blog posts) and how often. Report counts, not impressions. (The
   descriptions are visible on the video pages; `yt-dlp --write-info-json`
   would also expose them but you cannot run it.)
2. For each host seen: can the deck be fetched by a script without an
   account, in what format (PDF, PPTX, HTML), with what URL transformation
   (for Google Slides, the export-to-PDF endpoint; for Speaker Deck, the
   download link; for Notion, the public page export), and are there rate
   limits or bot checks?
3. Beyond descriptions: does the ai.engineer talk page, the event schedule
   page, or the speaker's ai.engineer profile link decks? Does the channel
   pin a comment with resources?
4. Speakers often post decks elsewhere (personal sites, LinkedIn, social
   posts). Is searching for those automatically worth it, or out of scope?
   Give a view with reasons.
5. Text extraction: for the fetched formats, which tools extract text with
   layout and code blocks intact (PDF text layer, PPTX XML), and what fails
   (image-only PDFs, which would need OCR anyway).
6. What to store: the original file, the resolved URL, fetch time, hash,
   and extracted text, keyed by video ID. Note anything about respecting
   the deck's licence or the host's terms that the owner should know for a
   private archive.

## Out of scope

Keyframe OCR (brief 09 covers extraction; slide OCR is a later project);
transcription; anything requiring the owner to log in to a service.

## Deliverable

The survey table (host, count, fetchable without account yes/no, method);
a recommendation on whether to build the deck-fetch step now, and if so the
per-host fetch method; the text-extraction tool choice; and open questions
with the cheapest way to settle them.

## Suggested sources

The channel's video pages (descriptions and pinned comments); ai.engineer
talk pages; Google Slides, Speaker Deck, Notion, and GitHub documentation on
public export and download endpoints; PDF and PPTX text-extraction tool
documentation (for example `pdftotext`, `pdfplumber`, `python-pptx`).
