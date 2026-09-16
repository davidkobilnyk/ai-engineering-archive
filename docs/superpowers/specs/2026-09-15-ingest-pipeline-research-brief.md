# Ingest Pipeline: Research Brief

Date: 2026-09-15
Status: brainstormed, awaiting owner review before handoff to a research agent
Audience: a research agent with web access and scholarly search. This
document is self-contained; it assumes no prior conversation.

## 1. What is being decided

The owner maintains a local, full-text-searchable archive of AI Engineer
conference talk transcripts (this repository; design in
`2026-09-14-aie-archive-design.md`). The transcripts come from
https://ai.engineer/data, which publishes edited transcripts roughly two
weeks after a talk appears on the AI Engineer YouTube channel, and sometimes
much later. The owner wants new talks searchable sooner, by transcribing the
YouTube audio themselves and inserting a provisional transcript that is
replaced automatically when the upstream edited version arrives.

The research question is: **which tools and methods should this pipeline
use**, chosen against the constraints in section 2 and the evidence in
section 3, with the trade-offs made explicit. The output of the research is
a recommendation, not code.

## 2. Constraints and priorities

Priority order, most important first, with the owner's hard numbers:

1. **Accuracy.** Names and technical terms must match the quality of the
   upstream edited transcripts, so that search and future entity extraction
   work. General transcription accuracy matters next: content words,
   numbers, punctuation, sentence segmentation.
2. **Freshness.** A new talk is searchable at that quality within **4 days**
   of appearing on the channel.
3. **Unattended.** The owner spends at most **1 hour per week** on it.
4. **Cost.** At most **$40 per month** averaged over the year, including
   event bursts.

Operating environment:

- Orchestration runs as a **scheduled AWS job** that wakes on a timer, does
  the work, and leaves nothing running. The owner wants to learn AWS, so
  AWS-native services are a tiebreaker but not a requirement.
- Initial AWS setup must fit in about **5 hours** of the owner's time. The
  pipeline itself will be written and tested locally first.
- Storage and querying stay on the owner's Mac (Apple M1, 8 GB memory).
  Artifacts move through S3. No managed database or search service with a
  monthly floor.
- Local transcription on that Mac is possible but slow (section 3.3), so
  hosted transcription is on the table for bursts.
- Audio acquisition via `yt-dlp` is acceptable to the owner for this
  scenario, with the reasoning in section 4.1, pending the review requested
  there.

Volume: the corpus has 1,087 talks accumulated over three years. Arrival is
bursty: one conference can add about 300 talks within a few weeks, with a
trickle between events. Talks are mostly 15 to 25 minutes; some panels and
workshops run over an hour.

Target transcript style: the same as upstream's edited transcripts.
**Verbatim, fillers kept ("uh", "um"), punctuated, cased, sentence-length
segments with start times in milliseconds.** A clean-read variant for
embeddings, if wanted later, is a derived artifact, not the source of truth.

## 3. Evidence gathered so far

### 3.1 The corpus and its two transcript qualities

Two kinds of transcript exist in the current corpus (1,087 talks, 166,561
segments):

| | Edited (1,041 talks) | Auto-caption (46 talks) |
|---|---|---|
| Segments | 143,470 | 23,091 |
| Median segment length | 184 characters | 37 characters |
| Segments with any sentence punctuation | 95.5% | 33.7% |
| Segments with any capital letter | 98.4% | 42.8% |
| Talk metadata | complete | speakers and summary only, no topics, hash-style slugs |

The 46 auto-caption talks are raw YouTube captions. 44 of them are from
World's Fair 2026 (June 29 to July 2, 2026); the other 269 talks from that
event already have edited transcripts as of the September 3 corpus. This
looks like a processing backlog upstream, not a change in their pipeline.
The practical consequence is a **rolling window**: after every event, the
newest talks spend weeks or months as auto-captions before being replaced.

### 3.2 Name error rates

For 17 names known to be misheard, counting segments where the name appears
correctly versus in a known wrong form:

| | Right | Wrong | Error rate |
|---|---|---|---|
| Edited talks | 3,592 | 15 | 0.42% |
| Auto-caption talks | 47 | 31 | 39.7% |

The edited transcripts keep every filler word yet get names right. That
combination indicates upstream runs verbatim speech-to-text followed by a
name-correction pass, most likely an LLM with a name list. The two-week gap
is that pass plus curation.

