# Research brief 05: Running an unattended nightly job on a MacBook

Read `00-shared-context.md` first.

## The question

The download job runs on an M1 MacBook that sleeps, is sometimes closed,
and is sometimes away from home. What is the reliable pattern on macOS 15
for a scheduled job that runs nightly when it can, does not run when it
should not (on battery, away from home, during the owner's work), keeps
its API keys safe, and tells the owner when it has not run?

## Why it matters

The owner's budget is one hour a week of attention across the whole
pipeline. A job that silently fails to run because the lid was closed, or
runs the backfill while the owner is on a video call, or drains the battery
in a bag, will consume that hour in frustration. The job itself is simple;
the scheduling on a consumer laptop is where such projects fail.

## What is already known

- macOS provides `launchd` (with `StartCalendarInterval`), `cron` (legacy
  but present), `pmset` scheduled wake, `caffeinate` to prevent sleep during
  a run, and Keychain for secrets. The interplay under lid-closed, battery,
  and Power Nap conditions is the question.
- The job phases: check the channel feed (seconds), download new videos
  (minutes to hours in bursts), extract keyframes (CPU-bound, minutes per
  talk), upload artifacts to hosted transcription services (seconds), and
  later phases not covered here.
- The backfill is about 240 GB and 1,135 talks; it must run across many
  nights without the owner starting it each time.

## Questions to answer

1. `launchd` versus `cron` versus a third-party scheduler for this: which
   is reliable across sleep, lid closed, user logged out, and reboots? What
   happens to a `launchd` calendar job whose scheduled time passes while the
   Mac is asleep (does it run on wake)?
2. Waking the Mac on a schedule: `pmset repeat` and its limits, whether wake
   works with the lid closed (with and without external display or power),
   and whether it is better to schedule wake or to run at a time the Mac is
   usually awake.
3. Keeping the Mac awake during a long run (`caffeinate`, assertions), and
   releasing it when done. Behaviour on battery versus mains, and how to
   make the job refuse to start on battery or on a metered or unknown
   network (detect home network by SSID or gateway).
4. Secrets: storing API keys for transcription services and any YouTube
   Data API key in the login Keychain and reading them from a script
   (`security` command or Python keyring), and the pitfalls (Keychain locked
   when logged out, prompts on first access).
5. Resumability: the pattern for a job that may be killed mid-run
   (sleep, shutdown): idempotent per-video steps, a manifest of completed
   video IDs, partial-file handling, and a lock to prevent two overlapping
   runs.
6. Logging and alerting: where logs should live, and the lightest reliable
   way to notify the owner when the job has not completed successfully for
   N days: local notification (`osascript`), email via a simple relay, a
   message to a chat app, or a status file the owner checks. Recommend one
   that works when the owner is away from the Mac.
7. Backfill scheduling on top of the nightly job: a per-night quota
   (talks or gigabytes) that yields to the fresh-talk work first.
8. Anything about macOS 15 specifics: App Management or Full Disk Access
   prompts for scripts writing to an external drive, `launchd` permissions,
   sandboxing of scheduled scripts, behavior when the external drive is
   not mounted.

## Out of scope

Cloud scheduling; the transcription and correction phases; `yt-dlp`
specifics (briefs 01 to 03).

## Deliverable

A recommended scheduling design with the `launchd` plist (or equivalent)
shown, the wake and sleep handling, the guard conditions (battery, network,
drive mounted), the secrets approach with commands, the resumability
pattern, the alerting choice, and a table of failure modes with what the
owner would observe and what the job does. Dated citations to Apple
documentation and credible operator write-ups.

## Suggested sources

Apple developer documentation for `launchd` and `pmset`; `man` pages for
`launchctl`, `pmset`, `caffeinate`, `security`; Apple support articles on
Power Nap and scheduled wake on Apple Silicon; well-regarded macOS
automation write-ups from 2024 to 2026.
