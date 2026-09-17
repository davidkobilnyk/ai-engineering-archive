# Research Brief 09 — Extracting Slide Keyframes from Talk Videos

## Recommendation summary
Do **not** rely on ffmpeg's `select='gt(scene,T)'` global scene score as the primary slide detector. It provably misses low-contrast text-slide advances because the score is a global mean-absolute-difference metric (see Q1). Instead detect with **PySceneDetect's `ContentDetector` run with its edge-difference component enabled and a lowered threshold**, decoding once through ffmpeg/libdav1d and detecting on a lightly-downscaled luma frame; then **deduplicate with a difference-hash (dHash) at Hamming ≤ ~6 plus a 2-second crossfade collapse**, keeping the last build state of each slide. Classify camera/panel frames cheaply by edge density (plus OpenCV face rejection) and sparse-sample them. Recognize screen-recording segments by a sustained high rate of small changes and switch them to time-sampling. Store JPEG at quality ~90, 1080p, with a per-talk JSON manifest. No existing open-source tool fits end-to-end; assemble the pipeline yourself, borrowing the face-rejection and slide-region crop ideas from `vid2slides`. Everything below the parameter level must be confirmed by the five local tests specified at the end, because the only ground truth is the owner's own eyes (no slide decks exist for this channel).

Source types are labelled inline as **[official doc]**, **[peer-reviewed]**, **[measured]** (a reproducible benchmark with numbers), **[vendor]**, or **[community]**. Where sources conflict I say which I trust and why.

---

## Q1 — Threshold and detector choice for slide decks

**Why ffmpeg's scene score misses low-contrast text slides.** The `select` filter's `scene` value is computed in `libavfilter/f_select.c` as: for each 8×8 block it sums the absolute difference against the previous frame (SAD), divides by the number of pixels compared to get the mean absolute frame difference `mafd = sad / nb_sad`, computes `diff = |mafd − prev_mafd|`, and returns `av_clipf(min(mafd, diff) / 100, 0, 1)` **[official doc / source, FFmpeg f_select.c, retrieved 2026-09-16]**. Two consequences: (1) it is a **global** average over the whole luma/RGB frame, so a text-slide advance that changes only a small fraction of pixels by a small magnitude produces a tiny `mafd`; (2) it takes the **minimum** of `mafd` and the change in `mafd`, further shrinking the score for gradual changes. A bullet appearing on a white slide moves the global mean by a fraction of a percent — far below 0.06. That is exactly the 3:55–6:29 gap the owner observed: the picture *did* change but the global average barely moved. `scdet` uses the same MAFD basis (it exposes `lavfi.scd.mafd` and `lavfi.scd.score`) and shares the weakness **[official doc, FFmpeg scdet, retrieved 2026-09-16]**.

**What catches low-contrast text changes.** The multimedia literature is consistent that **edge-based and region/block-based** differences beat global luma MAFD for slides. An edge-map difference fires strongly when text glyphs (high-contrast edges) appear or disappear even if the mean luma is unchanged; an edge-based shot-change algorithm is the documented basis of lecture-video slide-structure reconstruction **[peer-reviewed, "An experimental comparative study on slide change detection in lecture videos," academia.edu, retrieved 2026-09-16]**. SliTraNet and SIFT-similarity approaches likewise operate on slide-region features rather than global frame means **[peer-reviewed, SliTraNet, TU Graz, 2022]**.

**Recommended detector.** PySceneDetect's `ContentDetector` computes a weighted content score over HSV components plus an **edge component** (`delta_edges`), each independently weighted; `AdaptiveDetector` is a two-pass rolling-average variant that suppresses false positives from camera/inset motion **[official doc, scenedetect.com detectors, v0.7.1, retrieved 2026-09-16]**. The default is `ContentDetector(threshold=27.0, min_scene_len=15, weights=Components(delta_hue=1.0, delta_sat=1.0, delta_lum=1.0, delta_edges=0.0))` — the edge term is **off by default** (verbatim: "Threshold value that the content_val frame metric must exceed to trigger a new scene... [default: 27.0]... Weights of the 4 components... [default: 1.000, 1.000, 1.000, 0.000]") **[official doc, scenedetect.com CLI detectors, retrieved 2026-09-16]**. For slide decks I recommend:

- **Detector:** `ContentDetector` with `delta_edges` weighted **up** (start `weights=(1,1,1,1)`), `threshold≈12–15` (roughly half the default, biased for recall because a miss is 10× a duplicate), `min_scene_len≈0.6–1.0 s`.
- Consider `AdaptiveDetector` (exact defaults `adaptive_threshold=3.0, min_scene_len=15, window_width=2, min_content_val=15.0` **[official doc, scenedetect.com API detectors, v0.7.1, retrieved 2026-09-16]**) specifically on inset/alternating-cut talks where a fixed threshold over-fires.

PySceneDetect is actively maintained (v0.7.1) and installs from PyPI (`pip install scenedetect[opencv]`); its build matrix has tracked recent CPython, and the OpenCV backend is pure-CPU, so Python 3.13 compatibility is expected — **confirm the exact version resolves under the owner's interpreter as a setup step** (it is a component the archive imports, not the archive's own Python 3.14/yt-dlp environment).

This is a **recommendation to be confirmed by local Test A**, not a measured result — no public benchmark exists for this specific channel. The reasoning: enabling the edge term directly addresses the failure mode the owner measured; the low threshold plus the 10×-miss asymmetry means we deliberately over-detect and let dedup clean up.

**On keeping ffmpeg as a fast pre-filter.** ffmpeg `select` at a very low threshold (0.06) is cheap and can serve as a first-pass candidate generator, but on its own it is unsafe for the recall target. If Test A shows `ContentDetector`-with-edges also misses the 3:55–6:29 class of change, the fallback is a **custom block-max / edge-map difference** (compute per-block MAFD and trigger on the block maximum, not the frame mean) — this is the localized metric the brief anticipates and the literature supports.

| Detector | Basis | Catches low-contrast text? | Robust to inset/camera motion? | Cost | Verdict |
|---|---|---|---|---|---|
| ffmpeg `select` scene / `scdet` | Global MAFD (min of mafd, Δmafd) | **No** (measured miss) | Poor | Lowest | Pre-filter only |
| PySceneDetect `ContentDetector` (default, edges off) | HSV weighted | Weak | Moderate | Low | Better with edges on |
| **`ContentDetector` + edges, low thr** | HSV + edge delta | **Yes (expected)** | Moderate | Low | **Recommended primary** |
| `AdaptiveDetector` | Rolling-avg ContentDetector | Yes | **Best** | Low (2-pass) | For cut-heavy talks |
| Custom block-max / edge-map diff | Local max difference | Yes | Tunable | Medium | Fallback if Test A fails |
| SliTraNet / CNN | Deep model | Yes | Best | High (GPU-ish) | Out of budget |

---

## Q2 — Deduplication (the main open problem)

**Which hash.** Use a **difference hash (dHash)** or **perceptual hash (pHash)** on the *captured full-resolution* frames (not the downscaled detection frames). Both are in the `imagehash` library the owner already knows. Guidance on thresholds (all for 64-bit hashes unless noted):

- dHash: "distances less than 10 (96.09% similarity) likely indicate similar/duplicate images" **[community, mattpodolak/duplicate-img-detection citing hackerfactor, retrieved 2026-09-16]**. A production image store set a 128-bit dHash threshold of 2 for *near-identical* dedup **[community, benhoyt.com, retrieved 2026-09-16]**.
- pHash: `imagededup`'s documented default is **`max_distance_threshold=10`** (verbatim: "max_distance_threshold: ... hamming distance between two images below which retrieved duplicates are valid. (must be an int between 0 and 64). Default is 10.") — some code examples show 15, but 10 is the library default **[official doc, idealo/imagededup hashing.py, retrieved 2026-09-16]**. A fauxtography study tuned pHash to Hamming 6 (verbatim: "the maximum product of precision and recall is obtained at Hamming distance 6 (0.89 precision and 0.69 recall), hence, we use 6 as the threshold") **[peer-reviewed, arXiv 2009.11792, 2020]**; a controlled evaluation labels Hamming 0 = strict, 10 = moderate near-dup, 32 = relaxed for 64-bit hashes **[peer-reviewed, MDPI Electronics 15(7):1493, 2026]**.

