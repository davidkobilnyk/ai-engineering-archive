# Brief B: Audio and Caption Acquisition from YouTube — Recommendation

## TL;DR
- **Primary path:** Poll the AI Engineer channel's free RSS/WebSub feed for new video IDs, then fetch each talk from AWS using **yt-dlp with throwaway-account cookies + a self-hosted PO-token provider**, downloading **both the auto-caption track and audio-only** in one call; the corrected-caption arm should be the fast, cheap default and audio the fallback when captions are thin — but **run a one-day AWS reliability probe first**, because it decides the whole architecture.
- **Reliability is the real risk, not cost.** Datacenter (AWS) IPs are heavily bot-flagged (a vendor fleet reported ~1 in 4 fresh AWS IPs hitting the bot wall in Aug 2026); cookies from a flagged IP now last only 3–5 days; PO tokens no longer reliably bypass the check. Because of this, the **recommended fallback (and arguably co-primary) is the Mac (M1, residential IP) running a nightly launchd job** that downloads audio/captions to S3, with the cloud doing everything downstream.
- **Cost is a non-issue** at this volume: audio-only is ~1 MB/min → ~7.5 GB/year; even routed entirely through the cheapest credible residential proxy (DataImpulse, $1/GB pay-as-you-go) that is **~$7.50/year**; at a premium $8/GB rate, ~$60/year. Either way, trivial against the $40/month ceiling. Terms of Service prohibit automated download, but there is **no documented case of an individual's Google account being terminated purely for downloading**; enforcement has targeted tool operators and stream-ripping services.

## Key Findings

