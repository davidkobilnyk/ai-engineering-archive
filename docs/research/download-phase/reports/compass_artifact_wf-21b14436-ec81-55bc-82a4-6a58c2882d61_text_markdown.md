# Research Brief 05 — Running an Unattended Nightly Job on a MacBook

## TL;DR

- **Use a user LaunchAgent with `StartCalendarInterval` (01:00 ET), wrapped in `caffeinate -i -m -s`, and never trust the fact that launchd fired you — re-derive the allowed window from the clock at startup.** A calendar job whose time passes while the Mac is *asleep* fires once on wake (coalesced); a job whose time passes while the Mac is *off* is skipped entirely until the next 01:00. Keep the owner's lid-open-on-mains routine as the primary design; closed-lid unattended operation requires the global, risky `sudo pmset disablesleep` and should stay opt-in.
- **Guard the run with a strict, fail-closed sequence — window → mains (`pmset -g batt`) → drive mounted → home network by public-IP **ASN** → VPN off (default-route interface, not `ifconfig | grep utun`) → `fcntl.flock` lock — and on any failure, write the reason to a status file, log it, and exit 0 (never alert).** Read API keys from the login Keychain via `security find-generic-password -w` with a one-time "Always Allow" ACL on the venv Python binary.
- **On the VPN question the honest answer is negative: Proton VPN's macOS split tunnelling can only exclude `.app` bundles (not a `yt-dlp`/Python binary, and no IP rules on macOS), and the tunnel cannot be cleanly scripted off (an OS on-demand rule reconnects it after `scutil --nc stop`).** So run the window with the VPN off and let the **ASN guard** be the guarantee: refuse to download unless the egress IP belongs to Charter/Spectrum. Surface everything through one glanceable `status.json`, with a free healthchecks.io dead-man's switch (2-day threshold) as the only secondary alert.

## Key Findings

1. **`StartCalendarInterval` is the only built-in that survives sleep.** Per Apple's `launchd.plist(5)`: *"Unlike cron which skips job invocations when the computer is asleep, launchd will start the job the next time the computer wakes up. If multiple intervals transpire before the computer is woken, those events will be coalesced into one event upon wake from sleep."* This holds for **sleep only** — a Mac powered off at 01:00 does **not** run the job at next boot (Apple Developer Forums thread 52369). `StartInterval` firings are simply *missed* across sleep since OS X 10.11 and must not be used for the window.

2. **A coalesced fire-on-wake is indistinguishable from an on-time run from inside the process** — so the job must read the wall clock at startup and skip media work if it is outside 01:00–07:00 ET. This is the clean separation of "window start" from "resumed after sleep." There is also an Apple-Silicon wrinkle (Apple Developer Forums 815034, 2025–2026): lid-open-asleep calendar jobs may begin under DarkWake and be **suspended mid-run** until full wake, which is exactly what the `caffeinate` system-sleep assertion prevents.

3. **`caffeinate` cannot keep an Apple-Silicon MacBook awake with the lid closed** — a lid close is an explicit sleep request no power assertion overrides. The only override is the kernel flag `SleepDisabled` (`sudo pmset -a disablesleep 1`), a global, root, no-auto-off, thermally significant change. Apple's supported closed-lid mode needs power + external display + external input device.

4. **SSID is unreliable from a background job on macOS 15.** Since macOS 14.4, reading the SSID requires Location Services authorisation the launchd job cannot easily hold; Apple DTS confirmed this is deliberate (Developer Forums 732431). The robust home-network guard is therefore a **public-IP → ASN** check, exactly as the brief anticipated.

5. **Proton VPN macOS (stable v6.5.0, April 24 2026): split tunnelling is app-bundle-only and exclude-only, with no IP rules, and it is mutually exclusive with the kill switch.** Proton's own doc: *"Split tunneling on macOS is currently an experimental feature that supports excluding apps from the VPN tunnel."* It cannot target a Homebrew `yt-dlp` binary or a venv Python interpreter. The tunnel registers with `scutil --nc` but an OS-enforced on-demand rule reconnects it after `scutil --nc stop` (only the app can clear it). Conclusion: guard, don't script.

6. **`fcntl.flock` gives a self-clearing lock** (released automatically when the process dies, including SIGKILL), and **yt-dlp's `.part` + atomic-rename** behaviour means a kill mid-download never leaves a truncated final file — the two facts that make the job safely resumable.

