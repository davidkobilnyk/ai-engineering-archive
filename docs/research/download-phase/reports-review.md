# Review of the download-phase research reports

Date: 2026-09-16. Reviewed: the eight reports in `reports/` (briefs 01 to
06, 08, 09; brief 07 was retired) against briefs 00 to 10 and the
decisions recorded in memory. Items marked *(inference)* are my reading,
not something a report measured.

## 1. Overall verdict

Every report stays inside its brief's accepted defaults, dates its sources,
labels source types, and ends with ranked uncertainties plus a local test.
None reopens a settled decision (Mac acquisition, no cookies or proxies,
video ID as key, subprocess yt-dlp). The reports are usable as written for
their own question.

The work that remains is reconciliation. Each report was written without
seeing the others, and they contradict each other on the shape of the
yt-dlp invocation, retry policy, fragment concurrency, `.part` handling,
scheduling of stream captures, and where premiere classification happens.
Section 3 rules on each.

## 2. What the reports settle

| Brief | Settled |
|---|---|
| 01 | Request rate, not bytes, is the limit. Pace with `--sleep-requests 3`, `--sleep-interval 10 --max-sleep-interval 30`, `--sleep-subtitles 5`, `--limit-rate 4M`, `--concurrent-fragments 1`, `--extractor-retries 0`, `-4`. Cap 200 videos per night. Wrapper, not yt-dlp, detects a challenge, stops, backs off 24 h, alerts after two consecutive. No client override, no user-agent override. |
| 02 | yt-dlp in a pip venv as `yt-dlp[default]`, not Homebrew; ffmpeg and deno stay Homebrew, pinned, referenced by absolute path in a config file. Update reactively on an extractor-change signature, then weekly floor; smoke test = caption fetch of `FLUoowDJg4I`, validated structurally (never by hash, captions drift); rollback = `pip install yt-dlp==LKG`. JS runtime is required only for media downloads. |
| 03 | Selector confirmed: `-f "bv*[height<=1080][protocol!*=m3u8]" -S "res:1080,vcodec:av01:vp9:h264,fps:30,proto"`. Keep three elementary streams as separate files, no merge. Audio selectors exclude DRC (`[format_id!$=-drc]`) and prefer the original-language track. STT gets the AAC/M4A file as-is. Verify with ffprobe; hash with `ffmpeg -f streamhash`. Fresh upload missing 1080p/AV1: one re-check after 6 h. Ended streams: gate on `live_status == was_live`. |
| 04 | Stream recordings are ordinary VODs after processing; gate on `was_live` plus AV1-1080p rung present; done means ffprobe duration matches metadata (silent truncation is a known yt-dlp failure on long VODs). Keep every `was_live` recording in the event window (split days and duplicate IDs happen: Paris 2025 Day 1 has two IDs). Paris streams have no chapters; snapshot description, comments, and the ai.engineer schedule page at T-1 and T+1. Dry run on `wyUdpmj9-64` before Sept 23. |
| 05 | User LaunchAgent with `StartCalendarInterval` 01:00, wrapped in `caffeinate -i -m -s`, no `RunAtLoad`; the job re-derives the window from the clock because launchd fires coalesced on wake. Guards in order: window, mains, drive mounted, egress ASN is Charter/Spectrum (SSID is unreadable from launchd on macOS 15), default-route interface not `utun`, `flock`. Fail closed, exit 0, never alert on a skip. Proton VPN cannot exclude a CLI binary and cannot be scripted off; the ASN guard is the guarantee. Keys in the login Keychain via `security` with `-T`. Full Disk Access to the resolved venv Python. `status.json` plus a free healthchecks.io dead-man check. Closed-lid operation is opt-in and needs `pmset disablesleep`. |
| 06 | **No fingerprint at download time.** Drops one item from the artifact list in brief 00. Later: audfprint (MIT, Python) with `--find-time-range --max-matches N --maxtimebits 16` gives multi-cluster time mappings; caption-text alignment runs alongside as an independent check. Panako is the fallback. |
| 08 | Watch with RSS (keyless, hourly, 15-minute cadence after a hit) plus the YouTube Data API: `playlistItems.list` on `UULKPca3kwwd-B59HNr-_lvA` for the zero-miss walk (stop after a full page with no new IDs and 30 known IDs re-matched), `videos.list` batched 50 per call to classify. Fetch-ready iff `liveBroadcastContent == none` and `duration` is real, not `P0D`. Never `search.list`. Playlist membership by a daily sweep into an inverted index. Quota is a rounding error; no audit needed. Retire yt-dlp from the watcher. |
| 09 | ffmpeg's scene score is a global mean difference and provably misses text-slide advances. Primary detector: PySceneDetect `ContentDetector` with the edge weight on, threshold 12 to 15, detection at about 720p, capture at detection + 500 ms, JPEG q90 at 1080p. Dedup with dHash Hamming <= 6 plus a 2 s crossfade collapse, keep the last build state; validate white-slide merges with an edge check. Classify camera frames by edge density plus face rejection; time-sample screen recordings. Per-talk JSON manifest and a contact sheet. No off-the-shelf tool fits. |

