# Brief 06 — Audio Fingerprinting to Locate Talks Inside Conference Livestream Recordings

## TL;DR
- **Use audfprint (Dan Ellis, MIT license, Python) as the primary localization tool.** It is the only candidate that is pip-installable, pure-Python-plus-ffmpeg, runs far under 2 GB RAM, and — critically — natively returns a *time mapping* (multiple offset clusters with per-cluster time ranges and match counts) via `--find-time-range --max-matches N`, which satisfies the hard requirement that cut talks with removed sections/added intros be represented as several clusters rather than one best offset.
- **Run caption-text alignment alongside it as an independent consistency check, not a fallback.** Both the stream and each talk already carry timestamped auto-caption tracks, so a lexical-overlap sliding alignment is free, needs no audio decode, and votes on the same ±0.5 s / zero-false-positive targets from a completely different signal.
- **Compute nothing at download time.** No fingerprint format is tool-agnostic; audfprint fingerprints are cheap to (re)compute later (indexing runs at ~100× real-time), the retained unprocessed audio makes recomputation lossless, and committing to a fingerprint schema now would be premature. If the owner wants one optional cheap artifact, precompute audfprint `.afpt` peak files per talk, schema-versioned and explicitly discardable.

## Key Findings

1. **Only two open tools clear the hard requirement (a genuine time mapping) with acceptable install/memory on the M1: audfprint and Panako.** Chromaprint/fpcalc is a whole-track identifier that emits a single fingerprint string with no built-in localizer or cluster output; Olaf is excellent and tiny but its matcher reports one match region, not cleanly separated multi-cluster output, and needs an LMDB setup step on Apple Silicon; dejavu returns a single best offset and is effectively unmaintained; neural entrants (NeuralFP/PeakNetFP/neural-music-fp) require a GPU and TensorFlow/PyTorch and are training-heavy.

2. **audfprint is the recommendation.** MIT-licensed (per its GitHub `LICENSE`, dated as observed 2026-09-16), Python 3 + ffmpeg only, installed with `pip install -r requirements.txt`, and its `--find-time-range` output prints, per match, the matched duration, the start time in the query, the start time in the reference, and the count of consistent hashes — exactly a time-mapping row. Setting `--max-matches` above 1 makes it emit several such clusters per (query, reference) pair, which is how a trimmed/edited talk shows up.

3. **The owner's task is far easier than the published benchmarks suggest, because query and reference are literally the same recording.** In the ISMIR 2022 BAF broadcast-monitoring benchmark (Cortès et al., *"BAF: An Audio Fingerprinting Dataset For Broadcast Monitoring,"* pp. 908–916), **"none of the algorithms obtain a F1-score above 47%"** — but that task matches *background* production music (≈80% of annotated time is background music) inside unrelated TV audio. Here the cut talk and the stream segment are the *same* performance (only re-encoded, trimmed, re-leveled), which is the easy case landmark fingerprinting was built for. Expect very high recall and near-perfect precision, well inside the ±0.5 s and ≥95%-recall targets.

4. **Duplicate detection and re-edit detection fall out of the same index for free** — the canonical reason to index the corpus as the database.

## Details

### Q1 — Tool comparison against the hard requirement and targets