The wrong forms that recur: Anthropic as "Entropic"; Claude as "Cloud",
"claw", "clawed"; Claude Code as "cloud code" (this one also appears in 3
edited talks); PyTorch as "pi torch" or "pietorch"; Vercel as "Versel";
Playwright as "playright"; Codex as "codeex"; a speaker named Yuchen as
"Euchen"; LangChain as "lang chain"; Karpathy as "Carpathy"; Qwen as "Quen".

Ambiguous pairs that only context can resolve, with segment counts in the
edited corpus: Grok/Groq 44/44, VLM/vLLM 39/118, Jason/JSON 47/617,
Claude/cloud 2,923/961, RAG/rack 1,303/9.

A phonetic and fuzzy scan of the whole corpus for unknown misspellings found
almost nothing beyond the list above: rare technical vocabulary swamped the
candidates, and essentially every near-match was a correctly spelled term
paired with a similar-sounding speaker or company name. On this corpus,
string-similarity candidate generation is noise.

### 3.3 Local transcription spike

Two talks were transcribed on the owner's Mac (Apple M1, 8 GB) with Whisper
large-v3-turbo via MLX, with a vocabulary prompt listing about 40 names
including Claude and Anthropic:

| Talk | Audio | Elapsed | Speed |
|---|---|---|---|
| Red Hat talk (auto-caption upstream) | 21.5 min | 4.8 min | 4.5x real time |
| Hugging Face talk (edited upstream) | 20.8 min | 2.9 min | 7.2x real time |

Against the edited Hugging Face transcript the word error rate was 4.6%,
inflated by Whisper dropping fillers that the reference keeps. Output was
punctuated, cased, and in sentence-length segments.

Names, however, were not fixed by the vocabulary prompt:

| Name | Edited reference | Local Whisper |
|---|---|---|
| Claude | 4 right | 0 right, 4 as "Cloud" |
| Anthropic | 4 right | 2 right, 2 as "Entropic" |
| Hugging Face | 44 | 37, plus 4 as "HuggingFace" |
| Langfuse | 3 | 3 as "LangFuse" |
| llm-d (Red Hat talk) | n/a | all as "LLMD" or "LMD" |
| prefill (Red Hat talk) | n/a | "pre-fill", "prefilled" |

It did fix the auto-caption's "Euchen" and "disagregation". Net: roughly one
name mention in ten was wrong, versus one in 240 in the edited corpus.
**Self-transcription with Whisper-class models does not remove the name
problem; it needs a correction stage to reach upstream quality.**

### 3.4 YouTube's own caption track

The 46 auto-caption talks in the corpus are YouTube's automatic English
caption track, word for word (verified on one talk). Third-party "YouTube
to transcript" sites serve this same track; one such site's output for a
talk was compared against a direct fetch and differed by 9 words in 3,500,
all small decode slips.

**The track is not stable over time.** Of ten auto-caption talks re-fetched
two weeks after the corpus date, eight were identical and two had drifted by
about 3% of words. The site comparison above shows the same kind of drift.
It looks like periodic re-decoding by the same class of model rather than a
quality upgrade, but the sample is small. A pipeline that uses the track
must record fetch time, and the researcher should find out whether YouTube
documents re-captioning behavior and whether quality improves with time.

Its quality varies a lot per video and is not predictable from metadata.
On the Hugging Face talk from section 3.3 it matched the edited transcript
on all 61 name mentions with a 3.7% filler-insensitive word error rate,
better than local Whisper. Across nine other edited 2026 talks it got 85 of
105 name mentions right (about 81%), with word error rates from 2.3% to
17.2%, median about 6.5%. Net: roughly Whisper-class on average, sometimes
much better, sometimes much worse; not a substitute for the correction
stage.

It is, however, a free, zero-compute source that needs only a caption fetch
rather than an audio download, and it is an independent second machine
transcript of every talk. Both properties matter for section 5.

### 3.5 Available reference data

Every upstream talk record carries a YouTube `videoId`, so a self-produced
transcript can be matched to its upstream replacement by ID. The 46
auto-caption transcripts are snapshotted locally against the corpus version
that contained them, so when upstream replaces any of them there will be a
before-and-after pair for the same audio.

Most importantly: **1,041 edited transcripts paired with public audio form a
ready-made benchmark** for any transcriber on exactly this domain, these
accents, and this vocabulary. See section 5.

## 4. Assumed architecture

