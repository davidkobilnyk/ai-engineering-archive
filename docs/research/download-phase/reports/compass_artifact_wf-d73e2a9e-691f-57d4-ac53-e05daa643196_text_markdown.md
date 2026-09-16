# Research Brief 08 — Watching the Channel: RSS Feed, Uploads Playlist, and the YouTube Data API

## Summary recommendation

Build the watcher on **two data sources and one enrichment call**: the free RSS feed as the fast, keyless trigger; the uploads playlist (`playlistItems.list`, 1 unit/page) via the YouTube Data API v3 as the authoritative enumerator for the zero-miss recovery walk; and one `videos.list` call (1 unit) per new or re-checked ID to get duration, `liveBroadcastContent`, and `liveStreamingDetails`. Do **not** use `search.list`: it costs 100 units/call — a hard ceiling of about 100 searches per day out of the 10,000-unit budget (OutlierKit, 2026) — and, per SocialCrawl (2026) citing Google's Search:list docs, "You cannot retrieve the oldest-first results for a keyword, which makes chronological corpus collection impractical." Retire `yt-dlp --flat-playlist` from the watcher entirely except as an optional fallback for the Streams tab; the Data API enumerates uploads for 1 unit/page with no scraping exposure on the home IP, which is strictly better for this job. Quota use is trivial: a 30-video burst day costs ~35 units, a 7-day recovery a few hundred units, and the one-time 1,135-video enumeration ~46 units — all against the YouTube Data API v3 default of 10,000 units/day per Google Cloud project, resetting at midnight Pacific (OutlierKit, 2026: "Every Google Cloud project gets 10,000 YouTube Data API quota units per day by default... the quota resets at midnight Pacific Time"). A personal API key needs no audit at default quota. Premieres and finished stream recordings are both disambiguated by the same two fields: `snippet.liveBroadcastContent` (must be `none`) and `contentDetails.duration` (must be a real, non-`P0D` value). Every Data API claim below is documentation-derived and marked with a local key test; the owner can obtain a free key in minutes.

This design meets the latency budget (detection within 6 h during event weeks, 24 h otherwise) with hourly RSS polling, and meets the hard zero-miss recovery requirement by walking the uploads playlist to a set of recent known IDs rather than a fixed page count.

---

## 1. RSS feed behaviour (observed + community-reported)

