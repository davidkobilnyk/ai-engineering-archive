# Audio Backfill: Design

Date: 2026-09-16
Status: approved in brainstorming, awaiting written review
Inputs: `docs/research/download-phase/reports-review.md` (rulings and test
results), briefs 00 to 05 and their reports, the calibration run below.

## 1. Purpose

Fetch and keep, for every talk in the corpus, the two audio streams of
record (best Opus, best AAC), the English automatic caption track, and a
metadata snapshot, on the archive drive, keyed by YouTube video ID. This is
the first phase of the download pipeline: brief 01 orders the backfill
"audio for the whole corpus first, video later". It is also the audio the
transcription benchmark and the provisional-transcript path will consume.

The job runs unattended in the nightly window under the guards from brief
05, capped at 200 videos per night, so the corpus (about 1,100 talks, about
40 GB) finishes in about six nights.

Out of scope: video streams, keyframes, the channel watcher, the Data API,
transcription, yt-dlp auto-update, stream recordings. The pieces built here
(invocation builder, guards, records, status) are designed so the video
backfill and the watcher reuse them.

## 2. Calibration run (2026-09-16, evidence for the choices below)

Run from the owner's terminal on the home line (AS20115, VPN off) with the
exact invocation in section 5, yt-dlp 2026.08.19 in the project venv, Deno
2.9.6, writing to `/Volumes/Archive/_calibration/`.

| Talk | Wall | Opus | AAC | Captions | ffprobe vs info.json duration |
|---|---|---|---|---|---|
| `FLUoowDJg4I` (2026) | 55 s | 251, 113 kbps, 17.5 MB | 140, 129 kbps, 20.0 MB | json3, 1,146 events | 1236.7 vs 1237 |
| `knDDGYHnnSI` (2024) | 78 s | 251-12, 141 kbps, 20.3 MB | 140-12, 129 kbps, 18.7 MB | json3, 912 events | 1154.4 vs 1154 |

Findings:

- **The original-language clause is load-bearing.** The 2024 talk carries
  12 auto-dubbed audio tracks (65 audio formats). Without
  `[format_note*=original]`, `ba` would have chosen the Malayalam dub, which
  has the highest bitrate. With it, both talks yielded the `en-US` original.
  Dubbed videos give every track, including the original, a numeric suffix
  (`251-12`), so filenames must come from `%(format_id)s`, not a fixed id.
- `ffprobe` reports codec, duration, and language on both containers;
  `ffmpeg -f streamhash` hashes both.
- The only stderr line is `WARNING: The extractor specified to use
  impersonation for this download, but no impersonate target is available`.
  Benign (curl_cffi not installed; brief 01 forbids client tricks); the
  classifier ignores it.
- Guard lookups that work from the owner's shell: public IPv4 from
  `dig -4 +short TXT o-o.myaddr.l.google.com @ns1.google.com`, ASN from
  `dig +short TXT <reversed-ip>.origin.asn.cymru.com` (returned `20115`),
  default route from `route -n get default`, power from `pmset -g batt`.

## 3. Architecture

New subpackage `src/aie/ingest/`, one purpose per module:

| Module | Purpose | Depends on |
|---|---|---|
| `ytdlp.py` | Build the invocation for one video; run it; parse the `after_move` rows and stderr into an `Outcome` (ok, challenge, unavailable, extractor, transient) | subprocess |
| `verify.py` | ffprobe a file, streamhash a stream, sha256 a file; check a fetched track against intent | subprocess |
| `records.py` | Read and write the per-video fetch record; list done IDs; case-collision check | filesystem |
| `guards.py` | Window, mains, drive, ASN, VPN, backoff, lock; each returns pass or a `skipped:<name>` reason | subprocess, DNS |
| `status.py` | Atomic `status.json` writer; healthchecks ping | httpx |
| `backfill.py` | Queue from talks.json or an ID file; run loop with cap, window end, breaker, challenge stop | all above |
| `cli.py` (existing) | `aie backfill` subcommand | `backfill` |

yt-dlp is a subprocess, called by absolute path from the project venv,
installed through a new optional dependency group `ingest = ["yt-dlp[default]"]`.
ffmpeg, ffprobe and Deno are Homebrew binaries referenced by absolute path.

