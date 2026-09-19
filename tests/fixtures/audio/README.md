# Audio fixtures

`tone.*` (the fake yt-dlp's normal download): one second of a 440 Hz sine,
generated on 2026-09-18 with Homebrew ffmpeg 9.0.1:

    ffmpeg -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=1" -ac 2 \
        -c:a libopus -b:a 64k -metadata:s:a:0 language=eng tone.f251.webm
    ffmpeg -f lavfi -i "sine=frequency=440:sample_rate=44100:duration=1" -ac 2 \
        -c:a aac -b:a 128k -movflags +faststart tone.f140.m4a

`silence.*` (the fake's "silent" mode): one second of silence in each of the
two containers the backfill keeps, generated on 2026-09-16 with Homebrew ffmpeg 9.0.1:

    ffmpeg -f lavfi -i anullsrc=r=48000:cl=stereo -t 1 -c:a libopus -b:a 64k \
        -metadata:s:a:0 language=eng silence.f251.webm
    ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 1 -c:a aac -b:a 128k \
        -movflags +faststart silence.f140.m4a

Values recorded at generation time; the tests use them as literals.

| file | bytes | ffprobe codec / rate / channels / duration | streamhash sha256 (`ffmpeg -map 0:a:0 -c copy -f streamhash -hash sha256 -`) | file sha256 |
|---|---|---|---|---|
| `silence.f251.webm` | 1010 | opus / 48000 / 2 / 1.008 | `e80bf0d53e2e9756c2a0dcf16a486493e917cacf4cb57adcadc9394eac2d7eb4` | `04ed4546fe104003e5e71d3edeed135df0ed69b9c77b81ab7a1fac64d2ee8f29` |
| `tone.f251.webm` | 10973 | opus / 48000 / 2 / 1.008 | `f7b1b18bd04034c21c1f4b9d0ae12d3390bb1d30b7935ab96a0cb2a6ca86c4d8` | `5092e98b6465060eb49fec1c600b628c78a3c026abc8289947ad40cc59ea39f5` |
| `tone.f140.m4a` | 17333 | aac / 44100 / 2 / 1.000 | `8498e98adc87b1d02da471ea127ddb111f7019a7be8cc0c5ec2a95cc7475a4a6` | `484a88019f4e2e6ce51b8065697b17898f5ff6cd74ce0fb9cf9c1716df15789e` |
| `silence.f140.m4a` | 1271 | aac / 44100 / 2 / 1.000 | `4025563f21c80dda474e195f5b8d3c8b5165b31a17af5c477114d401dce81957` | `0ea96d6011b3d8131a93edeb19c18ea33e17b92cca4bb590f04cf980fecfc07b` |

Full decode (`ffmpeg -i <file> -af volumedetect -f null -`), measured at generation:

| file | decoded samples (all channels) | decoded duration | mean_volume |
|---|---|---|---|
| `tone.f251.webm` | 96000 | 1.000 s | -24.1 dB |
| `tone.f140.m4a` | 88200 | 1.000 s | -24.1 dB |
| `silence.f251.webm` | 96000 | 1.000 s | -91.0 dB |
| `silence.f140.m4a` | 88200 | 1.000 s | -91.0 dB |

Do not regenerate casually: a different ffmpeg build may encode
differently and change every literal in `tests/test_backfill.py`.
