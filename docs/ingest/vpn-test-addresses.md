# VPN test: exit addresses tried

One row per Proton exit tried with `scripts/vpn_test.py`. Raw logs are on the
archive drive under `/Volumes/Archive/vpn-test/`.

"yt-dlp result" is what the script got. "Browser" is the owner's manual check
of YouTube playback in a browser on the same exit.

| Time (UTC) | Proton server | Exit IPv4 | ASN | yt-dlp result | Videos before block | Browser | Log |
|---|---|---|---|---|---|---|---|
| 2026-09-17 12:54 | CA#620 | 149.22.82.105 | AS212238 | Blocked on first request: `/watch` 302 to `google.com/sorry` captcha, 429 there; player `LOGIN_REQUIRED`; no Retry-After | 0 | Played normally | `vpn-test-2026-09-17-0854.log` |
| 2026-09-17 13:00 | CL#40 | 195.86.38.41 | AS212238 | Same as CA#620: `/watch` 302 to `google.com/sorry`, 429 there; player `LOGIN_REQUIRED`; no Retry-After | 0 | not checked | `vpn-test-2026-09-17-0900.log` |
| 2026-09-17 13:05 | CO#77 | 62.93.177.118 | AS212238 (in 62.93.177.0/24; the covering 62.93.160.0/19 is AS3257 GTT, which the first lookup happened to return) | No block. Stopped by owner (Ctrl-C) after 6.7 min: 6 attempted, 4 ok, 1 wrong_track verify failure (Yyg_BoeB2LU), 1 interrupted mid-sleep (UlFB6efYN5Q). 61-83 s per video, 7-12 requests per video, no 403/429 (only googlevideo 302 redirects) | none (4 ok, stopped by owner) | not checked | `vpn-test-2026-09-17-0905.log` |