## 3. Conflicts between reports, with a ruling

| Topic | One report | Another report | Ruling |
|---|---|---|---|
| Invocations per video | 03 and 04: three passes (video, Opus, AAC), separate commands "for clean filenames" | 01: one invocation is one extraction contact; fetch every artifact for a video in one call | **One invocation.** Comma-separated selectors (`-f "VIDEO_SEL,ba[opus...],ba[mp4a...]"`) download each format separately without merging; the output template must contain `%(format_id)s`. This keeps 01's request budget intact; three passes would triple extraction requests and sleeps. |
| Fragment concurrency | 04: `-N 4` for long streams | 01: `--concurrent-fragments 1`, parallel fragments are a bot signal | **1 everywhere.** A 1.4 GB stream is four minutes on this line; not worth the signal. |
| Retries | 04: `--retries infinite --fragment-retries infinite` | 01: `--retries 3 --fragment-retries 10 --extractor-retries 0`, never hammer | **01's values.** Raise fragment retries for stream items only if the dry run shows truncation that a resume does not fix. Never infinite. |
| `.part` files | 03: `--no-part` to make `after_move` reliable | 05 and 04: `.part` plus atomic rename is the resumability guarantee | **Drop `--no-part`.** 03 itself says to derive the path from the deterministic template instead of parsing `after_move`. |
| Caption flags for streams | 04: `--write-subs --sub-langs "en.*"` | 03: `--write-auto-subs --sub-langs en` | **03's.** The channel has no manual tracks; 04's flags fetch nothing. |
| Stream discovery | 04: `yt-dlp --flat-playlist` on the `/streams` tab | 08: retire yt-dlp from watching; the Data API has no scraping exposure | **Data API.** Stream IDs surface through the same RSS and uploads walk as talks, and `videos.list` returns `liveStreamingDetails` for them. Keep 04's flat listing only as the Paris dry-run fallback if the uploads playlist turns out not to include streams (08's uncertainty 1). |
| Stream capture schedule | 04: a dedicated 06:00 ET attempt the morning after, retry every 6 h for 48 h | 00: one nightly window plus a midday pass in event weeks | **No special schedule.** A stream recording is a queue item tried in every window, gated on `was_live` plus the AV1 rung. The 01:00 ET window is 13 h after a Paris day ends, past 04's own 12 h worst case; the midday pass covers the retry. |
| Premiere classification | 02: `yt-dlp -J` `live_status` / `release_timestamp` | 08: `videos.list` fields | **Data API classifies**; yt-dlp is only invoked for IDs already known to be fetchable. 02's `-J` check remains the guard inside the download invocation. Removes 01's "one `-J` probe per new video" load entirely. |
| Status file | 02: `status.txt` with a paragraph of fields | 05: `status.json` | One JSON file with 02's field list. |
| Alerts | 01: after two consecutive challenges; 02: email on BROKEN rollback; 05: healthchecks.io dead-man only, never alert on skips | | One channel: healthchecks.io success ping; a `/fail` ping with the reason on BROKEN or two-strikes. Nothing else emails. |
| Python environment | 02: ingest venv on Homebrew Python 3.14 | 06 and 09: install into the archive's 3.13 venv | One venv on 3.13 (yt-dlp needs >= 3.11; 02's reasons for a venv hold either way). |
| Event-week table | 05: hard-coded list of event weeks in the Python | 08: the owner maintains nothing; adaptive polling covers bursts | **Neither: drop the midday pass** (test 7, section 8). Nightly-only never exceeds 24 h of delay or overflows, and uploads do not track event weeks. |
| ASN guard scope | 05: check IPv4 and IPv6 egress | 01: force IPv4 with `-4` | Check the IPv4 egress; the IPv6 check is harmless but not load-bearing. |

