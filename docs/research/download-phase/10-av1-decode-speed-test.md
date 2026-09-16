# Local test 10: AV1 decode and keyframe-extraction speed on the M1

Not a research brief. A step-by-step test for the owner to run in a normal
terminal (outside any sandbox). Purpose: decide whether keyframe extraction
should run on the AV1 stream (smallest, software decode only on M1) or on
the VP9 stream (hardware decode) while AV1 is stored.

Expect 20 to 30 minutes, mostly waiting on downloads and decodes. Run it
while you are not otherwise using the laptop; the decodes use every core.

## 1. Install the tools

```bash
brew install ffmpeg yt-dlp
```

Confirm ffmpeg can decode AV1 in software and has the Apple hardware path:

```bash
ffmpeg -hide_banner -decoders | grep -E "av1|dav1d"
```

```bash
ffmpeg -hide_banner -hwaccels
```

You want to see `libdav1d` (or `libaom-av1`) in the first, and
`videotoolbox` in the second.

## 2. Make a working folder

```bash
mkdir -p ~/av1test && cd ~/av1test
```

## 3. Download the same talk in three codecs, video only, 1080p

The talk is the 21-minute Hugging Face talk used in earlier spikes
(video `FLUoowDJg4I`, 1237 seconds).

```bash
yt-dlp -f "bv*[height=1080][vcodec^=av01]" -o "hf-av1.%(ext)s" "https://www.youtube.com/watch?v=FLUoowDJg4I"
```

```bash
yt-dlp -f "bv*[height=1080][vcodec^=vp09]" -o "hf-vp9.%(ext)s" "https://www.youtube.com/watch?v=FLUoowDJg4I"
```

```bash
yt-dlp -f "bv*[height=1080][vcodec^=avc1]" -o "hf-h264.%(ext)s" "https://www.youtube.com/watch?v=FLUoowDJg4I"
```

Check the sizes; expect roughly 40 MB, 135 MB, 470 MB:

```bash
ls -lh ~/av1test
```

## 4. Time a full software decode of each

Each command decodes the whole file and discards the output. Note the
`real` time printed at the end.

```bash
time ffmpeg -hide_banner -loglevel error -i hf-av1.mp4 -f null -
```

```bash
time ffmpeg -hide_banner -loglevel error -i hf-vp9.webm -f null -
```

```bash
time ffmpeg -hide_banner -loglevel error -i hf-h264.mp4 -f null -
```

Real-time factor = 1237 divided by the `real` seconds. For example, 155
seconds means 8x real time.

## 5. Time the hardware decode for VP9 and H.264

```bash
time ffmpeg -hide_banner -loglevel error -hwaccel videotoolbox -i hf-vp9.webm -f null -
```

```bash
time ffmpeg -hide_banner -loglevel error -hwaccel videotoolbox -i hf-h264.mp4 -f null -
```

If the VP9 hardware run errors out, VideoToolbox VP9 decode is not
available on this machine or build; note that and keep the software number.

## 6. Time an actual keyframe extraction on the AV1 file

This decodes every frame, scores scene changes, and writes a JPEG for each
change above the threshold, with timestamps in a log.

```bash
mkdir -p frames-av1 && time ffmpeg -hide_banner -i hf-av1.mp4 -vf "select='gt(scene,0.3)',showinfo" -fps_mode vfr -q:v 3 frames-av1/%05d.jpg 2> av1-showinfo.log
```

Count the frames and look at a few to see whether they are slides:

```bash
ls frames-av1 | wc -l && grep -c pts_time av1-showinfo.log && open frames-av1
```

Repeat on the VP9 file with hardware decode to compare:

```bash
mkdir -p frames-vp9 && time ffmpeg -hide_banner -hwaccel videotoolbox -i hf-vp9.webm -vf "select='gt(scene,0.3)',showinfo" -fps_mode vfr -q:v 3 frames-vp9/%05d.jpg 2> vp9-showinfo.log
```

## 7. Optional: the two-pass trick that makes AV1 speed matter less

Detect scene changes on the small 360p AV1 stream (fast to decode), then
pull full-resolution frames from the 1080p file only at those timestamps.

```bash
yt-dlp -f "bv*[height=360][vcodec^=av01]" -o "hf-av1-360.%(ext)s" "https://www.youtube.com/watch?v=FLUoowDJg4I"
```

```bash
time ffmpeg -hide_banner -i hf-av1-360.mp4 -vf "select='gt(scene,0.3)',showinfo" -fps_mode vfr -f null - 2> small-showinfo.log
```

Then, for one timestamp from the log (replace 123.456):

```bash
ffmpeg -hide_banner -ss 123.456 -i hf-av1.mp4 -frames:v 1 -q:v 3 one-frame.jpg
```

Time that single extraction; multiply by the number of scene changes for
the per-talk cost of the second pass.

## 8. Record the results

| Measurement | Seconds | Real-time factor |
|---|---|---|
| AV1 1080p software decode | | |
| VP9 1080p software decode | | |
| VP9 1080p hardware decode | | |
| H.264 1080p hardware decode | | |
| AV1 keyframe extraction (full pass) | | |
| VP9 keyframe extraction (hardware) | | |
| 360p AV1 detection pass | | |
| Single 1080p frame seek | | n/a |

## 9. How to read it

Backfill compute for 463 hours of video is 463 divided by the real-time
factor of whichever path you choose.

- **AV1 extraction at 8x real time or better** (about 60 hours of compute
  or less): extract straight from the stored AV1 file. Simplest.
- **AV1 between 3x and 8x**: store AV1, but extract from the VP9 stream
  with hardware decode, or use the two-pass trick from step 7. Both add a
  download or a second pass.
- **AV1 below 3x** (more than 150 hours of compute): do not decode AV1 for
  the backfill; use VP9 with hardware decode or the two-pass trick.

Also note whether the frames in step 6 look like one clean image per slide.
If there are many near-duplicates or the speaker-camera cuts dominate, that
is input for brief 09, not a problem with this test.

## 10. Clean up

```bash
rm -rf ~/av1test
```