| Tool | License | Lang / deps | Maintenance (to 2026-09-16) | macOS/M1 install | Returns time mapping (multi-cluster + density)? | Index size / memory | Notes |
|---|---|---|---|---|---|---|---|
| **audfprint** | MIT | Python 3 + numpy/scipy + docopt + ffmpeg | Mature, low-churn; 611 GitHub stars, 169 commits; still the reference Python landmark tool | `pip install -r requirements.txt`; `brew install ffmpeg` (9.0.1 already present) | **Yes** — `--find-time-range`, `--max-matches N`, `--time-quantile`; prints per-match query start, reference start, matched duration, consistent-hash count | Hash table = 2²⁰ (~1M) buckets, 100 entries each, default 20 hashes/s; in the BAF benchmark audfprint produced the **smallest index of any system, 19 MB for 74 h** of reference | Must raise `--maxtimebits` (e.g. 16) so reference times beyond ~6 min don't alias; default 2¹⁸ = 262k-track ceiling |
| **Panako** | AGPL-3.0 | Java 17 + LMDB (lmdbjava) + JGaborator/Gaborator (JNI) + ffmpeg | Active in bursts; author states time is limited and "goes in activity bursts"; v2.1 (2022-05) set JDK 17 and added M1 support | Gradle wrapper build; per README, "current release does not support Apple M1 out of the box… additional steps are needed to provide the Java lmdb bridge" | **Yes** — query output columns: query start/stop (s), match start/stop (s), match score (matching-fingerprint count), and "seconds with match (%)"; one row per match region; time-scale + pitch robust | LMDB B+-tree; **273 MB index for 74 h** in BAF | Heavier stack; AGPL; Shazam-patent caveat (US7627477 B2, US6990453) noted in repo |
| **Olaf** | AGPL-3.0 | C (+ Zig/Ruby wrapper) + ffmpeg + LMDB | Active (copyright 2019–2025); JOSS-published 2023 | `make && make install`; LMDB key-value store setup on M1 | Reports a match region; not cleanly multi-cluster out of the box | **<512 kB RAM** per 20-s query on a 1-h index; ~2.5 s to analyze+store 1 h of audio (~1429× RT); **349 MB index for 74 h** in BAF | Extremely light/fast; embedded/IoT focus |
| **Chromaprint / fpcalc** | LGPL-2.1-or-later | C lib + ffmpeg | Active, widely packaged | `brew install chromaprint` (Homebrew formula present) | **No** built-in localizer; single compressed fingerprint per track (or `fpcalc -raw`); sliding alignment must be hand-rolled | tiny | Vendor description: "designed to identify near-identical audio… not a general purpose audio fingerprinting solution… trades precision and robustness for search performance"; target use = whole-file ID, dup detection, stream monitoring |
| **dejavu** | MIT | Python + MySQL/Postgres | Effectively stale (Python-3 port via community PRs) | pip + DB server | No — single best offset (align step collapses to one) | DB-backed | README: "for voice recognition, Dejavu is not the right tool" |
| **NeuralFP / PeakNetFP / neural-music-fp** | MIT/varies | Python + TF/PyTorch + FAISS (+GPU) | Active research (ICASSP 2021; PeakNetFP 2025; neural-music-fp ISMIR 2025) | Heavy; GPU expected (neural-music-fp: full train <1 day on 24 GB GPU) | Segment retrieval + timestamp, but not multi-cluster out of the box | ~1.25 GB subfingerprint DB in one report | Needs training/GPU; incompatible with the 8 GB M1 constraint; overkill for same-source matching |

**Verdict:** audfprint is primary; Panako is the credible backup if audfprint's time aliasing or density tuning proves fiddly (Panako is inherently time-scale-robust and gives a richer per-match row). Chromaprint is retained only conceptually, for cheap whole-file duplicate detection.

### Q2 — Parameters, query window, and false-match behaviour

- **Direction:** index the ~463 h talk corpus as the DB (canonical landmark usage; gives duplicate detection for free) and slide the *stream* against it in overlapping query windows. The inverse (index the stream, query with talks) also works in audfprint and Panako, but the corpus-as-DB direction is preferred because it is reused across every future stream.
- **Window length:** ~20–30 s windows with ~5–10 s overlap is the community-standard query length — Panako's `monitor` mode chops incoming audio into 25 s parts with 5 s overlap by default. Longer windows give more landmarks and safer ±0.5 s localization.
- **audfprint knobs:** `--density` (default 20 hashes/s; raise for robustness, lower for a smaller DB — the README notes "a density of 7.0 works well"); `--maxtimebits 16` (**mandatory** here: the default 14-bit time field aliases past ~6 min; 16 bits → ~25 min at 11 kHz, covering full talks); `--min-count` (raise from default 5 to ~20–50 to kill spurious matches); `--max-matches` >1 (to obtain multiple clusters); `--find-time-range`; `--exact-count`.
- **False-match behaviour when the query talk is NOT in that day's stream:** landmark matchers score matches by *temporally consistent* shared hashes. The audfprint README states: **"Generally, anything more than 5 or 6 consistently-timed matching hashes indicate a true match, and random chance will result in fewer than 1% of the raw common hashes being temporally consistent."** So a `--min-count` threshold set well above chance, combined with a minimum matched-duration requirement, cleanly rejects talks that are absent from the stream — the mechanism that delivers the zero-talk-level-false-positive target.

### Q3 — Compute-now decision