## 4. Claims to doubt or verify before relying on them

- **json3 `_UnsafeExtensionError` (03).** *Resolved by test 1:* `--sub-format json3` wrote `FLUoowDJg4I.en.json3` on 2026.08.19 with no error. Skip 03's direct-URL fetch path; brief 02's smoke test stands as written.
- **Backfill in 12 nights (01).** 01 counted bytes at the measured 6.5 MB/s. Its own flags cap transfer at 4 MB/s and add 10 to 30 s of sleep before each download. With one invocation per video the arithmetic still fits a 6 h window; with 03's three passes it does not. Measure the first backfill night and set the ceiling from that.
- **`--sleep-interval` per format.** *Resolved by test 1:* it sleeps before each format download (three sleeps of 10 to 30 s per video) plus 5 s before the caption fetch. One call took 79 to 92 s for a 21-minute talk, so a 200-video night is about 4.5 to 5 h before transfer time on the large H.264-era files; measure the first backfill night before trusting 200.
- **audfprint install (06).** The codebase is old; compatibility with numpy 2 and Python 3.13 is unverified. Cheap to test, and the confirmation test is deferred anyway.
- **PySceneDetect decoding AV1 (09).** *(inference)* The OpenCV wheel's bundled ffmpeg may not include an AV1 decoder. Confirm it opens the stored AV1 file; otherwise use the PyAV backend or pipe frames from Homebrew ffmpeg.
- **Deepgram 10-minute timeout (03).** Applies to synchronous prerecorded requests; Deepgram also has a callback mode. Irrelevant until the segmentation project transcribes whole streams.
- **Homebrew lag "1 to 2+ weeks" (02).** Not pinned to dated evidence; the venv recommendation stands on rollback and isolation regardless.
- **Keychain `-T` on the venv Python (05).** The venv binary is a symlink; use the resolved path, as 05 already does for Full Disk Access.

## 5. Local tests, in priority order

1. Paris dry run on `wyUdpmj9-64` (04 section 7): discovery, ladder gate, download, ffprobe check, resume test. This week.
2. Single-invocation calibration on one talk with `-v` (01 Q3): count extraction requests, confirm one extraction pass and per-format sleeps.
3. json3 write on 2026.08.19 (03), and `--no-js-runtimes` for captions and `-J` (02).
4. Data API key, then 08's T1 (feed shape), T2 (classify a premiere, a stream, a VOD), T3 (full uploads walk, does it include streams).
5. Detector Test A on `FLUoowDJg4I` (09): does edge-weighted ContentDetector catch the 3:55 to 6:29 advances.
6. launchd-fired probe write to the drive with FDA granted (05).
7. audfprint install and confirmation test (06). After Paris.

## 6. Effect on the next steps

