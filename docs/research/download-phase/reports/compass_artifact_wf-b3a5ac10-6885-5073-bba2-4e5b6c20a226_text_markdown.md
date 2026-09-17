# Research brief 01: Operating envelope for yt-dlp on a residential connection

*Prepared 2026-09-16. All flags verified against the yt-dlp README at/after release 2026.08.19; all challenge/rate figures dated and typed by source (official documentation / measured / vendor claim / community report). Where a fact can only be settled on the owner's machine, the exact local test is given.*

## TL;DR
- A single Charter Spectrum residential line running yt-dlp 2026.08.19 can safely fetch on the order of **150–250 videos per nightly window** unattended — far below the maintainer-documented guest-session ceiling of "~300 videos/hour (~1000 webpage/player requests per hour)" (yt-dlp Extractors wiki, edited 2025-06-11). The binding constraint is request **rate**, not bandwidth, so `--sleep-requests` and `--sleep-interval` matter more than `--limit-rate`.
- Force IPv4 (`-4`); pace with `--sleep-requests 3 --sleep-interval 10 --max-sleep-interval 30 --sleep-subtitles 5`; keep `--concurrent-fragments 1`; disable extractor retries; and let the **wrapper** (not yt-dlp) detect a "Sign in to confirm you're not a bot" / HTTP 429 / reCAPTCHA challenge, stop the run, back off 24 hours, and alert after two consecutive. This satisfies the zero-household-tolerance rule and the 4-day freshness goal with wide margin.
- The 240 GB backfill is ~10 hours of pure transfer but should be spread over **~12 conservative nights** (audio first, ~6 nights; video, ~6 nights), never during event weeks or the week after. A 300-talk burst is only ~2 hours of transfer and fits inside one nightly window plus the event-week midday pass, so bursts always pre-empt backfill and still land inside 4 days.

## Key Findings

1. **The only maintainer-stated number is the guest-session rate limit.** The yt-dlp Extractors wiki (page last edited by maintainer *bashonly*, 11 Jun 2025) states verbatim: "With the default yt-dlp settings, the rate limit for guest sessions is ~300 videos/hour (~1000 webpage/player requests per hour). For accounts, it is ~2000 videos/hour (~4000 webpage/player requests per hour)," and "It is recommended to add a delay of around 5-10 seconds between downloads with `-t sleep` or with the sleep options." This is the single most authoritative pacing figure; every number below is calibrated well beneath it.

2. **Requests, not bytes, trip the wall.** The yt-dlp.net 429 guide (2026) states "the requests that matter are the metadata ones, not the downloads … A 200-video playlist makes several hundred of those before the first byte of video is transferred. That is why `--limit-rate` alone never fixes a 429," and calls `--sleep-requests` "the flag that addresses it, and it is the one most often left out."

