# Research Brief 04 — Capturing conference livestream recordings

## TL;DR

- **Capture each conference day's keynote-stage recording *after the day ends*, as an ordinary `was_live` video, using the same video+audio policy as talks.** Discover it by listing the channel's `/streams` tab flat, keeping entries where `live_status == was_live` and the (separately probed) upload date is inside the event window — one script then works unchanged for Paris, NYC, Shanghai, and Code. Run the capture at **06:00 US Eastern the morning after each day** (~18 h after a Paris day ends), which is safely past YouTube's worst-case processing window; if the recording is not yet a fully-processed VOD, retry every 6 h for up to 48 h.
- **"Not yet available" is detectable in yt-dlp output** from `live_status` (`is_upcoming` / `is_live` / `post_live`), from a nonzero exit carrying `No video formats found` / "live event will begin" / "should already be available", and from a missing AV1-1080p rung in `-F`. Only download when `live_status == was_live` **and** the full ladder (AV1-1080p + Opus + AAC) is present, and only mark "done" after an `ffprobe` duration check catches silent truncation.
- **Do not assume one recording per day.** An encoder drop mid-day yields a second recording with a new video ID; Paris 2025 already shows a split day (8.4 h Day 2 vs 1.4 h Day 1) and a probable duplicate upload. Enumerate *every* `was_live` video in the date window, key everything on the concrete `watch?v=<ID>`, and keep all of them. Disk is a non-constraint: **~2.5 GB per full ~9 h day, ≤4 GB for all of Paris**.

All yt-dlp flags below were verified against the yt-dlp README/manpage at version **2026.08.19** and the release notes dated 2026.06.09, 2026.07.04, and 2026.08.19 (checked 2026-09-16). Where a fact can only be settled on the owner's machine, I give a conservative default plus the exact calibration test.

---

## Key Findings

- **Timing is a solved problem for this schedule.** YouTube converts a raw broadcast into a standard VOD after it ends; during conversion the video plays in a browser but external tools see missing/unstable formats. The 06:00-ET-next-morning slot runs ~18 h after a Paris day ends — beyond even the worst-case ~12 h processing estimate — so availability is effectively guaranteed on the first attempt.
- **The video ID is stable and is the right key.** A single continuous broadcast keeps one `watch?v=<ID>` after it ends; the `@handle/live` URL is only a redirect and must never be stored as a key. The one break is an encoder disconnect (>~1 min), which ends the stream and starts a *new* broadcast with a *new* ID.
- **The format ladder lags during `post_live`.** AV1 and high-quality VP9 are produced during full VOD processing and appear later than a live-derived H.264 rung. yt-dlp's own live/post-live format handling was changing during the research window (fixes shipped in 2026.07.04 and 2026.08.19), which is a further reason to gate on "AV1-1080p present" rather than on a fixed wait time.
- **The channel keeps all stream recordings and stays under YouTube's limits.** All 32 recordings back to Summit 2023 were public on 2026-09-16; stage-days run 8.4–9.2 h, comfortably under YouTube's 12-hour auto-archive ceiling.
- **Stream descriptions are timestamp/lineup-oriented, not the talk template — and Paris has no chapters.** US World's Fair/Summit streams lead with a schedule link and a hand-authored `0:00:00 - start …` chapter list; Paris 2025 Day 2 instead carries a schedule link plus a bulleted speaker/talk lineup and **no YouTube chapters**. Capture the description + web schedule + comments so the later segmentation project has ground truth to align against.
- **The main capture hazard is silent truncation of long VODs**, documented in yt-dlp for years with no error emitted — which is why post-download verification is part of the definition of "done," not an optional extra.

---

## Details

### 1. Availability after a long stream ends: timing, video ID, format-ladder lag, length limits

**Bottom line: by the time the 06:00 ET job runs (~18 h after a Paris day ends), the VOD is reliably a fully-processed `was_live` video at the same ID with the full ladder. The only real risks are (a) a day exceeding YouTube's 12-hour archive ceiling and (b) a silent truncated download — both handled by the verification gate.**

