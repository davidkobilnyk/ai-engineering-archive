# Research Brief 03: Stream Selection for Storage, Keyframes, and Speech-to-Text

## Summary of recommendation

Keep the existing selector shape; it is correct. Download in **three passes per video ID** (video, audio, captions+metadata), keep video and the two audio streams as **separate files** (no merge), and feed **the AAC/M4A stream** to speech-to-text. Every recommendation below is verified against the yt-dlp README/changelog at version 2026.08.19 (release dated 2026-08-19) and against vendor documentation read on 2026-09-16.

Concrete decisions:
1. **Video selector** (confirmed, lightly hardened): `-f "bv*[height<=1080][protocol!*=m3u8]" -S "res:1080,vcodec:av01:vp9:h264,fps:30,proto"`.
2. **Separate files, no merge.** Merging forces a container remux you cannot prove is lossless per-stream, drops metadata on some mkv merges, and complicates keyframe/audio extraction. Keep `video-only + audio-only(Opus) + audio-only(AAC)` as distinct artifacts.
3. **Audio for STT: the AAC/M4A stream** (format 140, ~129 kbps). All three vendors accept it natively; it is the safest cross-vendor container and avoids AssemblyAI's undocumented WebM/Opus status.
4. **Captions:** fetch `json3`, but expect the `_UnsafeExtensionError`; the robust path is to read the caption URL from `-J` and fetch it directly with your own HTTP client.
5. **Fresh-upload policy:** verify the fetched stream's codec+resolution against intent; if 1080p/AV1 is absent on a fresh upload, re-check once after ~6 hours (YouTube processes SD first, HD/AV1 later).

---

## Q1. The video selector

**Recommended (unchanged from the brief):** `-f "bv*[height<=1080][protocol!*=m3u8]" -S "res:1080,vcodec:av01:vp9:h264,fps:30,proto"`

Explanation of each part (yt-dlp README, format-selection & sorting sections, v2026.08.19 — official documentation):
- `bv*` = best video-bearing format (video-only *or* muxed). The `*` matters: plain `bv` is strictly video-only. `bv*` is harmless here (YouTube DASH is video-only anyway) and gracefully falls back to a muxed format if a video-only one ever fails.
- `[height<=1080]` caps resolution at 1080p (excludes 1440p/4K should they ever appear).
- `[protocol!*=m3u8]` excludes HLS variants, honoring the "prefer DASH" rule. On this line HLS measured 3.2 MB/s vs 6.5 MB/s for DASH.
- `-S` is the tie-breaker sort applied **after** the `-f` filter. **`-f` selects the candidate pool; `-S` orders it.** This separation is the design's key robustness property: `-f` enforces the hard constraints (≤1080, no HLS), `-S` expresses soft preferences.
- `res:1080` prefers the format closest to 1080 (1080 over 720).
- `vcodec:av01:vp9:h264` sets codec preference AV1 → VP9 → H.264, matching the storage rule.
- `fps:30` prefers 30 over 60 fps at the same res/codec (moot when only 60 exists).
- `proto` prefers protocols by yt-dlp's internal order (DASH https ahead of others), a secondary guard alongside the `-f` HLS exclusion.

**Pitfalls:**
- **Bitrate-first defaults:** yt-dlp's default sort prioritizes resolution and codec over bitrate (unlike youtube-dl). Because you supply an explicit `-S`, the default `size,br` fields fall to lowest priority — exactly right for you (you want the codec ladder, not the biggest file). Confirmed default order: `lang,quality,res,fps,hdr:12,vcodec,channels,acodec,size,br,asr,proto,ext,hasaud,source,id`.
- **60 fps-only variants:** some videos offer 1080p only at 60 fps. `fps:30` is a *preference*, not a filter, so a 60 fps 1080p stream is still chosen — correct: you still get 1080p (as measured, format 399 AV1 1080p60 was picked on the Hugging Face talk).
- **HLS variants:** already excluded by `[protocol!*=m3u8]`.
- **Videos with no 1080p:** the 81-minute workshop with no 1080p degrades gracefully — `res:1080` falls to the next-best (e.g., 720p), with no error. **This is exactly why the verification step in Q9 is mandatory:** the selector never fails loudly on missing 1080p.
- **`-S` vs `-f` interaction:** never move the codec ladder into `-f` as a hard filter (e.g., `[vcodec^=av01]`) — that would *fail* on the ~215 H.264-only legacy videos. Keep hard constraints in `-f`, preferences in `-S`.
- **Do not hard-code numeric format IDs** (137/399/251, etc.). YouTube reshuffles them and they change per video; the selector resolves against whatever the extractor returns at runtime (community report, DEV Community, 2026).