## 4. Command line

```
aie backfill [--archive-dir DIR] [--ids-file FILE | --ids ID ...]
             [--limit N] [--now] [--window HH:MM-HH:MM] [--dry-run]
             [--yt-dlp PATH] [--ffmpeg-dir DIR] [--deno PATH] [--verbose]
```

| Option | Default | Meaning |
|---|---|---|
| `--archive-dir` | `$AIE_ARCHIVE_DIR` or `/Volumes/Archive` | Root of the archive drive |
| `--ids-file` / `--ids` | video IDs from `data/raw/talks.json`, in file order | Queue source; the ID file is one ID per line, `#` comments |
| `--limit` | 200 | Videos started per run |
| `--now` | off | Manual run: skip the window and mains guards. Drive, ASN, VPN, backoff and lock still apply |
| `--window` | `01:00-07:00` America/New_York | Nightly window |
| `--dry-run` | off | Run guards, print the queue that would run, exit |
| `--yt-dlp` | `<venv>/bin/yt-dlp` beside the running interpreter | |
| `--ffmpeg-dir` | `/opt/homebrew/bin` | Passed as `--ffmpeg-location`; ffprobe is taken from here too |
| `--deno` | `/opt/homebrew/bin/deno` | Passed as `--js-runtimes deno:PATH` |

Exit codes: 0 for a completed run and for every guard skip (brief 05: a
skip is not a crash); 1 when the run stopped on a challenge or the circuit
breaker; 2 for usage errors.

## 5. The invocation (one call per video)

```
yt-dlp -4 --sleep-requests 3 --sleep-interval 10 --max-sleep-interval 30 --sleep-subtitles 5
  --limit-rate 4M --concurrent-fragments 1 --extractor-retries 0
  --retries 10 --retry-sleep http:exp=1:60 --fragment-retries 10 --abort-on-unavailable-fragments
  --no-playlist --no-overwrites --newline
  --js-runtimes deno:/opt/homebrew/bin/deno --ffmpeg-location /opt/homebrew/bin
  -f "ba[acodec^=opus][format_note*=original][format_id!$=-drc]/ba[acodec^=opus][format_id!$=-drc],ba[acodec^=mp4a][format_note*=original][format_id!$=-drc]/ba[acodec^=mp4a][format_id!$=-drc]"
  --write-info-json --write-auto-subs --sub-langs en --sub-format json3
  -o "<dir>/%(id)s.f%(format_id)s.%(ext)s"
  -o "subtitle:<dir>/%(id)s.%(ext)s"
  -o "infojson:<dir>/%(id)s.%(ext)s"
  --print "after_move:ROW\t%(format_id)s\t%(acodec)s\t%(abr)s\t%(format_note)s\t%(language)s\t%(filepath)s"
  "https://www.youtube.com/watch?v=<id>"
```

Every flag follows a ruling in the review: brief 01 pacing; test 3's
finite retries; test 4's `.part` kept; test 1's one call, per-type
templates and `--no-overwrites`; brief 02's absolute runtime paths. In
yt-dlp's selector grammar a comma binds looser than a slash (checked in
`YoutubeDL._parse_format_selection` for 2026.08.19), so the two fallback
chains need no parentheses. `--print` implies `--quiet`; errors and
warnings still reach stderr, which is saved per video. No `-v` unless
`--verbose`. No `--download-archive`; the record is the manifest.

## 6. Layout on the drive and the record

```
/Volumes/Archive/
  status.json
  .backfill.lock
  logs/backfill-YYYY-MM-DD.log       one line per event, appended
  videos/<id>/
    <id>.f<format_id>.webm           best Opus, untouched
    <id>.f<format_id>.m4a            best AAC, untouched
    <id>.en.json3                    caption track
    <id>.info.json                   yt-dlp metadata snapshot
    <id>.yt-dlp.log                  stderr of the last attempt
    <id>.fetch.json                  the record; present means done
```

`<id>.fetch.json`, schema version 1:

```json
{
  "schema_version": 1,
  "video_id": "FLUoowDJg4I",
  "status": "ok",
  "fetched_at": "2026-09-17T02:00:29Z",
  "yt_dlp_version": "2026.08.19",
  "duration_s": 1237,
  "upload_date": "20260820",
  "audio": {
    "opus": {"format_id": "251", "file": "FLUoowDJg4I.f251.webm", "bytes": 17544466,
             "codec": "opus", "abr_kbps": 113.488, "language": "en-US",
             "format_note": "English (US) original (default), medium",
             "probe_duration_s": 1236.741, "streamhash_sha256": "240a3d..."},
    "aac":  {"format_id": "140", "file": "FLUoowDJg4I.f140.m4a", "...": "..."}
  },
  "captions": {"file": "FLUoowDJg4I.en.json3", "bytes": 314637, "sha256": "...", "events": 1146},
  "info_json": {"file": "FLUoowDJg4I.info.json", "bytes": 596142, "sha256": "..."},
  "warnings": []
}
```

`status` is `ok` or `unavailable` (with `unavailable_reason`, no `audio`).
`captions` is `null` with a warning `captions_missing` when yt-dlp wrote
none; that is recorded, not retried nightly. With `--subtitles off`
(audio only, added 2026-09-18) captions are never requested, and the record
says so in words instead of `null`:
`"captions": {"status": "not_requested", "reason": "audio-only fetch
(--subtitles off); fetch later with --subtitles only"}` with the warning
`captions_not_requested`. `--subtitles only` fetches captions (no audio) for
exactly those records, replaces the block with the normal one, adds
`captions_fetched_at`, and drops the warning. The record is written with
temp file plus `os.replace` after every check in section 7 passes, so a
kill at any point leaves no record and the next run redoes the video
(yt-dlp resumes the `.part` or reports "already downloaded").

No SQLite manifest. Listing about 1,200 record files takes milliseconds
and the records travel with the drive. Timestamps in the record are UTC.

Because the volume is case-insensitive APFS and video IDs are
case-sensitive, `records.py` refuses to create `videos/<id>` when a
directory exists whose name equals `<id>` ignoring case but not exactly,
and reports the video as failed with reason `case_collision`.

## 7. Verification before a record is written

For each of the two audio rows from `after_move`:

1. The file named in the row exists in the video's directory, and there
   is no `.part` file beside it.
2. The row's `language` starts with `en` and `format_note` contains
   `original` (the dub guard). Otherwise the video fails with reason
   `wrong_track` and the files are left for inspection. Changed
   2026-09-18: `original` is required only when info.json lists an audio
   format in another language. YouTube adds the label only when dubs
   exist, so single-language English talks (e.g. VrpEyglYgeU: 10 audio
   formats, all `en`, notes like `medium, VISI`) were being refused; 8 such
   videos had been, all valid on a full audio check.
3. `ffprobe` codec is `opus` for the Opus row and `aac` for the AAC row.
4. `ffprobe` format duration is within 2 s of `duration` in info.json
   (the truncation check from brief 04; both calibration talks differ by
   under 0.3 s).
5. `ffmpeg -map 0:a:0 -c copy -f streamhash -hash sha256` succeeds.

Exactly one Opus row and one AAC row must be present. The caption file, if
present, must parse as JSON with an `events` list. The info.json must
parse and carry `duration`.

Added 2026-09-18, because step 4 reads only the container header: a file
cut to 5000 bytes, or with 400 bytes damaged mid-file, still reported its
full duration there (measured on the test fixtures).

6. The Opus file size equals the `filesize` info.json lists for its format.
   Not applied to AAC: yt-dlp's `FixupM4a` remuxes it, which changed one
   file by 13 KB.
7. Full decode (`ffmpeg -loglevel level+info -i <file> -af volumedetect -f null -`)
   prints no error lines. Records `decoded_duration_s` (decoded samples /
   rate / channels) and `mean_volume_db`, plus Opus `listed_bytes`.