- **Paris script this week.** Use 03's selector strings, one invocation per recording with the three selectors, 01's pacing flags, 04's `was_live` plus AV1 gate and ffprobe check, keep all in-window recordings, snapshot description, comments, and the schedule page. Discovery can use the Streams tab flat listing for the dry run; switch to the Data API once the key exists.
- **Artifact list shrinks by one.** No audio fingerprint at download time.
- **Budget.** Transcription $6 to $16 per month at 40 talk-hours (03); Data API, healthchecks.io, and all tools are $0. Well inside $40.
- **Setup time.** *(inference)* venv and config 0.5 h; LaunchAgent, FDA, Keychain, ASN allow-list 2 h; Data API key 0.5 h; healthchecks 0.25 h; Paris dry run 1 h. Fits the 5 h budget.
- **Pipeline brainstorm** should start from section 3's rulings rather than from the individual reports.

## 7. Decision tests for the section 3 conflicts

Added 2026-09-16. Each test names the information that would settle the
conflict, a command shape, what to measure, and which result picks which
side. All run on the home line with the VPN off. Tests 1 to 4 use one
talk or one audio stream and cost a few requests each. Tests 5 and 6 run
during Paris Day 1 and double as brief 08's T5 and T2. Test 7 needs the
uploads walk from brief 08's T3 first, because the archive holds no
upload dates (checked `data/raw/talks.json` and `data/aie.db`).

Common pacing flags, referred to below as `$PACE`:
`-4 --sleep-requests 3 --sleep-interval 10 --max-sleep-interval 30 --sleep-subtitles 5 --limit-rate 4M --concurrent-fragments 1 --extractor-retries 0`.

### Test 1. One invocation or three passes

Information that decides it: extraction requests per shape, whether the
sleep runs once per video or once per format, whether a comma-joined
selector picks the intended three formats without merging, whether the
`after_move` rows identify each file's role, and whether a shared
`--download-archive` breaks a second pass.

```
# one call
time yt-dlp -v $PACE \
  -f "bv*[height<=1080][protocol!*=m3u8],ba[acodec^=opus][format_id!$=-drc],ba[acodec^=mp4a][format_id!$=-drc]" \
  -S "res:1080,vcodec:av01:vp9:h264,fps:30,proto" \
  --write-info-json --write-auto-subs --sub-langs en --sub-format json3 \
  -o "%(id)s.f%(format_id)s.%(ext)s" \
  --print after_move:"%(format_id)s	%(vcodec)s	%(acodec)s	%(filepath)s" \
  "https://www.youtube.com/watch?v=FLUoowDJg4I" 2> one-call.log

# three passes: same flags, one selector each, then a fourth run of the
# second selector with --download-archive a.txt after the first pass wrote it
grep -c "\[youtube\] FLUoowDJg4I: Downloading" one-call.log pass-*.log
grep -c "Sleeping" one-call.log pass-*.log
```

| Measure | Picks one call | Picks three passes |
|---|---|---|
| Extraction lines | 1 vs 3 or more | equal |
| Sleep lines in one call | 3 (per format; sets the backfill ceiling) | 1 (sleeps are per video, so three passes cost only extraction) |
| Files produced by one call | three, no merge, roles readable from the `after_move` rows | wrong audio track, a merge, or roles not resolvable |
| Archive re-run | second pass reports "already recorded" (three passes need per-pass archives) | second pass downloads normally |

### Test 2. Fragment concurrency 4 or 1

Information: whether `--limit-rate` caps the whole download or each
thread, and whether concurrency changes wall time or stall count under
the cap. Bot-signal risk cannot be measured without provoking it; this
test settles only the throughput claim.

```
URL="https://www.youtube.com/watch?v=wyUdpmj9-64"
time yt-dlp -4 --limit-rate 4M -N 1 --newline -f "ba[acodec^=opus][format_id!$=-drc]" -o "n1.%(ext)s" "$URL" > n1.log
time yt-dlp -4 --limit-rate 4M -N 4 --newline -f "ba[acodec^=opus][format_id!$=-drc]" -o "n4.%(ext)s" "$URL" > n4.log
```

Measure wall time, peak rate from the progress lines, and the number of
progress lines reporting a stall. Note the protocol column from `-F`
first; if the audio stream is plain https rather than DASH fragments,
`-N` does nothing and the question is moot for audio.

