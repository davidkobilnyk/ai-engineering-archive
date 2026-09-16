# Research brief 08: Watching the channel — RSS feed, uploads playlist, and the YouTube Data API

Read `00-shared-context.md` first.

## The question

The job must notice every new video on the AI Engineer channel within
hours, skip scheduled premieres that have not aired, never miss uploads
during a burst of 30 in a day, and enrich each new video with duration,
publish time, description, and playlist membership. Which combination of
the channel RSS feed, the uploads playlist, and the YouTube Data API does
this within the API's free quota, from a laptop that cannot receive push
callbacks?

## Why it matters

Freshness within 4 days is the second priority, and the watcher is the
first link. Missing an upload during a burst means a talk silently never
enters the archive until the upstream feed catches up weeks later. Fetching
a premiere before it airs wastes a run and logs a failure. Playlist
membership is the only early source of which event and track a talk belongs
to, which the upstream feed provides weeks later.

## What is already known

- The channel RSS feed at
  `https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA`
  is free, needs no key, and lists roughly the 15 most recent uploads with
  video ID, title, publish time, and description, but not duration. It
  supports WebSub push, which needs a public callback URL the laptop does
  not have.
- The YouTube Data API v3 has a free daily quota of 10,000 units. Costs
  reported: `playlistItems.list` and `videos.list` 1 unit each,
  `search.list` 100 units. The channel's uploads playlist ID is derivable
  from the channel ID.
- Premieres: on 2026-09-16 the channel's upload listing (as seen by
  `yt-dlp --flat-playlist`) showed two scheduled premieres, hours before
  airing, with no duration. Whether they also appear in the RSS feed, and
  whether the Data API marks them (`liveBroadcastContent`,
  `liveStreamingDetails.scheduledStartTime`), is the question.
- The channel posts up to about 30 videos in a day after events; the
  uploads playlist is complete and ordered.

## Questions to answer

1. RSS feed behaviour: how many entries, how quickly a new upload appears,
   whether scheduled premieres and live streams appear before they start,
   and what the `published` and `updated` fields mean for a premiere.
2. Data API: which fields on `videos.list` identify a premiere or live
   stream not yet available (`snippet.liveBroadcastContent`,
   `liveStreamingDetails`), the recording status, and duration
   (`contentDetails.duration`, ISO 8601). Confirm quota costs in 2026 and
   the daily limit, and whether a personal API key needs any approval.
3. A polling design for a laptop: poll the RSS feed hourly during event
   weeks and a few times daily otherwise; enumerate the uploads playlist
   via `playlistItems.list` daily (or on each run) to catch anything the
   feed missed; call `videos.list` once per new ID. Compute the daily quota
   use for a 30-video day and for the 1,135-video backfill enumeration.
4. Playlist membership: how to find which of the channel's playlists a
   video is in, at what quota cost (`playlists.list` then
   `playlistItems.list` per playlist versus any cheaper way), and how the
   channel organizes playlists (by event, by track?). Check the channel.
5. `yt-dlp --flat-playlist` on the channel as a watcher: it works but
   carries YouTube-scraping exposure; is it acceptable as a daily complete
   enumeration on a residential address, or should the Data API do that?
6. Detecting changes to already-known videos: title edits, description
   edits (deck links added later), a video going private or being deleted.
   What is the cheapest way to re-check known videos periodically
   (`videos.list` accepts up to 50 IDs per call)?
7. Live streams: how the feed and API represent an in-progress stream and
   its recording afterward (same ID?), so brief 04's capture job can be
   triggered by the watcher.

## Out of scope

WebSub or any push mechanism needing a public endpoint; cloud hosting;
pacing of media downloads (brief 01).

## Deliverable

A watcher design with the polling schedule, the exact endpoints and
parameters, the premiere and live-stream detection rule, the quota
arithmetic for burst days and for backfill, and the periodic re-check
policy for known videos. Dated citations to the Data API reference and any
community reports on feed latency.

## Suggested sources

YouTube Data API v3 reference (videos, playlistItems, playlists, quota
calculator, live streaming details); Google's quota policy pages; community
reports on RSS feed latency and premieres in feeds; the channel's own
playlists page.
