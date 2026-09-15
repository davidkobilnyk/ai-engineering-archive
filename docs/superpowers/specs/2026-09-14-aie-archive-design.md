# AI Engineer Transcript Archive: Design

Date: 2026-09-14
Status: approved in brainstorming, awaiting written review

## 1. Purpose

A local, searchable archive of the AI Engineer conference transcripts published
at https://ai.engineer/data, used by Claude Code to answer questions such as
"what are the pitfalls of Claude research mode" or "how do I get Claude to
search exhaustively before giving up", with citations into the talks.

The motivating problem: the remote search at ai.engineer/mcp is keyword search
over metadata plus transcript passages, rate limited, and has returned empty
results for information that is present in the transcript text. The archive
holds the full text of every transcript locally so that a search never comes
back empty when the answer is in a talk.

Scope of this version:

- Full-text search only (SQLite FTS5, BM25). No embeddings, no vector index.
- Claude Code is the consumer. The project does no LLM calls of its own.
- A CLI plus a Claude Code skill. No MCP server.

Deliberately excluded for now: semantic search, an MCP wrapper, an `ask`
command that calls an LLM, incremental per-talk sync, scheduling, and
speaker biographies or organization rows as searchable text.

## 2. Data source

Public bulk endpoints, no sign-in, JSON:

| Collection | URL |
|---|---|
| Status | `https://ai.engineer/api/data/status` |
| Talks | `https://ai.engineer/api/data/talks?format=json` |
| Speakers | `https://ai.engineer/api/data/speakers?format=json` |
| Topics | `https://ai.engineer/api/data/topics?format=json` |
| Organizations | `https://ai.engineer/api/data/organizations?format=json` |
| Chapters | `https://ai.engineer/api/data/chapters?format=json` |
| Transcripts index | `https://ai.engineer/api/data/transcripts?format=json` |
| One transcript | `https://ai.engineer/api/data/transcript?slug=<slug>&format=json` |

As of the 2026-09-03 corpus: 1,087 talks, all with transcripts, 170,944
segments, roughly 14.5M tokens of transcript text.

Record shapes that matter:

- Talk: `slug, title, url, videoId, event, durationMs, speakers[{name}],
  topics[{slug,name}], summary`. No date field.
- Transcript file: a bare JSON array of `{startMs, text}`. No end times, no
  speaker labels.
- Chapter: `talkSlug, title, startMs, endMs`.
- Status: includes `corpusVersion` and counts.

The `event` field is inconsistent. Some values are display names
("AI Engineer World's Fair 2025"), others are slugs ("worldsfair-2024",
"worldsfair-2026-online-track"). The index normalizes them (section 4).

Per-talk dates are not published anywhere on the site. Conference editions
have date ranges, which the archive uses as the best available resolution.

The published rate limit (60 requests per minute per IP) applies to the MCP
endpoint. Nothing is published for the bulk endpoints, so sync is
conservative (section 5).

## 3. Repository layout

```
pyproject.toml                       uv-managed; package "aie"; console script "aie"
src/aie/
  sync.py                            HTTP -> data/raw
  index.py                           data/raw -> data/aie.db
  search.py                          queries against data/aie.db
  cli.py                             argparse entry point
  editions.json                      hand-maintained conference edition dates
tests/
  fixtures/                          real API responses trimmed to three talks
  test_cli.py                        seam tests
data/                                gitignored
  raw/
    talks.json speakers.json topics.json organizations.json
    chapters.json transcripts.json
    transcripts/<slug>.json
    version.json
  aie.db
.claude/skills/aie-archive/SKILL.md
docs/superpowers/specs/              this document
```

Stack: Python 3.12, `uv`, `httpx`, standard-library `sqlite3` and `argparse`,
`pytest`.

## 4. Data model

SQLite database `data/aie.db`.

```
editions(series, year, title, start_date, end_date, location)
  Seeded from src/aie/editions.json at index time. One row per conference
  edition, e.g. ("worldsfair", 2025, "AI Engineer World's Fair 2025",
  "2025-06-03", "2025-06-05", "San Francisco").

talks(slug PK, title, event_raw, series, year, start_date, end_date,
      url, video_id, duration_ms, summary, speakers_json, topics_json)
  event_raw is the string from the talks collection. series and year come
  from normalizing event_raw; start_date and end_date are copied from the
  matching edition. Talks whose event_raw cannot be resolved keep NULL
  series, year, and dates, and are listed by `aie index`.

chapters(talk_slug, title, start_ms, end_ms)

segments(id PK, talk_slug, seq, start_ms, end_ms, text)
  One row per transcript segment. end_ms is the next segment's start_ms, or
  the talk's duration_ms for the last segment.

segments_fts    FTS5 virtual table over segments.text, porter tokenizer.
talk_docs_fts   FTS5 virtual table over talks.title and talks.summary.

meta(key, value)
  corpus_version, indexed_at, raw_counts.
```