Decision: equal wall time means concurrency is moot under the cap, keep
1. If `-N 4` is several times faster, the cap is per thread and four
threads would draw four times the intended bandwidth on the household
line; keep 1 unless you decide the nightly line is idle enough to raise
the cap deliberately.

### Test 3. Infinite or finite retries

Information: what yt-dlp does when fragment retries are exhausted (skip
and continue, or abort), what exit code and file result from each, and
whether a re-run resumes to the full duration.

```
URL="https://www.youtube.com/watch?v=wyUdpmj9-64"
# variant a: default
yt-dlp -4 --limit-rate 4M --fragment-retries 2 --retry-sleep fragment:1 \
  -f "ba[acodec^=opus][format_id!$=-drc]" -o "ra.%(ext)s" "$URL"; echo "exit=$?"
# variant b: add --abort-on-unavailable-fragments
# during each run, about a minute in:
networksetup -setairportpower en0 off; sleep 30; networksetup -setairportpower en0 on
# after each run:
ls -la ra.* ; ffprobe -v error -show_entries format=duration -of csv=p=0 ra.webm
# then re-run the identical command and ffprobe again (expect 30240 s)
```

| Result | Meaning |
|---|---|
| Variant a exits 0 with a final-named file shorter than the metadata duration | finite retries silently truncate by default; finite is only safe with the abort flag |
| Variant b exits non-zero, leaves a `.part`, and the re-run resumes to full duration | finite plus abort plus resume converges; brief 01's values win |
| The re-run restarts from zero or never reaches full duration | infinite fragment retries for stream items is the pragmatic choice |

### Test 4. `.part` or `--no-part`

Information: whether an interrupted download resumes in each mode, what
the directory looks like after a kill, and whether `after_move:filepath`
is correct with `.part` on 2026.08.19 (the concern that motivated 03).

```
URL="https://www.youtube.com/watch?v=wyUdpmj9-64"
for mode in "" "--no-part"; do
  timeout 60 yt-dlp -4 --limit-rate 4M $mode -f "ba[acodec^=opus][format_id!$=-drc]" \
    -o "p${mode:+-nopart}.%(ext)s" --print after_move:filepath "$URL"; ls -la p*
  yt-dlp -4 --limit-rate 4M $mode -f "ba[acodec^=opus][format_id!$=-drc]" \
    -o "p${mode:+-nopart}.%(ext)s" --print after_move:filepath "$URL" | tee -a resume.log
done
ffprobe -v error -show_entries format=duration -of csv=p=0 p.webm p-nopart.webm
```

Measure: a "Resuming" line on the re-run, final durations, stray
intermediate files, and whether the printed path matches the real file.

Decision: both resume and the printed path is right, keep the default
`.part` and its final-name-means-complete invariant for free. Only if
`.part` mode fails to resume or leaves the wrong path does `--no-part`
earn its place, and even then the path should come from the template.

### Test 5. Dedicated stream schedule or ordinary queue item

Information: the elapsed time from a stream's end to `was_live` with the
AV1-1080p rung present. Nothing before Sept 23 can measure it; Paris Day
1 is the test and Day 2 the confirmation. Cost is about five requests
per tick, 48 ticks a day.

```
ID=<Day 1 stream ID from the feed that morning>
while true; do
  ts=$(date -u +%FT%TZ)
  yt-dlp -4 --skip-download -J "https://www.youtube.com/watch?v=$ID" 2>/dev/null \
  | jq -c --arg ts "$ts" '{ts:$ts, live:.live_status, dur:.duration,
      av1_1080:([.formats[]?|select(.vcodec|startswith("av01"))|select(.height==1080)]|length),
      opus:([.formats[]?|select(.acodec|startswith("opus"))]|length),
      aac:([.formats[]?|select(.acodec|startswith("mp4a"))]|length)}' >> stream-readiness.jsonl
  sleep 1800
done
```