**Recommended thresholds.** Two different jobs need two different distances:
1. **Collapse crossfade/transition pairs and inset jitter** (drop intermediate/dirty frames): treat frames within the **2-second** window (brief default) as one event, then within that event keep the frame with the **highest detection score** and the **latest timestamp** that still passes a similarity check.
2. **Global near-duplicate suppression across the talk** (same slide shown twice, speaker returns to a slide): dHash Hamming **≤ 6** to call two frames "the same slide" conservatively; use **≤ 10** only if Test C shows recall is safe. Bias low, because over-merging risks dropping a genuinely new slide (a miss), which is 10× worse.

**Keeping the last build state without losing a new slide.** Bullet builds are a monotonic sequence where each frame is a *superset* of the previous. The clean rule: within a run of detections that are each near-duplicates of their predecessor under a **loose** hash distance but where content is *growing*, keep only the **final** frame of the run (the last state before a change that exceeds the distance is detected). This reconciles with the brief's "capture at detection+500 ms" default as follows: capture at detection+500 ms as specified for the *citation timestamp and stored image*, but in the manifest also mark whether a frame was superseded by a later build; the dedup pass then drops superseded builds and keeps the terminal one. (A stricter "detect at change, then keep the frame just before the next distinct change" scheme would reopen the settled capture-time default, so I place it under **suggestions outside scope**.)

**Critical caveat — pHash on white slides.** Perceptual hashing "is ineffective when dealing with images that are dominated by a single background color (e.g., screenshots on a white background)" **[peer-reviewed, arXiv 2009.11792, 2020]**. Most text slides are dark text on white. This means pHash/dHash may *under*-distinguish two different mostly-white text slides (collapsing them = a miss). **Mitigation:** for slide-classified frames, prefer a higher-frequency hash (pHash from the DCT, which weights structure) and validate the merge with a secondary check — e.g., a coarse edge-map or text-region difference — before dropping a frame. This is important and under-appreciated; it is why dedup must be validated (Test C), not assumed.

---

## Q3 — Speaker cuts and picture-in-picture

Two cheap strategies, in increasing effort:

1. **Frame classification (slide vs camera), discard camera frames.** The cheapest discriminator is **edge density / text density**: slides have high, spatially-structured edge density (text and diagram lines); camera shots of a face have low, smooth edge density. Edge density is an established proxy for "visual clutter"/text in slide-analysis work **[peer-reviewed, "Seeing Like a Designer Without One," arXiv 2508.19289, 2025]**, and edge strength + edge density + horizontal distribution are standard text-frame classification features **[peer-reviewed, "Novel Edge Features for Text Frame Classification in Video," ResearchGate, retrieved 2026-09-16]**. Add OpenCV face detection to *reject frames dominated by a full-screen face* — exactly what `vid2slides` does ("throws out frames with full-screen faces detected with OpenCV") **[community, patrickmineault/vid2slides, retrieved 2026-09-16]**. A diagonal-covariance Gaussian model on tiny 64×64 grayscale DCT features was enough to separate slide/speaker/crowd classes in early work **[peer-reviewed, US Patent 6,751,354, retrieved 2026-09-16]**, confirming this is a low-dimensional, cheap problem.

2. **Score change only inside a detected slide region (crop-then-detect).** Detect the slide rectangle once (OpenCV, as `vid2slides` does — "detects a crop frame around slides using OpenCV") and run change detection only inside it, ignoring the speaker inset **[community, patrickmineault/vid2slides, retrieved 2026-09-16]**. This handles both the small-inset case and picture-in-picture. IBM's spatiotemporal matching used a SIFT+RANSAC background model and a binary slide/no-slide classifier feeding an HMM, ~95% accuracy — but it needs the original slide deck, which this channel does not provide **[peer-reviewed, Pan & Fan et al., WACV 2011, IBM Research, retrieved 2026-09-16]**.