8. Opus and AAC agree: decoded durations within 0.5 s and mean volume
   within 1 dB. On 25 real talks (FR#414) the worst gaps were 0.059 s and
   0.1 dB, with 0 decode errors; decoding took about 3 s per video.
9. If both tracks average below -50 dB (talks measured -25 to -35 dB), the
   record is still written with the warning `audio_quiet`.

`aie audit-audio --archive-dir <root>` reruns 3, 4 and 6 to 8 on every ok
record's files, and recomputes each stream hash against the record. It
changes nothing, prints one line per video, and exits 1 if any problem.

## 8. Outcome classification and the run loop

Per video, from exit code and stderr, in this order:

| Class | Signature | Effect |
|---|---|---|
| challenge | `Sign in to confirm you're not a bot`, `HTTP Error 429`, `This content isn't available, try again later`, `reCAPTCHA` | Stop the run now. `backoff_until` = now + 24 h in status. `consecutive_challenges` += 1; at 2, ping `/fail`. Exit 1. |
| unavailable | `Video unavailable`, `Private video`, `This video has been removed`, `members-only`, `not available in your country` | Write a record with `status: unavailable`. Never retried. Continue. |
| extractor | `n challenge solving failed`, `nsig extraction failed`, `Requested format is not available`, `Only images are available`, `HTTP Error 403` | No record. Counts toward the breaker. Continue. |
| transient | anything else non-zero, or a verification failure | No record. Counts toward the breaker. Continue. |
| ok | exit 0 and section 7 passes | Record written. Breaker and `consecutive_challenges` reset to 0. |

Circuit breaker: 3 consecutive extractor or transient failures stop the
run with outcome `error` and a `/fail` ping, matching the existing sync's
`MAX_CONSECUTIVE_FAILURES`. The owner updates yt-dlp by hand in the weekly
hour; brief 02's reactive auto-update is a later addition.

Loop: build the queue (IDs without a record, in source order), take
`--limit`, and before starting each video check that the window has not
ended (unless `--now`) and that no stop signal arrived. SIGTERM or SIGINT
sets a stop flag and forwards the signal to the running yt-dlp, which
leaves a `.part`; the loop then writes status and exits within launchd's
`ExitTimeOut`.

## 9. Guards, in order, fail closed

| # | Guard | Check | Skip reason |
|---|---|---|---|
| 1 | window | local time in America/New_York inside `--window` | `skipped:window` |
| 2 | backoff | `status.json` `backoff_until` is in the past | `skipped:backoff` |
| 3 | mains | `pmset -g batt` contains `AC Power` | `skipped:power` |
| 4 | drive | `os.path.ismount(archive_dir)` and `videos/` creatable | `skipped:drive` |
| 5 | vpn | `route -n get default` interface does not start with `utun` | `skipped:vpn` |
| 6 | asn | public IPv4 from Google's DNS TXT, then Team Cymru DNS; ASN in {20115, 11351, 7843, 20001, 12271} | `skipped:asn`, or `skipped:asn-unknown` when either lookup fails |
| 7 | lock | `fcntl.flock(LOCK_EX | LOCK_NB)` on `.backfill.lock` | `skipped:lock` |

`--now` skips 1 and 3 only. Commands are found on `PATH` (`pmset`,
`route`, `dig`), which the LaunchAgent sets explicitly and the tests
override with fakes. Any skip writes `status.json` and exits 0 without
pinging healthchecks.

## 10. Status file and alerting

`<archive>/status.json`, written atomically at run start, after every
video, and at run end:

```json
{"last_run_start": "...", "last_run_end": "...", "last_outcome": "success | skipped:<guard> | challenge | error",
 "last_success_time": "...", "videos_completed_last_run": 0, "videos_failed_last_run": 0,
 "queue_depth": 0, "records_total": 0, "unavailable_total": 0, "captions_missing_total": 0,
 "yt_dlp_version": "2026.08.19", "backoff_until": null, "consecutive_challenges": 0,
 "last_error": null, "current_video": null}
```

If `AIE_HEALTHCHECK_URL` is set, a run that ends in `success` (including
one with an empty queue) GETs it; a challenge second strike or a breaker
stop GETs `<url>/fail`. Nothing else alerts.

## 11. Scheduling

`docs/ingest/com.aie.backfill.plist` is the LaunchAgent from report 05
(`StartCalendarInterval` 01:00, `caffeinate -i -m -s`, explicit `PATH`,
`ProcessType Background`, `LowPriorityIO`, `ExitTimeOut 240`, no
`RunAtLoad`) running `<venv>/bin/python -m aie backfill`.
`docs/ingest/audio-backfill-setup.md` lists the one-time steps: install
the `ingest` extra, grant Full Disk Access to the resolved venv Python,
bootstrap the agent, the first manual run with `--now --limit 2`, optional
healthchecks URL, and how to read `status.json`.

## 12. Testing

Seams, confirmed with the owner on 2026-09-16: the `aie backfill` command
run in a subprocess, the executables it calls on `PATH`, and the files it
leaves on the archive directory.

Fakes under `tests/fakes/`: `yt-dlp` (a Python script that copies the
fixture audio files into the requested output paths, writes a caption
file and an info.json with `duration` 1, prints the two `after_move`
rows, appends its argv to the file named by `FAKE_YTDLP_LOG`, and follows
per-ID behaviour from `FAKE_YTDLP_SCRIPT`: `challenge`, `unavailable`,
`fail`); `pmset` and `route` (print canned output from an environment
variable); `dig` (returns the TXT answers from an environment variable).
Real `ffprobe` and `ffmpeg` from Homebrew run on the fixtures.

Fixtures under `tests/fixtures/audio/`: `silence.f251.webm` and
`silence.f140.m4a`, one second of silence generated once with ffmpeg; the
fixtures README records the generating commands and the streamhash and
sha256 literals, which the tests use as expected values.

Tests, in order:

1. Tracer bullet: two IDs via `--ids`, `--now`, fake guards passing. Both
   video directories hold the four files and a record with the literal
   streamhashes; `status.json` shows 2 completed; a second run makes zero
   yt-dlp calls and reports queue depth 0.
2. Invocation shape: the recorded argv contains the selector string and
   the three templates exactly as section 5 lists them.
3. Guard skips: window excluding the current time; `pmset` on battery;
   `route` through `utun4`; `dig` returning an ASN not in the list; each
   yields exit 0, `status.json` with the reason, and zero yt-dlp calls.
4. Challenge: the fake prints the bot-wall line for the first ID; the run
   stops with exit 1, no record for that ID, `backoff_until` about 24 h
   ahead; the next run within the backoff skips with `skipped:backoff`.
5. Unavailable: a record with `status: unavailable` and no audio; the ID
   is not queued again.
6. Breaker: three consecutive failing IDs stop the run with `error`; the
   fourth ID is never attempted.
7. Dub guard: the fake prints a row with language `ml`; no record, reason
   `wrong_track`.
8. Limit and queue order: five IDs, `--limit 2`, the first two in file
   order are fetched.
9. Case collision: an existing `videos/abcdef` directory and a queued ID
   `ABCDEF` yields reason `case_collision` and no yt-dlp call.

## 13. Owner setup, in order (about 1 hour)

1. `.venv/bin/pip install -e ".[dev,ingest]"` (yt-dlp is already installed
   from the calibration).
2. First manual run from the terminal: `aie backfill --now --ids FLUoowDJg4I --limit 1`,
   then read `/Volumes/Archive/status.json` and the record.
3. Grant Full Disk Access to the resolved venv Python
   (`readlink -f .venv/bin/python`).
4. Bootstrap the LaunchAgent; run `launchctl kickstart` once during the
   day to confirm it skips with `skipped:window` and writes status.
5. Optional: create a healthchecks.io check, export its URL in the plist.
6. Delete `/Volumes/Archive/_calibration/`.

## 14. Open items, not blocking

- The uploads-playlist walk (1,188 IDs, includes stream recordings) is
  not in the repo; when it is, pass it with `--ids-file`.
- The Sept 16 corpus release has 1,135 talks; `data/raw/talks.json` is the
  Sept 3 release with 1,087. Re-run `aie sync` before the first night, or
  use the ID file.
- Whether `--sleep-interval` should drop for a two-format call: the
  calibration spent about 40 s of each 55 to 78 s in sleeps. At 200 per
  night that is about 4 h, inside the window; measure the first night
  before changing anything.