1. **Cloud-side download is unreliable and getting worse.** Independent and vendor reports through 2026 agree datacenter IPs (AWS/GCP/Azure) are scored far below residential connections and challenged with "Sign in to confirm you're not a bot." One extraction-fleet operator reported roughly one in four fresh AWS exit IPs hit the bot wall on first contact in August 2026, with IPv6 worse (a whole /64 scored as one unit). Serverless/Lambda is the worst case (shared, already-burned IP pools).
2. **The mitigations are individually fragile.** Cookies from a datacenter IP now survive only ~3–5 days (down from ~1 month, yt-dlp issue #13964, 2026); PO-token providers (bgutil) now carry an explicit maintainer caution — verbatim: *"Passing PO tokens no longer bypasses the bot check for majority of cases"*; residential proxies work but are a costed fallback, not primary, per the brief.
3. **Captions are not meaningfully safer than audio from the cloud.** The same bot-check/IP-reputation system gates the caption (timedtext) endpoint; both youtube-transcript-api and yt-dlp get "Sign in to confirm you're not a bot" from cloud IPs. Captions are far smaller and faster, so they are worth fetching first, but they do not dodge the acquisition risk.
4. **The official caption API is a dead end here.** `captions.download` requires an OAuth token from the video's owner and returns 403 for third-party videos by design. No compliant API route exists for a channel you do not own.
5. **Channel-watching is solved cheaply.** The channel RSS/Atom feed (`youtube.com/feeds/videos.xml?channel_id=…`) is free, needs no quota, and supports near-real-time WebSub push. It gives video ID, title, description, author, publish time — but **not duration**, which needs one `videos.list` call (1 quota unit).
6. **yt-dlp needs frequent updates but this can be automated.** Stable releases ship roughly every few weeks (current stable **2026.08.19**, published Aug 19, 2026; nightly master builds ship daily, e.g. 2026.08.30). YouTube breaks extractors every few weeks; a weekly auto-update in the scheduled job is the recommended pattern, with version-pinning as a rollback.
7. **Terms and enforcement.** Automated download violates YouTube's ToS "Permissions and Restrictions," but documented enforcement is against operators (stream-ripping services, hosting providers), not individual downloaders. No verified case of a personal Google account terminated purely for yt-dlp use.

## Details

### Q2 — Reliability from cloud addresses

**Baseline failure rate.** As of 2026, requests to YouTube's player endpoint from datacenter ranges are scored on IP reputation, PO-token presence, session cookies, and request volume; a bad score returns a login wall. A vendor extraction fleet reported ~25% of fresh AWS exit IPs blocked on first contact in Aug 2026 (vendor claim, directional only). Community consensus across yt-dlp issues and guides is that the identical command working on a laptop fails on a VPS/Lambda purely due to IP reputation.

**Mitigation comparison (dated):**

| Mitigation | Cost | Setup effort | Fragility |
|---|---|---|---|
| Throwaway-account cookies (`--cookies`) | Free | Low (export Netscape cookies.txt from an incognito session, ship to server) | High: from a datacenter IP, cookies now last **3–5 days** (yt-dlp #13964, 2026), down from ~1 month; must be re-exported on breakage; heavy automated use from a flagged IP can get the *account* restricted |
| Self-hosted PO-token provider (bgutil, Docker) | Free (compute) | Medium (Docker sidecar or Deno/Node ≥20 runtime; requires yt-dlp ≥ 2025.05.22) | High and worsening: bgutil now warns PO tokens **"no longer bypasses the bot check for majority of cases"**; still a useful trust signal, not a guaranteed fix |
| Residential proxy (rotating) | ~$1–8/GB (see below) | Medium (account + gateway URL) | Medium: residential IPs mostly pass but can still be blocked; rotation + retries needed; pools get burned over time |
| Mac on residential IP (fallback stack) | Free (owner already has the M1) | Low–medium (launchd job) | Low: consumer ISP IP is the highest-trust option available; single point of failure is the Mac being on/online |

**Residential proxy pricing (mid-2026, pay-as-you-go, from vendor pages):** DataImpulse ~$1/GB (cheapest credible published rate; ~$0.80/GB at 1 TB, versus a $3–8/GB industry average); IPRoyal from ~$1.75/GB; Decodo ~$2–3.75/GB; Webshare ~$3–6/GB; Oxylabs ~$2.50–8/GB; Bright Data ~$2.50–15/GB by volume. **Cost at this workload:** audio-only is ~128 kbps opus/m4a ≈ ~1 MB/min. At ~7,500 audio min/year that is **~7.5 GB/year**. Routed entirely through DataImpulse at $1/GB that is **~$7.50/year**; at a premium $8/GB, ~$60/year. Captions are ~27–400 KB each, negligible. **Bandwidth cost is never the constraint under the $40/month ceiling.**

**yt-dlp update cadence and safety.** Stable releases land every few weeks (current stable 2026.08.19; nightlies daily); YouTube changes its player/signature code every few weeks and distro packages lag. Current yt-dlp also requires an external JavaScript runtime (Deno recommended; Node/Bun work) plus the yt_dlp_ejs package to solve challenges and mint tokens. **Auto-updating inside a scheduled job is safe and recommended:** run `yt-dlp -U` (binary) or `pip install -U yt-dlp` weekly / before each burst, log the result, and keep a last-known-good pin to roll back if an update regresses. One production operator (~8,800 jobs/day) reported that pulling the latest build weekly beat pinning, because pinning left them broken mid-week when YouTube shipped a player change — but for a 1-hour/week unattended budget, a weekly update plus a pinned fallback is the right balance.

### Q3 — Captions vs audio

**Bot-check treatment.** Caption fetching is **not** treated more leniently than audio: the timedtext/player path is gated by the same IP-reputation bot check. youtube-transcript-api explicitly documents cloud-IP blocking (RequestBlocked/IpBlocked), and yt-dlp's subtitle fetch hits "Sign in to confirm you're not a bot" from flagged IPs. YouTube's *web* client now also needs a PO token for subtitle requests; libraries have moved to the Android-client caption URL to avoid this.

**Auto-caption availability latency.** Community reports vary: 5–30 minutes for short clear-audio English clips; several hours to 12–24 hours for longer or non-English videos. For 15–25-minute English talks, minutes-to-a-few-hours is typical — comfortably inside the 4-day freshness target, and far faster than waiting ~2 weeks for the upstream raw auto-caption record. **Fetching the caption track directly is strictly faster than waiting for the feed.**

**Lighter caption-only tools.** `yt-dlp --skip-download --write-auto-subs --sub-langs en` fetches only the VTT and is the lowest-risk single tool (same hardened extractor as audio). youtube-transcript-api is lighter (~62–419 KB/transcript depending on client path) but carries the same IP exposure and an evolving PO-token problem. **Recommendation:** use yt-dlp for both captions and audio to keep one hardened toolchain rather than adding a second fragile dependency.

### Q4 — Least-fragile hybrid

Given cloud download is unreliable, the least fragile design puts acquisition on the **residential IP (the Mac)** and everything else in AWS:

| Design | Owner time/week | Freshness | Assessment |
|---|---|---|---|
| **Mac nightly launchd job downloads audio+captions on residential IP → S3; cloud does the rest** | Low (mostly unattended; occasional cookie/yt-dlp fix) | ~within 24 h of upload + processing → still ≪ 4-day target | **Recommended fallback / co-primary.** Highest-trust IP, lowest block rate; Mac only needs to be on overnight |
| **Cloud attempts first, Mac fills failures** | Low–medium | Fastest when cloud succeeds; Mac backfill within 24 h | Best freshness but two code paths to maintain; good once the cloud path is proven |
| **Captions from cloud, audio from Mac** | Medium | Captions fast; audio nightly | Splits the toolchain; only worth it if cloud caption success proves markedly higher than audio (benchmark first) |

The nightly-Mac design meets the 4-day target with wide margin (talks arrive in bursts over days/weeks; a nightly cadence plus transcription/correction lands well inside 4 days) while keeping AWS for transcription, correction, and reconciliation and sidestepping the single biggest failure mode. The brief permits the Mac fallback to download/upload to S3, so this is fully in-scope.

### Q5 — Channel watching

**RSS/Atom feed** (`https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`): free, no quota, no account. Supports WebSub/PubSubHubbub push for near-real-time notification (subscribe a callback to `pubsubhubbub.appspot.com`; note WebSub delivery has historically had occasional multi-hour gaps, so keep a low-frequency poll as backstop). Fields per entry: `yt:videoId`, `yt:channelId`, title, author/channel name, `published`, `updated`, description, thumbnail, stats. **Does not include duration.** The feed is a rolling recent window (~15 latest) — fine for watching, not for backfill.

**YouTube Data API v3:** free (no dollar cost), 10,000 quota units/day. `search.list` = 100 units (avoid); `playlistItems.list` = 1 unit (enumerate the channel's uploads playlist — best for backfill and catching missed uploads); `videos.list` = 1 unit (returns `contentDetails.duration`, full description, tags). Provides everything RSS does plus duration and complete metadata.

**yt-dlp flat-playlist** (`--flat-playlist` over the channel/@handle URL) also enumerates IDs and metadata and is what the community used to snapshot the AI Engineer channel — but it carries the same bot-check exposure as any cloud yt-dlp request, so it is not the ideal watch mechanism from AWS.

**Recommendation:** Use **RSS/WebSub as the primary watch trigger** (free, quota-free, near-real-time, Mac-or-cloud agnostic) and a **single `videos.list` call per new ID (1 unit) to enrich the provisional record with duration and full description** for per-talk keyterm biasing. `playlistItems.list` on the uploads playlist handles the 46-talk backfill and any missed uploads at 1 unit/page. The channel is `@aiDotEngineer`; resolve its `UC…` ID once from the channel page (`meta[itemprop=channelId]` or the RSS `<link rel="self">`) and hard-code it.

### Q1 — Terms of service and enforcement (factual summary, not legal advice)

**What the ToS prohibit.** YouTube's Terms of Service (current version effective in the US since **November 2020**, outside the US since **June 1, 2021**), section **"Permissions and Restrictions,"** state you may not "access, reproduce, download, distribute, transmit, broadcast, display, sell, license, alter, modify or otherwise use any part of the Service or any Content except: (a) as specifically permitted by the Service; (b) with prior written permission from YouTube…; or (c) as permitted by applicable law," and may not "access the Service using any automated means (such as robots, botnets or scrapers) except (a) in the case of public search engines, in accordance with YouTube's robots.txt file; (b) with YouTube's prior written permission; or (c) as permitted by applicable law." Automated download via yt-dlp is therefore contrary to the ToS unless it falls under an applicable-law exception.

**Documented enforcement against individual downloaders.** There is **no documented case** of Google terminating an individual's Google account purely for using yt-dlp/youtube-dl to download videos. What exists: (a) IP-level bot-blocking and rate-limiting; (b) a community report (yt-dlp issue #10085, June 2024) that *YouTube login sessions used heavily for scraping* get blocked from the web player — recoverable, not a Google-account deletion, and the same account still worked in the Android app; (c) uncorroborated forum claims of accounts banned after active cookie-substitution circumvention. No news report, court filing, or verified account documents termination of a primary Google account for personal downloading. Merely downloading (vs. redistributing) public videos has produced **no documented legal consequence for an individual in the US or EU** — legal explainers and EFF's 2020 position both treat personal, non-commercial downloading as a ToS/contract matter, not a prosecuted offense.

**Enforcement against tools/operators (documented, dated):**
- **RIAA vs. youtube-dl (2020):** DMCA §1201 takedown filed Oct 23, 2020; GitHub reinstated the repo **Nov 16, 2020** after EFF argued it does not circumvent DRM, and GitHub pledged a **$1M open-source legal defense fund** (TechCrunch, Nat Friedman).
- **Germany (Hamburg):** Landgericht Hamburg ordered youtube-dl's webpage host (Uberspace) to take the page down, enforced 2023.
- **Stream-ripping services:** YouTube-MP3.org (settled/shut 2017), Convert2MP3 (ceased 2019), and Yout LLC (Yout v. RIAA, US, district court ruled for RIAA 2022, appeal to the Second Circuit argued Feb 2024 — verify current status); Yout's operator was criminally convicted in **Brazil in 2025** (operator, commercial service — not an individual downloader).
- **2024 "crackdown":** the Aug-2024 "Sign in to confirm you're not a bot" rollout, 403s against third-party clients (NewPipe, Invidious, SmartTube), and ad-blocker enforcement (announced Apr 15, 2024). This is technical friction and action against apps, not bans of individual downloaders.

**Compliant route for a channel you don't own:** None via API (`captions.download` is owner-only; 403 otherwise). **Off-platform, a possible lower-risk source exists:** the AI Engineer talks share an ecosystem with the Latent Space podcast (swyx et al.), which publishes an RSS podcast feed and show-notes/transcripts. Worth checking as a licensed source for a subset of content — but conference talks and podcast episodes are largely different corpora, so treat this as supplementary, not a replacement.

## Recommendations

**Stage 0 — Resolve the decision-driving uncertainty first (1 day, before Sept 23).**
Run a **cloud reliability probe:** execute the exact production yt-dlp command from the target AWS region on 20–30 recent AI Engineer videos, in four configs — (a) bare, (b) + throwaway cookies, (c) + bgutil PO token, (d) + cookies + PO token — and record the bot-check rate for both audio and caption fetches. This single experiment decides primary vs. fallback and is the cheapest way to avoid building the wrong architecture.

**Stage 1 — Minimum stack for Sept 23.**
1. Stand up the **RSS/WebSub watcher** keyed to the `@aiDotEngineer` channel ID; diff against a video-ID manifest; enrich each new ID with one `videos.list` call (1 unit) for duration + description.
2. Implement acquisition as **yt-dlp fetching both the auto-caption track and audio-only** per video, keyed by video ID, writing artifacts to S3 with source/model/prompt/hash metadata.
3. If the probe shows AWS clears the bot check reliably (say >80% first-try with cookies + PO token), run acquisition in AWS. **If not, ship the Mac nightly launchd job** (residential IP → S3) as primary acquisition and keep AWS for transcription/correction/reconciliation.

**Stage 2 — Harden during the first burst (Paris, late Sept).**
4. If running from AWS: throwaway-account cookies + self-hosted bgutil PO-token sidecar + Deno runtime; weekly yt-dlp auto-update with a pinned rollback; SNS alert on any bot-check failure.
5. Benchmark the **corrected-caption arm vs. self-transcribed audio** on the 46 auto-caption talks that already have upstream edited pairs (entity error + filler-insensitive WER). Prefer captions when they clear the accuracy bars (near-zero transcription cost, fastest); fall back to audio + Whisper otherwise.

**Signals that tell the owner to switch paths:**
- **Cloud → Mac** when the SNS failure stream shows the bot check on >~20% of attempts in a burst, or cookies need re-export more than once a week.
- **Add a residential proxy (costed fallback)** only if the Mac is unavailable (travel/offline) during a burst; at ~7.5 GB/year the bandwidth cost is ~$8–60/year, trivially under budget. Choose a *rotating residential* pool (DataImpulse ~$1/GB or IPRoyal ~$1.75/GB) — not datacenter or static residential, which get blocked.
- **Re-evaluate captions-only** if benchmarking shows YouTube auto-captions meet the entity/WER bars after LLM correction — that removes audio download and transcription entirely.

**Not worth doing:** the official YouTube Data API caption endpoint (owner-only dead end); serverless/Lambda acquisition (worst IP pools); relying on PO tokens alone to beat the bot check (no longer effective); `search.list` for watching (100 units when `playlistItems.list` costs 1).

## Caveats
- The ~25% AWS bot-wall figure and the 3–5-day cookie lifetime are **vendor/community reports**, not YouTube-published numbers; treat as directional — the Stage 0 probe converts them into measured fact for this specific channel and region.
- Auto-caption latency figures are community-sourced and vary; verify on the first few Paris talks.
- The exact `UC…` channel ID for `@aiDotEngineer` should be resolved once from the channel page before hard-coding.
- ToS analysis is factual, not legal advice; the applicable-law exceptions (personal-use/fair-use arguments) are unsettled and jurisdiction-dependent. The Yout v. RIAA Second Circuit outcome should be independently verified for current status.
- The Latent Space podcast/transcript feed covers podcast episodes, which overlap only partially with conference talks; confirm coverage before treating it as any kind of source of record.

## References
**Official documentation:** YouTube Terms of Service, "Permissions and Restrictions" (effective US Nov 2020 / intl Jun 1 2021); YouTube Data API captions.list / captions.download docs (Google Developers); YouTube Data API push-notifications (PubSubHubbub) guide; yt-dlp README/PyPI (release channels, JS-runtime requirement, current stable 2026.08.19); bgutil-ytdlp-pot-provider (GitHub/PyPI, "no longer bypasses the bot check" caution).
**Community reports:** yt-dlp issues #10085, #13964, #15865, #12475, #10128; youtube-transcript-api issues #303, #467, #587, #593; hxckya/youtube-transcript-ip-blocked-guide (checked 2026-09-13); Tunelio, Dalvo, ytdlp.org, Pickuma (DEV) operational guides; residential-proxy pricing pages (DataImpulse, IPRoyal, Oxylabs, Bright Data, AIMultiple, Cybernews, 2026).
**Legal/news:** EFF and TechCrunch on the 2020 RIAA youtube-dl takedown/reinstatement and $1M fund; TorrentFreak on stream-ripper cease-and-desists, the Hamburg/Uberspace case, and the Yout Brazil conviction; 9to5Google / The Verge on the Apr 2024 third-party-app enforcement.