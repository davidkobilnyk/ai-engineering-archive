# VPN test: every request made per video, and what is recorded

Measured from the saved logs of `scripts/vpn_test.py` runs (2026-09-17/18),
mainly `ewtOo0scUh0` (ok, DK#148), `2bvtay8wGYI` (subtitle 429) and the DO#27
bot-check run. yt-dlp 2026.08.19, one `yt-dlp` process per video
(`ytdlp.build_command`).

## Where request data ends up

| Place | What it holds | Kept |
|---|---|---|
| `videos/<id>/<id>.traffic.log` | yt-dlp **stdout** with `--print-traffic`: `send:` (method, full URL, request headers), `reply:` (status), `header:` (response headers). Covers the **urllib/requests** handlers only | Overwritten when the video is retried |
| `videos/<id>/<id>.yt-dlp.log` | yt-dlp **stderr** with `-v`: `Invoking http downloader on "<url>"`, sleeps, errors, and the **curl_cffi** trace (`> GET`, `< HTTP/2 429`, headers) | Overwritten when the video is retried |
| Run `.log` (one line per video) | outcome, detail, seconds, `N req`, download speeds, non-200/206 codes, ip, pace. `N req` and the codes come **only from stdout** | Kept |
| Run `.summary.json` | `requests`: count by endpoint + status; `non_2xx`: every non-redirect >= 300 reply with headers. **Only from stdout** | Kept |
| `videos/<id>/<id>.fetch.json` | files, sizes, hashes, codec checks. No request data | Overwritten by the next ok fetch |

Summary endpoint names come from `endpoint()` in `vpn_test.py`: `timedtext` ->
`caption`, `/videoplayback` or any `googlevideo` host -> `media`,
`/youtubei/...` -> `api:<name>`, `/watch` -> `webpage`, `/s/player` ->
`player_js`, anything else -> its path.

## Requests per video, in order

| # | Request | Host | When | Counted as | In the summary? |
|---|---|---|---|---|---|
| 0a | DNS TXT `o-o.myaddr.l.google.com` (`dig`, public IPv4) | ns1.google.com | Before every video (`network()`) | not counted | **No.** The result only shows in the `ip` column |
| 0b | DNS TXT `<ip>.origin.asn.cymru.com` (`dig`, ASN) | Cymru DNS | Before every video | not counted | **No.** Failure stops the run ("could not look up egress ASN") |
| 1 | `GET /watch?v=<id>` | www.youtube.com | Every video | `webpage` | Yes. On a bot check it is a **302** to google.com/sorry |
| 1b | `GET /sorry/index` | www.google.com | Bot check only | `/sorry/index` | Yes, **429** (CA#620, CL#40, DO#27) |
| 1c | `GET /iframe_api`, `POST /youtubei/v1/next`, extra `POST /youtubei/v1/player` | www.youtube.com | Bot check only (fallback clients) | `/iframe_api`, `api:next`, `api:player` | Yes |
| 2 | `GET /s/player/<hash>/.../base.js` | www.youtube.com | Only when the player JS is not cached (1-4 per run) | `player_js` | Yes |
| 3 | `POST /youtubei/v1/player` (visionos client) | www.youtube.com | Every video | `api:player` | Yes |
| 4 | `GET /api/manifest/hls_variant/...` (m3u8) | manifest.googlevideo.com | Every video | **`media`** (host matches googlevideo) | Yes, but **mislabelled**: every `media 200` is this manifest, not audio |
| 5 | `GET /api/timedtext?v=<id>...` (auto subtitles, en, json3) | www.youtube.com | Every video that gets past #3; 5 s `--sleep-subtitles` first | `caption` | **Only until 2026-09-17 ~16:36.** See below |
| 6 | `GET /videoplayback` format **251** (opus), one request per ~10 MB chunk (`Range: bytes=...`) | rr*.googlevideo.com | Every ok video; 10-30 s sleep first | `media 302` then `media 206` | Yes |
| 7 | `GET /videoplayback` format **140** (aac), same chunking | rr*.googlevideo.com | Every ok video; 10-30 s sleep first | `media 302` / `media 206` | Yes |

Chunk detail for #6/#7: each chunk usually goes to one googlevideo host, gets a
**302** to another, then a **206** with the byte range. `ewtOo0scUh0` (19 min,
17.7 MB + 18.6 MB): 2 chunks per format = 4 x 302 + 4 x 206. Chunk sizes
seen: 10,417,872 and 10,265,553 bytes. Retries (`--retries 10`,
`--fragment-retries 10`) would show as extra 206/5xx lines.

Typical ok video, 20 min: **2 DNS + 1 watch + 1 player API + 1 manifest +
1 subtitle + 8 media = 12 HTTP requests**, of which the summary counts 11
since 16:36 on 09-17.

## Why subtitles stopped being counted

- yt-dlp's YouTube extractor asks for browser **impersonation** only on
  subtitle (`timedtext`) URLs.
- Until 2026-09-17 ~16:36 `curl_cffi` was not installed, so yt-dlp warned "no
  impersonate target is available" and fetched subtitles with urllib over
  HTTP/1.1. `--print-traffic` wrote that to stdout, and it was counted:
  `caption 200` / `caption 429` appear in the 0905, 0938, 1307 and 1451
  summaries.
- `curl_cffi` 0.16.3 appeared in `.venv` at **2026-09-17 16:36:25** (file
  times). It is not in `pyproject.toml` or `uv.lock`. Every video log from
  16:43 on lists it.
- Since then subtitles go through curl_cffi over HTTP/2 with impersonation.
  Its trace goes to **stderr**, i.e. `.yt-dlp.log`, which `parse_traffic()`
  never reads. The 1641, 1658, 0011, 0537 and 0604 summaries have no
  `caption` entries, and the subtitle 429s are missing from `non_2xx`.

The subtitle 429s happened both before (1307, 1451, and the home nightly on
09-17 05:54) and after curl_cffi was installed, so installing it is not shown
to cause them.

## Fixed 2026-09-18 (runs from then on)

- `parse_traffic(stdout, stderr)` also reads the curl trace in stderr, so
  subtitle requests are counted again (`caption <status>`), and a subtitle
  429 lands in `non_2xx` with its headers.
- The HLS manifest is counted as `manifest`, not `media`.
- Each video's two `dig` lookups are counted in the summary as
  `dns:public-ip ok|fail` and `dns:asn ok|fail`.
- Tests: `tests/test_vpn_test.py`, with fixtures in `tests/fixtures/vpn_test/`
  (trimmed real logs of ewtOo0scUh0 and 2bvtay8wGYI).
- Replaying the new parser over all 136 saved video logs: 133 have one
  subtitle request each, and 3 have none (a bot check and two videos whose
  captions were already on disk).
- Summaries written before this fix are unchanged. Runs from 09-17 16:41
  onward still undercount subtitles.

## Not tracked anywhere

- Normal DNS lookups by yt-dlp for youtube.com / googlevideo.com.
- For the home nightly job (`aie backfill`): no `--print-traffic`, so no
  request counts at all. Only `status.json` and the stderr log per video.
