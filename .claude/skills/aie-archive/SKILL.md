---
name: aie-archive
description: Answer questions about AI engineering practice, tools, models, and vendors from the local archive of AI Engineer conference transcripts. Use for any question where conference speakers would have opinions or experience to share.
---

# AIE archive

A local, full-text-searchable copy of every AI Engineer conference transcript,
queried through the `aie` CLI (run it as `.venv/bin/aie` from the repo root,
or `aie` if the venv is active).

## Before answering

Run `aie status`. If it says "not synced" or "not indexed", stop and tell the
user to run `aie sync` (about 36 minutes the first time) and then `aie index`.
Do not answer from anything but the archive.

## How to search

The query language is SQLite FTS5: bare words are ANDed, `"quoted phrases"`
match exactly, `OR` works, `NEAR(a b, 10)` finds words close together, and
`term*` matches prefixes. Words are stemmed, so `prompting` finds `prompt`.
Hyphenated words must be quoted: `"auto-compaction"`.

1. Write two or three phrasings of the question in the words a speaker would
   use, not the user's words. Cover the product name, the generic term, and a
   concrete symptom. Example for "pitfalls of Claude research mode":
   `aie search '"research mode" OR "deep research"'`,
   `aie search 'research agent pitfalls OR mistakes OR failure'`,
   `aie search 'claude research citations wrong OR hallucinated'`.
2. Run at least three distinct searches before concluding the archive has
   nothing. Use `--after YYYY-MM-DD` to prefer recent editions on fast-moving
   questions such as model comparisons, and `--speaker`, `--topic`, `--event`,
   `--talk` to narrow. `aie talks --topic <slug>` lists what exists.
3. Use `--json` when you need to process many hits; the plain output is for
   reading a few.

## Before quoting

A hit is one transcript segment and often cuts mid-thought. For every hit you
intend to use, run `aie show <slug> --from MM:SS --to MM:SS` with a window of
two to three minutes around the hit's timestamp, and read it before quoting.

## How to answer

- Group findings by claim, not by talk.
- Attribute every claim to the speaker and talk, with the timestamped YouTube
  link from the hit (`https://www.youtube.com/watch?v=...&t=...`).
- Say whether the speaker asserted something or demonstrated it.
- Note the edition date; a 2026 talk outweighs a 2023 talk on anything that
  changes fast.
- Automated transcripts contain errors. Quote short passages and say when a
  word is likely a transcription mistake.

## Never

- Never quote the `summary` field or a metadata hit as if it were something
  the speaker said. Metadata hits (`[metadata]`) only tell you which talk to
  open.
- Never answer from general knowledge, web search, or any source other than
  this archive. When the archive has nothing, say exactly that and list the
  queries you tried.
