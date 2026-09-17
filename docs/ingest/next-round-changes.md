# Audio backfill: changes for next round

Changes the owner has asked for after reviewing runs. Nothing here is
implemented until the owner approves the round.

Started 2026-09-17, after the first nightly run (2026-09-17 01:00-01:54
local): 37 completed, 4 failed, stopped on HTTP 429 on a caption fetch
for `jVjt-2g8NMY`.

## Requested

### 1. Log more when a 429 happens

**Why:** the first 429 left only the one-line yt-dlp error. It could not
tell us how long YouTube meant the block to last, or whether the limit is
per endpoint (captions) or across all requests.

**What to capture on a challenge outcome:**

- The `Retry-After` response header, if present.
- The response body, or its first part (it may name the limit).
- The request URL's endpoint (e.g. `timedtext` for captions,
  `videoplayback` for media, player API for extraction), without query
  parameters that carry tokens.
- Counts for the run up to the challenge: videos attempted, caption
  fetches, media requests, extraction requests, and elapsed time.
- Any HTTP 403s earlier in the same run, with timestamps and endpoints.

### 2. ASN guard: use the most specific prefix, not the first line

**Why:** Team Cymru's `origin.asn.cymru.com` lookup returns one line per
announced prefix covering the address, in no fixed order.
`guards.asn_of` (`src/aie/ingest/guards.py`) parses only the first line.
Measured 2026-09-17 on Proton server CO#77 (62.93.177.118): one lookup
returned AS3257, a later one AS212238. `dig` showed both lines:

```
"212238 | 62.93.177.0/24 | US | ripencc | 2002-02-21"
"3257 | 62.93.160.0/19 | US | ripencc | 2002-02-21"
```

Routing follows the longest (most specific) prefix, so the address belongs
to AS212238. The guard can therefore report the covering block's ASN.

**Effect today:** fails closed. A wrong answer at home can only cause a
spurious `skipped:asn` (a lost night), never a run through a non-Charter
address, unless the covering block of a non-Charter address happened to be
Charter's. Not yet checked: whether the home address returns more than one
line (`dig +short TXT <reversed home IPv4>.origin.asn.cymru.com`).

**What to change:** parse every line and take the ASN of the longest prefix;
treat unparseable output as unknown (`skipped:asn-unknown`), as now.