**Cheapest approach that works:** classify by edge density with an OpenCV full-frame-face reject (strategy 1). Add region-cropping (strategy 2) only if Test A shows the speaker inset's motion is causing false detections that dedup can't absorb. Camera-classified frames are then sparse-sampled per the brief (1 frame / 5 min).

---

## Q4 — Screen recordings and demos

Screen recordings (live coding, terminal demos, scrolling) produce either **no discrete scene cuts** (continuous small changes never cross the threshold) or **thousands** (every keystroke/scroll triggers). Neither is "one clean frame per slide."

**Recognizing a screen-recording segment.** The signature is a **sustained high rate of small-magnitude changes**: many consecutive frames with low-but-nonzero difference (low `mafd`, high temporal frequency of sub-threshold change), low global motion, high text/edge density. Concretely: if over a rolling window (e.g., 30 s) the fraction of frames exceeding a *small* difference floor is high but few exceed the *slide* threshold, flag the window as "screen recording."

**Sampling policy for such segments.** Switch from event detection to **time-sampling** — one frame every N seconds (e.g., N=15–30) — and then run **mpdecimate-style near-duplicate rejection** so static stretches don't waste budget. ffmpeg's `mpdecimate` "drops frames that do not differ greatly from the previous frame"; its documented defaults are "default value for hi is 64*12 [=768], default value for lo is 64*5 [=320], and default value for frac is 0.33. A frame is a candidate for dropping if no 8x8 blocks differ by more than a threshold of hi, and if no more than frac blocks (1 meaning the whole image) differ by more than a threshold of lo." **[official doc, FFmpeg 8.0.3 mpdecimate, retrieved 2026-09-16]**. This gives "a frame whenever the screen has meaningfully changed, but never more than one per N seconds."

**Graceful degradation at the 400-frame / 150 MB cap.** When a talk would exceed the cap, degrade in this order:
1. **Per-segment budgets:** allocate the 400-frame budget proportionally across detected segments so a single runaway screen-recording section cannot starve the slide sections.
2. **Keep-highest-score within each segment:** rank the segment's candidate frames by detection score and keep the top-k that fit the budget (preserves the biggest visual changes).
3. **Uniform temporal thinning** as the final leveler: if still over budget, drop every other frame uniformly in time so coverage stays even rather than clustered.
This ordering protects slide recall (priority 1) while letting demo-heavy talks degrade to an even time-lapse. Record in the manifest that the cap was hit and which rule fired.

---

## Q5 — Memory

**The pipeline stays comfortably under 2 GB.** A single decoded 1080p frame is small: 1920×1080×3 = ~6.2 MB in RGB24, ~2.1 MB as 8-bit grayscale, and ~0.13 MB downscaled to 480×270 grayscale. ffmpeg filtergraphs hold only a handful of frames in flight (tens of MB); PySceneDetect on the OpenCV backend holds essentially the current and previous frame plus a downscaled working copy, and since v0.6 it decodes in a background thread and does its own downscaling via the `downscale`/`auto_downscale` properties **[official doc, PySceneDetect v0.6 release notes, retrieved 2026-09-16]**. Realistic peak resident set is a few hundred MB, dominated by the Python/OpenCV/ffmpeg runtimes, not frame buffers.

**Is downscale-before-detection needed for memory? No — only for speed, and even then optionally.** Because the compute budget is loose (measured 17× real time; a 30-talk day ~1 h), aggressive downscaling is unnecessary and *risky for recall*: reducing to 320–480 px can blur small text so a single-line bullet change disappears — the opposite of what we want given the miss penalty. **Recommendation: detect at a moderate scale (e.g., 720p / ~960–1280 px wide luma), not 320–480 px**, and reserve heavy downscaling only if a memory problem is actually observed. Confirm with **Test B** using macOS `/usr/bin/time -l`, which reports "maximum resident set size" (on macOS this field is in **bytes**, unlike GNU `time -v` which reports kilobytes) **[official doc / community, man time + baeldung.com, retrieved 2026-09-16]**. If measured max RSS approaches 2 GB, add downscaling; the loose CPU budget means this trade is free.

