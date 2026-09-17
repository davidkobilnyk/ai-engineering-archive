# Audio fixtures

One second of silence in each of the two containers the backfill keeps,
generated on 2026-09-16 with Homebrew ffmpeg 9.0.1:

    ffmpeg -f lavfi -i anullsrc=r=48000:cl=stereo -t 1 -c:a libopus -b:a 64k \
        -metadata:s:a:0 language=eng silence.f251.webm
    ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 1 -c:a aac -b:a 128k \
        -movflags +faststart silence.f140.m4a

Values recorded at generation time; the tests use them as literals.

| file | bytes | ffprobe codec / rate / channels / duration | streamhash sha256 (`ffmpeg -map 0:a:0 -c copy -f streamhash -hash sha256 -`) | file sha256 |
|---|---|---|---|---|
| `silence.f251.webm` | 1010 | opus / 48000 / 2 / 1.008 | `e80bf0d53e2e9756c2a0dcf16a486493e917cacf4cb57adcadc9394eac2d7eb4` | `04ed4546fe104003e5e71d3edeed135df0ed69b9c77b81ab7a1fac64d2ee8f29` |
| `silence.f140.m4a` | 1271 | aac / 44100 / 2 / 1.000 | `4025563f21c80dda474e195f5b8d3c8b5165b31a17af5c477114d401dce81957` | `0ea96d6011b3d8131a93edeb19c18ea33e17b92cca4bb590f04cf980fecfc07b` |

Do not regenerate casually: a different ffmpeg build may encode
differently and change every literal in `tests/test_backfill.py`.
