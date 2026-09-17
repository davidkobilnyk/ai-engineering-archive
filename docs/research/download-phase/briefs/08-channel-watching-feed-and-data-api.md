# Research brief 08: Watching the channel — RSS feed, uploads playlist, and the YouTube Data API

Read `00-shared-context.md` first.

## The question

The job must notice every new video on the AI Engineer channel within the
latency budget, skip scheduled premieres that have not aired, recover with
zero misses after the laptop has been offline for days, and hand the
download job enough to decide what to fetch. Which combination of the
channel RSS feed, the uploads playlist, and the YouTube Data API does this
within the API's free quota, from a laptop that cannot receive push
callbacks?

## Defaults the owner already accepts

- **Latency budget:** detection within 6 hours of upload during event
  weeks, within 24 hours otherwise. The other phases consume the rest of
  the 4-day freshness goal.
- **Offline tolerance:** the laptop may be offline up to 7 days. On
  recovery the watcher must miss nothing, by walking the uploads playlist
  back to the last-seen video ID, never a fixed page count. Hard
  requirement.
- **Responsibility boundary:** the watcher emits video ID, title, publish
  time, duration, premiere or live status, and playlist membership. The
  full metadata snapshot (description and its URLs, view and like counts,
  heatmap, comments) is the download job's, via yt-dlp. Do not research
  comments or heatmap APIs here.
- **Live streams:** this phase handles the finished recording only, picked
  up like any other video.
- **Premiere retry:** re-check at the scheduled start plus the expected
  duration (or plus 2 hours if unknown), then hourly until the broadcast
  status is "none" and a duration exists. Confirm those are the right
  signals.
- **Cadence:** an adaptive rule is the primary design (poll faster whenever
  the last poll found something new), with the event calendar as an
  optional seed, so the owner maintains nothing.
- **Research method:** fetch the RSS feed and the channel playlists page
  during research and report what was actually observed. Mark every Data
  API claim as documentation-only and specify the local key test that
  confirms it; the owner can obtain a free key.

## What is already known (observed 2026-09-16)

- The channel RSS feed at
  `https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA`
  is free, needs no key, and held 15 entries. Each entry carries
  `yt:videoId`, title, `published`, `updated`, author, and a `media:group`
  with title, content, thumbnail, **description**, and community
  statistics, but no duration. It supports WebSub push, which needs a
  public callback URL the laptop does not have.
- **Scheduled premieres appear in the feed before they air, with
  `published` set to the scheduling time.** "Stop Chunking Like It's 2022"
  had `published` 2026-09-15T07:36Z; its `updated` changed to 09:26Z on the
  16th; at 15:44Z on the 16th it still had not aired (yt-dlp reported
  "Premieres in 74 minutes"), more than 32 hours after `published`. A
  watcher keyed on `published` would treat an unaired premiere as a
  day-old video, and a change in `updated` does not mean it aired. The
  other premiere that day ("Pinecone 2.0") aired at about 13:00Z and had
  the full 1080p ladder 2.8 hours later.
- Burst shape: the channel posted four videos between 13:00Z and 14:30Z on
  2026-09-16, one every 30 minutes; after events it posts 5 to 30 a day.
- yt-dlp's `--flat-playlist` on the channel lists uploads and the Streams
  tab with id, title, duration, and live status (but not dates), and
  metadata probes expose `live_status`, `availability`, and
  `release_timestamp`. It carries scraping exposure on the home address
  (brief 01) and is not the ideal watcher.
- The YouTube Data API v3 has a free daily quota of 10,000 units;
  `playlistItems.list` and `videos.list` are reported at 1 unit each,
  `search.list` at 100. The uploads playlist ID is derivable from the
  channel ID. None of this has been tested locally yet.

## Questions to answer

1. RSS feed behaviour: how quickly a new upload appears, how the feed
   represents premieres and live streams (given the observation above),
   and whether any field or the `media:group` distinguishes an unaired
   premiere from a published video.
2. Data API: which fields on `videos.list` identify a premiere or live
   stream not yet available (`snippet.liveBroadcastContent`,
   `liveStreamingDetails.scheduledStartTime` and `actualEndTime`), the
   recording's status, and duration. Confirm quota costs and the daily
   limit in 2026, and whether a personal key needs approval.
3. The polling design: adaptive rule as above, with the daily uploads
   playlist walk to the last-seen ID for zero-miss recovery, and one
   `videos.list` call per new ID. Compute quota use for a 30-video day, for
   a 7-day recovery, and for the one-time 1,135-video enumeration.
4. Playlist membership: how to find which of the channel's playlists a
   video is in, at what quota cost, and how the channel organizes playlists
   (by event, by track). Fetch the playlists page and report.
5. How the finished stream recording appears: same ID as the live event,
   when it gets a duration, what `liveBroadcastContent` and
   `liveStreamingDetails` show after it ends, so the fetch job picks it up
   like any other video.
6. Detecting changes to known videos: title and description edits, a video
   going private or deleted. The cheapest periodic re-check
   (`videos.list` with up to 50 IDs per call) and its cadence.
7. Whether `yt-dlp --flat-playlist` should be used at all for watching,
   given the Data API can enumerate the uploads playlist for 1 unit per
   page, or kept only for the Streams tab.

## Out of scope

WebSub or any push mechanism needing a public endpoint; cloud hosting;
pacing of media downloads (brief 01); comments and heatmap (download job,
brief 03).

## Deliverable

A watcher design with the adaptive polling rule, the recovery walk, the
exact endpoints and parameters, the premiere and stream-recording
detection rules with the fields relied on, the quota arithmetic, and the
re-check policy for known videos. Observed feed and playlist behaviour
reported separately from documentation-derived claims, each of the latter
with its confirming local test. Dated citations.

## Suggested sources

YouTube Data API v3 reference (videos, playlistItems, playlists, quota
calculator, live streaming details); Google's quota policy pages; the
channel's RSS feed and playlists page fetched during research; community
reports on feed latency and premieres in feeds.