**What the feed is.** `https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA` is a free, keyless Atom feed. During research it was **not directly fetchable** by automated tools (YouTube returns a robots-disallowed / automated-access-blocked response to the fetcher; this is a fetch-tool limitation, not a statement about a real browser or a scripted `curl`/`requests` GET from the owner's Mac, which community tools use routinely). All feed-shape claims below therefore come from the brief's own dated observations (2026-09-16) plus community reports; the owner should confirm with the local test at the end of this section.

**Speed of appearance.** Community reports converge on new uploads appearing in the feed within minutes to about an hour of publication. YouTube's own (legacy) data-latency documentation states uploaded videos appear in a channel's public uploads feed "a few minutes after the upload completes and YouTube finishes processing." A feed-to-email operator (FeedMail, 2023) reports that entries sometimes lag the WebSub push "for up to an hour," and that YouTube occasionally emits notifications for items not yet in the feed. **Conservative planning number: assume up to ~1 hour of feed lag after publication.** With hourly polling, worst-case detection is ~2 hours — comfortably inside the 6-hour event-week budget.

**The 15-entry cap.** The feed holds exactly the 15 most recent uploads (the brief observed exactly 15). This is a hard, well-documented native limit: WP RSS Aggregator (2026) states "The feed returns that channel's 15 most recent uploads in XML," and Narro states "YouTube publishes a native RSS feed for every channel... it's capped at 15 videos." **Implication for bursts:** the channel posts 5–30 videos/day after an event, and on 2026-09-16 posted four in ninety minutes. If more than 15 videos are published between two polls, the feed silently drops the oldest of them off the bottom and the watcher would miss them if it trusted the feed alone. This is the single most important reason the feed cannot be the only source. Two mitigations, both used below: (a) poll faster during bursts (adaptive rule), so ≤15 new items accumulate between polls; (b) the daily uploads-playlist walk backstops any feed miss.

**How premieres appear (the core hazard).** The brief's own observations are the authoritative evidence here and they are unambiguous: scheduled premieres **do** appear as ordinary-looking feed entries *before they air*, and the entry's `published` is set to the **scheduling time**, not the air time. "Stop Chunking Like It's 2022" had `published` 2026-09-15T07:36Z, its `updated` moved to 09:26Z on the 16th, and at 15:44Z on the 16th it still had not aired (yt-dlp said "Premieres in 74 minutes") — more than 32 hours after `published`. Conclusions the brief already drew, which the research confirms:
- A watcher keyed on `published` treats an unaired premiere as a day-old (or older) video. **Do not trust `published` as an "is it live yet" signal.**
- A change in `updated` does **not** mean the premiere aired.
- **No field in the RSS `media:group` reliably distinguishes an unaired premiere from a published video.** The feed carries `yt:videoId`, title, `published`, `updated`, author, and a `media:group` (title, content, thumbnail, description, community statistics) — but **no duration** and no broadcast-status field. This matches community findings: feed readers cannot tell a premiere apart from a normal upload from feed fields alone; some third-party feed generators (e.g. Open RSS) work around this by re-probing each video and prefixing "UPCOMING:" themselves. Therefore **the RSS feed can detect a candidate ID but cannot classify it.** Classification must come from `videos.list` (Section 2).

**Live streams in the feed.** Conference days are livestreamed. A live/upcoming stream appears in the feed the same way — as an entry with no duration and no reliable status field. Same conclusion: detect from feed, classify from API.

**Caching/staleness.** The Coders Blog (2026) reports YouTube's native RSS feeds show "frequent 404/500 errors and severe item caps (10-15 videos)... its instability represents a deliberate move toward platform lock-in." This is another reason to treat the feed as a fast-but-lossy trigger and the playlist walk as the source of truth.

> **Local test T1 (feed shape & premiere representation).** Tool: `curl` (or Python `requests`) from the Mac, off the VPN. Command shape: `curl -s 'https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA'`. Measure: (a) entry count (expect ~15); (b) for a known unaired premiere ID, confirm it is present and record its `published`/`updated`; (c) diff the raw XML of a premiere entry vs. a normal entry to confirm no distinguishing field. What would change the recommendation: if a distinguishing field *does* appear (e.g., a status attribute), the per-ID `videos.list` classification could be skipped for feed-detected items — but do not assume this.

---

## 2. Data API: premiere / live / recording detection, quota, key approval (documentation-derived)

All of this section is **documentation-only** unless stated; each claim gets a local test. Sources: Google's YouTube Data API v3 reference (Videos, PlaylistItems, Playlists, quota/compliance pages), dated to 2026 revisions where possible, plus one community capture of real premiere-lifecycle JSON (jschuur gist).

**Fields that identify not-yet-available premieres and streams.** Request `part=snippet,contentDetails,status,liveStreamingDetails` on `videos.list`. The decisive fields:

| State | `snippet.liveBroadcastContent` | `liveStreamingDetails` present? | `contentDetails.duration` | `status.uploadStatus` |
|---|---|---|---|---|
| Upcoming premiere / scheduled stream | `upcoming` | yes — `scheduledStartTime` set, no `actualStartTime`/`actualEndTime` | absent or `P0D` | `uploaded` / `processed` |
| Currently live / premiering | `live` | yes — `actualStartTime` set, `concurrentViewers` may be present, no `actualEndTime` | `P0D` | `processed` |
| Finished (normal VOD or ended stream/premiere) | `none` | for a former broadcast: yes — `actualEndTime` set; for a plain upload: absent | real value, e.g. `PT23M11S` | `processed` |

This table is corroborated by a community capture of the same video across its lifecycle (jschuur gist): `upcoming` → `liveStreamingDetails.scheduledStartTime` only; `live` → adds `actualStartTime` + `concurrentViewers`; available → `liveBroadcastContent: none`, `actualEndTime` set, `status.uploadStatus: processed`. Google's field docs confirm `liveStreamingDetails` "will only be present if the video is an upcoming, live, or completed live broadcast," that `actualEndTime` "will not be available until the broadcast is over," and that `liveStreamingDetails` is documented for the videos resource.

**The two fields to rely on for "fetchable now":** `snippet.liveBroadcastContent == "none"` **AND** `contentDetails.duration` is present and not `P0D`. A premiere satisfies both only after it has aired and finished. This is the same rule for premieres and for finished stream recordings (Section 5). `scheduledStartTime`/`actualEndTime` are useful secondary signals for the retry scheduler but are not needed for the go/no-go decision.

**Duration for upcoming/live content.** Community and API behaviour: live/upcoming content has no meaningful duration — it is reported as `P0D` (or absent). Treat `P0D` as "not ready."

**Deleted / private videos.** In `videos.list`, deleted or private IDs are simply **omitted from `items`** (the response returns fewer items than IDs requested; totalResults reflects what's visible). In `playlistItems.list`, they instead appear with placeholder titles **"Deleted video"** or **"Private video"** and `status.privacyStatus` of `private`; public playlists silently skip duration for inaccessible items. This asymmetry is what makes the recovery stopping rule (Section 3) need to be robust to a last-seen ID that later goes private/deleted.

**Quota costs and daily limit (2026).** Confirmed against Google's "determine_quota_cost" page and multiple corroborating 2026 secondary sources:
- Default free quota: **10,000 units/day per Google Cloud project**, resetting at midnight Pacific.
- `playlistItems.list`: **1 unit/call** (returns up to 50 items/page). Confirmed on the method page ("quota cost of 1 unit").
- `videos.list`: **1 unit/call** (returns up to 50 IDs/call; the 50-ID cap is a hard limit — TechNetExperts, 2026: a request with 51+ IDs "will fail immediately," and cost is "1 quota point regardless of whether it returns 1 or 50 records").
- `playlists.list`: **1 unit/call** (up to 50 playlists/page).
- `search.list`: **100 units/call**, confined to a separate ~100-call/day bucket, and cannot return oldest-first. **Avoid it.**
- A June 1, 2026 quota change moved uploads and some write ops into separate buckets; it did not change the 1-unit read cost for the list endpoints this design uses. Blotato (2026): "since the June 1, 2026 update [videos.insert] bills to its own dedicated bucket at 1 unit per call with a default limit of 100 calls a day, so uploads no longer compete with your reads and searches for budget."

**Does a personal key need approval/audit?** No — at default quota. Creating an API key is free, needs no credit card, takes minutes, and grants read access to public data immediately with no approval wait. Audit/compliance review (the "Audit and Quota Extension Form") is required **only** to exceed the default 10,000 units/day, or for OAuth apps touching private/user data. This design stays far under 10,000 units/day and reads only public data with an API key, so **no audit is needed.** Two caveats from Google's developer policies: (1) a project inactive for 90 consecutive days may have its access curtailed — not a concern here given daily polling; (2) the key reads public data only, which is all the watcher needs.

> **Local test T2 (API classification).** Tool: `curl` with a free API key. Command shape: `curl 'https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,status,liveStreamingDetails&id=VIDEOID&key=KEY'`. Inputs: one known unaired premiere ID, one live ID (during a conference day), one normal VOD ID. Measure: the four fields in the table. What would change the recommendation: if `liveBroadcastContent` or duration behave differently than documented (e.g., a premiere shows a real duration before airing), adjust the go/no-go rule accordingly.

---

## 3. Polling design, recovery walk, and quota arithmetic

### 3.1 Adaptive polling rule (primary design)
- **Baseline:** poll the RSS feed **hourly**.
- **Speed-up on hit:** if a poll finds any new video ID, poll again in **15 minutes**, and keep the 15-minute cadence as long as consecutive polls keep finding new IDs; fall back to hourly after two consecutive empty polls. This adapts to bursts (5–30/day, or four in 90 minutes) without a maintained calendar.
- **Optional calendar seed (no maintenance):** the four upcoming events can be used as an optional hint to start in fast mode, but the adaptive rule already covers bursts, so the calendar is not required. Per the official AI Engineer registry (ai.engineer): **Paris Sept 23–24 (Station F), NYC Oct 12–14 (Sheraton New York Times Square Hotel), Shanghai Nov 5–6 (Hilton Shanghai Hongqiao), Code SF Nov 10–12 (Hilton San Francisco Union Square).** Per the brief, the owner maintains nothing.
- RSS polling is a plain keyless fetch with no scraping exposure and negligible cost, so hourly-or-faster is free.
- **Daily uploads-playlist walk:** once per day (in the nightly window), regardless of feed activity, walk the uploads playlist to reconcile against the feed. This is the backstop for the 15-entry cap and feed staleness.

### 3.2 The zero-miss recovery walk
The uploads playlist ID is the channel ID with `UC` → `UU`: **`UULKPca3kwwd-B59HNr-_lvA`**. Walk it with `playlistItems.list?part=snippet,contentDetails&playlistId=UU...&maxResults=50`, following `nextPageToken`, **newest-first**, and **stop when you have seen the last-known set of IDs** — never a fixed page count (hard requirement).

**Robust stopping rule (addresses backdating, deletion, privacy).** Do not stop on a single last-seen ID, because that ID may be deleted, made private, or displaced by a backdated/future-dated upload. Instead:
1. Keep a persistent set of the **last N known video IDs** (recommend N = 60, i.e. > one big burst day and > the 15-entry feed window).
2. Walk pages newest-first, collecting IDs not in the known set as "new candidates."
3. **Stop only after a full page of 50 items contains no new candidates** *and* you have re-matched at least ~30 of your known-recent IDs — i.e., a time/overlap margin, not a single sentinel. This survives the last-seen ID being deleted (you match the others in the set) and survives modest reordering.
4. Use `contentDetails.videoPublishedAt` (the real publish timestamp, present on uploads-playlist items) rather than `snippet.publishedAt` (which is the *playlist-add* time) for ordering sanity checks; be aware the uploads playlist is ordered by upload recency and is generally but not perfectly chronological.

**Ordering caveats (documentation/community).** The uploads playlist is newest-first by upload time (widely relied upon; not formally guaranteed by Google). Known quirks to defend against: occasional reordering, the **20,000-item cap** documented in Google Issue Tracker #166292064 ("PlaylistItems list API only returning latest 20,000 videos on a [channel]", issuetracker.google.com/issues/166292064; irrelevant here at ~1,135), and items for deleted/private videos surfacing as "Deleted video"/"Private video" placeholders (skip these for fetching but count them toward matching known IDs). Whether the `UU` uploads playlist includes **unaired premieres/upcoming streams** is not authoritatively documented; the robust rule tolerates either case because classification happens in `videos.list`, not in the walk. Confirm with test T3.

### 3.3 One `videos.list` per new ID (batched)
For every new candidate ID (from feed or walk), call `videos.list?part=snippet,contentDetails,status,liveStreamingDetails` — **batching up to 50 IDs per call** (1 unit per call, not per ID). Emit the watcher's payload (ID, title, publish time, duration, premiere/live status, playlist membership) and let the download job proceed only for IDs that pass the go/no-go rule.

### 3.4 Quota arithmetic
Costs are dominated by whole-call charges (1 unit each), and `videos.list` batches 50 IDs/call.

| Scenario | Playlist-walk calls | `videos.list` calls | Total units |
|---|---|---|---|
| **Typical quiet day** (0–2 new) | 1 walk (1–2 pages) ≈ 2 | 1 | **~3** |
| **30-video burst day** | walk until overlap ⇒ ~2–3 pages ≈ 3 | ceil(30/50) = 1 | **~4**; with hourly re-probes of still-upcoming premieres over the day, still **< 40** |
| **7-day offline recovery** | one deep walk: up to ~210 new + overlap ⇒ ~5 pages, ≤ 8 to be safe | ceil(210/50) = 5 | **~13** for the catch-up; even with generous re-probing, **< 100** |
| **One-time 1,135-video enumeration** | ceil(1,135/50) = 23 pages = 23 | ceil(1,135/50) = 23 | **~46** (23 walk + 23 videos.list) |

Every scenario is a rounding error against 10,000 units/day. Even pathological event-week behaviour (fast polling + hourly premiere re-probes + daily walk) stays in the low hundreds of units. **The free quota is not a binding constraint for this workload.**

> **Local test T3 (walk & ordering).** Tool: `curl` + key. Walk `UULKPca3kwwd-B59HNr-_lvA` fully once. Measure: total item count (expect ~1,135 + any placeholders), whether ordering is strictly by `videoPublishedAt`, whether any unaired premiere/upcoming stream appears in the list, and how deleted/private items render. What would change the recommendation: if ordering is materially non-chronological, raise N and the overlap margin in the stopping rule.

---

## 4. Playlist membership: how, cost, and how this channel organizes playlists

**There is no direct "which playlists is this video in?" endpoint.** The YouTube Data API has no reverse lookup from a video to its containing playlists. The only supported approach is: (1) `playlists.list?channelId=...&maxResults=50` (1 unit/page) to enumerate the channel's playlists; (2) for each playlist, `playlistItems.list` (1 unit/page) and check membership. For a channel with P playlists averaging K pages each, membership for the whole channel costs roughly P + Σ(pages) units per full sweep.

**Observed channel organization (from search snippets + the channel's own site/X, 2026-09-16; the playlists page itself was not directly fetchable).** The AI Engineer channel organizes playlists by **both event and track** — the dominant naming pattern is `"<Track>: AI Engineer World's Fair <Year>"` (e.g. **"Infra: AI Engineer World's Fair 2025"**, **"SWE Agents: AI Engineer World's Fair 2025"**, **"RL + Reasoning : AI Engineer World's Fair 2025"**, **"LLM Recommendation Systems: AI Engineer World's Fair 2025"**, **"AI in the Fortune 500: AI Engineer World's Fair"**). There are also event-level umbrella playlists (**"AIEWF 2025 Complete Playlist"**, **"AI Engineer World's Fair 2026"**, **"AI Engineer World's Fair Online Track 2026"**, **"AIE CODE 2025 Online Track"**) and a few cross-event thematic playlists (**"MCP @ AI Engineer"**, described as "All MCP Talks and Workshops — AI Engineer 2025 & 2026"). Most playlist IDs share the `PLcfpQ4tk2k0...` prefix. The 2025 World's Fair alone had roughly two dozen tracks (AI Architects, AI Infrastructure, AI in the Fortune 500, Agent Reliability, Autonomy + Robotics, Design Engineering, Evals, Generative Media, GraphRAG, Keynote, LLM RecSys, MCP, Reasoning + RL, Retrieval + Search, SWE Agents, Security, Tiny Teams, Voice, Workshop, Online, Product Management, etc.), each broadly its own playlist; across 2024/2025/2026 World's Fairs plus Summit and CODE events the channel plausibly hosts on the order of 40+ playlists (exact count not confirmed — see T4).

**Cost for this channel.** Enumerating playlists: ~1 unit/page × ceil(P/50). At ~40–60 playlists that's 1–2 units. A *full* membership sweep (walking every playlist's items) would be roughly (number of playlists) + (total pages across all playlists) units — on the order of a few hundred units at most for this channel, still trivial. **Recommendation:** do not compute playlist membership on every new video. Instead, run a **single daily or post-burst membership sweep**: enumerate playlists once, walk each, and build an inverted index (videoId → [playlistIds/titles]). Then the watcher's "playlist membership" field is a cheap local lookup. Because talks are added to their track playlist around publication, a daily sweep during event weeks keeps membership fresh well within the freshness budget. This is far cheaper and simpler than per-video reverse lookups and stays within the watcher's responsibility boundary (it emits membership; it does not fetch descriptions/heatmaps).

> **Local test T4 (playlists).** `curl 'https://www.googleapis.com/youtube/v3/playlists?part=snippet,contentDetails&channelId=UCLKPca3kwwd-B59HNr-_lvA&maxResults=50&key=KEY'`. Measure: exact playlist count, naming scheme, and `contentDetails.itemCount` per playlist (to budget the sweep). What would change the recommendation: if P or total items is much larger than expected, move the membership sweep to weekly + on-demand for new IDs only.

---

## 5. How the finished stream recording appears

Each conference day is livestreamed on the keynote stage; the recording remains as an ordinary video with the **same video ID** as the live broadcast (a `liveBroadcast` resource shares its ID with the `video` resource). The lifecycle, per the field docs and the community capture:
- **During the stream:** `liveBroadcastContent: live`, `liveStreamingDetails.actualStartTime` set, `concurrentViewers` may be present, `contentDetails.duration` is `P0D`.
- **After it ends:** `liveBroadcastContent` flips to **`none`**, `liveStreamingDetails.actualEndTime` gets set, `concurrentViewers` disappears, and `contentDetails.duration` becomes the **real recorded length** once YouTube finishes processing the DVR/VOD. `status.uploadStatus` reads `processed`.

**When it gets a duration:** not at `actualEndTime` instantly, but after YouTube processes the recording — typically minutes to a couple of hours for a long stream. Until then, duration may still read `P0D` even though `liveBroadcastContent` is `none`. **This is why the go/no-go rule requires BOTH `liveBroadcastContent == none` AND a real, non-`P0D` duration** — it prevents the fetch job from grabbing a just-ended stream before the VOD is ready. The finished recording then satisfies the identical rule used for any other video, so this phase picks it up "like any other video," exactly as the brief intends.

**Premiere retry signals — confirmation.** The brief proposes re-checking at scheduled start + expected duration (or +2 h if unknown), then hourly until broadcast status is "none" and a duration exists. **Confirmed correct.** The right signals are: `liveStreamingDetails.scheduledStartTime` (when to first re-check), then poll `videos.list` until `snippet.liveBroadcastContent == "none"` **and** `contentDetails.duration` is real (not `P0D`). `actualEndTime` becoming present is a good corroborating signal that the broadcast is over, but duration availability is the gate for fetch-readiness. For premieres with no known duration, +2 h is a sound default (talks average 25 min, so 2 h is generous; conference-day streams run hours, so for those key the first re-check off `scheduledStartTime` and then poll hourly after start).

> **Local test T5 (stream lifecycle).** During a Paris/NYC conference day, poll one live stream ID every 30 min through `videos.list`. Measure the exact transition: when `liveBroadcastContent` flips to `none`, when `actualEndTime` appears, and when `duration` stops being `P0D`. What would change the recommendation: if duration lags `none` by more than ~2 h routinely, lengthen the premiere/stream retry interval.

---

## 6. Detecting changes to known videos (edits, private, deleted)

The watcher should periodically re-check known IDs to catch title/description edits and disappearances. Cheapest mechanism: **`videos.list` with up to 50 IDs per call, 1 unit per call.**

- **Title/description edits:** compare `snippet.title` / `snippet.description` against stored values. (The watcher only needs title; the download job owns the full description snapshot, so the watcher can limit itself to title changes and flag the download job to re-snapshot.)
- **Private/deleted:** an ID that **drops out of the `videos.list` `items`** (fewer items returned than IDs sent) is now private, deleted, or region-blocked. Cross-check against the uploads-playlist walk, where such videos show as "Private video"/"Deleted video" placeholders — that disambiguates "made private" (still in playlist as placeholder) from "hard-deleted."
- **Cadence:** re-checking all ~1,135 IDs costs ceil(1,135/50) = **23 units** per full sweep. A **weekly** full sweep (23 units/week) is ample and effectively free; during event weeks, a **daily** sweep of just the last ~200 IDs (4 units) catches edits to fresh talks quickly. Recommendation: weekly full sweep + daily sweep of recent IDs during event weeks.

> **Local test T6 (change detection).** Send a batch of 50 known IDs (including at least one you expect to be stable) to `videos.list`; store `etag` per item. On the next sweep, compare `etag`s to cheaply detect any change before diffing fields. Measure whether `etag` reliably changes on metadata edits. What would change the recommendation: if `etag` is a stable change signal, you can skip field-by-field diffing.

---

## 7. Should `yt-dlp --flat-playlist` be used for watching at all?

**No — retire it from the watcher.** Compared head-to-head:

| Capability | Data API (`playlistItems.list` + `videos.list`) | `yt-dlp --flat-playlist` |
|---|---|---|
| Enumerate uploads | 1 unit/page (50/page), authoritative | Lists uploads + Streams tab with id/title/duration/live status, **but no dates** |
| Scraping exposure on home IP | None (official API, keyed) | **Yes** — carries scraping exposure on the residential address (brief 01) |
| Premiere/live classification | `liveBroadcastContent` + `liveStreamingDetails` + duration, precise | `live_status`, `availability`, `release_timestamp` on a per-video metadata probe (extra requests) |
| Dates for ordering | `videoPublishedAt` present | **Absent in flat mode** — weak for the recovery walk |
| Cost | Trivial quota | Bandwidth + exposure + monthly-changing extractor |

The Data API enumerates uploads for 1 unit/page with no scraping exposure and includes the publish dates the flat-playlist mode omits, so it is strictly better for detection, classification, and the recovery walk. yt-dlp is already the tool of record for the **download** phase (subprocess, v2026.08.19); keep it out of watching. **One narrow exception:** if a future need arises to enumerate the **Streams tab** specifically and the Data API's uploads playlist proves not to include a given stream cleanly, `yt-dlp --flat-playlist` against the Streams tab is a reasonable *fallback probe* — but it should not be part of the routine hourly/daily watcher loop, to avoid recurring scraping exposure on the home IP. Verify any yt-dlp flag against the README at 2026.08.19 before use; the YouTube extractor changes monthly, and recent releases include YouTube extractor changes plus a now-required external JavaScript runtime (e.g. Deno) for full YouTube support.

---

## Deliverable: the watcher design (consolidated)

**Sources & keys.** RSS feed (keyless trigger) + Data API v3 (API key, public read, no audit). Uploads playlist `UULKPca3kwwd-B59HNr-_lvA`. Video ID is primary key.

**Adaptive polling rule.** Hourly RSS baseline; on any hit, switch to 15-minute polling until two consecutive empty polls; optional (unmaintained) event-calendar seed to start fast. Daily uploads-playlist reconciliation walk in the nightly window (01:00–07:00 US Eastern), plus a midday pass during event weeks — subject to the on-home-network / off-VPN / on-mains gate; otherwise skip and let the queue accumulate.

**Recovery walk (zero-miss).** On every daily walk and after any offline gap, page `playlistItems.list` on `UU...` newest-first; collect IDs not in the persistent known-set (N=60); stop only after a full 50-item page yields no new candidates AND ≥30 known IDs have been re-matched (overlap margin, not a single sentinel). Tolerates deletion/privatization of the last-seen ID and modest reordering.

**Endpoints & parameters.**
- Trigger: `GET https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA`
- Enumerate/recover: `GET https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails&playlistId=UULKPca3kwwd-B59HNr-_lvA&maxResults=50&pageToken=...&key=...`
- Classify/enrich: `GET https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,status,liveStreamingDetails&id=<up to 50 IDs>&key=...`
- Playlist membership: `GET https://www.googleapis.com/youtube/v3/playlists?part=snippet,contentDetails&channelId=UCLKPca3kwwd-B59HNr-_lvA&maxResults=50&key=...` then walk each once/day to build the inverted index.

**Premiere & stream-recording detection rule (fields relied on).** Fetch-ready iff `snippet.liveBroadcastContent == "none"` AND `contentDetails.duration` present and ≠ `P0D`. Secondary: `liveStreamingDetails.scheduledStartTime` schedules the first premiere re-check; `actualEndTime` corroborates end. Retry: at scheduled start + expected duration (or +2 h if unknown), then hourly until the rule passes.

**Quota arithmetic.** Quiet day ~3 units; 30-video burst day < 40 units; 7-day recovery < 100 units; one-time 1,135 enumeration ~46 units — all vs. 10,000/day free.

**Re-check policy for known videos.** `videos.list` batched 50 IDs/call (1 unit). Weekly full sweep (~23 units) + daily sweep of the last ~200 IDs (4 units) during event weeks. Dropped-from-`items` ⇒ private/deleted; cross-check placeholders in the playlist walk.

---

## Open uncertainties (ranked by impact) and cheapest resolving experiment

1. **Does the `UU` uploads playlist include unaired premieres / upcoming streams, and exactly how is it ordered?** (Highest impact: affects whether the walk surfaces premieres early and whether the stopping rule's overlap margin is enough.) *Experiment:* Test T3 — one full walk while a known premiere is unaired; check for its presence and position. Cost: ~23 units.
2. **Feed lag distribution and premiere representation in this channel's feed.** (Affects whether hourly polling truly meets the 6-hour event-week budget and whether any feed field distinguishes premieres.) *Experiment:* Test T1 — script an hourly `curl` of the feed for one event week, log first-seen time per ID vs. actual publish time. Cost: ~zero.
3. **Time gap between `liveBroadcastContent==none` and a real duration on finished streams/premieres.** (Affects the retry interval and risk of fetching a not-yet-ready VOD.) *Experiment:* Test T5 — 30-minute polling of one live ID across a conference day. Cost: ~48 units.
4. **`etag` reliability as a cheap change-detection signal.** (Affects re-check efficiency, not correctness.) *Experiment:* Test T6 — compare `etag`s across sweeps after a known edit. Cost: a few units.
5. **Exact playlist count and item totals** (affects membership-sweep budget, already trivial). *Experiment:* Test T4. Cost: 1–2 units.

---

## Suggestions outside scope
- Consider persisting the Data API `etag` per resource and using `If-None-Match` to shrink payloads (does not reduce quota — every request still costs ≥1 unit — but reduces bandwidth on the metered home connection).
- A tiny local "premiere queue" table keyed on `scheduledStartTime` would let the retry scheduler wake exactly when needed rather than polling all known upcoming IDs hourly. (Implementation nicety, not a requirement.)
- The membership inverted index could later feed the archive's citation UI (e.g., "this talk is in the Retrieval + Search track"), but that is beyond the download phase.

## Reference list (grouped by source type)

**Official documentation (Google/YouTube), accessed 2026-09-16:**
- YouTube Data API v3 — Videos resource (fields: `liveBroadcastContent`, `contentDetails.duration`, `status.uploadStatus/privacyStatus`, `liveStreamingDetails`).
- YouTube Data API v3 — PlaylistItems: list (quota cost 1 unit; `contentDetails.videoPublishedAt`; deleted/private placeholders).
- YouTube Data API v3 — Playlists: list (quota cost 1 unit; channelId enumeration).
- YouTube Data API v3 — Search: list (quota cost 100 units; separate bucket; no oldest-first).
- YouTube Data API v3 — determine_quota_cost (10,000 units/day default; per-method costs).
- YouTube Data API v3 — Quota and Compliance Audits; YouTube API Services Developer Policies (audit only for >default quota; 90-day inactivity clause).
- YouTube Live Streaming API — LiveBroadcasts / liveStreamingDetails (shared ID with video resource; `scheduledStartTime`/`actualStartTime`/`actualEndTime`).
- Legacy Google Data API reference (data-latency expectations for uploads feed).
- yt-dlp 2026.08.19 release notes (YouTube extractor changes; external JS runtime requirement).

**Measured / community capture:**
- jschuur GitHub gist — real `videos.list` JSON for a video before/during/after a premiere (`upcoming`→`live`→`none` with corresponding `liveStreamingDetails`).

**Community reports (dated where available):**
- FeedMail, "Delay on YouTube Feeds" (2023) — feed lag up to ~1 h after WebSub push; notifications for items not yet in feed.
- WP RSS Aggregator (2026), Narro, RSScribe, The Coders Blog (2026), RSS-Bridge issue #891 — native feed capped at exactly the 15 most recent uploads; not a complete archive; includes Shorts; 404/500 reliability concerns in 2025–2026.
- Open RSS — feed readers cannot distinguish premieres from feed fields; some prefix "UPCOMING:" via re-probing.
- Google Issue Tracker #166292064 — `playlistItems.list` 20,000-item cap.
- TechNetExperts (2026) — `videos.list` hard 50-ID limit; 1 unit/call regardless of ID count.
- Secondary 2026 quota write-ups (OutlierKit, SocialCrawl, Blotato, Phyllo, bundle.social) — corroborate 10,000-unit default resetting at midnight Pacific, 1-unit reads, 100-unit search in a separate ~100/day bucket, audit-only-for-increase, and the June 1 2026 bucket change for uploads.

**Channel observation (search snippets + ai.engineer / X, 2026-09-16; playlists page and RSS feed not directly fetchable by the research tool):**
- AI Engineer channel playlists organized by both event and track (e.g. "Infra: AI Engineer World's Fair 2025", "SWE Agents: AI Engineer World's Fair 2025", "AIEWF 2025 Complete Playlist", "MCP @ AI Engineer"); ~40+ playlists; `PLcfpQ4tk2k0...` ID prefix.
- ai.engineer / ai.engineer/worldsfair — event/track structure and upcoming-event dates (Paris Sept 23–24, NYC Oct 12–14, Shanghai Nov 5–6, Code SF Nov 10–12).