## Details

### 1. launchd — the plist and the sleep/wake handling

Primary nightly agent in `~/Library/LaunchAgents/com.owner.ingest.nightly.plist`, loaded with `launchctl bootstrap gui/$(id -u) <path>`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.owner.ingest.nightly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string><string>-m</string><string>-s</string>
    <string>/Users/OWNER/ingest/.venv/bin/python</string>
    <string>/Users/OWNER/ingest/run_window.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>1</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>/Users/OWNER/ingest</string>
  <key>StandardOutPath</key>
  <string>/Users/OWNER/ingest/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/OWNER/ingest/logs/launchd.err.log</string>
  <key>ProcessType</key>
  <string>Background</string>
  <key>LowPriorityIO</key>
  <true/>
  <key>Nice</key>
  <integer>5</integer>
  <key>ExitTimeOut</key>
  <integer>240</integer>
</dict>
</plist>
```

Handle the midday event-week pass by **gating inside the Python** against a known event-week table (Paris Sept 23–24, NYC Oct 12–14, Shanghai Nov 5–6, Code SF Nov 10–12), rather than a second schedule — one schedule to reason about. If you prefer a separate agent, keep it `Disabled` normally and enable it only during event weeks.

Key choices, verified against `launchd.plist(5)` and Apple's forums:
- **`ProcessType Background`** + **`LowPriorityIO`** + positive **`Nice`** mark the run as throughput-oriented, non-interactive work so it stays out of the owner's way if they wake the Mac mid-run.
- **`ExitTimeOut 240`** raises the default 20 s grace between `SIGTERM` and `SIGKILL` at logout/shutdown/unload, so an atomic rename can finish; the job should treat `SIGTERM` as "stop starting new videos, finish the current chunk, exit."
- **`RunAtLoad` is omitted** so reloading the agent after an edit never kicks off an out-of-window download.

**Sleep vs off, restated for the design:** because the owner keeps the Mac awake overnight, the 01:00 fire normally happens on time and coalescing is a safety net. If the Mac was asleep and launchd fires a coalesced job at, say, 09:30, the "am I inside the window?" clock check returns false and the job **skips media downloads** (the separate lightweight hourly RSS-poll agent can still run). You never trust that launchd fired you; you always re-derive the window from the clock.

### 2. Staying awake, and its cost

**Primary (lid open, on mains, display asleep):** `caffeinate -i -m -s` wrapping the Python process is the correct, privilege-free pattern. `-i` blocks idle system sleep, `-s` blocks system sleep (honoured on AC), `-m` blocks disk idle sleep; **no `-d`**, so the display still sleeps as the owner wants. The assertion is scoped exactly to the process lifetime and released automatically on exit — no global state to clean up.

**What awake-overnight costs (the owner asked):** the M1 is very efficient. Apple's published Mac mini figures (same M1 SoC, Apple Support doc 103253, "Mac mini power consumption and thermal output (BTU) information") are **6.8 W idle / 39 W CPU-max, thermal 23.2–133 BTU/h** for the M1 (16 GB, 2 TB). A MacBook with the display off idles at a couple of watts, rising during downloads and AV1 keyframe extraction; over a 6-hour window this is a small amount of energy and negligible heat (M1-class surface temps sit in the high-20s °C at idle). On mains, **Optimized Battery Charging** — and, on macOS versions that expose it, a **Charge Limit** slider — holds the battery near 80% rather than pinning 100%, which is good for longevity under chronic AC use. Net: cheap and safe; the only "cost" is the battery resting near 80% overnight by design and the machine running a few degrees warmer than asleep.

**Secondary (closed lid, no external display):** state it plainly — not supported by `caffeinate`. The only built-in override is `sudo pmset -a disablesleep 1` (verify `pmset -g | grep SleepDisabled` → `1`), which never auto-clears. `pmset repeat wakeorpoweron MTWRFSU 00:55:00` *does* schedule a wake on Apple-Silicon laptops with the lid closed, but the Mac may **immediately return to sleep** unless `disablesleep` is set or a job grabs an assertion fast, and on battery macOS may skip the power-on entirely to protect the battery (consistent 2026 operator reports). If the owner ever needs this: keep it on mains, schedule the wake a few minutes before the window, and have the job acquire `caffeinate -s` plus set `disablesleep 1` at window start / clear it at window end (the `pmset` calls need a narrowly-scoped `sudoers` entry for `/usr/bin/pmset`). Treat as opt-in. **This can only be settled on the owner's exact hardware — test:** schedule the wake, close the lid on mains, and confirm from `/var/log` timestamps and the status file that a full uninterrupted window ran; suspension gaps mean closed-lid is not viable.

### 3. The guard sequence (fail-closed, skip-and-log, never alert)

Run in order, cheapest and most-decisive first. On any failure: write the reason to `status.json`, log it, **exit 0** (so launchd does not treat a deliberate skip as a crash) — the queue simply accumulates for the next run.

| # | Guard | Check (command shape) | Pass condition |
|---|-------|----------------------|----------------|
| 1 | Inside window | Python: current `America/New_York` time in 01:00–07:00 (or midday event-week window) | true |
| 2 | On mains | `pmset -g batt` → parse `'AC Power'` vs `'Battery Power'` | AC power |
| 3 | Drive mounted & awake | `os.path.ismount('/Volumes/Archive')` + tiny read to spin it up | mount present, readable |
| 4 | Home network | Public-IP → ASN check (below) | ASN ∈ Charter/Spectrum allow-list |
| 5 | VPN off | default-route interface is `enX`, not `utunX` | not tunnelled |
| 6 | Lock | `fcntl.flock(LOCK_EX\|LOCK_NB)` | acquired |

- **Power (2):** `pmset -g batt` prints `Now drawing from 'AC Power'` / `'Battery Power'`; parse that string.
- **Drive (3):** desk-only, so "drive mounted" doubles as a home-location signal (per the brief). Do one small stat/read to wake the spinning disk (it takes seconds). If absent → skip.
- **Home network by ASN (4) — the primary guard:** fetch the public egress IP and confirm its ASN is Charter/Spectrum, for **both IPv4 and IPv6**. The relevant Charter/Spectrum ASNs include **AS20115** (registered "Charter Communications LLC") and **AS11351** (registered "Charter Communications Inc."), plus AS7843/AS20001/AS12271 — pin the exact registered spellings in the allow-list, since the two flagship ASNs resolve to slightly different names. With a **$0 budget**, use **Team Cymru's DNS-based IP-to-ASN service** as primary (`whois -h whois.cymru.com " -v <ip>"` or the DNS interface — free, no API key, no rate limit for casual use, run since 2005), with a plain HTTPS lookup (hackertarget-style `q=<ip>`) as fallback. If the lookup itself fails, **fail closed** (skip-and-log) rather than risk a wrong-network run; cache the last-good ASN to avoid false skips on a transient outage. This guard should **hard-abort the media phase** for any non-allow-list ASN — the cheapest insurance against an accidental VPN or hotspot run.
- **VPN off (5):** read the **default route's** interface: `route -n get default` (or `netstat -rn -f inet`) → the `interface:` line. A `utunX` means tunnelled → skip; `en0`/`en1` means the physical link. The trap (widely documented): a Mac keeps several `utun` interfaces even with no VPN, so **never** grep `ifconfig` for `utun` — only the default route reveals real egress. Guards 4 and 5 reinforce each other: if the VPN were up, the egress ASN would be Proton's datacenter, not Charter, so the ASN check backstops any VPN state the route check misses.

### 4. Secrets in the Keychain

Store each key (transcription vendor(s), YouTube Data API) as a generic password in the **login** Keychain. Create once, granting the venv Python read access:

```
security add-generic-password -a ingest -s deepgram-api-key -w 'THEKEY' \
  -T /Users/OWNER/ingest/.venv/bin/python
