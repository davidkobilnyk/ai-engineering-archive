# Brief A1: Transcription Candidates — Recommendation

## TL;DR
- **Benchmark three transcribers against the 1,041-talk edited corpus: ElevenLabs Scribe v2 (batch), Deepgram Nova-3, and a corrected-YouTube-caption arm.** All three keep names via keyterm/keyterm-style biasing (1,000, 100, and N/A terms respectively), all clear the $40/month budget by a wide margin at this volume (~7,500 min/yr → ~$28–32/yr in transcription), and all expose async batch APIs callable unattended from an AWS scheduled job. Scribe v2 is the accuracy favorite; Nova-3 is the cost/speed/keyterm-maturity favorite; the corrected-caption arm is the freshness/near-zero-cost favorite whose quality is the biggest open question.
- **No hosted ASR removes the name problem on its own.** The literature shows contextual biasing reliably lifts entity/keyword recall (Deepgram's docs claim Keyword Recall Rate improvements "up to 90%," and the Talkatoo vet-tech case reports a "625% improvement in keyterm recognition") but rarely fixes names entirely, and long/global bias lists can *hurt* precision via hallucinated insertions. This confirms the owner's plan: transcription **plus** a separate LLM correction pass (Brief A2) is required to reach the ≤1% entity-error bar. Whisper-class self-transcription is explicitly **not** recommended as the primary transcriber given the owner's own spike (≈1-in-10 names wrong) and documented hallucination on silence/applause.
- **The corrected-caption arm is "unknown, leaning viable for content but risky on names/formatting."** YouTube auto-captions run ~9.9% median WER on general English but degrade sharply on accents + dense technical vocabulary; the owner's 39.7% name error and 33.7%-punctuated numbers are consistent with published tech-content results. The deficit is *mostly* names + punctuation (fixable in correction) rather than content words — but re-punctuation/re-segmentation and residual content errors on non-native speakers are real risks. Benchmark it as a genuine option, as the owner asks.

## Key Findings

### The candidate list in the brief is stale; update it
Several products named in the brief have been superseded by 2026 releases:
- **Deepgram Nova-3** (batch $0.0043/min, verified on Deepgram's pricing page Sep 2–8 2026) replaced Nova-2 as flagship; **keyterm prompting** (up to 100 terms) is Nova-3-only and is the relevant biasing mechanism (legacy "Keywords" is Nova-2 and older).
- **OpenAI**: the March-2025 `gpt-4o-transcribe` is superseded for new projects by **`gpt-transcribe`** (released Jul 28 2026, $0.0045/min) plus a dedicated **`gpt-4o-transcribe-diarize`** for speaker labels. `gpt-transcribe` and the 4o models accept a prompt/keyword field; the diarize model does *not* support prompts, and word-level timestamps still require the legacy `whisper-1`.
- **Mistral Voxtral Transcribe 2** (released Feb 4 2026): **Voxtral Mini Transcribe V2** batch at $0.003/min with diarization, context biasing, word timestamps, 13 languages; ~4% WER on FLEURS (vendor). Cheapest credible hosted option.
- **ElevenLabs Scribe v2** (batch, released Jan 2026) at **$0.22/hr** ($0.0037/min); keyterm prompting +$0.05/hr, entity detection +$0.07/hr.
- **AssemblyAI Universal-3 Pro** ($0.21/hr = $0.0035/min); **Universal-3.5 Pro** released Jul 7 2026. `keyterms_prompt` up to 1,000 terms (pre-recorded), max 6 words/phrase.
- **Amazon Transcribe**: standard $0.024/min Tier 1; custom vocabulary/CLM +$0.006/min; diarization bundled; 15-second minimum per request.
- **Local/open**: Whisper large-v3 / large-v3-turbo; **NVIDIA Parakeet TDT 0.6B v3** (6.32% English WER on Open ASR, ~60x real-time on Apple Silicon via `parakeet-mlx`) and **Canary Qwen 2.5B** (5.63% Open ASR, briefly leaderboard-topping); Voxtral open weights. The open-weights race is now separated by <1 WER point (Cohere Transcribe 5.42%, IBM Granite Speech 4.1 5.33%, all 2026).

### Comparison table (dated citations per cell)

| Candidate | Accuracy (accented/technical) | Timestamps | Keyterm biasing (limit) | Fillers kept? | Diarization | Price/min (batch) | Max file / rate limits | Hallucination on silence |
|---|---|---|---|---|---|---|---|---|
| **ElevenLabs Scribe v2 (batch)** | Best on independent Artificial Analysis non-streaming leaderboard: Scribe v2 ranked 4th overall at 2.2% AA-WER (retrieved Sep 2026); its AA-WER v2 update reports "a word error rate of just 2.3 percent," leading; vendor 96.7% EN | Word-level (vendor) | keyterm prompting, **up to 1,000 terms, 50 chars each** (+$0.05/hr) | Verbatim default; "No Verbatim" mode toggles filler removal | Up to 32–48 speakers (batch only); no published DER | **$0.0037/min** ($0.22/hr) | Files up to 10 hrs; async + webhooks | Detects/tags non-speech events (laughter, music) — designed for messy audio |
| **Deepgram Nova-3** | Vendor 5.26% median WER pre-recorded; independent leaderboards mid-pack | Segment + word-level, high precision | **keyterm prompting, up to 100 terms** (Nova-3 only); +~$0.0013/min; KRR "up to 90%" | Configurable; not verbatim by default | Bundled free (batch); +$0.002/min (streaming); no published DER | **$0.0043/min** (PAYG, verified Sep 8 2026) | Batch async; parallelizable | Not specifically documented; CTC-family generally robust vs. Whisper |
| **Corrected YouTube auto-caption** | ~9.9% median WER general English; ~78% (≈22% WER) on jargon-heavy tech (independent) | Segment-level (caption cues) | None at capture; biasing happens in LLM correction | Not verbatim (captions drop fillers) | None | **~$0 transcription** (only LLM correction cost) | Depends on yt-dlp acquisition (Brief B) | N/A (captions omit rather than hallucinate) |
| **Mistral Voxtral Mini Transcribe V2** | ~4% FLEURS (vendor); AA-WER competitive; Voxtral Small 2.8–3.0% open-weights | Word-level | Context biasing (limits undocumented) | Undocumented | Speaker labels + timestamps (batch) | **$0.003/min** | Files up to 3 hrs | Not documented |
| **AssemblyAI Universal-3(.5) Pro** | Vendor mean WER ~5.6% (U-3 Pro) / 4.35% (U-3.5 Pro); top-tier | Word-level | **keyterms_prompt up to 1,000 (6 words/phrase)**; +$0.05/hr on U-3 Pro | `prompt` controls disfluencies/formatting | Speaker-count error 2.9% (vendor); part of platform | **$0.0035/min** ($0.21/hr) | Async; 5 concurrent (free), 200+ (paid) | Documented hallucination fixes in changelog |
| **OpenAI gpt-transcribe** | Vendor: 19.27% vs whisper-1 40.37% CommonVoice (22 langs) | **No word timestamps** (whisper-1 only); diarize model separate | prompt/keyword field (soft hints; ~224 tok on whisper-1) | Can preserve fillers via prompt | Separate `gpt-4o-transcribe-diarize` model | **$0.0045/min** | 25 MB upload limit → chunking | Whisper-lineage; known silence hallucination |
| **Amazon Transcribe** | Independent: trails leaders | Word-level | Custom vocabulary/CLM (+$0.006/min) | Configurable | Bundled (≤ ~5–10 speakers) | **$0.024/min** Tier 1 | 15-sec min/request | Not documented |
| **Groq Whisper large-v3 / turbo** | Whisper-class (~12% WER turbo) | Word + segment | prompt field (Whisper-style) | Whisper drops fillers by default | None | **$0.04/hr turbo** ($0.00067/min); $0.111/hr large-v3 | 2,000 req/day free; 10-sec min/req | Whisper silence hallucination |
| **Local Whisper large-v3-turbo (MLX)** | Owner spike: 4.6% WER but ~1-in-10 names wrong | Segment; word via WhisperX | prompt (~224 tokens) — owner found it did NOT fix names | Drops fillers by default | Via pyannote/WhisperX add-on | ~$0 (Mac electricity) | M1/8GB: 4.5–7.2x real-time (owner spike) | High on silence/applause (well-documented) |
| **Local Parakeet TDT 0.6B v3 (MLX)** | 6.32% EN Open ASR (better than turbo 7.83%) | Word + segment | CTC keyword boosting (via CTC-WS) | Not verbatim | Via pyannote | ~$0 | ~60x real-time on Apple Silicon (M3/M4; M1 lower, runs on 8GB) | CTC-family robust vs. Whisper |

### Biasing evidence (the decisive question for the global-vs-per-talk split)
The most directly relevant study is **Contextual Earnings-22** (Argmax, arXiv 2604.07354, Mar 28 2026) — earnings calls with dense proper nouns, tested on Deepgram Nova-3, Whisper (prompt), AssemblyAI, Whisper-OSS, and CTC-WS boosting. Findings that map onto this pipeline:
- **Context reliably raises keyword F-score for every system**, but **WER changes are small and inconsistent — sometimes worse** (OpenAI's WER *increased* under context in their setup).
- **Local context (only terms actually in the clip) is systematically easier** and yields higher precision than **global context (full inventory with distractors)**, which "primarily stresses precision" via distractor-induced false positives.
- Documented failure modes from large/global lists: **hallucinated insertion of context words not spoken, partial/empty outputs, and even language switching.** Whisper-OSS produced a repetition loop ("Sify, Sify, Sify…") under context.

This is strong evidence for the owner's exact design: **a small per-talk list (~5 speaker/title/summary terms) is the high-value, low-risk lever; a large global list of ~50 risks precision loss and artifacts.** A Deepgram GitHub discussion (#1233) corroborates the precision risk directly: increasing the number of keyterms "leads to a higher error rate… the model begins to overfit, often forcing matches." The right split is per-talk terms always applied, plus a global ~50 kept short and de-duplicated — and crucially, most hard name correction should happen in the **LLM correction stage** (Brief A2), not by over-stuffing the ASR bias list.

Academic corroboration that biasing helps proper nouns specifically: contextual density-ratio biasing cut name errors 46.5% relative vs. an E2E baseline (arXiv 2206.14623); n-gram boosting improved biasing-WER 26% relative on in-domain keywords (arXiv 2308.02092). All show the same shape: large gains on the biased terms, marginal/mixed effect elsewhere.

### Keyterm/vocabulary per-request limits (determines Q4 split)
- **ElevenLabs Scribe v2 batch: up to 1,000 keyterms, 50 chars each** (realtime: 50 terms, 20 chars). +$0.05/hr.
- **AssemblyAI Universal-3 Pro: up to 1,000 terms** (max 6 words/phrase); Universal-2: 200. +$0.05/hr on U-3 Pro (free in beta on Universal).
- **Deepgram Nova-3: up to 100 keyterms** (plain terms, no weights); Deepgram's docs state that beyond 100 you "contact us to discuss custom model training… available on our Enterprise Plan."
- **Speechmatics: up to 1,000 custom-dictionary words**, included free.
- **Amazon Transcribe: custom vocabulary** (thousands of entries) but +$0.006/min for CLM.
- **OpenAI whisper-1 prompt: 224-token cap**; gpt-transcribe keyword field larger but soft hints only.

**Conclusion for Q4**: all three shortlist candidates comfortably hold the global ~50 list; the ~5 per-talk terms matter most, and both the literature and Deepgram's own issue tracker say keep the list tight to protect precision.

### YouTube auto-captions as a candidate (Q5)
- **Latency**: the owner's feed shows the raw auto-caption *record* ~2 weeks out, but the *caption track itself* is usually fetchable via yt-dlp much sooner — the freshness advantage is real if acquisition works (Brief B scope).
- **Accuracy (independent 2026 studies)**: a 264-video study (997,401 words of human ground truth) found **median WER 9.9%, mean 14.8%**, with a 10th–90th-percentile spread of 1.7%–31.5%; **20% of captions had zero sentence-ending punctuation and 32% lacked commas** — and even among sub-10%-WER transcripts, 27% still had zero sentence punctuation. On jargon-heavy technical content an independent test measured YouTube captions at **78% accuracy vs. Whisper's 94%**, with consistent errors on terms like "asymmetric encryption," "superposition," "eigenstate." For accented/multi-speaker content (panels, international speakers), a 2026 accuracy guide puts auto-captions at **75–85%**. These match the owner's corpus (39.7% name error, 33.7% punctuated).
- **The prior (deliverable 3)**: **unknown, leaning "viable for content, fails raw on names/formatting until corrected."** The deficit is mostly names + punctuation + casing (fixable), not wholesale content-word loss, though non-native accents widen the gap. An LLM caption-correction study (arXiv 2412.00342) cut caption WER from 23.07% to 9.75% (ChatGPT-3.5) — showing LLM correction recovers most of the deficit and supporting the arm as a genuine competitor, not a fallback. Benchmark it head-to-head.

### Diarization (panels/workshops, ≤15% DER target)
No provider publishes a classic time-based DER for Scribe v2, Nova-3, or AssemblyAI on panel audio. The closest cross-provider numbers come from **AssemblyAI's own (vendor) benchmark** using cpWER on meeting corpora (DiPCo/CALLHOME/NOTSOFAR/AMI): Universal-3.5 Pro 30.17% avg cpWER, ElevenLabs Scribe v2 35.26%, Deepgram Nova-3 37.93% (lower better; interested-party source). AssemblyAI also claims a 2.9% speaker-count error rate and a 17.62% streaming DER (vendor). Truly independent DER on meeting corpora comes from academia/pyannoteAI/Picovoice, but those largely exclude these three cloud providers with extractable numbers. For the **local diarization sidecar**, the transparently benchmarked options are **pyannote (~12–14% AMI DER, 9–11% VoxConverse)** and **NVIDIA Sortformer (~32% AMI SDM DER, hard 4-speaker cap)**; an independent ETH Zurich benchmark (arXiv 2509.26177, Sep 30 2025) reports pyannoteAI 11.2% and DiariZen 13.3% average DER, with Sortformer degrading badly beyond 4 speakers.

**Recommendation: run diarization as a provider-independent pyannote sidecar** (the owner already plans a timestamp-aligned sidecar), since it plausibly hits the ≤15% target on ≤4-speaker panels, is provider-independent, and survives upstream replacement — rather than relying on any single ASR vendor's bundled, un-benchmarked diarization.

### Error classes beyond names (Q3)
- **Spoken numbers / version strings** ("four point five" → "4.5"): best handled downstream by the LLM correction pass; ASR inverse-text-normalization is inconsistent across vendors. A correction-stage concern (A2), not a transcriber discriminator.
- **Punctuation/segmentation/casing**: Whisper-class and Scribe produce well-punctuated, cased, sentence-segmented output (owner's spike confirmed for Whisper). YouTube captions are the weak case (one-third punctuated) — the corrected-caption arm must re-punctuate and re-segment.
- **Repetition loops / hallucinated phrases**: a documented Whisper failure mode, especially under context prompts and on silence/music. This is the single strongest reason to prefer a non-Whisper primary transcriber (Scribe/Nova-3) and to add VAD if any Whisper variant is used.
- **Code identifiers** (`llm-d`, `prefill`): the owner's spike shows even prompted Whisper mangles these ("LLMD", "pre-fill"); these must be caught by the closed-vocabulary correction pass.

### Bedrock billing (verification requested)
**Verified**: Amazon Bedrock bills Claude at per-token on-demand rates with **no monthly floor / no minimum spend**. On-demand token rates for Claude on Bedrock match Anthropic's direct API (e.g., Sonnet-class ~$3/$15 per M input/output tokens; batch 50% off; prompt caching up to 90% off), read from AWS's pricing page and multiple dated 2026 sources (Sep 8 2026; Aug 24 2026). The only Bedrock services with a monthly floor are Knowledge Bases / OpenSearch Serverless (~$350+/mo) and Provisioned Throughput — none of which this pipeline needs. This confirms the brief's assumption: Bedrock Sonnet-class correction has no fixed cost, only per-token.

### Cost sanity check against the $40/month budget
At ~7,500 audio min/year (~625 min/month average; bursts up to ~300 talks × ~20 min ≈ 6,000 min in a few weeks):
- **Scribe v2**: 7,500 min × $0.0037 + keyterm $0.05/hr ≈ **~$28/yr** transcription.
- **Nova-3**: 7,500 × $0.0043 ≈ **~$32/yr**.
- **Corrected caption**: ~$0 transcription; only LLM correction cost.
- Even a 6,000-minute burst month costs **~$22–26** in transcription — well under $40/month, before LLM correction (A2) and S3/SNS (C). **Transcription cost is not the binding constraint; accuracy and freshness are.**

## Details

### Shortlist of transcribers for the Brief A2 benchmark (deliverable 2)

**1. ElevenLabs Scribe v2 (batch) — the accuracy pick.**
- *Why*: Best independent accuracy (Artificial Analysis non-streaming leaderboard, Scribe v2 4th overall at 2.2% AA-WER; AA-WER v2 update reports it leading at ~2.3%); verbatim by default (keeps fillers, matching upstream style) with an optional "No Verbatim" mode; the largest keyterm budget (1,000 terms) comfortably holds the global ~50 + per-talk lists; designed for messy audio with non-speech event tagging (mitigates applause/laughter hallucination); word-level timestamps and up to 32–48-speaker diarization; async batch with webhooks and 10-hour file support (handles hour-plus panels). Price ~$0.0037/min is trivial.
- *Key risk*: Closed, undisclosed model with **no published DER** — panel diarization is unproven and must be validated (favor a pyannote sidecar). It is a newer STT entrant; long-term API stability less proven than AWS/Deepgram.

**2. Deepgram Nova-3 — the cost/keyterm/throughput pick.**
- *Why*: Cheapest credible enterprise-grade hosted option with a first-class **keyterm prompting** mechanism built for proper nouns (KRR "up to 90%"; the Talkatoo vet-tech case reports moving from "only 10% of critical veterinary terms" recognized to a "625% improvement in keyterm recognition"); fastest documented throughput (605x real-time on Artificial Analysis); diarization bundled free on batch; high-precision word timestamps; transparent per-minute pricing with no floor; batch async trivially callable from AWS. It is the direct commercial baseline in the Contextual Earnings-22 study, so its biasing behavior on proper nouns is documented.
- *Key risk*: Keyterm cap of **only 100 terms** (vs. 1,000 for Scribe/AssemblyAI) — fine for the ~50 global + ~5 per-talk list today but limits headroom as vocabulary grows, and Deepgram's own issue tracker warns that pushing more keyterms raises error rates via overfitting; independent leaderboard accuracy is mid-pack, so it leans harder on the LLM correction stage; not verbatim by default (may drop fillers — acceptable per brief, since fillers are preferred not required).

**3. Corrected YouTube auto-caption — the freshness/near-zero-cost pick (benchmark as a real option, per the owner).**
- *Why*: Near-zero transcription cost, fastest path (no audio download or ASR inference), same acquisition risk as audio. Evidence says the deficit is mostly names + punctuation (fixable by the LLM pass) rather than content words, and LLM caption correction has recovered WER from ~23% to ~10% in a study. If it passes the A2 benchmark, it is the cheapest and freshest option by far.
- *Key risk*: Quality ceiling is YouTube's ASR — on jargon-heavy, non-native, multi-speaker talks the raw WER (~22% on tech content; 75–85% accuracy on accented/panel audio) and near-total lack of punctuation/casing put heavy load on correction, and residual content-word errors on accented speech may be unrecoverable. No diarization. Highest uncertainty of the three.

*Not shortlisted, and why*: **Mistral Voxtral Mini Transcribe V2** is the honorable mention — cheapest ($0.003/min), open-weights sibling, diarization + context biasing + word timestamps — a reasonable fourth arm if benchmark bandwidth allows; excluded from the top three only because Scribe (accuracy) and Nova-3 (keyterm maturity) have more documented proper-noun evidence. **Local Whisper/Parakeet** belong in the **Mac fallback** (Q6), not the primary stack: the owner's spike proved Whisper leaves ~1-in-10 names wrong and the primary stack must not depend on the Mac. **OpenAI gpt-transcribe** is deprioritized: no word-level timestamps (needs whisper-1), 25 MB upload limit forcing chunking on hour-long panels, and diarization requires a separate model. **Amazon Transcribe** (the AWS-native tiebreaker) is deprioritized on accuracy — it trails leaders independently — but is a viable low-effort AWS-native fallback. **Speechmatics** is a strong dark-horse (1,000-word dictionary free, diarization free, strong accent claims) worth a slot if one opens.

### Local feasibility for the Mac fallback (Q6)
On an M1/8GB the owner's spike measured Whisper large-v3-turbo (MLX) at **4.5–7.2x real-time**. **Parakeet TDT 0.6B v3 via `parakeet-mlx`** is both more accurate (6.32% vs 7.83% English WER) and far faster (~60x real-time on M3/M4; lower on M1 but community reports confirm it runs on 8GB machines, ~2GB model footprint). For a **300-talk burst** (~6,000 audio min): at a conservative M1 Parakeet throughput of even 20–30x real-time, wall-clock compute is **~3.5–5 hours**; at Whisper-turbo's 5x, **~20 hours** spread over nightly launchd runs. **Recommendation for the fallback: Parakeet TDT 0.6B v3 (MLX)** for speed/accuracy, with a pyannote diarization sidecar and mandatory VAD to suppress silence hallucination; keep Whisper-turbo as compatibility backup. Both still require the LLM correction pass — local ASR changes the cost/latency profile, not the accuracy conclusion.

### Open uncertainties ranked by impact on the shortlist (deliverable 4)
1. **Does the corrected-caption arm pass ≤1% entity / ≤5% WER after LLM correction?** (Highest impact — it would be the cheapest, freshest winner.) *Cheapest experiment*: on the 44 World's Fair 2026 auto-caption talks that now have edited upstream transcripts, run caption→LLM-correction and score against the edited reference. Zero new transcription cost; reuses existing before/after pairs.
2. **Panel diarization: can any candidate + pyannote hit ≤15% DER?** (High — a pass criterion with no public numbers for these providers.) *Cheapest experiment*: hand-label speaker turns on 2–3 archived panels, run pyannote sidecar + one hosted diarizer, compute DER.
3. **Scribe v2 vs Nova-3 head-to-head entity error on this exact domain.** (Medium-high — decides the primary transcriber.) *Cheapest experiment*: transcribe 20–30 talks spanning native/non-native speakers with each (global 50 + per-talk 5 keyterms), score entity error against edited references *before* any LLM correction, isolating the transcriber's contribution.
4. **Does per-talk biasing measurably beat global-only here?** (Medium — validates the Q4 design.) *Cheapest experiment*: on the same talks, run each transcriber with (a) global-50 only vs (b) global-50 + per-talk-5; compare entity error and precision (watch for distractor-induced false positives per Contextual Earnings-22).
5. **Voxtral Mini Transcribe V2 real accuracy on non-native technical English.** (Low-medium — could promote the cheapest option.) *Cheapest experiment*: add it as a fourth arm on the same 20–30-talk set.

## Recommendations
1. **Build the minimum stack around Deepgram Nova-3 as the day-one primary transcriber** (fastest to integrate, cheapest, keyterm prompting mature, diarization bundled, batch async trivially callable from an AWS scheduled job), and **run Scribe v2 and the corrected-caption arm in parallel on the A2 benchmark.** Rationale: Nova-3 gets a working unattended pipeline live by Sept 23; the benchmark then decides whether to switch the primary to Scribe (if accuracy wins) or the corrected-caption arm (if it passes).
2. **Always apply the ~5 per-talk keyterms (speaker names, title/summary terms); keep the global list tight (~50, de-duplicated).** Local context is the high-value lever; long global lists erode precision. Do not attempt to fix all names via ASR biasing — reserve hard cases for the LLM correction stage (A2).
3. **Run diarization as a provider-independent pyannote sidecar aligned by timestamp**, not via any single ASR vendor's bundled diarization, so it survives upstream replacement and targets ≤15% DER on ≤4-speaker panels.
4. **For the Mac fallback, use Parakeet TDT 0.6B v3 (MLX) with VAD + pyannote**, Whisper-turbo as compatibility backup.
5. **Decision thresholds that change the plan**:
   - If the corrected-caption arm hits ≤1% entity error and ≤5% WER after LLM correction on the 44 World's Fair talks → **make it the primary** (cheapest + freshest); demote audio transcription to a fallback for talks with poor captions.
   - If Scribe v2 beats Nova-3 by a material margin on pre-correction entity error on non-native speakers → **switch primary to Scribe v2** (cost delta is negligible).
   - If no candidate + pyannote reaches ≤15% panel DER → treat diarization as best-effort and flag panels in the weekly digest rather than blocking the pipeline.
   - If vocabulary grows past ~100 terms while Nova-3 is primary → migrate to Scribe/AssemblyAI (1,000-term cap) or push more correction into the LLM stage.

## Caveats
- **Many accuracy numbers are vendor-published** (Deepgram WER, ElevenLabs 96.7%, AssemblyAI cpWER/speaker-count, Mistral FLEURS) and should be treated as marketing until validated on the owner's own 1,041-talk benchmark — the decisive test. The independent Artificial Analysis and Hugging Face Open ASR leaderboards are more trustworthy but use datasets (AgentTalk, VoxPopuli, Earnings22, TED-LIUM) only adjacent to conference-talk audio, not identical to it.
- **WER as a metric systematically penalizes verbatim models** that correctly transcribe backchannels/fillers a human reference omitted (AssemblyAI documented this in April 2026; Artificial Analysis built corrected ground-truth datasets for exactly this reason). The owner's filler-insensitive WER definition (A2) is the right response.
- **No public time-based DER exists for the shortlisted cloud providers on panel audio**; the cpWER figures are from an interested-party (AssemblyAI) benchmark. Diarization must be validated locally.
- **Prices verified Aug–Sep 2026** and are volatile (Deepgram's streaming rate is a labeled promotion; Bedrock Sonnet-class had launch pricing through Aug 31 2026). Re-verify before committing — though at this volume all options sit far under $40/month.
- **Contextual biasing can hurt**: long/global bias lists cause hallucinated insertions, partial outputs, and (for Whisper) repetition loops and language switching. A real risk if the correction/biasing design over-stuffs the term list.
- The corrected-caption arm's viability partly rests on **yt-dlp caption acquisition reliability** (Brief B's scope) — if caption tracks are unavailable or delayed, its freshness advantage evaporates.

## Reference list (by source type)

**Peer-reviewed / academic (arXiv, Interspeech, ISCA)**
- Contextual Earnings-22 (Argmax), arXiv 2604.07354, Mar 28 2026 — local vs. global context, precision trade-offs, artifacts.
- Contextual Density Ratio for LM Biasing, arXiv 2206.14623 — 46.5% relative name-error reduction.
- N-gram Boosting, arXiv 2308.02092 — 26% relative biasing-WER improvement on in-domain keywords.
- Empowering the Deaf/Hard-of-Hearing: LLM caption correction, arXiv 2412.00342 — caption WER 23.07% → 9.75%.
- Calm-Whisper (Interspeech 2025) / Whisper hallucination studies, arXiv 2505.12969, 2501.11378, 2606.07473, 2609.04561 — non-speech hallucination.
- Benchmarking Diarization Models (ETH Zurich), arXiv 2509.26177, Sep 30 2025 — pyannoteAI 11.2% / DiariZen 13.3% avg DER; Sortformer degradation >4 speakers.

**Leaderboards / independent benchmarks**
- Artificial Analysis Speech-to-Text (non-streaming) leaderboard — AA-WER v2; Scribe v2 2.2–2.3%, GPT-4o-transcribe 4.0%, Nova-3 5.2% (retrieved/updated 2026).
- Hugging Face Open ASR Leaderboard — Parakeet v3 6.32%, Canary Qwen 2.5B 5.63%, IBM Granite/Cohere Transcribe 2026.
- Picovoice "State of Speaker Diarization 2026" (updated Mar 11 2026) — VoxConverse DER: pyannote 9.0%, Amazon 11.1%–Google 50.2%.
- YouTube auto-caption accuracy study (youtube-transcript.ai, 2026) — median WER 9.9%, 20% zero sentence punctuation; mdisbetter.com tech-content test — 78% vs. Whisper 94%.

**Vendor documentation / announcements**
- Deepgram: pricing page (Nova-3 $0.0043/min batch, verified Sep 8 2026), Keyterm Prompting docs (100 terms, KRR up to 90%), Nova-3 launch + Talkatoo 625% case.
- ElevenLabs: Scribe v2 launch/pricing ($0.22/hr, keyterm +$0.05/hr, entity +$0.07/hr; 1,000 keyterms/50 chars; 32–48 speakers), API pricing page.
- AssemblyAI: pricing ($0.21/hr U-3 Pro), keyterms_prompt docs (1,000 terms/6 words), Slam-1 / Universal-3.5 Pro, cpWER/diarization benchmark, WER-metric-failure post (Apr 2026).
- Mistral: Voxtral Transcribe 2 launch (Feb 4 2026, $0.003/min).
- OpenAI: speech-to-text guide (gpt-transcribe Jul 28 2026, prompt field, whisper-1 timestamps, diarize model).
- Amazon: Transcribe pricing ($0.024/min Tier 1, CLM +$0.006/min, 15-sec min); Bedrock pricing (Claude per-token, no floor).
- Groq: pricing (Whisper turbo $0.04/hr, large-v3 $0.111/hr).
- Speechmatics: pricing/features (1,000-word dictionary free, diarization free).
- Parakeet-MLX / senstella & EliFuzz GitHub repos; NVIDIA Parakeet/Canary model cards.

**Community reports / secondary analyses**
- HappyRobot, DIYAI, Toolradar, Brasstranscripts, Markaicode (Deepgram pricing verification, Sep 2026).
- CloudZero, Caylent, Spheron, CloudForecast, PE Collective (Bedrock per-token/no-floor confirmation, 2026).
- Deepgram GitHub discussion #1233 (keyterm overfitting/precision risk).
- Northflank, MarkTechPost, Coval (open-weights ASR landscape 2026).
- opentranscription.io, elevenlabsmagazine, grabcaptions, mikeesto, whispernotes, arunbaby (Scribe v2, caption accuracy, Parakeet-on-Apple-Silicon field reports).