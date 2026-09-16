# Research Brief 02 — yt-dlp runtime requirements and safe auto-update on macOS

## Summary of the recommendation

Run yt-dlp from a **dedicated project pip virtual environment** (installed as `yt-dlp[default]`), not from the Homebrew formula, and keep Deno and ffmpeg as pinned Homebrew packages that the job points to by absolute path. This is the single most consequential decision in this brief: a pip venv picks up a new stable the same day it lands on PyPI and rolls back with one deterministic command (`pip install "yt-dlp==<version>"`), whereas the Homebrew formula lagged the 2026.08.19 upstream release by roughly one to two-plus weeks and a `brew upgrade` can drag `python@3.14`, `ffmpeg`, or `deno` along with it. Adopt the reactive-update policy the owner already favours: on a *classified extractor failure*, update to the latest stable, re-run the caption-fetch smoke test against `FLUoowDJg4I`, and if the smoke test fails, escalate to nightly, then roll back to the last-known-good pin and alert. All operations in the table work today on the owner's Apple-Silicon Mac with Deno 2.9.6 + `yt_dlp_ejs` 0.8.0; the JavaScript runtime is a hard requirement only for the operations that need real media-stream URLs (the video/audio/livestream downloads and the merge that depends on them), and is degrade-only for metadata, listing, and captions.