Event normalization: lowercase, strip the "ai engineer" prefix, collapse
punctuation and whitespace, map known aliases ("world's fair" and
"worldsfair" to `worldsfair`, "summit", "code", "paris", "europe", "miami",
"singapore", "nyc", "shanghai"), extract the four-digit year, and ignore
trailing qualifiers such as "online track". The result is looked up in
`editions`.

Ranking: BM25 from `segments_fts`. Hits from `talk_docs_fts` are merged in,
marked `kind = "metadata"`, and reported at `start_ms = 0`. Adjacent matching
segments from the same talk are collapsed into one hit, so N results are N
distinct places.

## 5. Sync behavior

`aie sync` downloads the corpus into `data/raw`.

1. Fetch the status endpoint. If its `corpusVersion` equals the one in
   `data/raw/version.json` and `--force` is absent, print "up to date" and
   exit 0.
2. Fetch the six collections, then every transcript listed in the
   transcripts index.
3. Write `version.json` last, only after every file succeeded.

Rules:

- One request at a time, with a fixed pause between requests. Default 2
  seconds, set by `--delay`. A full download takes about 36 minutes.
- Each file is written to `<name>.tmp` and renamed into place on completion,
  so an interrupted run never leaves a truncated file.
- Resume: a transcript whose final file exists is skipped. `--force`
  re-downloads everything.
- Retries: on HTTP 429, 529, any 5xx, or a connection error, wait 10 s, then
  20 s, then 40 s. After the third failure the file is marked failed and sync
  moves on.
- Circuit breaker: three consecutive failed files abort the run. Sync prints
  the failed slugs and the last error, and exits 1. A success resets the
  counter.
- Any failed file, even without an abort, means `version.json` is not
  written and the exit code is 1. The next run without `--force` finishes
  the job.
- A descriptive `User-Agent` header identifies the project.

Edition dates are not available from a bulk endpoint. They ship as
`src/aie/editions.json`, maintained by hand, one entry per edition with
`series, year, title, start_date, end_date, location`. Seeded from the
registry as of 2026-09-14:

| Edition | Dates | Location |
|---|---|---|
| summit 2023 | 2023-10-08 to 2023-10-10 | San Francisco |
| worldsfair 2024 | 2024-06-25 to 2024-06-27 | San Francisco |
| summit 2025 | 2025-02-19 to 2025-02-22 | New York |
| worldsfair 2025 | 2025-06-03 to 2025-06-05 | San Francisco |
| paris 2025 | 2025-09-23 to 2025-09-24 | Paris |
| code 2025 | 2025-11-19 to 2025-11-22 | New York |
| europe 2026 | 2026-04-08 to 2026-04-10 | London |
| miami 2026 | 2026-04-20 to 2026-04-21 | Miami |
| singapore 2026 | 2026-05-15 to 2026-05-17 | Singapore |
| worldsfair 2026 | 2026-06-29 to 2026-07-02 | San Francisco |

## 6. Index behavior

`aie index` rebuilds `data/aie.db` from `data/raw`.

- Builds into `data/aie.db.tmp`, then renames over `data/aie.db` after a
  sanity check that the talk count matches the raw talks file. On failure or
  interrupt the temp file is deleted and the previous database is untouched.
- A transcript file that fails to parse is skipped and named in the summary;
  the build continues.
- Prints counts of talks, segments, chapters, and editions, the list of
  unresolved `event_raw` values, and the list of skipped files.
- Exit 1 if `data/raw` is missing or has no talks file.

## 7. CLI contract

Every command accepts `--data-dir PATH`, defaulting to `$AIE_DATA_DIR` if
set, else `./data`.

### `aie sync [--force] [--delay SECONDS]`

As in section 5. Prints progress and a summary line: fetched, skipped,
failed, corpus version.

### `aie index`

As in section 6.

### `aie search QUERY [filters] [--limit N] [--json]`

Filters: `--event`, `--speaker`, `--topic`, `--talk`, `--after DATE`,
`--before DATE`. Dates are ISO `YYYY-MM-DD` and compare against the talk's
edition `start_date`, inclusive at both ends. Talks with no resolved edition
are excluded whenever a date filter is given. `--event` matches the normalized series or the edition
title, case-insensitively. `--speaker` and `--topic` match name or slug,
case-insensitively. `--talk` restricts to one slug.

QUERY is FTS5 match syntax: bare words are ANDed, quoted phrases, `OR`,
`NEAR(...)`, and prefix `*` all work.

