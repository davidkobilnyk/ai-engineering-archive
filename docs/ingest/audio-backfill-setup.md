# Audio backfill: setup and operations

`aie backfill` fetches the best Opus and AAC audio, the English caption
track, and the yt-dlp metadata snapshot for every corpus video onto
`/Volumes/Archive/videos/<id>/`, verifies each file with ffprobe, hashes the
elementary streams, and writes `<id>.fetch.json` when everything checks out.
Design: `docs/superpowers/specs/2026-09-16-audio-backfill-design.md`.

## One-time setup (about an hour)

1. Install the tools into the project venv:

       .venv/bin/pip install -e ".[dev,ingest]"
       .venv/bin/yt-dlp --version        # 2026.08.19 or newer

   ffmpeg and Deno stay Homebrew: `/opt/homebrew/bin/ffmpeg`,
   `/opt/homebrew/bin/deno`.

2. Refresh the corpus so the queue has every talk:

       .venv/bin/aie sync

3. First manual run from the Terminal, VPN off, drive attached:

       .venv/bin/aie backfill --now --ids FLUoowDJg4I --limit 1
       cat /Volumes/Archive/status.json
       cat /Volumes/Archive/videos/FLUoowDJg4I/FLUoowDJg4I.fetch.json

   `--now` skips only the window and mains guards. The drive, VPN, ASN and
   lock guards still run. A manual run on a hotspot or through Proton VPN
   ends in `skipped:asn` or `skipped:vpn`.

4. Grant Full Disk Access to the Python that launchd will run, so it can
   write to the USB volume. The venv binary is a symlink, so grant the
   resolved path: `readlink -f .venv/bin/python`. System Settings, Privacy
   and Security, Full Disk Access, add that file.

5. Install the LaunchAgent:

       cp docs/ingest/com.aie.backfill.plist ~/Library/LaunchAgents/
       launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aie.backfill.plist

   Then fire it once by hand during the day to prove the wiring:

       launchctl kickstart gui/$(id -u)/com.aie.backfill
       sleep 5; cat /Volumes/Archive/status.json

   Expect `"last_outcome": "skipped:window"`. Anything else in
   `~/Library/Logs/aie-backfill.err.log` is a setup problem.

6. Optional dead-man alert: create a check at healthchecks.io with a 2-day
   period, then add its URL to the plist's `EnvironmentVariables` as
   `AIE_HEALTHCHECK_URL` and re-bootstrap (`launchctl bootout` then
   `bootstrap`). A completed run pings it; a second consecutive challenge
   or a tripped breaker pings `/fail`.

7. Delete the calibration scratch folder: `rm -r /Volumes/Archive/_calibration`.

## What a night looks like

At 01:00 ET launchd starts the job under `caffeinate`. The guards run in
order: window, backoff, mains, drive, VPN, ASN, lock. Any failure writes
`status.json` with `skipped:<guard>` and exits 0. Otherwise the job takes
the first 200 videos without a record, in `talks.json` order, and fetches
them one at a time: about 55 to 80 s each with the pacing sleeps, so a
full night is 3 to 4.5 hours. No new video starts after 07:00 ET.

Outcomes per video: `ok` (record written), `unavailable` (record written
with `status: unavailable`, never retried), `challenge` (run stops, 24 h
backoff, alert on the second consecutive strike), anything else (no
record, retried the next night; three in a row stop the run).

## Reading status

    cat /Volumes/Archive/status.json

| field | meaning |
|---|---|
| `last_outcome` | `success`, `skipped:<guard>`, `challenge`, `error`, `interrupted` |
| `queue_depth` | videos still without a record |
| `records_total`, `unavailable_total`, `captions_missing_total` | counts over all records |
| `backoff_until` | set after a challenge; the job skips until then |
| `consecutive_challenges` | resets on the next successful video |
| `last_error` | the last per-video failure, with its video id |
| `yt_dlp_version` | from `yt-dlp --version` at run start |

Per-run lines are appended to `/Volumes/Archive/logs/backfill-YYYY-MM-DD.log`;
the last yt-dlp stderr for a video is `videos/<id>/<id>.yt-dlp.log`.

## Manual runs

    aie backfill --now --dry-run                 # guards plus the queue, no fetch
    aie backfill --now --limit 5                 # five videos, right now
    aie backfill --now --ids-file uploads.txt    # a different id list
    aie backfill --now --verbose --ids <id>      # yt-dlp -v into <id>.yt-dlp.log

## When yt-dlp breaks

Symptoms: `last_error` mentions `n challenge solving failed`, `Requested
format is not available`, or `HTTP Error 403`, and the breaker trips.
Update in the venv and re-run one talk:

    .venv/bin/pip install -U "yt-dlp[default]"
    .venv/bin/aie backfill --now --ids FLUoowDJg4I --limit 1

Roll back with `pip install "yt-dlp==2026.08.19"` if the new one is worse.