**Recommendation: compute nothing tool-agnostic at download time.** Every candidate uses an incompatible fingerprint representation (audfprint landmark hashes vs Chroma vectors vs Gabor peaks vs neural embeddings), so there is no portable intermediate that serves all tools. Because the unprocessed Opus/AAC is retained forever, fingerprints are a pure function of stored bytes and can be regenerated later as a background job at ~100× real-time. If the owner wants one optional cheap artifact anyway, store audfprint `precompute` `.afpt` files (peaks-only via `-K`/`--precompute-peaks`) per talk — schema-versioned, explicitly discardable, mergeable into a DB later with `merge`/`newmerge`. Size is on the order of the per-talk hash count (default ~20 hashes/s ⇒ ~30k hashes for a 25-min talk), i.e. a few hundred KB per talk — trivial against the ~40 MB of audio already kept per talk.

### Q4 — Duplicate & re-edit detection from the same index

- **Duplicates:** query a talk against the corpus DB; a near-100%-coverage, single-offset (slope-1) match to a *different* video ID = duplicate. This is the standard landmark-tool byproduct and requires no extra machinery.
- **Re-edits:** a talk vs its stream segment producing **multiple offset clusters** (each internally consistent but with a different query→reference offset) reveals removed sections / inserted intro cards; a break in the otherwise-linear match line marks the edit point. audfprint's `--find-time-range` exposes each cluster's time support; Panako's `same` reports the percentage of seconds that match and its per-match rows expose the same structure.

### Q5 — Speed on the M1

- **Indexing 463 h of talks:** audfprint's README shows ingest at ~0.008–0.011 × RT (≈**100× faster than real-time**) single-core; 463 h therefore indexes in roughly 4–6 h single-core, less with `--ncores`. Olaf reports ~2.5 s to analyze+store 1 h (~1429× RT) and Panako's own test shows ~80× RT store — both faster, but audfprint's speed is already comfortably inside budget.
- **Querying a 10-h stream** against that DB is the same order of magnitude — tens of minutes to ~1–2 h depending on density, window overlap, and cores. All comfortably within the "at most 1 hour/week of owner attention" budget, since the job is unattended.
- These are documented/vendor numbers and must be confirmed by the local test below.

### Q6 — Failure modes with conference audio

- **Music beds / applause / silence:** low-information, generate few stable landmarks; they simply produce no or weak matches — handled by the min-count threshold.
- **MC segments repeated across days & shared intro jingles:** these are genuinely repeated audio and will match in *multiple* places, producing spurious extra clusters. Mitigate by requiring a minimum matched *duration* per accepted cluster and by ignoring clusters that map to known boilerplate; the caption cross-check disambiguates which cluster is the real talk body.
- **Two talks with the same intro jingle:** the jingle matches both talks, but the *body* of each talk matches only its own segment; select the dominant long cluster, not the short jingle cluster.

### Q7 — Ranked alternatives; what runs alongside

1. **Caption-track text alignment — RUN ALONGSIDE (consistency check, not fallback).** Both the stream and each talk already have timestamped auto-caption tracks downloaded (json3, en/en-orig). Convert each to a timestamped token sequence and find the offset(s) that maximize lexical overlap in sliding time buckets (the standard subtitle-sync approach: bucket both sequences, search for the offset minimizing token mismatch, refine). It is free, needs no audio decode, and is fully independent of the acoustic path. **Scoring against the same targets:** report a located start per talk, count it a hit if within ±0.5 s of ground truth, and flag any talk where the caption-derived start and the fingerprint-derived start disagree by >0.5 s as needing review. Caveat: caption text drifts over time (2 of 10 tracks changed by a few percent over two weeks per the shared context), so use fuzzy/lemmatized matching and treat captions strictly as corroboration, never as the authority for citation timestamps.
2. **Schedule times** — weak prior only; useful to seed/limit the search window, not to localize to the second.
3. **Title-slide detection in keyframes (brief 09)** — out of scope here except as a future third vote.

## Recommendations

1. **Adopt audfprint.** Install `pip install -r requirements.txt` into the Python 3.13 archive venv; ffmpeg 9.0.1 is already present. Build the reference DB from the retained best-AAC talk audio (audfprint decodes Opus/AAC via ffmpeg, so no manual PCM step) with `--maxtimebits 16` and a tuned `--density`.
2. **Run the confirmation test** (below) on **Code 2025 Day 2** (ID `xmbSQz-PNMM`, 9.0 h, 26 chapters, 67 corpus talks) and **Europe 2026 Day 1** (ID `O_IMsEg91g8`, 9.2 h, 23 chapters, 187 corpus talks), using the YouTube chapter timestamps as ground truth.
3. **Cross-check three talk starts** per recording with caption alignment; require agreement within ±0.5 s.
4. **Compute-now: skip.** Optionally emit discardable, schema-versioned `.afpt` peak files.
5. **Thresholds that would flip the recommendation:** if audfprint recall <95% on the chaptered test, or any talk-level false positive survives min-count/duration tuning, switch primary to **Panako** (time-scale-robust, richer per-match output). If resident memory during query exceeds ~2 GB, lower `--density` and/or shard the DB.

