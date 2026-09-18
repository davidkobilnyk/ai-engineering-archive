# VPN test: exit addresses tried

One row per run of `scripts/vpn_test.py` on a Proton exit. Raw logs and
`.summary.json` files are on the archive drive under `/Volumes/Archive/vpn-test/`.

- "Starts" = videos attempted in that run. "Pace at end" = the script's `pace`
  column on the last video: starts in the trailing hour **across all exits**,
  so it carries over from the previous run.
- "Subtitles": `on` = audio and captions (every run so far), `off` = audio
  only (`--subtitles off`), `only` = captions pass for records fetched with
  `off`. The script writes it in the run's `start` line and summary.
- "Browser" is the owner's manual check of YouTube playback on the same exit.
- ASN is what the script's lookup returned; some lookups return a covering
  prefix (AS3257 GTT) instead of AS212238 for the same IP.

| Start (UTC) | Proton server | Exit IPv4 | ASN | Subtitles | Starts | ok | Pace at end | How it ended | Browser | Log |
|---|---|---|---|---|---|---|---|---|---|---|
| 09-17 12:54 | CA#620 | 149.22.82.105 | AS212238 | on | 1 | 0 | - | Bot check on first video: `/watch` 302 to `google.com/sorry`, 429 there; player `LOGIN_REQUIRED` | Played normally | `0854` |
| 09-17 13:00 | CL#40 | 195.86.38.41 | AS212238 | on | 1 | 0 | - | Same bot check as CA#620 on first video | not checked | `0900` |
| 09-17 13:05 | CO#77 | 62.93.177.118 | AS212238 | on | 6 | 4 | ~55/h (back to back) | Owner Ctrl-C after 6.7 min. 1 wrong_track (Yyg_BoeB2LU), 1 interrupted | not checked | `0905` |
| 09-17 13:38 | CO#77 | 62.93.177.118 | AS212238 | on | 58 | 56 | 20/h | Script stop: ASN lookup failed (16:30). 1 media 403 (HvMyYLTfvhg), 1 connection error. No 429 | not checked | `0938` |
| 09-17 17:07 | CO#77 | 62.93.177.118 | AS3257 | on | 17 | 15 | 17/h | **Subtitle 429** on u6q-byPWUuo at 17:55 (81st start on CO#77 that day) | not checked | `1307` |
| 09-17 18:41 | CR#4 | 195.177.92.62 | AS212238 | on | 1 | 1 | 6/h | Two duplicate runs started by accident; both killed | - | `1441`, `1442` |
| 09-17 18:51 | CR#4 | 195.177.92.62 | AS212238 | on | 13 | 12 | 9/h (target 8/h) | **Subtitle 429** on 1UmZHb_E_SM at 20:21, 1 h 30 min in | not checked | `1451` |
| 09-17 20:41 | not recorded | 85.204.78.22 | AS212238 | on | 5 | 4 | 9/h | **Subtitle 429** on GqoNrUz8hEU at 20:53, 12 min in | not checked | `1641` |
| 09-17 20:58 | AR#91 (same IP as the 09-18 04:11 run) | 84.233.234.202 | AS3257 | on | 26 | 25 | 21/h | Owner Ctrl-C at 22:15. 1 media 403 (CvRngaQZQ3Y). No 429 | not checked | `1658` |
| 09-18 04:11 | AR#91 | 84.233.234.202 | AS3257 | on | 11 | 8 | 11/h | **Subtitle 429** on ZFxh7sqbUZo at 04:41, 30 min in. 2 failed (the two known-bad videos below) | not checked | `2026-09-18-0011` |
| 09-18 09:37 | DK#148 | 159.26.114.8 | AS208172 | on | 9 | 6 | 9/h | **Subtitle 429** on 2bvtay8wGYI at 10:01, 24 min in. 2 failed (known-bad videos) | not checked | `2026-09-18-0537` |
| 09-18 10:04 | DO#27 | 89.238.155.157 | AS9009 | on | 2 | 0 | 11/h | **Bot check** on 2nd video (jQDXzEVHMSE) at 10:07: `/watch` 302 to `google.com/sorry`, 429 there. 1st video failed locally (known-bad) | not checked | `2026-09-18-0604` |
| 09-18 11:37 | FR#414 | 79.127.169.34 | AS212238 | **off** | 80 | 73 | 20/h | **Ran the full 4 h, no block.** 0 subtitle requests, 0 x 429, no bot check. 3 audio 403s on googlevideo (AMiyLItEtLA, ZyIoTOAbRfs, GgLQ02aO-hs; each video counted as failed, run went on), 4 wrong_track (the 2 known-bad + 2JX6JYyQG4Y, RGe6EjucbzI) | not checked | `2026-09-18-0737` |

Log names are `vpn-test-2026-09-17-<HHMM>.log` (local time) unless given in full.

## Patterns so far (measured)

- **Every 429 since 17:07 on 09-17 was on the subtitle download**
  ("Unable to download video subtitles for 'en': HTTP Error 429"). In each case,
  the video just before downloaded its audio normally.
- **Until the 2026-09-18 fix, the script's request counts missed subtitle
  requests** (see `vpn-test-requests.md`). No summary from 09-17 16:41 to
  09-18 10:04 has a
  `timedtext` entry, and the subtitle 429s are not in `non_2xx`. The reason:
  yt-dlp fetches subtitles through a different HTTP path that `--print-traffic`
  does not show. The request only appears in each video's `.yt-dlp.log`
  (stderr). It is one subtitle request per video that gets past the player
  step, so "Starts" is close to the subtitle count.
- **Two kinds of block:** a bot check at `/watch` on the first or second video
  (CA#620, CL#40, DO#27), and a subtitle 429 after 5-81 starts (all others that
  ran long enough).
- **Audio only (FR#414, 09-18): 80 starts at 20/h over 4 h with no 429 and no
  bot check.** With subtitles on, every VPN run that lasted past its first
  couple of videos hit a subtitle 429 after 5-17 starts in that run, except three that
  ended for other reasons (CO#77 13:05, 6 starts, Ctrl-C; CO#77 13:38, 58 starts, ASN lookup failed; AR#91 20:58, 26 starts, Ctrl-C). This is
  one run on one IP, but it is the most starts of any run without a block.
- **Two known-bad videos use up the first slots of every run:** CvRngaQZQ3Y
  (`unexpected codec ''`, leftover-file failure) and jQDXzEVHMSE (`wrong_track`).

## Open questions (inference, not tested)

- Is the 429 limit on the subtitle endpoint rather than on the IP as a whole?
  The FR#414 audio-only run supports "subtitle endpoint" (80 starts, no 429).
  Not yet tested: a `--subtitles only` pass, to find the subtitle budget by
  itself.
- AR#91 did 26 starts with no 429 on 09-17 evening, then hit a 429 after 11
  starts about 6 h later. The limit is not a fixed count per IP.