3. **Extraction runs once per video per invocation (verified).** yt-dlp 2026.08.19 verbose logs (GitHub issue #17538, 2026; corroborated by #6274 and #9371) show a single call requesting video + audio + subtitles + metadata issues ONE extraction pass (`Downloading webpage` → `Downloading visionos player API JSON` → `Downloading m3u8 information`), then reuses it for every artifact. Adding `--write-subs`/`--write-info-json` does not re-run extraction per artifact — it only adds artifact-specific transfers.

4. **The default player-client set changed inside the 90-day window.** Release 2026.08.19 removed `android_vr` from defaults (#17461), added the `visionos` client (#17184), and added `web_embedded` fallbacks (#17462). The README default is now `visionos,web` (it was `tv,android_sdkless,web` earlier in 2026). This matches the owner's observation that yt-dlp "selected the visionos player client on its own." Because defaults shift monthly, the recommendation is to **not hard-code a client** and re-verify after each update.

5. **IPv6 is scored by /64 block; force IPv4.** YouTube scores an entire IPv6 /64 as one unit (Tunelio extraction-fleet measurement, Aug 2026; corroborated by the podsync maintainer's 2020 finding that a shared DigitalOcean /64 gets "combined rate limits … The remedy here is to force IPv4"). On a residential line the safe, predictable choice is `-4`.

---

## Details — answers to the brief's questions

### Q1. Safe request rate and daily volume from one residential address (2026)

There is **no officially published number from YouTube**; the closest to authoritative is the yt-dlp maintainer's wiki figure. Sources are typed below.

**(a) Media downloads.** *Maintainer guidance (official-ish):* the Extractors wiki guest ceiling of "~300 videos/hour (~1000 webpage/player requests per hour)," with "a delay of around 5-10 seconds between downloads." *Community operator report:* the DEV Community write-up "yt-dlp: The CLI Video Downloader Developers Actually Use in 2026" (pickuma, 2026) recommends for unattended jobs "`--limit-rate 5M --sleep-interval 5 --max-sleep-interval 15` … Slower than you'd like, but it survives the night without a 429 storm," and warns "`--concurrent-fragments 16` from a single IP will get you throttled or temporarily blocked." **Conservative default for this pipeline: cap at 150–250 videos per nightly window** (≈25–42/hour over 6 hours) — one-sixth to one-twelfth of the guest ceiling, leaving large headroom for the household.

**(b) Caption fetches.** The caption (timedtext) endpoint is rate-limited separately and more tightly. The independently-maintained "youtube-transcript-ip-blocked-guide" (hxckya, last checked 2026-09-13) records: "There are no official numbers. The maintainer says limits are undocumented and reports vary … In July 2025 he noted that YouTube had tightened limits on the caption endpoint (#467)." Reported thresholds range from ~50 to a few thousand requests before a block, depending on IP reputation; a user in April 2026 "reported getting 10 to 20 videos through a VPN before the next block." Notably, that guide confirms it "fetched transcripts without any proxy from such a [consumer ISP] connection on 2026-09-13" — i.e., a clean residential IP handles caption fetches that cloud IPs cannot. Because captions drift and the archive re-fetches them, treat caption fetches as first-class requests, pace them with `--sleep-subtitles`, and never fetch captions in a tight loop separate from the main pass. Tens of caption fetches per night on this line is well within tolerance; hundreds in a burst is the zone to watch.

**(c) Metadata-only queries (`-J`, `--flat-playlist`).** Cheap, but they still count as extraction requests. Derived from the stated cadence:
- **Hourly feed poll:** 24/day. This is a plain RSS GET to `feeds/videos.xml` — *not* a yt-dlp call and not the internal player API, so it does not consume the guest download budget; it is the same endpoint any RSS reader hits.
- **Daily uploads-playlist listing** (`--flat-playlist`): 1/day, ≈1–2 requests.
- **One metadata probe per new video** (`-J`): trickle days ≈1–4; burst upload days up to ~30 (the channel posted four in ninety minutes on 2026-09-16 and posts 5–30/day after an event). Each `-J` probe ≈3–5 requests.
- **Peak metadata load:** ~1 listing + ~30 probes ≈ 31 extractions ≈ 100–150 internal requests/day — trivial versus the ~1,000/hour ceiling.

### Q2. Recommended pacing values; which lever matters most

**Inter-request sleep is the more important lever.** `--limit-rate` shapes bandwidth (courtesy + household protection) but does nothing about the extraction burst that trips 429/bot-wall. All values below are verified present in the README at this version and unchanged in name/behaviour across the Jun–Sep 2026 releases:

| Flag | Value | Why |
|---|---|---|
| `--sleep-requests` | `3` | Seconds between extraction requests; the primary anti-429 lever. Community 429 guides use 1–2; 3 is conservative for unattended overnight. |
| `--sleep-interval` / `--max-sleep-interval` | `10` / `30` | Random pause before each download; jitter defeats the "exact-gap machine signature." Wiki recommends 5–10 s; 10–30 is conservative and randomised. |
| `--sleep-subtitles` | `5` | Seconds before each subtitle download; caption endpoint is tightly limited (Q1b). |
| `--limit-rate` | `4M` | Below the ~6.5 MB/s sustained DASH rate, leaving headroom on the 340 Mbps line; a courtesy/self-preservation cap, not the main defence. |
| `--concurrent-fragments` | `1` | Parallel fragments are a throttling/bot signal; keep single-threaded (the observed ~10 MB chunk stalls are tolerable). |

### Q3. Does one invocation fetching several artifacts count as one contact or several?

**Partly knowable, and verified.** yt-dlp 2026.08.19 verbose logs (GitHub issue #17538, 2026; corroborated by #6274 and #9371) show a **single extraction pass per video per invocation** — one `Downloading webpage`, one `Downloading visionos player API JSON`, one `Downloading m3u8 information` — after which the subtitle (timedtext) and media (`videoplayback`) transfers reuse that extraction. So fetching video + both audio streams + captions + `-J` metadata in one call is **one extraction "contact"** plus a handful of media/caption transfers, not N separate extractions. (The `videoplayback` URL literally carries `c=VISIONOS`, confirming the client.)

**What remains unknowable from public sources** is exactly how YouTube's server-side scoring weights those media/caption transfers relative to the extraction. **Conservative default: treat each fully-processed video as ~1 "video" against the ~300/hour guest budget and ~5 internal requests, and always fetch all artifacts for one video in ONE `yt-dlp` invocation** (fewer requests and simpler). The internal-counting part is anecdotal — stated plainly.

**Calibration test (local; the owner must run it — I cannot reach the machine):**
- Command shape: `yt-dlp -v -J --write-subs --write-auto-subs --sub-langs en --write-info-json --skip-download "<one video URL>"`; count the `[youtube] Downloading …` lines. Repeat with a full media fetch.
- Inputs: 5 known channel video IDs.
- Measure: extraction requests per video (expect ~3–5) and whether adding artifacts increases extraction requests (expect no).
- Result that would change the recommendation: if extraction requests scale with the number of artifacts, split artifacts differently and lower the per-night video ceiling proportionally.

### Q4. If the residential address is challenged: duration, self-clearing, household impact, response

- **What a challenge looks like:** the extractor prints "Sign in to confirm you're not a bot" (a `LOGIN_REQUIRED` player response), or media requests return HTTP 429 / 403, or a reCAPTCHA page, or the rate-limit text: "This content isn't available, try again later. The current session has been rate-limited by YouTube for up to an hour" (yt-dlp error text; Extractors wiki / issue #14921).
- **Duration:** no official number. HTTP 429 carries a `Retry-After` header; MDN's "429 Too Many Requests" reference (last modified 2026-06-22) shows the canonical example "`Retry-After: 3600`" — requests allowed again "after 3600 seconds (60 minutes)." Community consensus (yt-dlp.net 429 guide, 2026): "minutes for a light trip, hours for a heavy one." Multilogin's 2026 analysis warns explicitly: "Do not promise readers that every temporary IP ban clears in 24 or 48 hours … YouTube does not provide a standard IP ban duration. A temporary block may clear after the triggering requests stop, but the timing varies." **Every retry restarts the timer.**
- **Self-clearing:** yes for light rate trips once activity stops; not reliably for a heavily-flagged address.
- **Household impact:** evidence is mixed but somewhat reassuring. In yt-dlp issue #16747 (May 2026) a user reported yt-dlp blocked by IP while "The videos play fine in the browser," suggesting some challenges are client/heuristic-specific rather than a blanket IP ban of all YouTube traffic. Because the acceptance criterion is zero household tolerance, **assume the worst and design to avoid the challenge entirely.**
- **Recommended unattended response (matches the owner's stated rule):** on detecting a bot-wall / 429 / reCAPTCHA, the wrapper **stops the run immediately, does not retry the video, does not probe again for ≥10 minutes, backs off 24 hours, and alerts after two consecutive challenged runs**, pausing the pipeline. yt-dlp's own extractor retries must be disabled (`--extractor-retries 0`), because retrying a bot-wall "makes your IP look more automated, not less" (ytdlp.org guide, 2026).

### Q5. IPv6: should the job force IPv4?

**Yes — force IPv4 with `-4`.** YouTube scores an entire IPv6 /64 as a single unit (Tunelio measurement, Aug 2026: "YouTube scores a whole /64 as one unit, so one noisy neighbour flags the block"; corroborated by podsync PR #121, 2020: shared /64 → "combined rate limits … The remedy here is to force IPv4"). Residential IPv4 addresses generally carry good reputation.

**Does it change pacing advice?** No — pacing values stay the same. The nuance: on IPv4 the job and the household share one scored address, which *reinforces* (not relaxes) the conservative pacing, because the address you must protect is exactly the one the household browses from. `--force-ipv4` (`-4`) and `--source-address IP` are both confirmed present in the README network options at this version.

### Q6. Backfill scheduling under the defaults

Arithmetic (sustained DASH rate 6.5 MB/s; the brief's stated volumes):
- **Audio backfill** ~20 GB → 20,480 MB / 6.5 ≈ 3,150 s ≈ **~0.9 h** of bytes.
- **Video backfill** ~220 GB → 225,280 MB / 6.5 ≈ 34,700 s ≈ **~9.6 h** of bytes.
- **Total ~240 GB ≈ ~10.5 h** of transfer — matches the brief's "~10 hours."

Bytes are not the constraint; **request rate and the zero-household-impact rule are.** Cap by video *count*:

| Phase | Items | Per-night ceiling | Nights | Notes |
|---|---|---|---|---|
| Audio-first backfill | 1,135 talks (best Opus + best AAC) | 200 videos/night | ~6 | ≈4 GB/night, ~33 videos/hour — deeply safe |
| Video backfill | 1,135 talks (1080p best codec) | 200 videos/night | ~6 | ≈30–40 GB/night; ~1–2 h of the 6-h window |
| **Total** | | | **~12 nights** | Excludes event weeks + the week after each |

- **Ordering:** within any run, new talks first, then backfill; audio for the whole corpus before any backfill video (per the brief).
- **Per-night ceiling of 200 videos ≈ 33/hour** — one-ninth of the guest ceiling — so overnight transfer never competes with (asleep) household use and leaves headroom if a probe count spikes.
- **Burst pre-emption:** feed-poll hits jump the queue. A 300-talk burst = 300 extractions + ~45 GB (mixed slide talks and larger panels) ≈ **~2 h of transfer**, which fits inside one 01:00–07:00 window; the event-week midday pass is a second window. A full conference burst is thus queryable well inside the 4-day freshness goal, and backfill simply doesn't run that week.

### Q7. What a well-behaved downloader looks like (cheap to emulate)

- **User agent:** do **not** spoof it. yt-dlp sets the correct per-client UA automatically; a mismatched UA is itself a bot signal. Leave `--user-agent`/`--add-headers` unset (the yt-dlp.net bot-wall guide explicitly names a stray `--user-agent` in a config file as a *cause* of challenges).
- **Client selection:** use the **default** (`visionos,web` at 2026.08.19). Do not hard-code a client, because defaults change monthly; `visionos` in particular serves AV1 over HTTPS/DASH (per PR #17184 discussion, it is "almost entirely the same as android_vr" with AV1 as https), matching the "prefer AV1, DASH not HLS" policy. Re-verify after each update.
- **JS runtime:** keep Deno present (Homebrew already pulled in Deno 2.9.6 + yt_dlp_ejs 0.8.0). Without a JS runtime yt-dlp drops the `web` client and warns that extraction is deprecated; with it, challenge/nsig solving happens locally with no extra YouTube request.
- **Format probing:** minimise it. Use `--download-archive` so already-fetched IDs are skipped without extraction, fetch all artifacts in one invocation, keep `--concurrent-fragments 1`, and avoid `-F`/repeated `--list-formats` in production.
- **Retries:** keep transient network retries (`--fragment-retries`) but disable extractor retries so a challenge is never hammered.

---

## Deliverable

### 1. Recommended nightly `yt-dlp` invocation (per video; pacing options only — format/output details are brief 03)

```
yt-dlp \
  -4 \
  --sleep-requests 3 \
  --sleep-interval 10 --max-sleep-interval 30 \
  --sleep-subtitles 5 \
  --limit-rate 4M \
  --concurrent-fragments 1 \
  --retries 3 \
  --fragment-retries 10 \
  --extractor-retries 0 \
  --retry-sleep fragment:exp=1:60 \
  --download-archive /Volumes/archive/yt-dlp-archive.txt \
  --no-playlist \
  -v \
  "https://www.youtube.com/watch?v=<VIDEO_ID>"
```

| Flag | Justification | Source type |
|---|---|---|
| `-4` | IPv6 /64 scored as one unit; residential IPv4 predictable (Q5) | Vendor/community measurement |
| `--sleep-requests 3` | Primary anti-429 lever; requests > bytes | Community + maintainer wiki |
| `--sleep-interval 10 --max-sleep-interval 30` | Randomised pre-download pause; wiki recommends 5–10 s, this is conservative + jittered | Maintainer wiki |
| `--sleep-subtitles 5` | Caption endpoint is tightly limited | Community (transcript guide) |
| `--limit-rate 4M` | Courtesy/household headroom below 6.5 MB/s sustained | Community |
| `--concurrent-fragments 1` | Parallel fragments = throttle/bot signal | Community |
| `--retries 3 --fragment-retries 10` | Tolerate transient network on an already-authorised transfer | Official README |
| `--extractor-retries 0` | Never hammer a bot-wall; wrapper handles back-off | Official README + community |
| `--retry-sleep fragment:exp=1:60` | Exponential fragment back-off, capped at 60 s | Official README |
| `--download-archive …` | Skip already-fetched IDs without extraction | Official README |

Put these in a yt-dlp config file so every subprocess inherits them. The **wrapper — not yt-dlp — must parse stdout/exit code** for "Sign in to confirm you're not a bot", HTTP 429, "This content isn't available, try again later", or reCAPTCHA, and enforce the 24-hour back-off / two-strikes alert. Do not set a client override; let the default track upstream and re-verify after each update.

### 2. Backfill plan

- Audio-first, ~20 GB, **~6 nights** at 200 videos/night; then video, ~220 GB, **~6 nights** at 200/night — **~12 nights total**.
- Never during an event week or the week after; new talks always pre-empt backfill within a run.
- A 300-talk burst (~2 h transfer) fits one nightly window; the event-week midday pass is the safety valve. Backfill is suspended that week.
- Per-night ceiling 200 videos ≈ 33/hour ≈ one-ninth of the ~300/hour guest ceiling.

### 3. "Signals that mean back off" table

| Signal | Category | What it means | Response |
|---|---|---|---|
| Sustained speed collapses to ~0.2–0.45 MB/s with periodic stalls; `--throttled-rate` re-extraction fires | Succeeding but throttled | Server-side speed shaping (same pattern seen through the VPN), not a challenge | Let the in-progress download finish; keep concurrency at 1; if it persists across several videos, stop starting new videos for the night. No alert. |
| Chunk-boundary stalls every ~10 MB | Succeeding but throttled | Normal on this line | Ignore. |
| `HTTP Error 429: Too Many Requests` (with `Retry-After`) | Challenged (rate) | Rate limit with a timer; every retry restarts it | Stop the run; no retry; wait ≥ `Retry-After` (assume 3600 s if absent); back off 24 h; alert after two consecutive. |
| `Sign in to confirm you're not a bot` / `LOGIN_REQUIRED` | Challenged (bot-wall) | Trust score too low for this address | Stop immediately; no retry; back off 24 h; alert after two consecutive. |
| reCAPTCHA page returned | Challenged | Heavy rate trip | Same as bot-wall. |
| `This content isn't available, try again later` | Challenged (rate) | Per yt-dlp text: session rate-limited "for up to an hour" | Stop; back off; raise sleep values. |
| `HTTP Error 403` on media only, first occurrence | Ambiguous | Usually an expired/SABR format URL, not an IP block | Re-extract that one video once; if it recurs across videos, treat as extractor breakage → update yt-dlp, alert. |

### 4. Evidence table (dates + source types)

| Evidence | Date | Type | Bearing |
|---|---|---|---|
| yt-dlp Extractors wiki: guest ~300 videos/hr (~1000 req/hr), 5–10 s between downloads | edited 2025-06-11 | Official-ish (maintainer wiki) | The one authoritative ceiling (Q1) |
| yt-dlp README `player_client` default `visionos,web`; sleep/limit/retry/`-4`/`--source-address` flags | viewed 2026-09-16 | Official docs | Flag verification (Q2, Q7) |
| yt-dlp release 2026.08.19 notes: add `visionos` (#17184), remove `android_vr` (#17461), `web_embedded` fallbacks (#17462) | 2026-08-19 | Official docs | Default client shift (Key finding 4) |
| yt-dlp verbose logs, issue #17538 (2026.08.19): single extraction per video; `c=VISIONOS` | 2026 | Community (with version banner) | Q3 extraction-once fact |
| hxckya youtube-transcript-ip-blocked-guide: caption endpoint tightened Jul 2025; 50–few-thousand req thresholds; residential fetch worked 2026-09-13 | checked 2026-09-13 | Measured/community | Q1b caption limits |
| Tunelio blog: IPv6 /64 scored as one unit; ~1-in-4 fresh datacentre exits hit bot wall | Jul 2026, upd. 2026-09-07 | Vendor claim (sells hosted API) | Q5 IPv6 |
| podsync PR #121: DigitalOcean /64 shared → combined limits → force IPv4 | 2020 | Community | Q5 IPv6 corroboration |
| yt-dlp.net 429 & bot-wall guides: requests > bytes; every retry restarts timer; light=minutes/heavy=hours | 2026 | Community | Q2, Q4 |
| DEV Community (pickuma): unattended `--limit-rate 5M --sleep-interval 5 --max-sleep-interval 15`; `-N 16` throttled | 2026 | Community | Q1a, Q2 |
| yt-dlp issue #16747: browser plays fine while yt-dlp IP-blocked | May 2026 | Community | Q4 household impact |
| MDN "429 Too Many Requests": `Retry-After: 3600` example (60 min) | modified 2026-06-22 | Official docs (web standard) | Q4 duration |
| Multilogin: "Do not promise … clears in 24 or 48 hours … timing varies" | 2026 | Vendor claim | Q4 duration |
| Narro / RSScribe: native channel feed capped at 15 entries, Atom+Media RSS, includes Shorts | 2026 | Vendor/community | Feed monitoring caveat |

---

## Recommendations (staged)

1. **Set up (fits in ~5 h):** deploy the invocation above behind the existing home-network / VPN-off / mains guard; add a public-address check that the exit IP belongs to Charter Spectrum (not just the Wi-Fi SSID) before any run; wire the wrapper's challenge detector (regex on stdout for the four challenge strings + exit code) to the 24-h back-off and two-strikes alert; place all pacing flags in a yt-dlp config file.
2. **Run the Q3 calibration test on 5 channel videos** before the first backfill night; confirm ~3–5 extraction requests/video and that artifacts don't multiply extraction.
3. **Backfill conservatively:** audio-first at 200/night, then video, pausing for event weeks. If **ten consecutive nights complete with zero challenges and zero household complaints**, *consider* raising the per-night ceiling toward 300–400 (still under the guest ceiling) — but only outside event windows.
4. **Track upstream monthly:** re-verify the default client set and flag names after each yt-dlp update (defaults changed twice in 2026 already). Pin the version in production and update deliberately.

**Thresholds that change the plan:** any single challenge during normal operation → hold the ceiling and investigate; two consecutive challenged runs → the pipeline pauses itself; any household YouTube complaint → halve the ceiling and raise `--sleep-requests` to 5.

## Caveats (open uncertainties, ranked by impact) + cheapest resolving experiment

1. **Whether a challenge on this shared residential IP actually degrades household YouTube (highest impact).** Evidence is mixed (issue #16747 suggests the browser can keep working while yt-dlp is blocked). *Cheapest experiment:* the next time the job is deliberately pushed to a 429 on a weekend, immediately test YouTube in a browser and app on the same line; if playback is unaffected, the zero-tolerance rule has more headroom than assumed.
2. **Exact server-side request counting per artifact (medium).** Extraction is once-per-video (verified), but how YouTube weights subsequent media/caption transfers is unknowable publicly. *Cheapest experiment:* the Q3 verbose-count test, plus, at the first 429, record how many videos preceded it.
3. **The live channel-feed entry count and premiere behaviour (low–medium).** The native `feeds/videos.xml` feed is capped at 15 entries (Narro, 2026: "capped at 15 videos … and includes Shorts"; RSScribe, 2026, corroborates a 15-item cap) and mixes Shorts/livestreams; the feed could not be fetched during research to confirm this channel's live entry count, most-recent timestamps, or whether scheduled premieres appear. *Cheapest experiment:* fetch the feed URL from the owner's machine/RSS reader and count `<entry>` elements; if premieres appear (future-dated, no duration/media), the poller must filter them, and the 15-entry cap means the hourly poll can miss uploads if more than 15 land between polls (unlikely at hourly cadence, but check during a burst).
4. **Caption-endpoint threshold on a clean residential IP (low).** Reports range 50–few-thousand requests; unverified for this line. *Cheapest experiment:* during the first burst, log caption fetches until the first caption-specific 429 and record the count.

## Suggestions outside scope (not folded into the recommendation)
- The livestream capture project (already noted as following this one) will change the request profile: 8–10 h stream recordings are few but long, and live / `--live-from-start` fragments behave differently from DASH talks.
- Consider a `--throttled-rate` value so yt-dlp auto-re-extracts a stream that drops to the VPN-like 0.2–0.45 MB/s pattern; this is a robustness detail rather than pacing.
- Pinning yt-dlp and rebuilding weekly against the newest stable (reproducibility practice, not a pacing lever).
- The 15-entry RSS cap suggests a fallback: on days the channel posts >15 items between two hourly polls (rare), reconcile against a daily `--flat-playlist` listing of the uploads playlist so nothing is missed.

## Reference list (grouped by source type)

**Official documentation (yt-dlp and web standards)**
- yt-dlp README (master, viewed 2026-09-16): sleep options, `--limit-rate`, `--concurrent-fragments`, `--retries`, `--fragment-retries`, `--extractor-retries`, `--retry-sleep`, `-4/--force-ipv4`, `--source-address`, `--download-archive`, `player_client` default `visionos,web`.
- yt-dlp Extractors wiki (edited 2025-06-11): guest ~300 videos/hr (~1000 req/hr); 5–10 s between downloads; mweb+PO-token guidance; "This content isn't available, try again later" rate-limit text.
- yt-dlp PO Token Guide wiki (viewed 2026-09-16): default clients avoid PO tokens; captions require a PO token for the web client.
- yt-dlp release 2026.08.19 notes: add `visionos` (#17184), remove `android_vr` from defaults (#17461), `web_embedded` fallbacks (#17462).
- MDN Web Docs, "429 Too Many Requests" (modified 2026-06-22): `Retry-After: 3600` example.

**Measured / verified**
- hxckya, "youtube-transcript-ip-blocked-guide" (checked 2026-09-13): caption-endpoint tightening (Jul 2025), 50–few-thousand request thresholds, cloud vs residential behaviour, yt-dlp 2026.08.19 caption fetch confirmed from a consumer ISP.
- Verification of yt-dlp 2026.08.19 verbose logs (GitHub issues #17538, #6274, #9371): single extraction pass per video per invocation; `c=VISIONOS` in the media URL.

**Vendor claims (weigh accordingly)**
- Tunelio blog (Jul 2026, updated 2026-09-07): IPv6 /64 scored as one unit; ~1-in-4 fresh datacentre exits hit the bot wall (their fleet, Aug 2026). Tunelio sells a competing hosted API.
- Narro (2026) and RSScribe (2026): native YouTube channel feed capped at 15 entries, Atom+Media RSS, includes Shorts/livestreams.
- Multilogin (2026): no dependable community timer for how long a block lasts.

**Community reports**
- yt-dlp.net 429 and bot-wall guides (2026): requests > bytes; `--sleep-requests` central; every retry restarts the timer; light trips minutes / heavy hours.
- ytdlp.org "Fix Sign in to confirm" (2026): "Do not hammer the same URL with retries while the check is active."
- DEV Community, pickuma (2026): unattended pacing `--limit-rate 5M --sleep-interval 5 --max-sleep-interval 15`; `--concurrent-fragments 16` gets throttled.
- yt-dlp GitHub issues #16747 (May 2026, browser works while yt-dlp blocked), #13770/#13831 (2026, caption 429s), #11047/#11897 (sleep-before-extraction behaviour), #17226 (visionos client characteristics).
- podsync PR #121 (2020): DigitalOcean /64 shared → combined rate limits → force IPv4.

*Note on conflicts: one older source (authory.com) states the native RSS cap is 10 entries; the strong 2023–2026 consensus (Narro, RSScribe, multiple RSS-reader docs) is 15. I trust 15, but the live feed for this channel was not directly counted during research — see Caveat 3.*