Default limit 10, maximum 50.

Plain-text output, one block per hit:

```
1. Harness Engineering — Sam Smith · AI Engineer Code 2025 (Nov 19-22, 2025)
   slug: harness-engineering
   [12:34] https://www.youtube.com/watch?v=abc123&t=754
   ...we found that the model would give up after two searches unless the
   harness explicitly told it how many it was expected to run...
```

Metadata hits show `[metadata]` in place of the timestamp and the talk URL
without `&t=`.

`--json` emits an array of objects: `talk_slug, title, speakers, event,
start_date, end_date, start_ms, end_ms, url, text, kind, score`.

Zero hits prints `No results` and exits 0.

### `aie show TALK_SLUG [--from MM:SS] [--to MM:SS] [--json]`

Prints the talk header (title, speakers, edition and dates, YouTube URL,
duration), the chapter list, and the transcript for the range as
`[MM:SS] text` lines. Times are `MM:SS` with minutes allowed to exceed 59,
so 1h05m is `65:00`. With no range, the whole transcript. Unknown slug
exits 1. A range with `--from` after `--to` is a usage error, exit 2.

`--json` emits `{talk: {...}, chapters: [...], segments: [...]}`.

### `aie talks [filters] [--json]`

Same filters as `search`, no query. One line per talk: slug, title,
speakers, edition, dates.

### `aie status`

Prints local corpus version, index build time, and counts. Reports
"not synced" or "not indexed" when the respective artifacts are missing.

## 8. Claude Code skill

`.claude/skills/aie-archive/SKILL.md` tells Claude:

- When to use: any question about AI engineering practice, tools, models, or
  vendors where conference talks would have opinions. Run `aie status`
  first; if the archive is missing or stale, tell the user to run `aie sync`
  then `aie index`.
- How to search: start with two or three phrasings, using vocabulary the
  speakers would use rather than the user's; try the product name, the
  generic term, and a concrete symptom; use `OR` and quoted phrases. Run at
  least three distinct searches before concluding something is not covered,
  and report which queries were tried when saying so.
- How to go deep: for every promising hit, run `aie show` with a two to three
  minute window around the timestamp before quoting, because a single
  segment often cuts mid-thought.
- How to answer: group findings by claim; attribute each to speaker and talk;
  include the timestamped YouTube link; distinguish what a speaker asserted
  from what they demonstrated; note the edition date so newer talks outweigh
  older ones on fast-moving questions such as model comparisons.
- What not to do: never quote the summary field as if it were a transcript
  line. Never answer from general knowledge. The skill answers only from what
  is in the archive: no general knowledge, no web search, no other materials.
  When the archive has nothing, say so and list the queries tried.

The skill is prose, not code, and is the place to tune when a question
misses.

## 9. Error handling

- Missing data: `search`, `show`, `talks` with no database print one line
  pointing at `aie sync` then `aie index`, exit 1. `index` with no raw files
  points at `aie sync`, exit 1.
- Bad query syntax: FTS5 errors are caught and reported as
  `invalid query syntax: <FTS5 message>`, exit 2. No auto-correction.
- Unknown filter values: zero results, exit 0, with a hint listing the
  nearest matches by substring.
- Malformed raw files: skipped during `index`, named in the summary.
- Interrupts: Ctrl-C during `sync` or `index` leaves no partial files.

Exit codes: 0 success or empty result; 1 missing data or failed operation;
2 usage or query error.

## 10. Testing

All tests run the `aie` command in a subprocess against a temporary data
directory. No test targets internal functions.

Seams under test:

1. `aie sync` against a local fake of the site: an in-test HTTP server
   serving `tests/fixtures/` under the real URL paths. Fixtures are real
   responses captured once and trimmed to three talks. The fake can be
   scripted to return 429s, 5xxs, and truncated bodies, covering retries,
   the circuit breaker, resume, and version-written-last.
2. `aie index` from fixture raw files, checked through `aie status` counts
   and through `aie search` against the result.
3. `aie search`, `aie show`, `aie talks` against an index built from the
   fixtures. Expected values are literals copied by hand from the fixture
   files (a phrase, a slug, a `startMs`, a URL), never computed by the code
   under test.
4. Exit codes and messages for every case in section 9.

Tracer bullet: the first test runs `sync` against the fake server, then
`index`, then `search` for a phrase present in exactly one fixture
transcript, and asserts the expected slug and timestamp. It fails until all
three modules exist in minimal form.

One live test, skipped unless `AIE_LIVE_TESTS=1`, fetches the real status
endpoint and one real transcript to catch upstream format changes.

Not asserted: BM25 ordering beyond "the expected hit is present".

Implementation follows RED then GREEN for every task, per CLAUDE.md.