- **How soon it is downloadable.** After a broadcast ends, YouTube converts the raw live feed into a standard VOD; while it converts, the video plays in a browser but external tools see missing/unstable formats. The 4K Download blog (*vendor/community report*, dated 2026-06-29) states verbatim: *"1080p streams under 2 hours: typically ready for download within 15–30 minutes · 4K streams or broadcasts over 4 hours: processing can take up to 12 hours · Streams over 12 hours: may never be fully archived by YouTube."* The Lynote blog (*vendor/community report*, 2026) corroborates: the video enters a *"'Processing' limbo … For a standard 1080p stream, wait 15–30 minutes after the broadcast ends. For 4K streams or broadcasts longer than 4 hours, processing can take up to 12 hours."* AI Engineer stage-days run ~8–9 h, so the conservative expectation is "ready within 12 h of the day ending"; running ~18 h later makes availability effectively certain. yt-dlp exposes the not-yet-processed state as `live_status == "post_live"`, defined in the README verbatim as one of the values *"'not_live', 'is_live', 'is_upcoming', 'was_live', 'post_live' (was live, but VOD is not yet processed)"* (*official documentation*, v2026.08.19, accessed 2026-09-16).
- **Video ID stability.** A single continuous broadcast keeps one `watch?v=<ID>` for the resulting VOD; the ID does not change when the stream ends (*community reports*: Quora, how2s.org, accessed 2026-09-16). Always resolve the `@handle/live` redirect to the concrete `watch?v=<ID>` and store that. Exception: an encoder disconnect longer than ~1 minute makes YouTube end the stream, and a reconnect starts a **new** broadcast with a **new** playback URL/ID (*community/vendor report*: 5centsCDN help, accessed 2026-09-16). See §6.
- **Does the ladder match an ordinary upload immediately, or lag?** It lags. During `post_live`, YouTube typically exposes only a subset (often a live-derived H.264 rung); the **AV1 and high-quality VP9 transcodes are generated during full VOD processing and appear later**. yt-dlp's handling of live/post-live adaptive formats was actively changing in this window: **2026.07.04 (dated 4 Jul 2026) added "[ie/youtube] Support live adaptive formats" (#16771)** and **2026.08.19 (19 Aug 2026) added "[youtube] Fix live adaptive fragments generation" (#17262)** (*official* release notes). Conservative default: **treat a recording as capturable only once `live_status == was_live` and the AV1-1080p rung is present in `-F`.** Calibration: the dry run (§7) — `wyUdpmj9-64` already shows AV1 at 1080p in the attached Streams data, so the gate passes immediately.
- **Documented length/availability limits.** YouTube Help, "Archive live streams" (support.google.com/youtube/answer/6247592, *official documentation*, accessed 2026-09-16): streams **under 12 hours** are auto-archived; it verbatim *"will also automatically archive streams of 1440p and 2160p (4K) video resolution"*; and, verbatim, *"Note: If your stream exceeds 12 hours, it may not be captured at all."* Creators can additionally disable auto-archiving in Advanced Settings, delete the replay, or set it Private/Unlisted, and Content ID can mute/block sections after broadcast (*community report*: StreamRecorder.io, "How to Save YouTube Live Streams (2026)", dated 2026-03-19). AI Engineer's historical stage-days (8.4 h Paris 2025 Day 2; 8.6–9.2 h for World's Fair 2026's three days) are safely under 12 h, and all 32 recordings back to 2023 were public on 2026-09-16 — so the channel keeps auto-archiving on and public. Residual risk: a future day running past 12 h would not be archived at all (the only case that would justify record-from-start — see §6).

### 2. Discovery method (portable across NYC / Shanghai / Code)

Discover recordings by listing the Streams tab and filtering, not by hard-coded URLs, so one script serves every event.

**Step 2a — list the tab flat (seconds, no per-video extraction):**
```
yt-dlp --flat-playlist \
  --print "%(id)s\t%(live_status)s\t%(duration)s\t%(title)s" \
  "https://www.youtube.com/@aiDotEngineer/streams"
```
**Fields available in flat mode:** `id`, `title`, `duration`, and `live_status` are populated per entry (consistent with the attached Streams-tab data). **Dates are not** returned in flat mode; `--flat-playlist` is documented as *"Do not extract a playlist's URL result entries; some entry metadata may be missing"* (README, v2026.08.19).