Everything below is verified against the yt-dlp README as published for **2026.08.19** (retrieved 2026-09-16) and release notes from 2026-06-09 through 2026-09-16. Source types are labelled inline: **official** (yt-dlp README/wiki/release notes), **measured** (owner's machine or fetched pages), **vendor claim**, and **community report**.

---

## 1. Operation-by-dependency matrix

The pivotal fact (**official**, yt-dlp README for 2026.08.19, retrieved 2026-09-16): *"`yt-dlp-ejs` — Required for full YouTube support … A JavaScript runtime/engine like deno (recommended), node.js, bun, or QuickJS is also required to run yt-dlp-ejs."* The external-runtime requirement was introduced in **yt-dlp 2025.11.12** (**official**, announcement issue #15012). The EJS wiki (**official**, retrieved 2026-09-16) explains the mechanism: yt-dlp must **solve JavaScript challenges** (signature / `n`-parameter deciphering, and the GVS/PO-token experiment) to produce *playable format URLs*. Anything that needs a real media URL needs the JS runtime; anything that only needs the InnerTube JSON metadata does not, though it will still print a warning.

Without a runtime, yt-dlp emits (**official**, verbatim from issue #15197, 2026): `WARNING: [youtube] No supported JavaScript runtime could be found. YouTube extraction without a JS runtime has been deprecated, and some formats may be missing. See https://github.com/yt-dlp/yt-dlp/wiki/EJS for details on installing one. To silence this warning, you can use --extractor-args "youtube:player_client=default"`, followed by `Some web_safari client https formats have been skipped as they are missing a url.` This is a **WARNING, not an error** — the run continues and produces whatever formats survive, which in practice means a degraded/partial format set and possible HTTP 403 on the media fetch.

| Operation | Deno / JS runtime | `yt_dlp_ejs` | ffmpeg/ffprobe | Other | Verdict without JS runtime |
|---|---|---|---|---|---|
| Metadata probe (`-J` / `--print`, with `--skip-download`) | Degrades | Degrades | No | curl_cffi (impersonation) present | **Works, degraded.** Title, upload date, duration, `live_status`, `release_timestamp`, view/like counts come from the InnerTube JSON and need no challenge solve. The `formats` array may be incomplete/without working URLs, but the probe does not download, so classification fields are intact. |
| Uploads/Streams listing (`--flat-playlist -J`) | Unaffected | Unaffected | No | — | **Works.** `--flat-playlist` explicitly does not extract per-video formats (README: *"some entry metadata may be missing and downloading may be bypassed"*), so no challenge is solved. |
| Video-only stream download (best AV1/VP9/H.264 ≤1080p, DASH) | **Required** | **Required** | Needed only if remuxing | — | **Fails / severely degraded.** `n`-sig deciphering is needed for the DASH format URLs; without it formats are skipped or 403. |
| Audio-only downloads (best Opus, best AAC) | **Required** | **Required** | No (raw stream kept) | — | **Fails / severely degraded**, same reason. |
| Merge (if brief 03 wants one container) | Inherits from the download | Inherits | **Required** (ffmpeg) | — | Merge itself is ffmpeg-only, but it has nothing to merge if the JS-gated downloads fail. |
| Caption fetch (`--write-auto-sub --sub-lang en --sub-format json3 --skip-download`) | Degrades (conservative default: treat as needed) | Degrades | No | — | **Likely works, degraded warning.** Caption-track URLs come from the player response and are not normally `n`-sig-protected; the owner measured success with Deno present. Whether it still succeeds with *no* runtime on 2026.08.19 is not settled by the sources — see calibration test. |
| Metadata snapshot (`--write-info-json` / `-J`) | Degrades | Degrades | No | — | **Works, degraded** (same as metadata probe; `formats` block may be thin). |
| Comments fetch (`--write-comments`) | Unaffected | Unaffected | No | — | **Works.** Comments come from InnerTube continuation JSON, no challenge. |
| Livestream recording download (8-hour file, after day ends) | **Required** | **Required** | **Required** (HLS/DASH handling, mpegts) | — | **Fails / degraded** without runtime; also the heaviest ffmpeg user. |
| Update smoke test (caption fetch of `FLUoowDJg4I`) | Same as caption fetch | Same | No | — | Same as caption fetch row. |

**Calibration test for the caption/metadata "degrades" rows** (the one thing the public sources do not settle): with the working install, run `yt-dlp --no-js-runtimes --skip-download --write-auto-sub --sub-lang en --sub-format json3 -o - FLUoowDJg4I` and separately `yt-dlp --no-js-runtimes -J --skip-download FLUoowDJg4I`. Measure: does a non-empty json3 file appear, and does `-J` still contain `upload_date`, `duration`, `live_status`? If both succeed with only a warning, captions and metadata are confirmed runtime-independent and the job can keep running those two operations even if Deno breaks. If either fails, treat the JS runtime as required for all operations.

**Component roles, confirmed:** ffmpeg/ffprobe (**official** README) is *"Required for merging separate video and audio files, as well as for various post-processing tasks"* — i.e., mandatory only for the merge and any remux, not for downloading a single stream. `curl_cffi` (0.16.2 on the owner's box) provides browser impersonation and is optional but present. `yt_dlp_ejs` version **must** track yt-dlp: the EJS wiki states its *"version MUST match the version specified in yt-dlp's pyproject.toml for the version of yt-dlp you are using … This library SHOULD be updated alongside yt-dlp to avoid running an outdated version,"* and yt-dlp *"may bump the minimum version on updates without warning, and old versions will be ignored by yt-dlp"* (**official**, 2026-09-16). Installing/upgrading with the `default` extra keeps them in lockstep — this is why the pip path uses `yt-dlp[default]`, not bare `yt-dlp`.

---

## 2. Installation and update mechanics; recommended path

### What `-U` does to a Homebrew (or pip) copy

**Official** README (2026.08.19, retrieved 2026-09-16): *"You can use `yt-dlp -U` to update if you are using the release binaries. If you installed with pip, simply re-run the same command that was used to install the program."* On a package-manager or pip install, `-U` does **not** self-overwrite; when a newer version exists it refuses. The refusal wording is install-method dependent (**official**, issue reports 2025–2026): older apt builds print *"As yt-dlp has been installed via apt, you should use that to update. If you're on a stable release, also check backports."*; the current 2026-era generic wording is established verbatim from issue #15790 (a user on `stable@2025.10.22` updating toward `stable@2026.01.31`):

```
Current version: stable@2025.10.22 from yt-dlp/yt-dlp
Latest version: stable@2026.01.31 from yt-dlp/yt-dlp
ERROR: You installed yt-dlp from a manual build or with a package manager; Use that to update
```

(A close variant reads *"…with a package manager or setup.py; Use that to update"*.) The owner's observation is consistent with this: `-U` reported *"up to date (stable@2026.08.19)"* because there was nothing newer to trigger the refusal — the refusal only fires when a newer version actually exists. Treat `-U` as effectively a **no-op for updating** on both Homebrew and pip installs; a local confirm of the exact string this particular build prints is still cheap and worthwhile (see calibration in §2 commands).

`--update-to CHANNEL@TAG` (**official** README): switches channels (`stable`/`nightly`/`master`) or pins a tag on release-binary installs only; it is refused on pip/Homebrew installs for the same reason `-U` is. So neither `-U` nor `--update-to` is the update mechanism for this project — pip is.

### Homebrew vs. pip venv

| Dimension | Homebrew formula | Project pip venv (recommended) |
|---|---|---|
| Update latency after a PyPI/GitHub stable | **~1–2+ weeks** for 2026.08.19: upstream released 2026-08-19 (**official** GitHub tag, "released 19 Aug 23:48"), while formula/bottle activity for `2026.8.19`/`2026.8.19_1` clustered late-Aug to early-Sep 2026 (**community/measured**; the owner's installed build is the `_1` revision, `2026.8.19_1`). yt-dlp is on Homebrew's autobump list, so the *typical* lag can be shorter (hours–days), but bottle CI can stall it. Exact per-release bump dates could not be pinned from accessible sources. | **Same day.** `pip install -U "yt-dlp[default]"` pulls the PyPI wheel published on release day (e.g., 2026.08.19). |
| Rollback | Awkward: needs `brew extract`/older-tap trick; not a first-class operation. | **One command, deterministic:** `pip install "yt-dlp==2026.8.19"`. |
| Collateral upgrades | `brew upgrade yt-dlp` may also bump `python@3.14`, `ffmpeg`, `deno` (**community report**, Homebrew discussion #6761). | None — venv is isolated; ffmpeg/deno stay pinned in Homebrew, untouched. |
| Dependencies | Formula has `depends_on "deno"` and bundles `yt-dlp-ejs` 0.8.0 (**measured**, formula source raw.githubusercontent.com, 2026-09-16). | `yt-dlp[default]` pulls `yt-dlp-ejs`; point `--js-runtimes` at the Homebrew Deno. |
| Nightly access | Not supported. | `pip install -U --pre "yt-dlp[default]"`. |

### Recommended exact commands

Setup (one time; Deno and ffmpeg stay as pinned Homebrew packages):
```
brew pin ffmpeg deno
/opt/homebrew/bin/python3.14 -m venv ~/ingest/venv
~/ingest/venv/bin/python -m pip install -U pip
~/ingest/venv/bin/python -m pip install "yt-dlp[default]"
# record last-known-good
~/ingest/venv/bin/yt-dlp --version > ~/ingest/state/ytdlp.lkg
```
Add a config file so the venv always finds the pinned Homebrew Deno (launchd will not have `/opt/homebrew/bin` on PATH — see §5):
```
# ~/ingest/yt-dlp.conf
--js-runtimes deno:/opt/homebrew/bin/deno
--ffmpeg-location /opt/homebrew/bin
```
Update + verify + roll back (the job pastes these; `$LKG` is read from `ytdlp.lkg`):
```
V_OLD=$(~/ingest/venv/bin/yt-dlp --version)
~/ingest/venv/bin/python -m pip install -U "yt-dlp[default]"
# smoke test (caption fetch of the smoke-test video as json3)
~/ingest/venv/bin/yt-dlp --config-location ~/ingest/yt-dlp.conf \
  --skip-download --write-auto-sub --sub-lang en --sub-format json3 \
  -o "~/ingest/tmp/smoke.%(ext)s" FLUoowDJg4I
# validate: file exists, is valid JSON, has non-empty "events" text; if not -> rollback
~/ingest/venv/bin/python -m pip install "yt-dlp==$LKG"   # rollback
```
Optional one-time calibration of the refusal string on a throwaway copy: `yt-dlp --update-to stable@2026.07.04` and capture the message.

---

## 3. The reactive-update policy (and weekly fallback)

**Classifying "an update would fix this."** The job inspects yt-dlp's exit code and stderr and buckets each result. The update path fires **only** on an *extractor-change signature*, not on any failure. Exit codes (**official** README behaviour + issue reports, 2026): `0` success; `1` generic error (most extraction/network failures); `2` command-line/usage error; `100` *"yt-dlp must restart for update to complete"* (only after a self-update — not relevant to a pip install, but the job should treat a bare `100` as benign/restart, not breakage, per issue #15247); `101` download aborted by a boundary condition such as `--break-on-existing`/`--max-downloads` (heritage code, sparsely documented — do not treat as breakage). Because most YouTube breakage exits `1`, the **stderr text is the real classifier**, not the code.

Extractor-change signatures (update-worthy):
- `WARNING: [youtube] <id>: n challenge solving failed: Some formats may be missing. Ensure you have a supported JavaScript runtime and challenge solver script distribution installed.` and the older `nsig extraction failed: Some formats may be missing` (**official**, issues #13436/community 2025–2026);
- `ERROR: Requested format is not available`;
- `Only images are available for download`;
- `HTTP Error 403: Forbidden` on the media fetch *after* metadata succeeded;
- `Sign in to confirm you're not a bot` **only** when it appears from the home IP off the VPN (per shared context, the home line normally clears the bot wall — if it appears here it usually means a stale extractor, so update first).

These are the cases where a newer release historically restores function.

Reactive flow (unattended):
1. Operation exits non-zero with an extractor-change signature → set status `UPDATING`.
2. `pip install -U "yt-dlp[default]"`. If the version is unchanged (already latest stable) → skip to step 5 with `nightly`.
3. Run the caption-fetch smoke test on `FLUoowDJg4I`; validate the json3 (below).
4. Smoke passes → record new version as last-known-good, re-queue the failed operation, status `OK (updated to X)`.
5. Smoke fails on latest stable → `pip install -U --pre "yt-dlp[default]"` (nightly), re-run smoke.
6. Nightly smoke passes → keep nightly, record it, re-queue, status `OK (nightly Y)`.
7. Nightly smoke also fails → `pip install "yt-dlp==$LKG"` (roll back to last-known-good), status `BROKEN — rolled back to $LKG`, send the secondary email. This is real breakage that an update cannot fix within the window (e.g., YouTube shipped something yt-dlp has not yet patched); it needs the owner's weekly hour.

**Smoke-test validation** (do not hash the caption text — the shared context measured that auto-caption text drifts a few percent over two weeks, so a hash would false-positive): assert the json3 file exists and is >1 KB, parses as JSON, contains an `events` array with at least one segment carrying non-empty `segs[].utf8` text, and that the last event's start time is within a plausible fraction of the known 21-minute duration. Any assertion failing = smoke fail.

**Weekly fallback** (the owner's hour, or automated the night before): `pip install -U "yt-dlp[default]"`; run the smoke test; on failure roll back to `$LKG` and flag. This catches slow regressions and keeps the install inside the 90-day window after which yt-dlp prints its own staleness warning (**official** README: *"When running a yt-dlp version that is older than 90 days, you will see a warning message suggesting to update"*). Homebrew's Deno and ffmpeg are updated by hand in that same hour (`brew unpin deno ffmpeg && brew upgrade deno ffmpeg && brew pin deno ffmpeg`, then re-run the smoke test).

This reactive-plus-weekly-floor policy is a better fit than the prior report's blanket "pull latest weekly." The owner's workload is bursty and small; reactive updates avoid introducing an *unforced* regression during a quiet week, while the weekly floor and the 90-day self-warning bound the staleness risk. (The prior report's supporting anecdote — a "~8,800 jobs/day operator" who found weekly pulls beat pinning — is an **unverified community report**; see §5.)

---

## 4. Operation-by-failure-signature table

Rows are the failure *class*; the job's action is in the last column. "Retry" means retry the same operation later on the existing version (transient); "Update" means enter the §3 reactive flow; "Alert" means write the status file and send the secondary email.

| Situation | Typical stderr (level) | Exit | How to recognise | Job action |
|---|---|---|---|---|
| YouTube changed the player/extractor | `WARNING: n challenge solving failed: Some formats may be missing`; `ERROR: Requested format is not available`; `HTTP Error 403: Forbidden` after metadata OK; `Only images are available for download` | 1 | Metadata/probe succeeded but media formats are missing/403, or n-challenge warning present | **Update** (§3), then retry; alert only if rollback reached |
| Network down / DNS / reset | `ERROR: Unable to download webpage`; `[Errno 8] nodename nor servname provided`; `Connection reset by peer`; `Unable to download API page` | 1 | Failure occurs before any YouTube JSON is parsed; also the home-network guard may be false | **Retry** with backoff; do not update. If the network/VPN/mains guard fails, skip the run (queue accumulates) |
| Video unavailable / private / removed / members-only | `ERROR: [youtube] <id>: Video unavailable`; `Private video`; `This video is available to this channel's members` | 1 | Specific per-video message; other videos in the batch succeed | **Skip that ID**, mark in queue; no update, no alert (it is not our break). Do **not** run the batch with `--abort-on-error` |
| Premiere not yet aired / scheduled | `ERROR: This live event will begin in …`; `WARNING: [youtube] Premieres in …`; via `-J`: `live_status: is_upcoming` with `release_timestamp` set | 1 (or clean `-J`) | Detect **before** downloading with `-J`/`--print "%(live_status)s %(release_timestamp)s"`; `is_upcoming` → not ready | **Defer**: re-queue for after `release_timestamp` (+ margin). No update, no alert |
| Download succeeding but throttled | No error; progress bar shows very low MB/s; or `fragment … throttled` with `--throttled-rate` re-extraction; possible `SABR`/`Some web client formats … skipped` notes | 0 if it finishes | Compare achieved rate to the ~6.5 MB/s DASH baseline; watch for stalls beyond the normal 10 MB chunk boundary | **Retry/continue** (yt-dlp resumes with `-c`); if rate stays a fraction of baseline, check the VPN guard first (VPN gives 0.2–0.45 MB/s), not an update |
| Bot wall (should be rare on home IP) | `ERROR: [youtube] <id>: Sign in to confirm you're not a bot` | 1 | Appears from the home line, off VPN | **Update first** (usually a stale extractor); if it persists post-update, alert — do **not** add cookies/proxies (out of scope) |
| JS runtime/EJS missing or too old | `WARNING: No supported JavaScript runtime could be found …`; or ejs version-mismatch (old ejs "ignored by yt-dlp") | 1 on media, warn on metadata | `yt-dlp -v` shows `JS runtimes: none` or an ejs older than the install needs | **Self-heal**: re-point `--js-runtimes` to `/opt/homebrew/bin/deno`; ensure `pip install -U "yt-dlp[default]"` bumped ejs; then retry; alert if still missing |

---

## 5. macOS 15 / Apple-Silicon and dependency notes

- **launchd PATH does not include `/opt/homebrew/bin`.** A scheduled job gets a minimal PATH, so it will not find `deno`, `ffmpeg`, or even the venv's `yt-dlp` by name. Use absolute paths for the binary and pass `--js-runtimes deno:/opt/homebrew/bin/deno` and `--ffmpeg-location /opt/homebrew/bin` (as in §2). This is the single most common way this exact setup silently half-works (yt-dlp runs but reports `JS runtimes: none` and drops formats). The owner already saw that Node exists only under nvm in the interactive shell and would be invisible to the job — the same trap; Deno is the right choice because the Homebrew formula installs it and it is enabled by default.
- **Deno on arm64 macOS** is native and is what the owner's `-v` reports (`deno-2.9.6`). Minimum supported Deno is **2.3.0** per two **official** sources: the EJS wiki (retrieved 2026-09-16, *"Minimum supported version: 2.3.0"*) and the 2026.06.09 release notes (*"The minimum required version of Deno is now v2.3.0"*). **Source conflict to note:** the older announcement issue #15012 and yt-dlp-ejs CI docs cite a Deno 2.0.0 floor; I trust the newer, version-specific EJS wiki and 2026.06.09 release notes (2.3.0) over the older announcement, and in any case 2.9.6 clears both. Keep Deno pinned so a `brew upgrade` cannot move it out from under a working yt-dlp; update it deliberately in the weekly hour and re-run the smoke test. The `yt-dlp-ejs` scripts run on whatever Deno you provide; there is no evidence of a specific Deno-version incompatibility at 2.9.6 with yt-dlp 2026.08.19.
- **Bun is deprecated** (**official**, EJS wiki 2026-09-16: supported only 1.2.11–1.3.14, *"support may be dropped entirely in the future"*). The owner has no Bun; do not add it. **QuickJS** is a lighter alternative but needs a binary named `qjs` (or a full path in `--js-runtimes`) and, per the EJS wiki, *"versions prior to 2025-4-26 (and QuickJS-NG prior to 0.12.0) lack certain optimizations, which can cause execution times to reach several minutes"* — not worth it here.
- **ffmpeg 9.0.1** from Homebrew with libdav1d is fine for the merge/remux. `brew upgrade` can jump ffmpeg major versions; pin it and update deliberately. (AV1 has no hardware decode on M1, but that only matters for the keyframe-extraction/transcode phases, which are out of this brief's scope.)
- **python@3.14** hosts the Homebrew yt-dlp; the *project* venv should be built from that same interpreter (`/opt/homebrew/bin/python3.14 -m venv`). A future `brew upgrade` that moves the formula to `python@3.15` would orphan the Homebrew yt-dlp's interpreter but **not** the project venv — another reason the venv is the safer home for yt-dlp.
- **Gatekeeper/quarantine** does not apply to pip- or Homebrew-installed executables (no quarantine xattr is set on them), so there is no notarisation prompt for this setup. It would only matter if the owner downloaded the standalone `yt-dlp_macos` binary, which this recommendation avoids. (For context, the **official** macOS release binary supports macOS 10.15+ on Apple Silicon; the legacy Intel-only build was discontinued end of August 2025.)
- **Community claim, unverified:** the "one production operator (~8,800 jobs/day) found pulling the latest build weekly beat pinning" statement from the prior report could not be traced to a primary source; treat it as an **unverified community anecdote**. It nonetheless points the same direction as the recommendation (bias toward fresh builds).

---

## Status-file contents (one paragraph)

Write a single plain-text file (e.g., `~/ingest/state/status.txt`) overwritten every run, glanceable in one screen: first line a status token (`OK`, `UPDATING`, `BROKEN`, or `SKIPPED`) and the local timestamp; then the yt-dlp version in use and channel (e.g., `yt-dlp 2026.08.19 (stable, pip venv)`), the last-known-good pin, and the Deno/ffmpeg versions; then the last successful run time per operation class (probe, listing, video, audio, captions, snapshot) and the current queue depth (talks waiting, oldest upload date, days-to-4-day-SLA); then the last smoke-test result (pass/fail, video `FLUoowDJg4I`, timestamp) and, if the last action was an update or rollback, the from→to versions and why; and finally the last error line verbatim with its classification (transient/deferred/extractor-change/broken) so a ten-second glance answers "is it running, what version, is anything stuck, and did the last auto-update hold." Email (secondary) fires only on the `BROKEN — rolled back` state and on a queue item breaching the 4-day freshness target.

---

## Open uncertainties (ranked by how much they would change the recommendation) and the cheapest resolving experiment

1. **Does the caption fetch (and `-J` metadata) actually survive with no JS runtime on 2026.08.19?** Highest impact: it determines whether a Deno/EJS break silently takes captions and metadata down too, or leaves the freshness-critical text path running (and thus whether §4's "JS runtime missing" row should alert immediately for captions). *Cheapest test:* run the two `--no-js-runtimes` commands in §1 against `FLUoowDJg4I` and read whether json3 and the metadata fields appear with only a warning.
2. **Exact Homebrew→upstream lag on this machine and the precise `-U` refusal wording on this build.** Medium impact: confirms the pip-venv recommendation's premise and hardens the classifier's handling of `-U`. The generic 2026 refusal string is now sourced (issue #15790), but the build-specific string and the actual install lag are not. *Cheapest test:* `brew info yt-dlp` for the install date vs. the 2026-08-19 release date, and `yt-dlp --update-to stable@2026.07.04` on a throwaway copy to capture the exact refusal string.
3. **Which exit code the pip install emits on a classified extractor `ERROR` vs. a benign `100`/`101`.** Medium impact: the classifier keys on stderr, but a clean code map hardens it against a stderr-format change. *Cheapest test:* deliberately request an impossible format (`-f "bv[height=99999]"`) and a removed video, and record `echo $?` for each.
4. **Whether nightly meaningfully beats latest stable during a real burst break.** Lower impact (the policy already escalates to nightly): *cheapest test:* the next time a stable smoke test fails, log whether the nightly smoke passed, building an evidence base over a few events.

---

## Suggestions outside scope

- A tiny local HTTP status page (rather than a text file) would make the glance easier but is a design addition, not part of the accepted defaults.
- Capturing yt-dlp `-v` output to a rotating log on every run would speed post-mortems; noted, not folded into the recommendation.
- A signed-checksum verification step (`gpg --verify` against yt-dlp's published SHA sums) on each pip pull would add supply-chain assurance; noted, not part of the accepted defaults.

---

## Reference list (grouped by source type)

**Official documentation (yt-dlp README / wiki / release notes / GitHub issues by maintainers)**
- yt-dlp README as published for 2026.08.19 (PyPI mirror), retrieved 2026-09-16 — dependencies (ffmpeg, `yt-dlp-ejs`, JS runtime), UPDATE section, `-U`/`--update-to` semantics, channels, 90-day staleness warning, exit-code and option reference. https://pypi.org/project/yt-dlp/
- yt-dlp Release 2026.08.19, retrieved 2026-09-16 — youtube player-client maintenance, `visionos` client added, `android_vr` removed from defaults, web_embedded fallbacks; released 19 Aug 23:48. https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19
- yt-dlp Release 2026.06.09, retrieved 2026-09-16 — minimum Deno raised to v2.3.0, Node v22+, Bun deprecated (1.2.11–1.3.14); CVE fixes. https://github.com/yt-dlp/yt-dlp/releases/tag/2026.06.09
- yt-dlp Release 2026.07.04, retrieved 2026-09-16 — minimum recommended Python raised to 3.11; CVE-2026-55404. https://github.com/yt-dlp/yt-dlp/releases/tag/2026.07.04
- yt-dlp Wiki: EJS, edited 2026-07-12, retrieved 2026-09-16 — runtime table (Deno min 2.3.0 recommended/default, Node min 22, Bun deprecated, QuickJS optimization caveat), ejs install options, `--remote-components`, ejs version-must-match warning. https://github.com/yt-dlp/yt-dlp/wiki/EJS
- yt-dlp Issue #15012 (announcement), 2025 — external JS runtime required for full YouTube support from 2025.11.12. https://github.com/yt-dlp/yt-dlp/issues/15012
- yt-dlp Issue #15197, 2026 — verbatim "No supported JavaScript runtime could be found" warning text. https://github.com/yt-dlp/yt-dlp/issues/15197
- yt-dlp Issue #15790, 2026 — verbatim package-manager `-U` refusal wording on stable@2026.01.31. https://github.com/yt-dlp/yt-dlp/issues/15790
- yt-dlp Issue #13436, 2025–2026 — nsig / n-challenge-solving-failed and GVS PO-token warning text. https://github.com/yt-dlp/yt-dlp/issues/13436
- yt-dlp Issue #15247, 2026 — meaning of exit code 100 ("must restart for update to complete"). https://github.com/yt-dlp/yt-dlp/issues/15247
- yt-dlp Issue #13856, 2025 — discontinuation of macos_legacy builds; macOS 10.15+ requirement for the release binary. https://github.com/yt-dlp/yt-dlp/issues/13856
- yt-dlp GitHub / Arch man page mirror — General Options, `--flat-playlist`, `--remote-components`, `--break-on-existing` semantics. https://man.archlinux.org/man/yt-dlp.1

**Measured / directly fetched pages**
- Owner's machine measurements, 2026-09-16 (from shared context and brief) — installed `yt-dlp 2026.8.19_1`, `deno 2.9.6`, `ffmpeg 9.0.1`, `yt_dlp_ejs-0.8.0`, `curl_cffi-0.16.2`; `-v` shows `JS runtimes: deno-2.9.6`, `PO Token Providers: none`; caption/metadata/media fetches succeed.
- Homebrew formula source `Formula/y/yt-dlp.rb`, raw.githubusercontent.com, retrieved 2026-09-16 — `depends_on "deno"`, `depends_on "python@3.14"`, `resource "yt-dlp-ejs"` = 0.8.0.
- Homebrew formulae index, formulae.brew.sh/formula/yt-dlp, retrieved 2026-09-16 — current stable 2026.8.19, deno 2.9.6 listed as dependency.
- PyPI project page/history, retrieved 2026-09-16 — yt-dlp 2026.8.19 current; release history dates.

**Vendor claims (commercial download-API vendors; treat as directional, not neutral)**
- Vid Kraken blog, retrieved 2026-09-16 — "most 'not a bot' errors are a stale binary"; datacenter-IP scrutiny; `-U` won't update a pip/package-manager install. https://vidkraken.com/blog/how-to-update-yt-dlp
- videoproc.com "How to Update YT-DLP 2026", retrieved 2026-09-16 — package-manager `-U` refusal behaviour; distro lag. https://www.videoproc.com/download-record-video/how-to-update-yt-dlp.htm

**Community reports (forums, blogs, third-party GUIs; corroborating but not authoritative)**
- Homebrew Discussion #6761 — `brew upgrade yt-dlp` "Will not overwrite"; resource list including `yt-dlp--yt-dlp-ejs`. https://github.com/orgs/Homebrew/discussions/6761
- Homebrew PR #302094 and BrewTestBot bottle commits (via mirrors) — `2026.8.19`/`2026.8.19_1` bottle activity clustered late-Aug to early-Sep 2026; merge-conflict note. (Exact bump date not verifiable from accessible sources.)
- neilzone.co.uk (2026-02) — pipx `inject` of deno into a yt-dlp venv; "No supported JavaScript runtime" warning. https://neilzone.co.uk/2026/02/injecting-dependencies-with-pipx/
- GIGAZINE (2025-11-13) — Deno now required for full YouTube support; Bun deprecation. https://gigazine.net/gsc_news/en/20251113-yt-dlp-required-deno-javascript-runtime/
- MX Linux / Arch forums, 2025–2026 — `nsig`/SABR warning transcripts; `-U` package-manager refusals.
- thsnkhn/harbor PR #91 (2026) — bundled yt-dlp bumped 2026.06.09→2026.08.19 to fix HTTP 403; visionOS client replaced android_vr; Apple-Silicon Deno bundling. https://github.com/thsnkhn/harbor/pull/91
- "~8,800 jobs/day operator prefers weekly latest over pinning" (from the prior internal report) — **untraceable to a primary source; unverified.**