### The confirmation test (exact shape)
- **Tool:** audfprint on the M1; single machine, no network.
- **Index:** `python audfprint.py new --dbase code2025.pklz --maxtimebits 16 --density 20 <the 67 Code-2025 talk AAC files>`.
- **Query (sliding, multi-cluster):** `python audfprint.py match --dbase code2025.pklz --find-time-range --exact-count --max-matches 50 --min-count 20 --maxtimebits 16 --sortbytime <stream.m4a>` (feed the stream in 30 s windows / 10 s hop, or as the full file if memory allows).
- **Inputs:** the 9.0-h Code 2025 Day 2 stream audio; the 67 talk audio files; the 26 chapter timestamps as ground truth.
- **Measure:** (a) for each chapter, whether the located talk start falls within **±0.5 s** of the chapter timestamp; (b) **recall** = talks located / talks present (target ≥95%); (c) **talk-level false positives** = matches to talks not in that day's stream (target 0 after thresholding); (d) inspect the multi-cluster output on any talk known to carry an added intro card / removed section.
- **Cross-check:** independently run caption alignment for 3 chapter starts and compare to the fingerprint result.
- **Result that changes the recommendation:** any false positive surviving threshold tuning, recall <95%, or offset error >0.5 s ⇒ escalate to Panako and re-run the identical test.

## Caveats
- **The BAF/ISMIR-2022 low-recall result does not bound performance here.** That benchmark (74 h / 2,000 Epidemic Sound reference tracks vs 57 h of TV audio, ~80% background music) reported seconds-based F1 of **0.47 (their PeakFP baseline), 0.12 (Panako 2.0), 0.11 (Olaf), and 0.04 (audfprint default)** — but those measure matching *background* music inside unrelated broadcast audio, and the authors note audfprint "reports 1 match per query by default," penalizing it there. In the owner's task the query and reference are the *same* recording, which is the easy same-source case. Interestingly, on precision the paper states **"PeakFP, Panako, Olaf obtain over 0.96,"** while cautioning that "BAF is not challenging to False Positives since the reference set is limited to 2,000 references" — a caveat that *favors* the owner, whose reference set is also small (hundreds of talks per event). This is an interpretive inference, flagged as such.
- **Landmark fingerprinters are tuned for music; these are spoken-word talks.** Speech still produces spectral peaks and same-recording matching is the easy case, but landmark robustness to *degraded* speech queries is weaker than for music. Not a concern for same-source matching; relevant only if stream vs cut-talk audio levels differ substantially, which the parameters (higher density, min-count) accommodate.
- **Panako's Shazam-related patents** (US7627477 B2, US6990453) are flagged in its own README; audfprint (MIT) and Chromaprint (LGPL) carry no such notice. For a private, non-commercial local archive this is unlikely to matter, but it is one more reason to prefer audfprint.
- All tools are free/open-source (no license cost, within the $40/month budget). Install commands and repository states are as observed 2026-09-16.
- The researcher cannot run the owner's machine; all speed/memory figures are from project docs and papers and must be confirmed by the local test.

### Suggestions outside scope
- A third vote from title-slide OCR (brief 09) would make the eventual reconciliation robust to simultaneous audio *and* caption failure.
- Chromaprint `fpcalc` could be used purely for cheap whole-corpus duplicate detection, independent of localization, if that becomes desirable.

### Open uncertainties (ranked) and the cheapest experiment that resolves each
1. **Does audfprint's `--find-time-range` output cleanly separate multiple clusters on a real edited talk?** (Highest impact — it is the hard requirement.) Resolve: run the confirmation test on one talk known to have an added intro card / removed section and inspect the reported clusters.
2. **Actual M1 resident memory at the 2,000-h reference scale.** Resolve: build a ~500-h DB and watch RSS during a 10-h query; extrapolate against the 2 GB ceiling.
3. **Caption-drift effect on alignment agreement.** Resolve: run caption alignment twice, days apart, on a track known to have changed, and measure offset stability.
4. **Whether raising `--density` is needed for spoken-word robustness.** Resolve: rerun the confirmation test at density 20 vs 40 and compare recall/offset error.