**Step 2b — cheapest way to get the date.**
- **Approximate, one request:** add `--extractor-args youtubetab:approximate_date` to the flat listing; the tab then exposes a humanized/approximate `timestamp`/`upload_date` per entry (yt-dlp issues #5634, #13879, *community reports*). Enough to bucket into an event window.
- **Exact, per-candidate probe (recommended):** because only ~1–3 entries per event survive the `was_live` filter, probe just those:
```
yt-dlp --skip-download \
  --print "%(id)s %(live_status)s %(upload_date)s %(release_timestamp)s %(duration)s" \
  "https://www.youtube.com/watch?v=<ID>"
```
`release_timestamp` / `upload_date` equal the stream day and `live_status` reads `was_live` for an ended, processed recording (matching the attached data).

**Step 2c — filter.** Keep entries where `live_status == was_live` **and** the probed `upload_date` is within the event window (Paris 2026 = 2026-09-23..2026-09-24, `America/New_York`). Pure string/date logic in the owner's Python; unchanged for NYC (Oct 12–14), Shanghai (Nov 5–6), Code (Nov 10–12). Because titles are inconsistent ("AI Engineer Paris 2025 (Day 2)", "AIE Europe Keynotes …", "WF26: …"), **do not** filter on title text — filter on `live_status` + date only, exactly as the brief specifies. (yt-dlp 2026.08.19 added "[youtube] tab: Always extract channel metadata" (#17386) — harmless, just populates channel fields on tab listings.)

### 3. Capture schedule for Paris and the "not yet available" retry rule

Paris days end ~18:00 CEST = 12:00 ET.

| Conference day | Day ends (ET) | First capture attempt | Retry cadence | Give-up |
|---|---|---|---|---|
| Day 1 — Wed 2026-09-23 | ~12:00 ET | Thu 2026-09-24 06:00 ET | every 6 h if not yet a full VOD | after 48 h |
| Day 2 — Thu 2026-09-24 | ~12:00 ET | Fri 2026-09-25 06:00 ET | every 6 h if not yet a full VOD | after 48 h |

06:00-ET-next-morning is ~18 h after the day ended — beyond even the ~12 h worst-case processing window — so the first attempt should normally succeed. (Actual firing of the job is brief 05's problem; this brief assumes it runs.)

**"Not yet available" — what it looks like, and the rule.** The controller probes first (Step 2b), branches on `live_status`, and downloads only on a fully-processed `was_live` VOD with a complete ladder:

| Observed state | `live_status` | yt-dlp signal | Action |
|---|---|---|---|
| Premiere/scheduled, not started | `is_upcoming` | Error like `This live event will begin in a few moments`; `--dump-single-json` prints `null`; nonzero exit (yt-dlp #14300, *community report*) | wait; retry in 6 h |
| Currently broadcasting | `is_live` | Extracts as live (fragments "unknown (live)") | do **not** capture during; retry in 6 h |
| Ended, still processing | `post_live` | Ladder incomplete (AV1/high VP9 absent); may error `No video formats found` or return only partial formats | wait; retry in 6 h |
| Ended, processed VOD | `was_live` | Full `-F` ladder incl. AV1-1080p, Opus, AAC | **capture** |

Additional error strings meaning "not ready / wrong path," from *community reports* (yt-dlp #15274, #16507, both 2026): `This live event has ended`, `Video should already be available`. These appear specifically **with cookies**; the owner uses **no cookies**, which is the configuration that works — a point in favour of the no-cookies decision already made.

**Exit codes:** yt-dlp returns **0** on success and **nonzero (1)** on a download/extraction error such as `No video formats found`. The controller should treat *(exit ≠ 0) OR (live_status ≠ was_live) OR (AV1-1080p rung absent)* as "not yet available → retry," and mark done only after the §5 verification passes.

### 4. Schedule ground truth to capture now, and what the channel puts in stream descriptions

For the later segmentation project, capture per-talk boundary evidence **at event time**, because both the ai.engineer schedule page and the YouTube description/comments drift or disappear later. Store all snapshots under the video ID with fetch time and schema version; timestamps in ms from video start.

**Capture set, per event:**
1. **Web schedule page** at **T−1 day** and **T+1 day**: fetch `https://ai.engineer/paris/2026` and the schedule view, saving raw HTML (and a rendered PDF) with the fetch timestamp. (The brief says not to spend effort confirming a machine-readable Paris 2026 schedule exists; just snapshot the human page. For comparison, past World's Fair editions published structured `sessions.json` / `llms.md` under `ai.engineer/worldsfair/<year>/`, observed 2026-09-16 — a cheap opportunistic check for Paris, not required.)
2. **Stream description + chapters + info + comments** via one metadata pull:
```
yt-dlp --skip-download --write-info-json --write-description \
  --write-comments \
  --extractor-args "youtube:comment_sort=top;max_comments=all,all,all,100" \
  -o "%(id)s.%(ext)s" "https://www.youtube.com/watch?v=<ID>"
```
`--write-info-json` captures the `chapters` array if present; `--write-description` captures the raw description; `--write-comments` captures comments (yt-dlp fetches comments only at the end of extraction, so this adds time). All flags verified against README v2026.08.19.

**What the channel typically puts in stream descriptions (observed 2026-09-16):**

| Video (ID) | Schedule link | Timestamp/chapter list in description | Speakers listed | Source |
|---|---|---|---|---|
| Paris 2025 Day 2 (`wyUdpmj9-64`) | Yes — `ai.engineer/paris#schedule` | Not confirmed | Yes — bulleted "Name, Title, Company, 'Talk'" | search snippet |
| WF 2025 Day 1 Keynotes (`z4zXicOAF28`) | Yes — `ai.engineer/schedule` | **Yes** — full list from `0:00:00 - start` (~25 entries "time – talk – speaker (company)") | Yes (in chapter lines) | full page fetched |
| WF 2025 Day 2 (`U-fMsbY-kHY`) | Yes — `ai.engineer/schedule` | **Yes** — `0:00:00 - start …` | Yes (in chapter lines) | snippet |
| Summit 2025 Agent Eng. Day 2 (`D7BzTxVVMuw`) | Not visible in snippet | **Yes** — `Timestamps 0:00:00 - start …` | Yes (in chapter lines) | snippet |
| Paris 2025 Day 1 "Opening Keynotes" (`W-51x-YJJMo`) | Not visible | Not visible (opens with prose about the reception/expo) | Not visible | snippet |

**Template summary:** US "keynote/track" stream recordings (World's Fair, Summit) reliably lead with a **schedule link** ("full schedule here:" / "see schedule" → `ai.engineer/schedule`) followed by a **hand-authored timestamp list that begins `0:00:00 - start`**, each line pairing a time with a talk title and speaker/company (often credited "thanks @user for timestamps"). Speakers appear **inside** the chapter lines, not in a separate "Speakers:" block. **Paris 2025 Day 2 is a variant**: schedule link plus a **bulleted speaker/talk lineup** rather than a timestamp list — and, like the World's Fair 2026 recordings, it has **no YouTube chapters**. So for Paris the description's speaker/schedule text plus the ai.engineer page are the ground truth, not `chapters`. Implication for segmentation: **do not assume the recording carries machine-readable chapters or an embedded timestamp list**; capture description + web schedule + comments so the later project has something to align against. (This differs from the owner's 205-talk description survey, which covers individual *talk* videos — abstract → "Speakers:" → links, almost no slide-deck links; stream descriptions are a different, timestamp/lineup shape.)

*Sourcing caveat:* every stream-description item except WF Day 1 (`z4zXicOAF28`, full page loaded) is from Google-quoted description snippets because youtube.com returned persistent HTTP 429/rate-limit errors during research; full durations, upload dates, complete speaker lists, and full-vs-partial chapter confirmation for Paris Day 2 remain unverified and should be re-fetched (the `youtube.com/live/<id>` URL format succeeded once and is the most reliable retry path).

### 5. Exact yt-dlp invocation for a ~10 h recording, large-file handling, and disk

**Policy (same as talks; selector details are brief 03's deliverable, cross-referenced here for ended `was_live` streams):** keep one video-only stream at best codec 1080p (AV1 → VP9 → H.264, prefer 30 fps, DASH not HLS) plus the two audio-only streams (best Opus, best AAC), all unprocessed, keyed by video ID. Because the two audio tracks are kept as separate unprocessed files, run video + two audio downloads rather than a merge.

**Video-only:**
```
yt-dlp \
  -f "bv*[height<=1080]" \
  -S "res:1080,fps:30,vcodec:av01,vext,proto" \
  -N 4 \
  --fragment-retries infinite --retries infinite \
  --retry-sleep fragment:exp=1:60 \
  --file-access-retries 10 \
  -o "%(id)s.f%(format_id)s.%(ext)s" \
  "https://www.youtube.com/watch?v=<ID>"
```
**Audio (once per codec):**
```
yt-dlp -f "ba[acodec^=opus]" -N 4 --fragment-retries infinite --retries infinite \
  -o "%(id)s.audio-opus.%(ext)s" "https://www.youtube.com/watch?v=<ID>"
yt-dlp -f "ba[acodec*=mp4a]" -N 4 --fragment-retries infinite --retries infinite \
  -o "%(id)s.audio-aac.%(ext)s"  "https://www.youtube.com/watch?v=<ID>"
```
`-S vcodec:av01` biases toward AV1 while `bv*[height<=1080]` still falls back to VP9/H.264 if AV1 is absent (e.g. the one Miami 2026 day with no AV1). The exact selector string is brief 03's call; this is the shape for an ended stream.

**Large files / resume / partial download.**
- yt-dlp resumes by default: `-c/--continue` is on, and an interrupted DASH download leaves a `.part` file (plus `.ytdl` fragment state) that the next run continues. Re-running the identical command resumes; no special flag needed.
- Multi-hour DASH is fetched as many fragments; `-N 4` (concurrent fragments) is the supported way to parallelize since **aria2c support for HLS/DASH was removed in 2026.06.09** ("migrate to `-N`", *official* release notes) — do not reach for an external downloader.
- `--fragment-retries infinite` + `--retries infinite` + `--retry-sleep` ride out the ~10-MB chunk-boundary stalls the owner measured on this line.
- **Known long-VOD failure mode (verification is mandatory):** yt-dlp has silently produced a **truncated** file for an ended long livestream — e.g. issue #1564 (*community report*, 2021) downloaded 4 h of a 10 h ended stream with **no error indicated**; #2898/#15921 show premature termination (mostly with `--live-from-start`, which we are **not** using for post-live capture). Mitigation below.

**Verification step (the definition of "done"):**
```
ffprobe -v error -show_entries format=duration -of csv=p=0 "<ID>.fXXX.<ext>"
```
Compare to `duration` from the info-json. Also hash each stored elementary stream (per the project's no-transcode/hash policy). Mismatch → re-run (resume) → only then mark done.

**Disk budget** (measured anchor: Paris 2025 Day 2 ≈ **1.36 GB** for 8.4 h of 1080p AV1 ≈ ~162 MB/h):

| Item | Rate | ~9 h stage-day |
|---|---|---|
| Video 1080p AV1 | ~162 MB/h | ~1.4 GB |
| Audio Opus ~113 kbps | ~50 MB/h | ~0.45 GB |
| Audio AAC ~129 kbps | ~58 MB/h | ~0.50 GB |
| Captions (json3) + info.json + comments | negligible | <10 MB |
| **Downloaded media per full day** | | **~2.4 GB** |
| Scene-change keyframes (extracted later; slide/podium = few scenes) | variable | ~0.1–0.3 GB (uncertain) |

- **Per day:** budget **~2.5 GB** for a full ~9 h stage-day (video + both audio + metadata); a short opening-evening day (Paris Day 1 was 1.4 h) is ~0.4 GB.
- **Per event:** **Paris 2026 ≈ 3 GB** (one short day + one full day; allow 4 GB headroom). A full 3-day event (NYC) ≈ **~7 GB**; a 3–4-day World's Fair at ~9 h/day ≈ **7–10 GB**. Against 1.76 TB free, disk is not a constraint; the drive spinning down when idle matters more for scheduling (brief 05) than capacity.
- If VP9 or H.264 is taken instead of AV1 (older events, or the AV1-less Miami day), files are several times larger per the brief's talk measurements (VP9 ~3.4×, H.264 ~12× vs AV1) — an all-H.264 ~9 h day could approach ~15–17 GB of video. Still trivial against 1.76 TB, but worth logging.

### 6. Mid-stream restarts, multiple recordings, split days, per-stage streams

A script keyed only on date can be fooled in several documented ways; the fix is the same for all — **enumerate every `was_live` video in the date window and key on video ID, keeping all of them:**

- **Encoder drop → second recording.** If the encoder disconnects for more than ~1 minute, YouTube ends the broadcast and archives it; a reconnect creates a **new** broadcast with a **new** video ID (*community/vendor report*: 5centsCDN, accessed 2026-09-16). Two `was_live` videos then share the same `upload_date`; a "one per day" assumption would silently drop the second half of a day.
- **Split / asymmetric days.** Paris 2025 already shows this: a full **8.4 h Day 2** but only a **1.4 h "Opening Keynotes" Day 1**. The Paris 2025 Day 1 title also resolved to **two distinct IDs** (`W-51x-YJJMo` and `d6dp_dwgpYQ`) — a probable duplicate/re-upload, i.e. two `was_live` entries for one day.
- **Per-stage / per-day counts vary by year.** World's Fair 2026 = 3 recordings (one per day, 8.6–9.2 h); Europe/Singapore/Miami/Code 2025 = 2 each. The count is not fixed, so the script must not hard-code it.

**Rule:** for each event window, take **all** `was_live` entries whose date is in-window, dedupe by ID, capture each, and record `duration` and `release_timestamp`. Flag for owner review any date with more than the expected number of recordings, or any pair whose durations look like a split day, so the segmentation project can decide how to stitch. Do not delete or prefer one; keep all. A `--download-archive` file keyed by ID prevents re-downloading already-captured recordings across retries.

### 7. Dry run against Paris 2025 Day 2 (`wyUdpmj9-64`) — run this week

Exercises discovery → download → verification exactly as the Paris 2026 script will. Touches only public data; downloads ~1.4 GB (~4 minutes at the home line's ~6.5 MB/s DASH throughput).

**A. Discovery (prove the filter finds the recording without hard-coding its URL):**
```
# A1. Flat list of the tab; confirm id/title/duration/live_status present, dates absent
yt-dlp --flat-playlist \
  --print "%(id)s\t%(live_status)s\t%(duration)s\t%(title)s" \
  "https://www.youtube.com/@aiDotEngineer/streams" | tee streams_flat.tsv
# Expect a line for wyUdpmj9-64 with live_status=was_live, duration ~30240s

# A2. Exact-date probe on the candidate (what the controller does per survivor)
yt-dlp --skip-download \
  --print "%(id)s %(live_status)s %(upload_date)s %(release_timestamp)s %(duration)s" \
  "https://www.youtube.com/watch?v=wyUdpmj9-64"
# Expect: wyUdpmj9-64 was_live 20250924 <ts> 30240  (date within a simulated 2025-09-23..24 window)
```

**B. Format-ladder / readiness check (the gate before downloading):**
```
yt-dlp -F "https://www.youtube.com/watch?v=wyUdpmj9-64" | tee formats.txt
# Gate passes only if: live_status is was_live AND an av01 1080p video-only rung,
# an Opus audio rung, and an AAC (mp4a) audio rung are all present.
```

**C. Download (talk policy; three artifacts):**
```
yt-dlp -f "bv*[height<=1080]" -S "res:1080,fps:30,vcodec:av01,vext,proto" \
  -N 4 --fragment-retries infinite --retries infinite --retry-sleep fragment:exp=1:60 \
  -o "%(id)s.f%(format_id)s.%(ext)s" \
  --write-info-json --write-description \
  --write-subs --sub-langs "en.*" --sub-format json3 \
  "https://www.youtube.com/watch?v=wyUdpmj9-64"
yt-dlp -f "ba[acodec^=opus]" -N 4 --fragment-retries infinite -o "%(id)s.audio-opus.%(ext)s" "https://www.youtube.com/watch?v=wyUdpmj9-64"
yt-dlp -f "ba[acodec*=mp4a]" -N 4 --fragment-retries infinite -o "%(id)s.audio-aac.%(ext)s"  "https://www.youtube.com/watch?v=wyUdpmj9-64"
```

**D. Verification (defines "done"):**
```
ffprobe -v error -show_entries format=duration -of csv=p=0 wyUdpmj9-64.f*.webm
# Compare to "duration" in wyUdpmj9-64.info.json (~30240 s). Mismatch => truncated => re-run C (resumes via .part).
```

**E. Ground-truth capture (as in §4):** confirm `wyUdpmj9-64.info.json` `chapters` is empty (expected — Paris Day 2 has none), confirm the description carries the `ai.engineer/paris#schedule` link and speaker lineup, and snapshot `https://ai.engineer/paris/2025`.

**F. Resume test (prove large-file robustness):** start C, `Ctrl-C` mid-download, confirm a `.part` file remains, re-run the identical command, and confirm it continues rather than restarts.

**What would change the recommendation, from the dry run:** AV1 missing on a `was_live` recording in B; truncation in D that a resume can't fix; `live_status` absent in flat mode in A1 (would force the `approximate_date` path or per-video probes for all entries); or a paginated/capped tab list where older events fall off (would require `--playlist-items` or date paging). Each is cheap to see now, months before Paris.

---

## Recommendations

1. **Build the discovery+capture controller now** around: flat-list `/streams` → keep `live_status == was_live` and probed date in-window → gate on `was_live` + AV1-1080p present → download video + Opus + AAC → `ffprobe`-verify → hash → `--download-archive` by ID. Key everything on the concrete `watch?v=<ID>`.
2. **Run the §7 dry run against `wyUdpmj9-64` this week.** Success criteria: A2 prints `was_live` with a 2025-09-24 date; B shows av01-1080p + Opus + AAC; D's `ffprobe` duration matches the info-json; F resumes from `.part`. This is the go/no-go for Paris.
3. **Schedule two Paris captures** — Thu 2026-09-24 06:00 ET (Day 1) and Fri 2026-09-25 06:00 ET (Day 2) — each retrying every 6 h until a full VOD or 48 h elapse. Keep **all** `was_live` recordings dated in-window, not just one per day.
4. **Snapshot ground truth at event time:** ai.engineer schedule page at T−1 and T+1, plus description + chapters + comments per recording, timestamped and stored under the ID.
5. **Do not enable record-from-start** unless uncertainty #5 fires (a day scheduled past ~11 h). Benchmarks that would change the plan: AV1 still absent 48 h after a day ends (extend the retry window / accept VP9); a `was_live` recording that never reaches a full VOD (fall back to record-from-start for that event); a tab flat-list returning <32 rows (add pagination).

---

## Caveats

- **YouTube web pages could not be fetched directly during research** (persistent HTTP 429/rate-limit). Direct channel observations (stream descriptions, the exact flat-mode field set, tab pagination behaviour) rest partly on Google-quoted snippets and the owner's attached Streams data rather than live page loads; re-confirm on the owner's machine via the dry run (A1/A2/B) and the `youtube.com/live/<id>` retry path.
- **Processing-time figures (15–30 min short / up to 12 h long) are vendor/community estimates, not official YouTube numbers.** They are used only to justify a schedule that already runs ~18 h out, so the margin absorbs their uncertainty; the real gate is `live_status == was_live` + AV1 present, not a clock.
- **Silent truncation of long VODs is a real, historically recurring yt-dlp failure.** The `ffprobe` duration check is not optional — treat any file whose duration disagrees with the metadata as not-done.
- **The Paris 2025 Day 1 double-ID** (`W-51x-YJJMo` vs `d6dp_dwgpYQ`) is unresolved; it is exactly the "multiple recordings per day" pattern the keep-all rule is designed to handle, but confirm during the dry run which is the canonical recording.
- **yt-dlp's YouTube extractor changes roughly monthly** (fixes to live/post-live formats shipped in 2026.07.04 and 2026.08.19). Re-run the §7 gate after any yt-dlp update before relying on it for a live event, and keep to the no-cookies configuration, which is the one that works for post-live capture (cookie-based paths are the ones reported broken in #15274/#16507).
- **Format-selector specifics are brief 03's deliverable;** the selectors here are the shape for an ended `was_live` stream and should be reconciled with brief 03's final strings before Paris.