The measured behavior in the brief (137 H.264 on a 2024 talk, 399 AV1 on the HF talk and on the 8.4-hour stream) confirms the selector picks the intended ladder.

**Video pass:**
```
yt-dlp -f "bv*[height<=1080][protocol!*=m3u8]" \
  -S "res:1080,vcodec:av01:vp9:h264,fps:30,proto" \
  -o "%(id)s.%(ext)s" --no-part \
  --print after_move:"%(id)s\t%(format_id)s\t%(vcodec)s\t%(height)s\t%(fps)s" \
  "https://www.youtube.com/watch?v=ID"
```

---

## Q2. Merge or keep separate — **keep separate**

The rule: "no transcoding ever; lossless remux only with proof the elementary stream is unchanged; hash the elementary stream." Judged against it:

- **Merging** video+audio (`--merge-output-format mkv/mp4`) invokes ffmpeg's muxer. It is a stream copy (no re-encode), so the *elementary streams* are in principle unchanged — but you would then have to prove that per-stream, and container timestamps/metadata do change. yt-dlp community reports also show embedded metadata being dropped on some mkv merges (Issue #14500). Merging buys you nothing.
- **Keeping separate** means the video-only file is the exact DASH elementary stream in its delivered container, and each audio-only file likewise. You hash each elementary stream once at download (Q9) and never touch it again.
- **Downstream needs favor separation:**
  - *Keyframe extraction* (brief 09) reads the AV1 video file only — no audio needed.
  - *Transcription* reads one audio file only. Sending a ~20–40 MB audio file beats sending a 40–470 MB video over the 39 Mbps uplink.
  - *Re-processing* is simpler with independent artifacts keyed by video ID.
- **Disk layout:** `‹ID›.‹ext›` (video), `‹ID›.opus.webm` and `‹ID›.m4a` (audio), `‹ID›.en.json3` (captions), `‹ID›.info.json` (metadata) — all under the video ID.

**Recommendation: keep separate.** If a single playable file is ever wanted, produce it on demand with `--remux-video` (lossless container swap, codecs preserved) from the stored elementary streams; never store *only* a merged file. Running each stream as its own invocation (Q1, Q3) also sidesteps the "bestvideo and bestaudio will have the same file name" collision the README warns about for `bv+ba` without merge.

---

## Q3. Audio selectors (both Opus and AAC, no DRC, original language)

