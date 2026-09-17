# Research brief 05: Running an unattended nightly job on a MacBook

Read `00-shared-context.md` first.

## The question

The download job runs on an M1 MacBook. What is the reliable pattern on
macOS 15 for a scheduled job that runs in its nightly window, refuses to
run when it should not (off the home network, on the VPN, on battery,
drive absent), keeps its API keys safe, survives being killed mid-run, and
leaves a status the owner can glance at?

## Defaults the owner already accepts

- **Overnight state:** the laptop is on the desk, on mains, lid open,
  display asleep, awake all night, with the archive drive attached. The
  owner will keep this routine for the project. Closed-lid scheduled wake
  is a secondary case to cover, not the primary design. Since the owner
  asked, state what running awake overnight costs (power draw, battery
  management on mains, heat).
- **Drive:** WD Elements 2 TB, USB, APFS, about 1.76 TB free; treat it as a
  spinning disk powered from the cable that spins down when idle and takes
  seconds to wake. Desk-only, so "drive mounted" doubles as the home guard.
- **Login:** FileVault is on; the owner stays logged in; a wait for the
  password after a reboot is acceptable. Focus on LaunchAgents, not
  daemons.
- **Window:** 01:00 to 07:00 US Eastern, plus a midday pass in event weeks.
  No new video starts after the window ends; an in-progress download
  finishes. Idle detection is an optional second guard, not a requirement.
- **Job shape:** a Python script in a virtual environment, invoked by
  launchd, calling yt-dlp as a subprocess. Prefer built-ins (launchd,
  pmset, caffeinate); reach for third-party schedulers only if launchd
  provably cannot do it.
- **Boundary with briefs 01 to 03:** treat "download one video" as a
  black-box step that is idempotent when re-run. This brief owns the
  manifest, the lock, queue ordering, and what happens when the step is
  killed mid-run.
- **Alerting is closed:** the owner checks the Mac more often than email or
  text, so the primary signal is a status file the owner can glance at
  (last successful run, last failure, current yt-dlp version). Email is
  secondary; a free hosted dead-man's switch with a 2-day silence threshold
  is acceptable if trivial; budget $0. One paragraph, no more.
- **VPN:** the owner runs Proton VPN by default and the job must not run
  through it.

## Why it matters

The owner's budget is one hour a week across the whole pipeline. A job
that silently fails to run, runs the backfill while the owner is on a
video call, or runs through the VPN and gets throttled, will consume that
hour in frustration. The job itself is simple; the scheduling and guards on
a consumer laptop are where such projects fail.

## Questions to answer

1. `launchd` for this job: the LaunchAgent plist for a window-based
   schedule, what happens to a calendar job whose time passes while the
   Mac is asleep, and how the job tells "window start" from "resumed after
   sleep."
2. Staying awake: how to guarantee the Mac stays awake in the window when
   the lid is open on mains (`caffeinate`, assertions, Energy settings) and
   releases when done. For the secondary case, closed-lid scheduled wake
   with `pmset repeat` on Apple Silicon: does it work without an external
   display, and how reliably.
3. Guards, in order: on the home network (how to detect: gateway, SSID,
   or public-address check), **VPN off** (see question 7), on mains, drive
   mounted and awake. What the job does when a guard fails: skip, log, do
   not alert.
4. Secrets: API keys for transcription services and the YouTube Data API
   in the login Keychain, read from a Python script (`security` command or
   `keyring`), and the pitfalls (locked Keychain, first-access prompts).
5. Resumability: manifest of completed video IDs keyed by video ID, a lock
   preventing overlapping runs, queue ordering (new talks before backfill,
   stream recordings within 48 hours of the day), partial-file handling
   when killed mid-download, and idempotent per-video steps.
6. The status file: contents and location, how the owner reads it, and the
   optional email or dead-man's switch in one paragraph.
7. **Proton VPN on macOS 15.** Can a scheduled command-line job (yt-dlp
   under launchd) be excluded from the tunnel by app-based split
   tunnelling, given it is a process not a bundled app? Can the tunnel be
   connected and disconnected from a script (Proton has no official macOS
   command-line tool; check `scutil --nc`, the app's automation surface, or
   a system VPN configuration)? What is the reliable guard if neither works
   (a public-address check before running, with the job skipping when the
   address is not the ISP's)?
8. macOS 15 specifics: Full Disk Access or App Management prompts for a
   script writing to an external drive, launchd permissions, behaviour when
   the drive is not mounted, and anything about running Python from a
   virtual environment under launchd (PATH, environment).

## Out of scope

Cloud scheduling; the transcription and correction phases; yt-dlp
specifics (briefs 01 to 03); anything requiring a new paid account.

## Deliverable

The LaunchAgent plist, the wake and sleep handling for the primary and
secondary cases, the guard sequence with the check for each, the secrets
approach with commands, the resumability design, the VPN answer, the
status-file paragraph, and a table of failure modes with what the owner
would observe and what the job does. Dated citations to Apple documentation
and credible operator write-ups.

## Suggested sources

Apple developer documentation for `launchd` and `pmset`; `man` pages for
`launchctl`, `pmset`, `caffeinate`, `security`, `scutil`; Apple support
articles on scheduled wake and Energy settings on Apple Silicon; Proton VPN
macOS documentation and support articles on split tunnelling and
automation; well-regarded macOS automation write-ups from 2024 to 2026.