```

Read at runtime:

```
security find-generic-password -a ingest -s deepgram-api-key -w
```

`-T` adds the Python binary to the item's ACL so it reads without a GUI prompt; the **first** access may still show an "Always Allow" dialog — click it once by running the job manually from the desktop session before trusting it unattended. Avoid `-A` ("allow any app"): less safe. Python `keyring` is a clean alternative (same login Keychain, same ACL semantics) at the cost of a dependency.

Pitfalls to design around:
- **Locked Keychain.** The login Keychain unlocks at login and stays unlocked while the owner is logged in (the accepted state). But "lock after N minutes" / "lock on sleep" can leave an overnight run facing a locked Keychain and `security` fails. Keep those auto-lock options off, and treat a Keychain-read failure as **skip-and-log** (`error:keychain`), not a crash. Footgun (Apple Developer Forums 116579): if a wrong password is ever entered at the prompt, later programmatic reads can silently fail until the Keychain is manually locked/unlocked — so verify the grant interactively during setup.
- **Never in the plist.** Keep keys out of `EnvironmentVariables` (world-readable via the plist and `launchctl print`); read them into the process at runtime only.

### 5. Resumability

- **Lock (no overlap):** `fd = os.open(lockpath, O_CREAT|O_RDWR); fcntl.flock(fd, LOCK_EX|LOCK_NB)`; on failure, another run holds it → exit. Write PID + start time after locking. `flock` releases automatically if the process dies (including SIGKILL), so **stale locks self-clear** — the classic leftover-PID-file problem does not occur. A midday pass starting while the nightly run is still going cleanly no-ops.
- **Manifest keyed by video ID:** a small SQLite table (or JSON-lines) recording per-artifact state (`video_done`, `audio_opus_done`, `audio_aac_done`, `captions_done`, `metadata_done`, `keyframes_done`, `hash`, `schema_version`, `fetch_time`). Skip any (video ID, artifact) already done — this is what makes the whole job idempotent and resumable.
- **Queue ordering:** new talks first (freshness = priority #2), then backfill, with conference-day **stream recordings captured within 48 h** of the day ending. Sort by (class, age) where class = {new_talk=0, stream_recording_due=1, backfill=2}. The one-time 240 GB backfill (~10 h transfer) always yields to fresh talks and spreads across multiple windows.
- **Partial files:** yt-dlp writes `*.part`/fragments and only **atomically renames** to the final name on success, so a kill never leaves a truncated final file; the next run resumes/overwrites the `.part`. Set the manifest "done" flag only **after** rename **and** hash. Apply the same discipline to your own artifacts: write to a temp path in the same directory, `fsync`, then `os.replace()` (atomic within a filesystem).
- **SIGTERM:** on window-end watchdog / logout / shutdown, set a flag: finish the current chunk/rename, update the manifest, release the lock, exit within the `ExitTimeOut` grace.

### 6. The status file (and the dead-man's switch)

Write one JSON file the owner can glance at — `/Users/OWNER/ingest/status.json` — updated atomically (temp + `os.replace`) at every run end and key transition. Contents: `last_run_start`, `last_run_end`, `last_outcome` (`success` | `skipped:<guard>` | `error`), `last_success_time`, `videos_completed_last_run`, `queue_depth`, `backfill_remaining_gb`, `current_ytdlp_version` (from `yt-dlp --version`), `last_error` (short). The owner reads it with `cat` or a one-line `jq` alias; keep human-readable run logs alongside in `logs/`. On **success only**, `curl` a ping to a free **healthchecks.io** check with a **2-day** period/grace: the free "Hobbyist" tier covers **20 jobs** (with 3 team members and ~100 ping-log entries retained per check) at **$0**, and emails the owner if no ping arrives in the window — a genuine dead-man's switch with no new paid account. Status file primary, healthchecks.io secondary, email only through that. Budget $0.

### 7. Proton VPN on macOS 15 — the definitive answer

**Bottom line: do not rely on split tunnelling to exclude the job, and do not rely on scripting Proton up/down. Run the window with the VPN off and guard with the ASN check.** Verified against Proton's official docs (retrieved 2026-09-16) and a credible community integration:

**(a) Split tunnelling cannot exclude a CLI process.** Proton introduced split tunnelling on macOS as **experimental** in app **v6.1.0 (Nov 5 2025)** — *"Introduced experimental support for split tunneling. Secure only what you need by routing selected apps through the encrypted tunnel while keeping others on your regular connection"* — and the current stable is **v6.5.0 (Apr 24 2026)**, whose changelog still lists split-tunnel network-interface fixes. Proton's official page states: *"Split tunneling on macOS is currently an experimental feature that supports excluding apps from the VPN tunnel,"* and the macOS procedure only lets you *"scroll through the list of apps installed on your Mac and select +"* — i.e., **`.app` bundles**, with no "Add / browse to an executable" option (that exists only on Windows). A Homebrew `yt-dlp` binary or a venv Python interpreter is not an app bundle and cannot be picked. **IP-based exclusion is not available on macOS** (IP rules were "coming soon" at the Aug-2025 launch, per TechRadar/Tom's Guide, and appear only in the Windows/Android docs). Additional macOS limits: split tunnelling requires the **WireGuard or Stealth** protocol (not IKEv2) and a network extension, and it **does not work with WebKit apps**.

**(b) The tunnel cannot be cleanly scripted off.** Proton ships **no official macOS CLI**. The tunnel registers as a system VPN service visible to `scutil --nc list`, and `scutil --nc start/stop <name>` can nominally drive it (documented by the community Raycast "proton-vpn" integration, PR #31012, Sep 2026, which uses only `scutil`, `defaults`, `sqlite3`, `open`, `osascript`) — **but** when the app made the connection, macOS enforces an **on-demand rule that immediately reconnects the tunnel after `scutil --nc stop`**; only the app itself can clear that rule, which it does while quitting. Proton macOS uses a **Network Extension / WireGuard system extension** (System Settings → General → Login Items & Extensions → Network Extensions).

**(c) Kill-switch interaction.** On macOS, Proton's **kill switch and split tunnelling are mutually exclusive** — *"split tunneling is not compatible [with] kill switch… you'll need to turn it off to use a kill switch"* (Windows is the sole exception) — and the kill switch *"blocks all internet traffic on your device until you're reconnected"* if the tunnel drops. So a kill-switch-on config would actively break the non-tunnel egress the job needs; the macOS app also lacks the "Advanced" always-on kill switch (Windows/Linux GUI/iOS only).

**The reliable guard when neither works** is exactly what the brief anticipated: **a public-address check before running, skipping when the address is not the ISP's (guard 4).** The owner keeps Proton's kill switch off (or simply disconnects for the overnight window), and the job refuses to download unless the egress ASN is Charter/Spectrum. An accidental VPN-on state then becomes harmless — the egress ASN is Proton's datacenter, the guard fails closed, the run skips and logs. If the owner wants the VPN programmatically off, the only fully reliable route today is a manual habit (disconnect before bed) or quitting the Proton app via `osascript`/`launchctl` before the window — optional; the ASN guard is the guarantee.

### 8. macOS 15 specifics (TCC, Login Items, venv under launchd)

- **"Removable Volumes" / Full Disk Access.** A launchd-spawned process writing to an external USB volume triggers macOS's TCC prompt, and a GUI approval granted to **Terminal does not transfer to a launchd job** (Apple Community 250766430). Fix on macOS 15: grant **Full Disk Access** to the **interpreter launchd actually executes** — the venv's `python`. Because that is typically a **symlink** to the Homebrew framework Python, add the **resolved real binary** (`readlink -f`) so TCC honours it. Verify with a first-run probe-write to the drive. One-time setup step.
- **"Background Items Added" / Login Items.** Installing a LaunchAgent triggers the notification and the agent appears under System Settings → General → Login Items & Extensions. It must stay **enabled**; if toggled off, the job silently won't run.
- **PATH and environment.** launchd provides a minimal environment (no `.zshrc`, bare `PATH`). Set `PATH` explicitly in the plist (include `/opt/homebrew/bin` for `yt-dlp`, `ffmpeg`, `deno`), and invoke the **venv's** Python by absolute path (which activates the venv without `source activate`). Call `yt-dlp`/`ffmpeg` by absolute path in subprocess calls too. Note macOS strips `DYLD_*` from protected interpreters — don't rely on them.
- **Drive not mounted:** guard 3 handles it. `StartOnMount`/`WatchPaths` could trigger a run on mount, but given the fixed window this is unnecessary complexity — leave it out.

### Failure modes

| Failure mode | What the owner observes | What the job does |
|---|---|---|
| Mac asleep (lid open) at 01:00 | Job fires on wake (coalesced); if now outside window, `skipped:window` | Skip media; hourly poll continues |
| Mac powered off at 01:00 | No run; status stale; healthchecks.io alerts after 2 days | Nothing until next 01:00 fire |
| On battery (mains unplugged) | `skipped:power` | Skip, log, exit 0 |
| Archive drive detached | `skipped:drive` | Skip, log, exit 0 |
| On VPN (tunnel up) | `skipped:vpn` or `skipped:asn` | Skip, log, exit 0 |
| Off home network (hotspot/travel) | `skipped:asn` | Skip, log, exit 0 |
| Killed mid-download | `.part` remains; manifest artifact still pending | Next run resumes/overwrites `.part`, re-verifies |
| Overlapping run attempted | Second run exits immediately | `flock` blocks it; no-op |
| Keychain locked / key missing | `error:keychain` | Skip transcription, log, exit 0 |
| Removable-volume TCC not granted | Write fails; `error:drive-permission` | Log; owner grants FDA to venv python once |
| LaunchAgent disabled in Login Items | Status file goes stale; healthchecks.io alerts | Nothing runs until re-enabled |
| ASN lookup service down | `skipped:asn-unknown` (fail-closed) | Skip rather than risk wrong-network run |
| yt-dlp outdated/extractor break | `current_ytdlp_version` old; downloads error | Log per-video errors; owner updates weekly |

## Recommendations

**Stage 1 — build it on the lid-open primary path (fits the ~5 h setup budget):**
1. Create the LaunchAgent above; load with `launchctl bootstrap`. Write `run_window.py` with the guard sequence, `fcntl.flock`, manifest, and atomic status writes.
2. Store keys with `security add-generic-password … -T <venv python>`; run once from the desktop and click **Always Allow**.
3. Grant **Full Disk Access** to the resolved venv Python binary; confirm with a probe-write from a launchd-fired run (not from Terminal).
4. Set the ASN allow-list (pin the observed IPv4 **and** IPv6 egress ASNs for the home line via Team Cymru; include AS20115 "Charter Communications LLC" and AS11351 "Charter Communications Inc." with exact spellings).
5. Keep Proton's kill switch off; adopt the habit of disconnecting the VPN before the window (the ASN guard makes a lapse harmless).
6. Create a healthchecks.io Hobbyist check (2-day period), ping on success only.

**Stage 2 — validate unattended (first week):** confirm the login Keychain stays unlocked across a 01:00 run; confirm a deliberately-skipped run (unplug mains one night) shows `skipped:power` and exits 0; confirm an accidental VPN-on night yields `skipped:asn`.

**Benchmarks/thresholds that would change the approach:**
- If the probe-write from launchd **fails** despite FDA on the venv Python → add the real resolved binary, or fall back to `LaunchControl`'s `fdautil` wrapper.
- If the owner decides to run **closed-lid** → only proceed if the closed-lid wake test shows a full uninterrupted window on mains; otherwise keep the lid open.
- If Proton later ships **IP-based** macOS split tunnelling or an official CLI (watch the macOS release notes) → the VPN-off habit could be replaced by excluding YouTube CDN prefixes; until then, guard-only.
- If the owner ever needs >20 monitored jobs → the healthchecks.io free tier is exceeded (Business tier is paid), but a single check suffices here.

## Caveats

- **Anecdotal / hardware-specific items, flagged as such:** closed-lid scheduled-wake reliability on this exact M1, the DarkWake mid-run-suspension behaviour, and whether the FDA grant to the venv Python holds under launchd are all **community-reported or environment-dependent** and can only be settled by the local tests specified above. Where a number was unknowable I gave a conservative fail-closed default plus a calibration test rather than a false precision.
- **Power figures** are Apple's Mac mini M1 numbers (Apple Support doc 103253) used as a proxy for the same SoC; a MacBook's real overnight draw with the display off is lower at idle and higher during active downloads — treat 6.8 W idle / 39 W load as bounds, not the measured laptop value.
- **Proton behaviour changes with app versions;** all Proton claims are pinned to stable v6.5.0 (Apr 24 2026) and docs retrieved 2026-09-16. Re-verify after any Proton macOS update, since split-tunnel/kill-switch behaviour is explicitly evolving.
- **ASN allow-lists drift;** Charter/Spectrum can announce IPs from additional ASNs over time. Fail-closed on unknown ASNs and re-pin the observed home ASN periodically.
- **The one-hour-per-week attention budget holds only if guards are fail-closed and silent;** the single biggest risk to that budget is a guard that alerts on benign skips — hence the strict skip-and-log-no-alert rule.

### Suggestions outside scope
- A launchd `WatchPaths`/`StartOnMount` trigger to also run when the archive drive mounts (convenience beyond the fixed window).
- A menu-bar glanceable status (a small SwiftBar/xbar plugin reading `status.json`) if the owner later wants a visual instead of `cat`.
- Charge-limit automation (AlDente/Battery Toolkit) if the owner wants a stricter overnight charge ceiling than Apple's Optimized Battery Charging.