Stated as assumptions the researcher may challenge with evidence.

1. **Channel watch.** A scheduled job polls the AI Engineer channel's upload
   feed and diffs against a manifest of video IDs already handled.
2. **Audio acquisition.** Audio-only download per new video.
3. **Transcription.** Hosted or local speech-to-text producing segments with
   start times.
4. **Correction.** An LLM pass over the transcript with a closed vocabulary
   (the name list in this repository, with canonical form, type, aliases,
   description, and confusable-with fields). Keep-by-default; every edit
   logged; the LLM chooses among rewrites built from the vocabulary rather
   than writing free text. Output shaped so that entity mentions can later
   be extracted from the same pass.
5. **Artifacts.** One file per talk per stage in S3, keyed by video ID,
   each carrying its source (upstream edited, upstream auto-caption,
   self-transcribed), the producing model and prompt version, and a content
   hash of its input. A changed input invalidates only that talk's downstream
   artifacts.
6. **Reconciliation.** The existing `aie sync` continues to fetch upstream.
   The index prefers an upstream edited transcript over a self-produced one
   for the same video ID, and a self-produced one over an upstream
   auto-caption.
7. **Query side stays local.** SQLite with FTS5 as today. Semantic search
   and graph RAG are later projects that add local indexes; this pipeline
   only has to not preclude them.

## 5. Research questions

Answer each with evidence. Distinguish published results, vendor claims,
and the researcher's own inference. Dated citations for every price and
every capability claim.

### 5.1 Audio acquisition

1. **Terms of service.** The owner's position: the channel already
   publishes its own transcripts of these talks publicly; this is a private
   search index over public conference content; the tool is `yt-dlp`.
   Review YouTube's current terms and any relevant precedent so the owner
   understands the situation fully. State what the terms prohibit, what
   enforcement looks like in practice (account or IP consequences), and
   whether any compliant alternative exists for a channel one does not own
   (the YouTube Data API's caption endpoint requires channel ownership, as
   far as the author knows; verify).
2. **Reliability from cloud addresses.** How often do downloads from AWS IP
   ranges fail with bot checks as of now? What do cookie files, proof-of-
   origin token providers, and residential proxy services cost and how
   fragile are they? How often does `yt-dlp` itself need updating? If
   cloud-side download is unreliable, what is the least fragile hybrid, for
   example the Mac uploading audio to S3 on a schedule and the cloud doing
   the rest?
3. **Channel watching.** The channel RSS feed versus the YouTube Data API:
   latency from upload to appearance, quota, and whether either exposes
   enough metadata (title, speakers in the title, duration) for the
   provisional talk record.

### 5.2 Transcription

4. **Candidates.** Include **YouTube's automatic caption track** as a
   zero-cost baseline candidate (section 3.4), assessed on the same terms as
   the others and separately for its acquisition properties: no audio
   download, lighter terms-of-service exposure, and whether caption fetches
   from cloud addresses are bot-checked the way audio downloads are. Also
   whether it is good enough on its own as a same-day provisional transcript
   before the corrected one is ready. Then hosted services and local models
   the author knows of, to be verified and extended: hosted, in no order:
   Deepgram, AssemblyAI,
   Amazon Transcribe, OpenAI transcription models, Google Cloud Speech,
   ElevenLabs Scribe, Mistral Voxtral, Groq-hosted Whisper, Speechmatics,
   Rev.ai. Local: Whisper large-v3 and turbo via whisper.cpp, faster-whisper,
   or MLX; NVIDIA Parakeet and Canary; Moonshine; Voxtral; Kyutai. For each:
   accuracy evidence on accented technical English, segment-level
   timestamps, name or keyterm biasing mechanism and any published evidence
   of its effect, price per audio minute, batch or async API, maximum file
   length, rate limits, and whether it hallucinates on silence or applause.
5. **Leaderboards and literature.** What do the public ASR leaderboards and
   recent papers say about these candidates on datasets closest to this
   domain: conference talks, technical vocabulary, non-native speakers?
   What is known about contextual biasing and keyword boosting: how much
   does it help for proper nouns, and does it hurt elsewhere?
6. **General error classes.** Beyond names: substituted content words,
   dropped and hallucinated phrases, repetition loops, spoken numbers and
   version strings ("four point five" versus "4.5"), code identifiers,
   punctuation and segmentation, casing, and multi-speaker panels. Which
   candidates are strongest on which classes? Is diarization worth having
   for panels, or is it out of scope for a search archive?