If the Data API key exists by then, add the `videos.list` call for the
same ID to each tick (this is also test 6 and brief 08's T5).

| Readiness lag after the stream ends | Decision |
|---|---|
| under 13 h | a queue item in the nightly window suffices; no dedicated schedule |
| 13 to 24 h | queue item, with the event-week midday pass as the retry |
| over 24 h | keep brief 04's retry loop for stream items |

For Paris 2026 itself, run the capture as a standalone script by hand or
from a one-off launchd entry regardless; the ruling is about the
eventual pipeline.

### Test 6. Premiere classification by yt-dlp or the Data API

Information: how many scraping requests one `-J` probe costs, whether the
API and yt-dlp agree on ready or not-ready at every tick, and whether the
API ever says ready before yt-dlp can download (a false positive) or
after (extra delay). Needs a free API key.

```
# find a scheduled premiere: newest IDs from the feed, probe each once
curl -s 'https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA' | grep -o 'yt:videoId>[^<]*' | head
# then every 30 min through airing, for the premiere, one VOD, one past stream:
yt-dlp -v -4 --skip-download --print "%(live_status)s %(release_timestamp)s %(duration)s" "$URL" 2> j.log; echo "exit=$?"; grep -c "Downloading" j.log
curl -s "https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,status,liveStreamingDetails&id=$ID&key=$KEY" \
  | jq -c '.items[0] | {lbc:.snippet.liveBroadcastContent, dur:.contentDetails.duration, sched:.liveStreamingDetails.scheduledStartTime, end:.liveStreamingDetails.actualEndTime}'
```

Decision: no API false positive across the run and a flip within one
tick of yt-dlp's, the API classifies alone and yt-dlp gates only inside
the download call. Any tick where the API says ready and yt-dlp lacks
formats, yt-dlp's probe stays as the gate and the API is just the
trigger. If a `-J` probe turns out to be one or two requests, the
request-budget argument for the API weakens and simplicity favours
yt-dlp.

### Test 7. Event-week table or a queue rule

Information: the channel's per-day upload counts over the last year,
which days a threshold rule would fire, and whether the nightly window
alone ever misses the freshness target or overflows its capacity.
Upload dates are not in the archive, so run brief 08's T3 walk first
(about 23 units) and keep `videoPublishedAt` per ID.

Offline simulation in Python over that list:

- Policies: nightly only; nightly plus the four known event weeks;
  nightly plus a midday pass that fires when at least k talks published
  in the last 4 days are still queued, for k in 1, 3, 5.
- For each talk, the delay from publish time to the start of the first
  window that would take it, with a 200-per-window capacity.
- Per policy: maximum and 95th-percentile delay, midday fires on
  non-event days, talks caught by the rule that the table would have
  missed (uploads outside the four weeks) and vice versa, and any window
  overflow.

| Simulation result | Decision |
|---|---|
| Nightly-only never exceeds one day of delay and never overflows | drop the midday pass entirely; neither table nor rule is needed |
| Rule at k=3 fires on a handful of non-event days a year and matches the table's delay | rule, no table |
| Rule fires on many ordinary weekdays | table, with the rule as a backup that only fires above a higher k |

## 8. Results of tests 1 to 4 (run 2026-09-16, 19:58 to 20:20 ET)

Run from the owner's Terminal on the home line (egress AS20115 Charter),
VPN off, mains power, yt-dlp 2026.08.19, deno 2.9.6. Raw logs were in
the session scratch folder and are not kept; the numbers below are
copied from them.

### Test 1: one invocation wins, with two flags it needs

Talk `FLUoowDJg4I`, brief 01 pacing flags, brief 03 selectors.

| Run | Extraction requests | Media sleeps | Caption fetches | Wall time (s) | Outcome |
|---|---|---|---|---|---|
| One call, `%(format_id)s` in the template | 4 | 3 | 3 | 92 | ok; captions and info.json written once per format |
| One call, per-type templates | 3 | 3 | 3 | 102 | ok; one caption file on disk but still fetched three times |
| One call, per-type templates plus `--no-overwrites` | 4 | 3 | 1 | 79 | ok; captions and info.json fetched once |
| Three passes | 11 | 4 | 1 | 95 | pass 2 failed: HTTP 403 on the media URL |

- `--sleep-interval` applies before each format download, not once per video. A three-format video spends about 40 s in media sleeps and about 10 s in request sleeps whichever shape is used, so wall time is the same; the difference is extraction requests, 4 versus 11.
- With `%(format_id)s` in the main template yt-dlp fetches the caption track once per format. The fix is per-type templates plus `--no-overwrites`, after which the second and third formats report "already present".
- Pass 2 of the three-pass run reused the cached player without re-running the JS challenge solver and got a 403; passes 1 and 3 and every one-call run solved the challenge and succeeded. Observed once; cause not established, but it is the failure mode brief 02's table classifies as "re-extract once".
- A shared `--download-archive` file records the video after pass 1 and makes pass 2 skip with "has already been recorded in the archive". Three passes would need one archive file per pass.

Ruling stands: one call per video. The production shape is
`-f "VIDEO,OPUS,AAC" -o "%(id)s.f%(format_id)s.%(ext)s" -o "subtitle:%(id)s.%(ext)s" -o "infojson:%(id)s.%(ext)s" --no-overwrites`.

### Test 2: not run, because it is moot on this recording

`-J` on `wyUdpmj9-64` shows every DASH format (399 AV1, 303 VP9, 299 H.264, 251/250/249 Opus, 140/139 AAC, and their `-drc` twins) with protocol `https`, a single file fetched with range requests. Only the HLS variants (`m3u8_native`) are fragmented, and the selector excludes them. `--concurrent-fragments` has nothing to act on, so the setting is 1 by default. The Paris logger should record the protocol field, since a fresh or post-live recording may present fragmented DASH instead.

### Test 3: finite retries converge; no truncation seen

Opus stream of `wyUdpmj9-64`, 373 MB, rate cap 4M, Wi-Fi cut for 30 s at 35 s in.

| Variant | In-run result | Exit | Left behind | Re-run |
|---|---|---|---|---|
| `--retries 3 --retry-sleep http:exp=1:60` | retries exhausted after 1+2+4 s of backoff | 1 | `a.webm.part`, 140 MB | resumed at byte 140108898, full duration 30398 s |
| `--retries 10 --retry-sleep http:exp=1:60` | survived the outage inside the run | 0 | complete file | "already been downloaded" |

Because the format is a single https file, the downloader resumes with a
range request rather than skipping a fragment; no truncated file with a
final name appeared in either variant. Ruling stands: finite. Use
`--retries 10 --retry-sleep http:exp=1:60` so a 30 s blip is absorbed
in-run, and keep `--fragment-retries 10 --abort-on-unavailable-fragments`
for any fragmented format. Never infinite.

### Test 4: keep `.part`

Same stream, SIGTERM at 40 s (SIGINT is ignored by background jobs in a non-interactive shell, so the first attempt ran to completion and had to be repeated).

| Mode | After kill | Re-run on the partial | Re-run on a complete file |
|---|---|---|---|
| default `.part` | `a.webm.part`, 157 MB; exit 143 | resumed, full duration, correct `after_move` path | "has already been downloaded", exit 0 |
| `--no-part` | `a.webm`, 157 MB, final name; exit 143 | resumed, full duration, correct `after_move` path | **HTTP 416 Requested range not satisfiable, exit 1** |

Both modes resume. `--no-part` loses the final-name-means-complete
invariant and, worse, makes an idempotent re-run on a finished file fail,
which the manifest logic would have to special-case. Ruling stands: keep
`.part`; derive paths from the template.

### Brief 08 checks T2, T3, T4 (run 2026-09-16 20:40 ET, 27 quota units)

Run with the Data API key from the login Keychain, sent as a header.

- **T2, classification.** Seventeen IDs in one `videos.list` call (the
  Hugging Face talk, the Paris 2025 Day 2 stream, and the 15 feed
  entries): every one returned, all `liveBroadcastContent: none` with a
  real duration and `uploadStatus: processed`. Videos that were premieres
  or streams carry `liveStreamingDetails` with scheduled, actual start,
  and actual end times; plain uploads do not. The Paris stream shows
  actual start 07:27Z and end 16:10Z on 2025-09-24, which is the ground
  truth the Paris 2026 logger will compare against. No unaired premiere
  existed in the feed at run time, so the `upcoming` state is still
  unobserved through the API (test 6 on Sept 23).
- **The feed rewrites `published` after a premiere airs.** "Stop
  Chunking Like It's 2022" showed `published` 2026-09-15T07:36Z while
  unaired (brief 08's observation) and 2026-09-16T17:00:06Z, its air
  time, once aired. The API's `publishedAt` matches the air time. So
  `published` is the schedule time before airing and the air time after.
- **The channel releases on a 30-minute schedule.** The 15 feed entries
  are timed 13:00, 13:30, ... 17:00Z on two consecutive days.
- **T3, uploads walk.** 24 pages, 1,188 items, `totalResults` 1,188, zero
  private or deleted placeholders, every item has `videoPublishedAt`,
  zero ordering inversions across 1,187 adjacent pairs, oldest
  2023-10-10. All 15 feed IDs and the stream recording are in the list,
  so the uploads playlist includes stream recordings and brief 04's
  Streams-tab fallback is not needed. Brief 08's uncertainty 1 is
  resolved for aired content.
- **T4, playlists.** 89 playlists holding 2,598 memberships. The three
  largest are the per-event "Complete Playlist" lists (368, 284, 247).
  A full membership sweep is about 89 plus 60 page calls, roughly 150
  units, so the daily sweep is affordable.

### Test 7: drop the midday pass

Simulated over the 654 uploads of the last twelve months
(2025-09-16 to 2026-09-16) from the T3 walk, using the edition dates in
the archive database. Nightly window 01:00 ET, capacity 200; midday pass
13:00 ET, capacity 60; delay measured from publish time to the start of
the window that takes the item. Event weeks are each event's dates plus
seven days.

| Policy | Median delay (h) | p95 (h) | Max (h) | Midday fires | Fires outside event weeks | Items taken at midday | Nights with leftover |
|---|---|---|---|---|---|---|---|
| Nightly only | 12.5 | 18.5 | 24.0 | 0 | 0 | 0 | 0 |
| Nightly + event-week table | 11.8 | 16.0 | 24.0 | 60 | 0 | 59 | 0 |
| Nightly + rule, k=1 | 4.1 | 12.0 | 12.0 | 132 | 105 | 332 | 0 |
| Nightly + rule, k=3 | 9.5 | 15.0 | 24.0 | 34 | 30 | 182 | 0 |
| Nightly + rule, k=5 | 10.6 | 16.0 | 24.0 | 19 | 17 | 132 | 0 |

Facts behind the table:

- Uploads are spread out: 654 items on 171 days, at most 25 in a day,
  only 3 days with 15 or more. The window's capacity never binds.
- Uploads do not track event weeks. Only 125 of 654 fell inside an event
  week plus seven days; the bursts arrive one to eight weeks after an
  event (July 2026 had 176 uploads for a World's Fair that ended July 2).
  The table therefore fires on 60 days and accelerates 59 items.
- Uploads cluster in US business hours: about 70% between 09:00 and
  14:00 ET, so the nightly window takes the day's talks about 12 hours
  later, and the worst case is 24 hours.

Ruling changes: **no midday pass at all.** Nightly-only meets the 4-day
freshness target with three days to spare for transcription and
correction, never overflows, and never downloads on the household line
in daytime. Brief 05's LaunchAgent loses its event-week table and its
second schedule; brief 08's adaptive feed polling stays as designed. The
only daytime work left is the keyless hourly feed poll and the 1-unit
API classification. If the freshness target ever tightens to under a day,
the k=3 rule is the fallback, not the table.

### Tests 5 and 6: pending Sept 23

Both run as one logger on Paris Day 1, with the Data API key now in
place. Nothing else is needed for them.