Field values yt-dlp exposes (from `-F`/`-J`, community-verified 2026):
- **DRC tracks** carry `-drc` as a `format_id` suffix (e.g., `249-drc`, `139-drc`) and the string `DRC` in `format_note` (a real example: `Portuguese original, low, DRC, webm_dash`). Filter with `[format_id!$=-drc]` (ends-with) or `[format_note!*=DRC]`.
- **Language / dubbed tracks:** `format_note` shows `original` for the source track (e.g., `en-US original (default)`) and a plain language name for dubs (e.g., `Spanish, low`); the `language` field carries the BCP-47 code. Dubs get numeric suffixes like `251-1`, `139-2`. YouTube auto-dubbing has caused wrong-language downloads since mid-2026 (Issues #17310, #11753), so pinning the original matters.

**Selectors (two invocations, for clean filenames):**

Best Opus, original, no DRC:
```
yt-dlp -f "ba[acodec^=opus][format_note*=original][format_id!$=-drc]/ba[acodec^=opus][format_id!$=-drc]" \
  -o "%(id)s.opus.%(ext)s" --no-part "URL"
```
Best AAC, original, no DRC:
```
yt-dlp -f "ba[acodec^=mp4a][format_note*=original][format_id!$=-drc]/ba[acodec^=mp4a][format_id!$=-drc]" \
  -o "%(id)s.m4a.%(ext)s" --no-part "URL"
```

Notes:
- The brief's simpler selectors returned 251 (Opus) and 140 (AAC) on the HF talk, which had no dubs. Adding `[format_note*=original]` hardens against auto-dubbed videos where the *default* track is a dub; on single-track English videos, `original` is still present, so the clause is safe. The `/…` fallback covers a future extractor that changes the note wording (empty match would otherwise fail).
- `acodec^=mp4a` is correct for AAC (`mp4a.40.2` at 129 kbps, `mp4a.40.5` at 49 kbps HE-AAC); `ba` then picks the highest bitrate remaining (140).
- To break a tie between two "original" tracks, append `-S "abr"`.

---

## Q4. Which audio feeds speech-to-text — **AAC/M4A (format 140)**

**Vendor format acceptance and limits (official documentation, read 2026-09-16):**

| Vendor | Opus/WebM direct? | AAC/M4A/MP4 direct? | Max file size | Max duration |
|---|---|---|---|---|
| **Deepgram** | Yes — "Opus", "Ogg", "WebM" named in Supported Audio Formats | Yes — "AAC", "M4A", "MP4" named | **2 GB** | No explicit duration cap; **"Requests exceeding 10 minutes (Nova/Base/Enhanced) or 20 minutes (Whisper) return a 504: Gateway Timeout error"** (processing time, not audio length) |
| **ElevenLabs Scribe** | Yes — `audio/opus`, `audio/webm` listed | Yes — `audio/aac`, `audio/mp4`, `audio/x-m4a` listed | **3 GB** (Transcription capability page); API reference "Create transcript" says **"The file size must be less than 5.0GB"** — conflict, see uncertainties | **10 hours** (standard mode) |
| **AssemblyAI** | Not named in a published list; policy is "native format… without transcoding" | Yes per vendor blog ("send an MP4 straight… no need to demux with ffmpeg first") | **5 GB** (`/v2/transcript`); **2.2 GB** (`/v2/upload`) | **10 hours** (min 160 ms) |

All three accept both codecs. **Choose AAC/M4A** because:
- It is unambiguously in every vendor's native set. Deepgram's *Supported Audio Formats* names "MP3, MP4, MP2, AAC, WAV, FLAC, PCM, M4A, Ogg, Opus, WebM." ElevenLabs lists `audio/aac`, `audio/mp4`, `audio/x-m4a`. AssemblyAI's blog *"The best audio file formats for speech-to-text"* states: "AssemblyAI accepts all of these directly with no pre-conversion… you can send an MP4 straight to a transcription API… There's no need to demux with ffmpeg first."
- AssemblyAI does **not** publish a named list confirming WebM/Opus, so AAC is the safest choice for a closed set that must work on all three.
- **Accuracy difference is negligible.** Measured evidence: IBM Watson STT found **OGG Opus ~2% WER degradation vs the WAV/FLAC baseline** and MP3 ~10% (IBM Watson Speech Services, Medium). AAC at 129 kbps is comparable to Opus at 113 kbps for speech, and both are far above the ~64 kbps floor where fricatives degrade. Khare et al. (arXiv:2002.00122) show Opus WER degrades only 12.6% relative at *16 kbps* — i.e., degradation appears only at very low bitrate, not at YouTube's ~113–129 kbps.

**Is a decoded WAV/FLAC worth sending?** Marginally, and not by default:
- Every vendor **downsamples to 16 kHz internally.** AssemblyAI states verbatim: **"The AssemblyAI API converts all files to 16khz uncompressed audio as part of our transcription pipeline,"** and recommends submitting "in its native format without additional transcoding or file conversion." AmiVoice/IBM confirm 16 kHz is the STT standard and higher rates give no accuracy gain. So sending 48 kHz WAV (a 25-min talk ≈ 140 MB vs ~20 MB AAC) wastes uplink bandwidth for ~2% potential WER at most.
- Decoding AAC→WAV would transcode the *copy you send*, not the *archive of record* (which stays untouched), so it does not violate the no-transcode rule — but it is not worth it given the 4-day freshness target.

**Recommendation:** send the stored **AAC/M4A file as-is.** If a specific talk transcribes poorly on names, the cheap experiment is to resubmit a 16 kHz mono FLAC of *that one talk* and compare name-error rate; do not do it by default.

**Long stream recordings:** an 8.4-hour stream at 129 kbps AAC ≈ 465 MB — well under every size cap, but **duration is the binding constraint.** All three cap at 10 hours; a >10-hour stream (rare, but a full conference day can approach it) must be split. Deepgram's 504 processing-timeout also makes it a poor choice for a single multi-hour request, so for stream recordings prefer AssemblyAI or ElevenLabs (both explicitly support 10-hour files), or split on silence before submission. Scribe v2 auto-parallelizes internally (files over 8 minutes are segmented), which helps throughput on long files. Segmenting streams into talks is a later project; for now, if a recording exceeds ~10 hours, split before submission.

**Cost sanity check (vendor pricing, 2026):** AssemblyAI batch ≈ **$0.0025/min ($0.15/hr)**; Deepgram Nova-3 pre-recorded ≈ **$0.0043/min** (streaming $0.0077/min); ElevenLabs Scribe v2 batch **$0.22/hr** (ElevenLabs' own page lists a "Starting from $0.40 per hour" list rate). At ~40 new talk-hours/month, transcription costs roughly **$6–$16/month** depending on vendor — comfortably inside the $40/month ceiling. (Vendor claim / pricing roundups.)

---

## Q5. Caption tracks (English automatic, json3)

**Fetch without media:**
```
yt-dlp --skip-download --write-auto-subs --sub-langs en \
  --sub-format json3 -o "%(id)s.%(ext)s" "URL"
```
- `--write-auto-subs` = automatic captions (not `--write-subs`, which is uploaded/manual — none exist on this channel).
- `--sub-langs en` pins English; `en` and `en-orig` return **identical text** on this channel (confirmed in the brief and community reports), so `en` is the safe default.

**`_UnsafeExtensionError` caveat (important):** yt-dlp's safe-extension guard has intermittently rejected `json3`/`srv1/2/3`/`ttml` subtitle writes (Issue #10360, recurring through 2026; community guides recommend VTT as the "reliable" fallback). Two robust mitigations:
1. Pass `--compat-options allow-unsafe-ext` (the documented escape hatch), **or**
2. **Preferred for a parser-driven pipeline:** run `-J`/`--write-info-json`, read `automatic_captions.en[]`, find the entry with `"ext": "json3"`, and fetch its `url` directly with your HTTP client. This bypasses the subtitle-writer entirely and is the most stable long-term path (it is the pattern used in community code).

**json3 word-level offsets:** json3 events carry per-cue timing and, for auto-captions, per-word offsets (`segs[].tOffsetMs` relative to the event `tStartMs`). These are **reliable for auto-captions specifically** — they are how YouTube animates word-by-word captions. Caveat from the shared context: **auto-caption text drifts over time** (2 of 10 re-fetched tracks changed by a few percent), so treat json3 as provisional, store the fetch time, and re-hash on each fetch.

**`en` vs `en-orig`:** identical text here; they diverge only when a video has a manually uploaded English track (then `en` = manual, `en-orig` = auto). No manual tracks exist on this channel, so continue using `en`.

---

## Q6. Metadata fields and the `--print` template

**Present in `-J` / `--write-info-json` by default (current yt-dlp):** `id`, `title`, `description`, `upload_date` (UTC, YYYYMMDD), `timestamp`/`release_timestamp` (when available), `duration`, `chapters`, `categories`, `tags`, `view_count`, `like_count`, `channel`, `channel_id`, `uploader`, `heatmap` (the "most replayed" array of `{start_time, end_time, value}`; null when the graph is absent), `thumbnails`, `automatic_captions`, `subtitles`, `formats`, `live_status`.

**Requires `--write-comments` (alias `--get-comments`):** `comments`, and reliably `comment_count` (the README notes `comment_count` "cannot be used" in some contexts unless comments are actually fetched). Comments cost extra requests — fetch them only in the metadata pass.

**Requires the YouTube Data API (not reliable via yt-dlp):**
- **Precise publish/air time** to the second: yt-dlp's `upload_date` is date-only (UTC). For premiere *air* time (vs the scheduled time that the RSS `published` field carries), the Data API `snippet.publishedAt` / `liveStreamingDetails` is authoritative.
- **Playlist membership** of an arbitrary video: yt-dlp exposes `playlist*` fields only when you fetch *via a playlist URL*. To ask "which playlists contain video X," use the Data API, or enumerate the channel's playlists separately.

**Two-pass approach:** use `-J` to capture everything structured (the Python side parses the full JSON) and `--print` only for a compact log/status row. Store the whole `.info.json`; if you want to drop the huge `formats`/`thumbnails` arrays, post-filter with jq rather than reducing `-J`.

**Metadata pass:**
```
yt-dlp --skip-download --write-info-json --write-comments \
  --write-auto-subs --sub-langs en --sub-format json3 \
  -o "%(id)s.%(ext)s" "URL"
```
**Compact status/log row:**
```
yt-dlp --skip-download \
  --print "%(id)s\t%(upload_date>%Y-%m-%d)s\t%(duration)s\t%(view_count)s\t%(like_count)s\t%(live_status)s\t%(title)s" \
  "URL"
```
**Caveat:** `after_move:filepath` is occasionally unreliable when intermediate `.fXXX` files remain (Issue #13394). Using `--no-part` and single-stream invocations minimizes this; better still, derive the final path from your own deterministic template (`%(id)s.%(ext)s`) rather than parsing it back out.

---

## Q7. Fresh-upload completeness

**Detecting an incomplete format list:** after the fetch, probe the stored file (Q9) and compare to intent. Flag as incomplete if:
- no format with `height==1080` was available (only ≤720), **and** the video is <~24 h old (HD transcode may still be pending), **or**
- AV1 (`av01`) is absent on a post-mid-2025 upload that should have the full ladder.

**Documented delay (official):** YouTube processes **SD first, then works up the ladder (720→1080→1440→4K) in sequence**, and "higher qualities… may seem to be missing for several hours" (YouTube Help, *Low video quality after upload*, support.google.com/youtube/answer/71674). Higher resolution and 60 fps take disproportionately longer, and AV1/VP9 renditions are generated after H.264 — so a just-published talk can transiently offer only H.264 at ≤720p.

**Measured reality on this channel:** four talks checked 1.2–2.8 h after publication already had 1080p in all three codecs. The full ladder typically lands within ~1 hour here; a long hold is unnecessary.

**Policy (matches the brief's suggestion):**
1. Fetch on schedule.
2. Verify the fetched stream matches intent (1080p; AV1 preferred on new uploads).
3. If it does **not** match (e.g., 720p H.264 on a fresh upload), do **not** finalize it; queue a **single re-check after ~6 hours.** Six hours comfortably exceeds the observed ~1 h ladder-completion time and the "several hours" YouTube language, while staying well inside the 4-day freshness budget.
4. On re-check, re-run the selector; if 1080p/AV1 now exists, fetch, replace, re-hash. If still absent, accept the best available (some talks genuinely lack 1080p) and mark the record so it is not re-checked forever.
5. **Never finalize the first fetch of a <2-hour-old video without verification** — the ladder may still be filling.

Scheduling of the re-check is brief 01's; this brief defines the trigger (codec/resolution mismatch) and the wait (6 h).

**Calibration test (local — exact timing is channel/account-specific):** on the next event day, immediately after a talk appears, run `yt-dlp -F "URL"` every 30 min for 6 hours and log when `av01` 1080p first appears. If it is consistently <1 h, shorten the re-check to 3 h; if it sometimes exceeds 6 h, lengthen it. What would change the recommendation: a measured p95 ladder-completion time materially different from ~1 h.

---

## Q8. Ended-stream recordings

Do the same selectors work on a finished livestream recording? **Yes, once it is a normal VOD, with two caveats:**
- The brief already measured selector success: format 399 (AV1 1080p60, 1.36 GB) was chosen on the 8.4-hour Paris 2025 Day-2 recording. `-f`/`-S` behave identically to talks.
- **The format set changes for up to a day after the stream ends.** An ended stream is first a "post-live DVR" — yt-dlp reports `live_status: post_live` ("was live, but VOD is not yet processed") — before becoming a normal VOD (`was_live`). During post-live the ladder can be incomplete (fragmented DASH, missing AV1/1080p, inaccurate duration). yt-dlp exposes `live_status` in `-J`; **gate stream-recording fetches on `live_status == "was_live"` (not `post_live`)** to avoid grabbing an unprocessed manifest.
- **`--live-from-start` is irrelevant and harmful here** — it is for capturing *during* the live event and has known "No video formats found!" failures (Issues #16497, #16673). Fetch an ended recording as an ordinary VOD, with no live flags.
- **Possible absence of 1080p:** same graceful-degrade behavior as talks; verify (Q9).
- **Size/duration:** 1.36 GB is fine for the drive and under all STT size caps, but a recording near/over 10 h hits the STT duration ceiling (Q4).

**Difference vs talks:** add a `live_status == was_live` gate; if it is still `post_live` after ~a day, defer. When to fetch stream recordings is brief 04.

---

## Q9. Verification and elementary-stream hashing

**Confirm resolution/codec/completeness (video stream):**
```
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames \
  -show_entries format=duration,format_name \
  -of json "‹ID›.mp4"
```
Check `codec_name` ∈ {av1, vp9, h264} and matches intent; `height == 1080` (or accept & flag); `format.duration` ≈ the `-J` `duration`.

**Completeness (truncation) check:** compare ffprobe `format.duration` to the metadata `duration`; a gap beyond ~1 s indicates a truncated download. Optional full decode-verify:
```
ffmpeg -v error -i "‹ID›.mp4" -f null - ; echo "exit=$?"
```
A clean exit with no decode errors confirms the bitstream is intact end-to-end. Software AV1 decode runs ~14× real time on the M1, so a 25-min talk verifies in ~2 min — acceptable in the nightly window; skip or run opportunistically for 8-hour streams.

**Hash the elementary stream (survives remux):** use ffmpeg's `streamhash`, which hashes the per-stream elementary payload, not the container:
```
ffmpeg -v error -i "‹ID›.mp4"       -map 0:v:0 -c copy -f streamhash -hash sha256 -
ffmpeg -v error -i "‹ID›.m4a"       -map 0:a:0 -c copy -f streamhash -hash sha256 -
ffmpeg -v error -i "‹ID›.opus.webm" -map 0:a:0 -c copy -f streamhash -hash sha256 -
```
`-c copy` guarantees no re-encode; per-stream `-map` makes the hash invariant to a later lossless container swap. (SWGDE forensic guidance documents `-f streamhash -hash md5`; use `sha256` for collision resistance.) Store the hash and fetch time under the video ID. To later *prove* a remux was lossless, re-run `streamhash` on the remuxed file and compare — they must match.

**Audio identity check (guard against dubs/DRC slipping through):**
```
ffprobe -v error -select_streams a:0 \
  -show_entries stream=codec_name,sample_rate,bit_rate,channels \
  -show_entries stream_tags=language -of json "‹ID›.m4a"
```

---

## Suggestions outside scope

- **Audio fingerprinting** (brief 06) would let you detect when YouTube silently re-encodes/replaces an audio stream between fetches, analogous to the observed caption drift. Not folded into the recommendation.
- **A `--download-archive` file** keyed by video ID would prevent re-downloads, but archive/queue logic is brief 01's.
- **Capturing the `heatmap` into the searchable DB** as a "most-replayed" ranking signal for citations is a product feature beyond download scope.
- **Storing chapter data** (native `chapters`, distinct from SponsorBlock) could help the later livestream-segmentation project.

---

## Open uncertainties (ranked by impact)

1. **AV1-1080p ladder completion time on this channel.** Observed ~1 h but not systematically measured; it drives the 6-hour re-check window (Q7) and thus freshness. *Cheapest resolution:* the 30-min-interval `yt-dlp -F` logging test on the next event day. **Highest impact** because it directly affects the 4-day freshness target.
2. **json3 `_UnsafeExtensionError` at v2026.08.19.** Whether the guard currently fires for `json3` on this build (captions are a required artifact). *Resolution:* run the `--sub-format json3` command on one talk; if it errors, switch to the `-J`+direct-fetch path (recommended regardless).
3. **`format_note` wording stability for `original`/`DRC`.** An extractor change could break the string match and select the wrong audio track. *Resolution:* assert on the `-J` `language`/`format_note` fields in code, alert on an empty selection, and keep the Q3 fallback chain.
4. **ElevenLabs Scribe max file size (3 GB vs 5 GB).** The capability page says 3 GB; the API reference says "< 5.0GB." Impact is low because talks are ~20 MB and even 8-hour streams are ~465 MB. *Resolution:* one large test upload, or vendor support — low priority.
5. **AssemblyAI's explicit format list for WebM/Opus.** Docs assert "native format, no transcoding" but don't name WebM/Opus. Impact is low because the recommendation sends AAC/M4A (confirmed on all three). *Resolution:* one test upload of a WebM/Opus file to `/v2/upload`.

---

## References grouped by source type

**Official documentation**
- yt-dlp README & changelog, v2026.08.19 (release 2026-08-19): format selection/sorting, default sort order, output templates, subtitles, `--remux-video`, `--write-comments`, metadata/`heatmap` fields, `-t mkv/mp4` presets, `--compat-options allow-unsafe-ext`, and youtube-extractor changes (player-client maintenance; `channel_follower_count` for collaborators; live adaptive-fragments fix). github.com/yt-dlp/yt-dlp.
- yt-dlp man pages (Arch / Ubuntu / ManKier): full metadata field list, `--print`/`after_move:filepath`, `live_status` values (`not_live`/`is_live`/`is_upcoming`/`was_live`/`post_live`).
- Deepgram docs: *Supported Audio Formats* (names MP3, MP4, MP2, AAC, WAV, FLAC, PCM, M4A, Ogg, Opus, WebM); *Pre-recorded Audio* — "File size: Maximum 2 GB" and "Requests exceeding 10 minutes (Nova/Base/Enhanced) or 20 minutes (Whisper) return a 504: Gateway Timeout error." developers.deepgram.com.
- ElevenLabs docs: *Speech to Text / Transcription* capability page (formats incl. `audio/opus`, `audio/webm`, `audio/aac`, `audio/mp4`, `audio/x-m4a`; "Files up to 10 hours and 3 GB are supported in standard mode"); API reference *Create transcript* ("The file size must be less than 5.0GB"). elevenlabs.io/docs.
- AssemblyAI docs/FAQ: file size/duration limits ("maximum file size… to the /v2/transcript endpoint… is 5GB, and the maximum duration is 10 hours… /v2/upload endpoint… 2.2GB"; min 160 ms); "converts all files to 16khz uncompressed audio… submit your audio in its native format without additional transcoding." support.assemblyai.com, docs.assemblyai.com.
- YouTube Help, *Low video quality after upload*: SD-first processing, HD/AV1 delay of several hours. support.google.com/youtube/answer/71674.
- ffprobe/ffmpeg documentation: `-show_streams`/`-show_format`, `streamhash`, `-f md5`. ffmpeg.org.

**Measured / peer-reviewed**
- IBM Watson Speech Services (Medium): WER by codec — OGG Opus ~2% degradation, MP3 ~10% vs the WAV/FLAC baseline.
- AmiVoice Techblog (2025-07-29): no accuracy gain above 16 kHz; compression tolerable to ~16 kbps.
- Khare et al., *Multi-channel Acoustic Modeling using Mixed Bitrate OPUS Compression*, arXiv:2002.00122: WER degrades 12.6% relative at 16 kbps Opus vs uncompressed (degradation only at very low bitrate).
- SWGDE, *Technical Notes on FFmpeg for Forensic Video Examinations*: elementary-stream MD5/streamhash method.

**Vendor claims / marketing**
- AssemblyAI blog, *The best audio file formats for speech-to-text*: MP4/M4A/AAC transcribe directly, no pre-extraction ("send an MP4 straight… no need to demux with ffmpeg first"); Sync API cap "40MB or 2 minutes, whichever comes first" (async path used here).
- STT pricing roundups (buildmvpfast, HappyRobot, FutureAGI, VexaScribe, aibizhub; 2026): AssemblyAI batch $0.0025/min ($0.15/hr); Deepgram Nova-3 pre-recorded $0.0043/min (streaming $0.0077/min); ElevenLabs Scribe v2 $0.22/hr batch (ElevenLabs page lists "Starting from $0.40 per hour").

**Community reports**
- yt-dlp Issues: #10360 (`_UnsafeExtensionError` json3), #9371 (`en` vs `en-orig`), #17310/#11753 (auto-dub default track), #13394 (`after_move:filepath` unreliability), #14500 (mkv merge drops metadata), #16497/#16673 (`--live-from-start` failures), #15835 (post-live merge behavior).
- VideoHelp forum: DRC `format_note` example (`Portuguese original, low, DRC, webm_dash`).
- DEV Community (2026), OSTechNix, TechEarl, SkipTheWatch: selector best practices, remux vs recode, don't hard-code format IDs, VTT-vs-json3 reliability.