### 5.3 Correction

7. **LLM post-editing.** What does the literature on generative error
   correction for speech recognition say about accuracy gains, and about the
   risk of confident fabrication? Which constraints keep it safe: closed
   vocabulary, keep-by-default, choosing among generated options rather than
   free rewriting, confidence thresholds, two-pass agreement?
8. **Division of labor.** If the transcriber's own keyterm biasing is good
   enough, does a correction pass still pay for itself? Can the same LLM
   pass do names and general errors, or should general errors be left alone?
   And: YouTube's caption track and a Whisper-class transcript of the same
   talk disagree on precisely the spans that need correction (section 3.4).
   Does a correction pass that sees two independent transcripts outperform
   one that sees either alone, and what does the literature on system
   combination or multi-hypothesis error correction say? This is cheap to
   test with the paired data already on hand.
9. **Cost and model.** Per-talk token counts are roughly 6,000 to 15,000
   input for a whole transcript. Which Claude model and settings are
   appropriate for a closed-vocabulary correction task, and what does a
   talk cost? Bedrock versus the Anthropic API, given the AWS learning goal.

### 5.4 AWS orchestration

10. **Shape.** EventBridge Scheduler with Lambda, versus Step Functions,
    versus a scheduled container task (ECS Fargate or AWS Batch). Judge
    against Lambda's execution time limit, ephemeral storage, memory, and
    lack of GPU, given 20-minute to 90-minute audio files and the
    transcription choice from 5.2. Which fits the 5-hour setup budget and
    teaches the most transferable AWS?
11. **Cost floor.** Idle cost when nothing runs, per-run cost, and the S3
    and secrets pieces. Confirm the whole thing sits well under $40 per
    month including a 300-talk burst.
12. **Failure handling.** How to make the job idempotent and resumable, so
    that a failed download or a rate-limited transcription is retried next
    run without duplicate work or duplicate spend.

### 5.5 Forward compatibility

13. **What constrains later stages.** Semantic search will embed segments or
    chunks; graph RAG will extract entities and relations. Which choices in
    this pipeline affect those, for example segment granularity, keeping
    word-level timestamps, the entity-mention shape from the correction
    pass, and artifact layout in S3, and which choices do not matter?
14. **Sizing the later stages.** Order-of-magnitude one-time and per-talk
    cost for embedding the corpus and for LLM entity extraction over it,
    with local storage, so the owner can see the whole budget.

## 6. Evaluation the researcher should design

Literature narrows the candidates; a trial on our own data decides. Propose
a benchmark using what already exists:

- **Reference set.** 20 edited talks stratified by event year, by speaker
  origin (include several non-native English speakers), and by format
  (solo, panel, workshop). The upstream edited transcript is the reference.
  Audio comes from YouTube via the acquisition method under test.
- **Metrics.** Filler-insensitive word error rate; entity error rate over
  the name list (about 50 names, expandable); number and version-string
  error rate; a hallucination and omission check on silence and applause
  sections; segmentation quality (segments per minute, share of segments
  ending in sentence punctuation); wall-clock time per talk; cost per talk.
- **Budget.** 20 talks is about 400 audio minutes, so each hosted candidate
  costs a few dollars to trial. Local candidates cost time.
- **Second set, later.** The 46 snapshotted auto-caption talks become a
  paired set as upstream replaces them; useful for the correction stage
  specifically.

The researcher should specify which candidates go into the trial, the exact
metric definitions, and the pass criteria implied by section 2.

## 7. Deliverable

A written report with:

1. Comparison tables for acquisition, transcription, correction, and
   orchestration, with dated citations for prices and capabilities.
2. A **recommended minimum stack** that fits the 5-hour setup and the $40
   average, and a **fallback stack** if the primary's key risk (most likely
   cloud-side download) fails in practice.
3. The evaluation plan from section 6, concrete enough to implement.
4. The terms-of-service review from 5.1.
5. Open uncertainties, ranked by how much they would change the
   recommendation, with the cheapest experiment that would resolve each.
6. A reference list separating peer-reviewed work, benchmark leaderboards,
   vendor documentation, and community reports.

## 8. Out of scope

Building semantic search or graph RAG; an MCP server; correcting the
1,041 edited transcripts (their error rate does not justify it); any change
to the upstream sync; re-transcribing talks that already have edited
transcripts, except as benchmark trials.