---

## Q6 — Output conventions

- **Frame naming:** `<video_id>/<video_id>_<detection_ms>.jpg` — video ID is the primary key (matches the project's storage convention), timestamp in **milliseconds from video start** in the filename so citations (`...&t=SECONDS`) derive directly.
- **JPEG quality:** **quality ≈ 90**, 1080p. Evidence for later OCR: practitioner guidance is that JPEG quality ~0.8 (≈80) "does not degrade OCR accuracy significantly," implying **85–95 is effectively lossless for OCR** while quality 100 buys nothing meaningful **[community, how-ocr-works.com, retrieved 2026-09-16]**; a countervailing caution notes default quality 70–80 "contains lots of compression artifacts that will make OCR detection of text very inaccurate," especially on small text **[community, SDSU/Tesseract guide (A. T. Young), retrieved 2026-09-16]**. I trust the conservative reading: stay at **≥90 and never re-save** (generational loss). The dominant factor is resolution/text size, not the quality factor: Tesseract "works best on images which have a DPI of at least 300," and its minimum-text-size guidance is verbatim "Accuracy drops off below 10 pt x 300dpi, rapidly below 8pt x 300dpi... Below an x-height of 10 pixels, you have very little chance of accurate results, and below about 8 pixels, most of the text will be 'noise removed'" **[official doc, Tesseract tessdoc ImproveQuality, retrieved 2026-09-16]**. Keeping 1080p (not downscaling the *stored* frame) is what protects future OCR; consider chroma subsampling 4:4:4 for text if size allows. (Note the honest evidence gap: no peer-reviewed paper found publishes a clean OCR-accuracy-vs-JPEG-quality curve for printed text/slides; the JPEG-QF sweeps that exist are for classification/segmentation tasks and show accuracy flat from ~Q100 down to ~Q50–80, collapsing only at Q10–30 — consistent with, but not a direct measurement of, OCR.)
- **Per-talk manifest (JSON, one file per video, with `schema_version` and `fetch_time`):** an array of frame records, each with:
  `detection_time_ms`, `capture_time_ms` (= detection+500 ms), `stored` (bool), `filename`, `scene_score` (raw detector score), `hash` (dHash/pHash hex), `kept` (bool), `drop_reason` (`crossfade_pair` | `near_dup` | `superseded_build` | `camera_frame` | `cap_thinned` | null), `segment_type` (`slide` | `camera` | `screen_recording` | `panel`), and `superseded_by` (filename or null). Add a talk-level block: detector + parameters, total detections, kept count, whether the anomaly fallback fired (0 or >1,500 detections → 1 frame/30 s + weekly-review line), and whether the 400-frame/150 MB cap fired and which degradation rule.
- **Thumbnail strip:** **yes, keep a contact-sheet** (ffmpeg `tile`) per talk. It is cheap, and it is the artifact that makes the 20-minute human validation and the weekly anomaly review fast. `select='gt(scene,T)',scale,tile` produces a mosaic in one command **[community, GDELT Project, retrieved 2026-09-16]**.

---

## Q7 — Is there an off-the-shelf tool to adopt?

**No tool fits this channel end-to-end; assemble your own and borrow ideas.** Assessment of the candidates:

| Tool | Method | Maintenance | Fit for this channel | Verdict |
|---|---|---|---|---|
| `patrickmineault/vid2slides` | ffmpeg keyframes → OpenCV full-screen-face reject → HMM slide-change → OpenCV crop; outputs JSON/PDF/GIF | Low activity | Closest conceptually; HMM tuned for single-camera lectures, outputs PDF not ms-keyed frames | **Borrow ideas** (face reject, crop) |
| `lukew3/vid2slides` | ffmpeg keyframes → Pillow ImageChops 2% diff dedup → PDF | Simple/low | Too naïve; global % diff = same MAFD weakness | No |
| `johan456789/slide-extractor` | `imagehash`+OpenCV frame diff → OCR → searchable PDF; **macOS-tested** | Moderate | Does OCR+PDF (out of scope), no ms timestamps or manifest | No (reference) |
| `HHousen/lecture2notes` | CNN slide classifier + perspective crop + clustering + OCR + summarization (PyTorch) | Active-ish, heavy | Overkill; PyTorch on 8 GB M1 for 1,135 talks is disproportionate | No |
| `SliTraNet` | Deep CNN slide-transition detection | Research code | GPU-oriented; outputs transitions, not stored frames | No (budget) |
| `slideextract` (szanni) | C/C++ region compare, one image per slide | Last push 2023-05-06 | Region-compare is sound but no dedup/manifest for these styles | No |
| PySceneDetect | Detector library | **Active, v0.7.1** | The right building block | **Adopt as component** |

The `awesome-video-to-slides` list itself concludes PySceneDetect is "useful as a baseline, though presentation builds often need slide-specific deduplication" **[community, larry-xue/awesome-video-to-slides, verified 2026-07-15]** — which is exactly the gap this brief's dedup design fills. Build on ffmpeg (decode) + PySceneDetect (`ContentDetector`+edges) + `imagehash` (dedup) + OpenCV (face reject / crop), and lift the face-rejection and slide-region crop from `vid2slides`.

---

## Recommended pipeline (parameters)

1. **Decode once** with ffmpeg using libdav1d (software AV1, ~17× real time measured; 30 fps talks faster). Emit two derived streams from the single decode where practical: a moderate-scale luma frame for detection and the full-res frame for capture.
2. **Detect** with PySceneDetect `ContentDetector`, `weights=(1,1,1,1)` (edges on), `threshold≈12–15`, `min_scene_len≈0.6–1 s`, detection scale ~720p. Use `AdaptiveDetector` on talks flagged cut-heavy.
3. **Classify** each detection's frame: edge-density threshold + OpenCV full-frame-face reject → `slide` / `camera` / `screen_recording` / `panel`.
4. **Capture** at detection+500 ms, full-res, JPEG q90, 1080p.
5. **Deduplicate:** (a) collapse detections within 2 s keeping highest-score/latest; (b) dHash Hamming ≤ 6 (≤10 if Test C permits) for global near-dups; (c) drop superseded bullet-build states, keep terminal; (d) validate white-slide merges with a secondary edge/text-region check.
6. **Camera/panel:** sparse-sample 1 frame / 5 min.
7. **Screen recording:** time-sample 1 frame / 15–30 s + mpdecimate-style dedup.
8. **Caps & anomalies:** hard cap 400 frames / 150 MB via per-segment budget → keep-highest-score → uniform thinning; 0 or >1,500 detections → fallback 1 frame/30 s + weekly-review line; never block.
9. **Write** JPEGs, per-talk JSON manifest, and a thumbnail contact sheet.

**Expected compute & memory.** Detection is dominated by the software AV1 decode (~17× real time at 60 fps, faster at 30 fps). A 30-talk day (~12.5 h of video) processes in ~1–1.5 h wall time even with detection overhead — well inside the 6 h budget; backfill (~463 h) ~30 CPU-hours, inside the 4-week window. Peak resident memory a few hundred MB — inside 2 GB (confirm via Test B).

---

## Five-talk validation plan

**Pick five talks spanning the production styles:** (1) clean full-screen slides; (2) full-screen slides with a small speaker inset; (3) alternating camera/slide cuts; (4) a screen-recording/code demo; (5) a camera-only panel.

**How the owner hand-labels true slide counts in <20 min/talk:** open the talk on YouTube, scrub at 1.5–2× using the generated **thumbnail contact sheet** as an index, and record the timestamp (ms) of each *distinct* slide state (count a completed bullet build as one slide, not one per bullet). For the panel, the expected true "slide" count is ~0; success is a non-empty sparse artifact.

**What to count per talk:**
- `T` = true distinct slides (human).
- `M` = misses: true slides with **no** kept frame within ±2 s → **recall = (T−M)/T**.
- `D` = kept distinct frames → **duplicate ratio = D / T**.
- Camera/screen-recording frames wrongly kept, or slides wrongly classified as camera.

**Targets:** recall ≥ 98% on slide talks (misses < 2%); duplicate ratio ≤ 2–3×.

**What result changes the parameters:**
- Misses > 2% → lower `threshold`, raise `delta_edges` weight, or switch to the block-max/edge-map fallback; reduce detection downscale.
- Duplicate ratio > 3× → tighten crossfade window handling or lower dHash distance; strengthen superseded-build dropping.
- White-slide false merges (two different slides collapsed) → raise hash bits / add the edge-region secondary check.
- Screen-recording section blows the cap or misses code changes → tune mpdecimate `hi/lo/frac` and the sample interval N.

---

## Exact local tests (only a local test can settle these)

- **Test A — detector recall.** Tool: ffmpeg + PySceneDetect. On the known 21-min talk, run (i) `ffmpeg -i in.mkv -vf "select='gt(scene,0.06)',showinfo" -f null -`; (ii) `scenedetect -i in.mkv detect-content -t 13 -w 1,1,1,1 list-scenes`; (iii) same with `detect-adaptive`. Input: the first 12 minutes (where misses were observed) and the 3:55–6:29 gap. Measure: number of true text-slide advances detected vs hand count. Change the recommendation if edge-weighted ContentDetector still misses the low-contrast advances → adopt the custom block-max/edge-map detector.
- **Test B — memory.** Tool: `/usr/bin/time -l python run_pipeline.py <talk>` on macOS. Measure: "maximum resident set size" (bytes). If it approaches 2 GB, enable/increase detection downscale and re-measure. This is the only way to settle peak RSS on the owner's exact M1 / 8 GB / ffmpeg-9.0.1 stack.
- **Test C — dedup threshold.** Tool: Python + `imagehash`. Compute dHash and pHash for all captured frames of talks 1–3; sweep Hamming 2–14; count merges that drop a genuinely distinct slide (bad) vs merges of true duplicates (good). Pick the largest distance with zero bad merges. Change the recommended ≤6 if the sweep shows headroom.
- **Test D — downscale-vs-recall.** Tool: PySceneDetect `downscale`. Re-run Test A at detection scales 1080p, 720p, 480p, 320p; measure recall of small-text changes at each. Sets the safe downscale for speed.
- **Test E — JPEG quality for OCR (defer-safe check).** Tool: ffmpeg export at q80/q90/q95 + a quick Tesseract pass on 10 slide frames. Measure character agreement vs q100. If q90 loses no characters, confirm q90; text extraction is a later project but this pins the storage parameter now.

---

## Open uncertainties, ranked by impact (cheapest experiment each)

1. **Does edge-weighted ContentDetector actually catch the low-contrast text advances?** (Highest impact — it is the whole recall target.) Cheapest experiment: **Test A** on the existing 21-min talk (minutes, no new data).
2. **White-slide hash collapse dropping distinct text slides.** (High — a silent miss.) Cheapest: **Test C** dHash/pHash sweep with human spot-check on talks 1–3.
3. **Screen-recording recognition and cap degradation on demo-heavy talks.** (Medium — affects code/demo talks, a real channel style.) Cheapest: run the mpdecimate + per-segment-budget path on one known demo talk and eyeball coverage.
4. **Peak memory on the real stack.** (Medium — could force downscaling.) Cheapest: **Test B**, one command.
5. **Detection downscale that is safe for small text.** (Lower — budget is loose so we can stay high-res.) Cheapest: **Test D**.
6. **JPEG quality floor for future OCR.** (Lowest now — OCR is a later project, and 1080p+q90 is already conservative.) Cheapest: **Test E** on 10 frames.

---

## Suggestions outside scope
- A "keep the frame just before the next distinct change" capture scheme would maximize final-build fidelity but reopens the settled detection+500 ms capture-time default; noted only as a future option.
- Aligning captured frames to the (rare) linked slide deck via SIFT+RANSAC/HMM (IBM WACV 2011 method) would give near-perfect slide boundaries but is impossible here — only 1 deck link exists across 205 sampled descriptions.
- Running OCR on the thumbnail strip to auto-suggest slide titles for the manifest (belongs to the later text-extraction project).

---

## Reference list (grouped by source type)

**Official documentation / primary source code**
- FFmpeg `libavfilter/f_select.c` (scene-score formula: `mafd`, `diff`, `av_clipf(min(mafd,diff)/100)`), FFmpeg source, retrieved 2026-09-16.
- FFmpeg `scdet` filter (MAFD basis; `lavfi.scd.mafd/score/time`), retrieved 2026-09-16.
- FFmpeg `mpdecimate` filter (defaults `hi=64*12`, `lo=64*5`, `frac=0.33`), FFmpeg 8.0.3 docs, retrieved 2026-09-16.
- PySceneDetect detectors (`ContentDetector`, `AdaptiveDetector` defaults and weights), scenedetect.com CLI & API docs, v0.7.1, retrieved 2026-09-16.
- PySceneDetect v0.6 release notes (background-thread decode, `downscale`/`auto_downscale`), retrieved 2026-09-16.
- idealo/imagededup hashing.py (`max_distance_threshold` default = 10), retrieved 2026-09-16.
- Tesseract `tessdoc` "Improving the quality of the output" (300 DPI, x-height thresholds), retrieved 2026-09-16.
- macOS `/usr/bin/time -l` "maximum resident set size" (man time), retrieved 2026-09-16.

**Peer-reviewed / academic**
- "An experimental comparative study on slide change detection in lecture videos" (edge-based shot-change for slide-structure), academia.edu, retrieved 2026-09-16.
- SliTraNet, "Automatic Detection of Slide Transitions in Lecture Videos using CNNs," TU Graz, 2022.
- Pan, Fan et al., "Robust spatiotemporal matching of electronic slides to presentation videos," WACV 2011, IBM Research.
- "Seeing Like a Designer Without One" (edge density as slide/visual-clutter metric), arXiv 2508.19289, 2025.
- "Novel Edge Features for Text Frame Classification in Video," ResearchGate, retrieved 2026-09-16.
- "Understanding the Use of Fauxtography on Social Media" (pHash Hamming-6 tuning; white-background weakness), arXiv 2009.11792, 2020.
- "Comparative Evaluation of Perceptual Hashing and Deep Embedding Methods," MDPI Electronics 15(7):1493, 2026.
- US Patent 6,751,354 (Gaussian slide/speaker/crowd classification on 64×64 DCT features), retrieved 2026-09-16.

**Vendor / commercial**
- CopySlides "Video to Slides Converter" (frame sampling + slide-change detection description), retrieved 2026-09-16.

**Community / practitioner**
- patrickmineault/vid2slides (face reject + OpenCV slide crop + HMM), GitHub, retrieved 2026-09-16.
- lukew3/vid2slides; johan456789/slide-extractor; HHousen/lecture2notes; szanni/slideextract; larry-xue/awesome-video-to-slides (verified 2026-07-15), GitHub, retrieved 2026-09-16.
- mattpodolak/duplicate-img-detection (dHash <10 rule, citing hackerfactor); benhoyt.com (128-bit dHash threshold 2), retrieved 2026-09-16.
- GDELT Project (ffmpeg scene→tile mosaic), retrieved 2026-09-16.
- how-ocr-works.com (JPEG ~0.8 does not significantly degrade OCR); SDSU/A. T. Young Tesseract guide (quality 70–80 artifacts hurt OCR), retrieved 2026-09-16.
- Baeldung / trembit.com (mpdecimate behavior; `/usr/bin/time` usage), retrieved 2026-09-16.