# Implementation Spec: Correcting Misrecognized Names and Tech Terms in Talk Transcripts
## Pipeline: phonetic/fuzzy candidate generation + LLM confirmation

This document is self-contained. It assumes no prior context. Follow the steps in order. Where a step says **HUMAN**, stop and get input from the project owner before continuing. Where a number is marked **(starting value, tune)**, it is a first guess, not a known-good setting; Step 10 tells you how to tune it.

---

## 0. Background you need

### 0.1 The problem
There are about 1,000 English transcripts of tech talks (mostly AI/ML and developer tooling). The speech-to-text system misheard many proper nouns and technical terms. Some speakers have strong accents. The goal is to fix those names and terms **in the text only**. The audio will not be re-transcribed.

Out of scope: fixing general transcription errors that have nothing to do with names, terms, or version numbers.

### 0.2 Input data format
Each transcript is one JSON file: an array of segments, each with exactly two fields.

```json
[{"startMs": 12719, "text": "All right, let's get started. Apologies"},
 {"startMs": 15360, "text": "for the delay, but I'm really excited to"}]
```

There are no end times, word timestamps, confidence scores, or alternative transcriptions. Segment length varies from fragments to paragraphs. **A name can be split across two segments** (e.g. "Browser" at the end of one segment, "Base" at the start of the next).

### 0.3 Real errors (correct → as transcribed)
- Anthropic → Entropic
- Claude → Cloud / quad / clawed
- Vercel → Versel
- Postgres → Postgress
- Replit → replet
- PyTorch → pi torch
- Qwen → Quen
- Llama.cpp → Llama CVP
- RAG → rack
- Swyx → Swix
- Andrej Karpathy → Andrew Carpathy
- Cat Wu → Cat Woo
- LangChain → lang chain
- Browserbase → Browser Base
- Sonnet 4.5 → Sonnet four point five
- GPT-4 → GPT for

Cases only context can resolve: Grok vs Groq, VLM vs vLLM, Jason vs JSON.

### 0.4 The central risk
Many errors are ordinary English words: Cloud, rack, for, quad, Jason. Replacing them blindly corrupts correct text ("cloud storage" → "Claude storage"). **A false correction is worse than a missed correction.** Every design choice below is made to keep false corrections low.

### 0.5 Design principles (do not violate)
1. **String matching proposes; only the LLM decides** (with one narrow exception in Step 5.5 for exact known aliases that are not English words).
2. **The LLM never writes free text into the transcript.** It only picks from a closed list of options you generate, including KEEP. Any output outside that list is discarded.
3. **Default is KEEP.** Apply a change only when the LLM chooses it with high confidence.
4. **Never change segment count, segment order, or `startMs`.** Only `text` changes.
5. **Log every change** with enough detail to review and undo it.
6. Do not overwrite input files. Write outputs to a separate directory.

### 0.6 Compute constraints
Hosted LLM APIs from any provider are allowed. Local non-LLM models (spaCy, GLiNER, KeyBERT) are allowed. No local LLMs are required.

---

## 1. Setup

### 1.1 Python packages
| Package | Purpose | License | Compute |
|---|---|---|---|
| `jellyfish` | Metaphone / NYSIIS phonetic codes, Jaro-Winkler similarity | BSD-2-Clause | CPU |
| `rapidfuzz` | Fast fuzzy scoring and ranking | MIT | CPU |
| `spacy` (blank `en` pipeline only) | Tokenizing with character offsets, exact phrase matching | MIT | CPU |
| `wordfreq` | English word-frequency lookup (to flag common-word collisions) | code Apache-2.0, data CC-BY-SA; data no longer updated | CPU |
| `gliner` | Zero-shot entity extraction to mine candidate terms | Apache-2.0 | CPU or GPU |
| `keybert` | Keyphrase extraction to mine candidate terms | MIT | CPU or GPU |
| `huggingface_hub` | Pull model/org names as an external name source | Apache-2.0 | none |
| `jiwer` | Word error rate for evaluation | Apache-2.0 | CPU |
| `nemo_text_processing` (optional, Step 6) | Inverse text normalization of spoken numbers | Apache-2.0 | CPU |
| an LLM provider SDK | Confirmation step | per provider | API |

Notes:
- `nemo_text_processing` depends on `pynini`, which is often hard to install with pip; conda is usually easier. If it will not install, use the fallback in Step 6.
- Optional: `abydos` provides Double Metaphone (better than single Metaphone for names), but it is **GPL-3.0** and its maintenance is dated. Ask the owner before adding it. Check the return type of its encoder in the installed version before using it.
- Pin every package version in a `requirements.txt` and record it in the run log.

### 1.2 Project layout
```
data/raw/            # input transcripts, read-only
data/names/          # name list files
data/eval/           # gold labels
work/                # intermediate files
out/corrected/       # corrected transcripts, same filenames as input
out/logs/            # edit logs, LLM request/response logs, run config
```

### 1.3 Config file
Put every threshold, batch size, model name, and prompt version in one `config.yaml`. Write a copy of it into `out/logs/` for each run. Never hard-code thresholds.

---

## 2. Load and join each transcript

For each file:

1. Load the segment array. Validate that every item has an integer `startMs` and a string `text`. Record and skip malformed files; do not guess repairs.
2. Build one continuous string `full_text` by joining segment texts with a **single space** separator. Do not strip or otherwise alter segment text.
3. Build an offset table: for each segment index `i`, store `(seg_start_char, seg_end_char)` in `full_text`.

```python
def join_segments(segments):
    parts, offsets, pos = [], [], 0
    for i, seg in enumerate(segments):
        if i > 0:
            parts.append(" ")
            pos += 1
        start = pos
        parts.append(seg["text"])
        pos += len(seg["text"])
        offsets.append((start, pos))
    return "".join(parts), offsets
```

4. Tokenize `full_text` with `spacy.blank("en")`. Keep each token's `idx` (start char) so every token and n-gram has exact character offsets.

All detection and correction work happens on `full_text` with character offsets. Step 9 maps changes back to segments.

---

## 3. Build the evaluation set first — HUMAN

Build this before tuning anything, so that tuning is measured rather than guessed.

### 3.1 Find real occurrences
For each transcribed form in section 0.3 (Entropic, Cloud, quad, clawed, Versel, Postgress, replet, "pi torch", Quen, "Llama CVP", rack, Swix, "Andrew Carpathy", "Cat Woo", "lang chain", "Browser Base", "four point five", "GPT for", Grok, Groq, VLM, vLLM, Jason, JSON), search all transcripts case-insensitively, including across segment boundaries (search `full_text`). Collect hits with about 200 characters of surrounding context.

### 3.2 Sample
Randomly sample hits so that each form has several occurrences where possible. Split files (not hits) into **dev** and **test**, so that no transcript appears in both. Suggested starting sizes: dev ≈ 60% of sampled hits, test ≈ 40%. If a form has few hits, keep them all.

### 3.3 Ask the owner to label each hit
Give the owner a CSV with columns:
`hit_id, file, char_start, char_end, transcribed_span, context, label, correct_form, speaker_accent_note`

- `label` = `ERROR` (should be changed) or `CORRECT` (ordinary use, leave alone).
- `correct_form` = the right text when `label` is `ERROR`.
- `speaker_accent_note` = optional; lets results be reported separately for accented speakers.

Hits labeled `CORRECT` form the **trap set** (for example "cloud storage", "a rack of servers", "wait for it"). The trap set is how false corrections are measured. If the sample contains fewer than about 30 trap hits for the common words (cloud, rack, for, quad, Jason), sample more hits of those words specifically.

### 3.4 Optional whole-segment references
Ask the owner to hand-correct the full text of about 30–50 segments in the dev set (names only, nothing else). These are used for a word error rate guardrail in Step 10.

Save to `data/eval/gold_dev.csv`, `data/eval/gold_test.csv`, `data/eval/segment_refs.jsonl`. **Do not look at the test set until Step 10.5.**

---

## 4. Build the name list

The list of correct names does not exist yet and its size is unknown. Build it in three passes, then have the owner review it.

### 4.1 Seed list
Start `data/names/seed.csv` with:
- every correct form in section 0.3 (including Grok, Groq, VLM, vLLM, JSON);
- the owner's speaker list (ask for it; it exists).

### 4.2 Mine candidates from the transcripts
Run all three and merge results into `work/term_candidates.csv` with columns `surface_form, source, doc_count, total_count, example_context`.

**a) GLiNER entity extraction.**
- Model: a GLiNER checkpoint from the `urchade` organization on Hugging Face (for example a medium or large English/multilingual v2.x model; record which one).
- Labels: `["company", "software product", "AI model", "programming library", "programming language", "person", "technical acronym", "database", "cloud service"]` (starting value, tune).
- GLiNER has a limited input length. Split `full_text` into chunks of about 1,500 characters with about 200 characters of overlap, splitting at token boundaries. Deduplicate overlapping entity hits.
- Threshold: 0.4 (starting value, tune). Keep label, score, and span text.

**b) KeyBERT keyphrases.** Per transcript, extract the top 30 phrases with `keyphrase_ngram_range=(1, 3)` and English stop words removed (starting values, tune).

**c) Rare-token clustering (finds misspelled variants).**
- For every token and 2-token n-gram in the corpus, compute `wordfreq.zipf_frequency(form, "en")`. Keep forms with zipf below 3.0 (starting value, tune) that occur in at least 2 documents.
- For each kept form, compute a **phonetic key**: lowercase, remove spaces and punctuation, then `jellyfish.metaphone(...)`.
- Group forms with identical keys, and also link forms whose keys have `rapidfuzz.fuzz.ratio ≥ 85` (starting value, tune).
- Output each cluster with counts. Clusters show both the likely correct form and its misrecognitions (e.g. Versel / Vercel).

### 4.3 Validate against external sources
A term mined from transcripts may itself be a misspelling ("Entropic"). Mark each candidate with whether it matches (case-insensitive, spaces and hyphens removed) any of these:
- **Hugging Face Hub**: model IDs and organization names via `huggingface_hub.HfApi().list_models(...)`, sorted by downloads, limited to a few tens of thousands. Use both the org part and the model part of each ID. Many names are noisy; low-download entries are weak evidence.
- **PyPI**: names of the most-downloaded packages (a public "top PyPI packages" list exists; check its license before use). Package names include typosquats; only trust popular ones.
- **GitHub**: organization and repository names for popular repos via the GitHub search API (respect rate limits).
- **Wikidata**: labels and aliases of items that are instances of software, companies, or people, via the SPARQL endpoint (verify class IDs before querying). Wikidata is CC0. Filter heavily; it is very broad.

A match is supporting evidence, not proof.

### 4.4 Optional LLM canonicalization pass
For each rare-token cluster from 4.2c, send the cluster members plus two example contexts to the LLM and ask it to return JSON: which member (if any) is the correct spelling of a real tech name, what the correct canonical spelling and casing is (only if it is one of the members, or a well-known name whose spelling differs only by casing, spacing, or punctuation), and which members are misrecognitions of it. Treat the output as a suggestion for the human review, never as final.

### 4.5 Owner review — HUMAN
Produce `work/name_list_for_review.csv`, sorted by total corpus count, with suggested values filled in. The owner approves, edits, or deletes rows. The approved file is `data/names/names.csv` with this schema:

| Column | Meaning |
|---|---|
| `canonical` | Exact correct form, with casing and punctuation: `LangChain`, `Llama.cpp`, `GPT-4` |
| `type` | person / company / product / model / library / acronym / other |
| `aliases` | Known misrecognitions, pipe-separated: `lang chain\|langchane` |
| `description` | One line the LLM will see: "Groq: company making LPU inference chips" |
| `confusable_with` | Other canonicals it is often confused with: `Grok` |
| `common_word_collision` | `yes` if any alias or likely misrecognition is an ordinary English word (Cloud, rack, for) |
| `has_versions` | `yes` if it is often followed by a version (GPT, Claude, Sonnet, Llama, Qwen) |

Rules for the owner review that you should explain to them:
- Keep `description` short and distinguishing, especially for confusable pairs.
- Do not add extremely generic words as canonicals.
- The list will grow over time; the pipeline must re-run cleanly when it changes.

Mark `common_word_collision` automatically as a suggestion: `yes` if any alias, or the canonical lowercased, has `zipf_frequency ≥ 3.0` (starting value, tune). The owner confirms.

---

## 5. Detect candidate spans

Run per transcript on `full_text`. The output of this step is a list of **candidates**: `(char_start, char_end, original_text, proposed_canonical, match_method, score)`.

### 5.1 Precompute for each name-list entry
For the canonical and each alias:
- `norm` = lowercase, remove spaces, hyphens, dots, and underscores (`Llama.cpp` → `llamacpp`).
- `phon` = `jellyfish.metaphone(norm)`.
- `n_tokens` = token count of the canonical as written with spaces (used to choose n-gram sizes).

Build lookup dictionaries from `norm` and from `phon` to entries, so you do not compare every n-gram with every entry.

### 5.2 Exact matches
Use a spaCy `PhraseMatcher` with `attr="LOWER"` loaded with all canonicals and aliases.
- A match whose text **exactly** equals its canonical (same case) is **already correct**. Record it in a per-document list `confirmed_terms` (used as context in Step 8). Do not create a candidate, **unless** the canonical has a non-empty `confusable_with` (Grok/Groq, VLM/vLLM, Jason/JSON): those become candidates offering the confusable alternatives.
- A match to a canonical that differs only in case → candidate with `match_method = "case"`.
- A match to an alias → candidate with `match_method = "alias"`.

### 5.3 Fuzzy and phonetic matches
For every n-gram of 1 to 3 tokens (starting value, tune; allow up to `max(n_tokens)+1`) that does not cross sentence-ending punctuation and is not already covered by 5.2:
1. Skip n-grams whose `norm` is shorter than 3 characters.
2. Compute `norm` and `phon` for the n-gram.
3. Look up entries whose `phon` equals the n-gram's `phon`, plus entries whose `phon` has `rapidfuzz.fuzz.ratio ≥ 80` (starting value, tune; to keep it fast, only compare against entries whose `phon` shares the first character or whose length is within ±2).
4. For each such entry compute:
   - `string_sim = jellyfish.jaro_winkler_similarity(ngram_norm, entry_norm)`
   - `phon_sim = rapidfuzz.fuzz.ratio(ngram_phon, entry_phon) / 100`
5. Keep the entry as a candidate if `phon_sim ≥ 0.85` or `string_sim ≥ 0.90` (starting values, tune). Record both scores.
6. Keep at most 3 proposed canonicals per span, ranked by `max(phon_sim, string_sim)`.

Why n-grams: many errors change token count ("pi torch" → PyTorch, "Browser Base" → Browserbase, "Andrew Carpathy" → Andrej Karpathy, "Llama CVP" → Llama.cpp).

### 5.4 Acronyms
Acronym canonicals (RAG, LoRA, vLLM) often become short common words ("rack"). For `type = acronym`, also compare the n-gram's `phon` against the metaphone of the acronym read as a word (`rag` → `RK`). These candidates always go to the LLM (Step 5.5 never auto-applies them).

### 5.5 Routing each candidate
Assign each candidate a route:
- **auto** — only if ALL are true: `match_method` is `alias` or `case`; the span text is not an English word (`zipf_frequency < 3.0` for every token, starting value, tune); the canonical has no `confusable_with`; `common_word_collision` is `no`. These are applied without an LLM call **only if** Step 10 shows the auto route has zero false corrections on the dev set. Until then, send them to the LLM too.
- **llm** — everything else.

Never auto-apply a fuzzy or phonetic match.

---

## 6. Version strings and spoken numbers

Target: "Sonnet four point five" → "Sonnet 4.5", "GPT for" → "GPT-4". Do **not** convert numbers anywhere else in the transcript.

1. Find every occurrence of a canonical with `has_versions = yes`, including candidates from Step 5 that propose such a canonical.
2. Look at the next 1–5 tokens (starting value, tune). Collect the maximal run of tokens that are number words (`zero`–`twenty`, `thirty`…`hundred`), `point`, `dot`, `o`/`oh`, digits, or version homophones: `for`→4, `to`/`too`→2, `won`→1, `ate`→8 (homophones only immediately after the name).
3. Convert the run to a version string:
   - Preferred: run `nemo_text_processing` inverse normalization **on that run only** (e.g. "four point five" → "4.5").
   - Fallback: a small hand-written converter for number words and "point"/"dot". Unit-test it on at least: "four point five" → 4.5, "three point seven" → 3.7, "four o" → 4o, "two" → 2, "for" → 4.
4. Build the full replacement from how the canonical is written in the name list and from real product naming (e.g. `GPT-4` uses a hyphen, `Sonnet 4.5` uses a space). If the name list has explicit version forms (add rows like `GPT-4`, `GPT-4o`, `Claude Sonnet 4.5` if the owner wants), prefer those. If you are unsure of the separator, offer both as options in Step 8.
5. Create a candidate spanning name + number run with `match_method = "version"`, route **llm**. Homophone runs (`for`, `to`) are the riskiest ("GPT for summarization" might be correct English) and must always go to the LLM.

---

## 7. Group candidates into items

1. Merge overlapping or touching candidate spans into one **item** covering their union span.
2. For each item, build a closed list of **options**. Each option is a complete rewrite of the item span:
   - `KEEP` (the original text, always option 0);
   - for each candidate inside the item, the item text with that candidate's sub-span replaced by its proposed canonical (or version string);
   - if two non-overlapping candidates both lie inside the item, also include the rewrite with both replaced.
   - Cap at 6 options per item (starting value, tune); keep the highest-scoring.
3. Attach for each option the `description` of each canonical it introduces, and for confusable pairs the descriptions of both.
4. Build the **context**: about 300 characters before and after the item (starting value, tune), cut at token boundaries, with the item marked as `[[item text]]`.
5. Assign each item a stable ID: `<file>#<char_start>-<char_end>`.

---

## 8. LLM confirmation

### 8.1 Batching
- Process one transcript at a time.
- Send items in batches of up to 25 per request (starting value, tune). Expected cost scales with the number of items, not with transcript length.
- Log, per request: model, prompt version, input tokens, output tokens, latency, and the raw response.
- Use temperature 0 (or the provider's most deterministic setting) and the provider's structured JSON output feature if available.
- Retry on API errors with backoff. If a response fails validation twice, mark all items in that batch as KEEP and log them as `unresolved`.

### 8.2 Document-level context
Include in every request for a transcript:
- `confirmed_terms` from Step 5.2 (names already correctly spelled in this talk), up to 40 (starting value, tune). These help: a talk that correctly says "Anthropic" three times makes "Cloud" → "Claude" more likely elsewhere in it.
- The speaker names, if the owner can map speakers to transcripts.

### 8.3 Prompt (version it; change the version string whenever you edit it)

**System message:**
```
You correct misrecognized names and technical terms in automatic speech-to-text transcripts of technical talks about AI, machine learning, and software tools.

For each ITEM you get: a CONTEXT excerpt in which the target span is marked [[like this]], and numbered OPTIONS. Option 0 always keeps the text unchanged.

Rules:
1. Choose exactly one option number per item. Never write any other text into the transcript.
2. Choose 0 (keep) unless the context makes it clearly more likely that the speaker said the named term.
3. Ordinary English stays unchanged. Examples that must stay unchanged: "cloud storage", "move to the cloud", "a rack of GPUs", "wait for it", "we built this for developers", a person called Jason.
4. Similar sound alone is not enough. Require supporting context: related technology, the company or product being discussed, other names in the talk, or the sentence making no sense as written.
5. For look-alike names (for example Grok vs Groq, VLM vs vLLM), decide using the descriptions and the surrounding topic. If the context does not decide it, choose 0.
6. Confidence: "high" only if you would bet heavily on it; otherwise "medium" or "low".

Return only JSON matching the schema. No commentary outside the JSON.
```

**User message (template):**
```
TERMS ALREADY CORRECTLY PRESENT IN THIS TALK: {confirmed_terms, comma-separated, or "none"}
SPEAKERS: {speaker names or "unknown"}

ITEMS:
--- item_id: {item_id}
CONTEXT: {context with [[span]]}
OPTIONS:
0: keep "{original span text}"
1: "{rewrite 1}"  — introduces {canonical}: {description}
2: "{rewrite 2}"  — introduces {canonical}: {description}
...
(repeat for each item)
```

**Required JSON output:**
```json
{"decisions": [
  {"item_id": "talk123.json#10452-10457",
   "choice": 1,
   "confidence": "high",
   "evidence": "short phrase from the context, max 20 words"}
]}
```

### 8.4 Validate every response
Reject a decision (treat as KEEP and log as `invalid`) if:
- `item_id` is not in the batch, or an item is missing or duplicated;
- `choice` is not an integer index of that item's options;
- `confidence` is not one of `high`, `medium`, `low`.

Items missing from a response get one retry in a new, smaller batch; then KEEP.

### 8.5 Accept rule
Apply a decision only if `choice != 0` and `confidence == "high"` (starting rule, tune in Step 10).

Optional stricter mode for risky items (`common_word_collision = yes`, any `confusable_with`, or homophone versions): send the item a second time in a separate request with options in shuffled order, and apply only if both runs pick the same rewrite with high confidence. Turn this on if Step 10 shows false corrections concentrated in those items.

---

## 9. Apply edits and map back to segments

### 9.1 Build the edit list
One edit per accepted item: `(char_start, char_end, original_text, new_text)`. Items do not overlap (Step 7 merged them), so edits do not conflict. Assert this.

### 9.2 Apply per segment
For each edit, find every segment whose offset range overlaps `[char_start, char_end)`.

- **Edit inside one segment**: replace the corresponding substring of that segment's `text` using local offsets (`char_start - seg_start_char`).
- **Edit crossing segments** (name split across the boundary): put the entire `new_text` in the **first** overlapping segment, replacing from the local start to the end of that segment's text. In each following overlapped segment, delete the part covered by the edit. Then strip leading whitespace from the remainder of the last overlapped segment. If a segment's text becomes empty, keep the segment with `text: ""` and flag it in the log.
- Apply edits within a segment from right to left so earlier offsets stay valid.

### 9.3 Checks before writing
- Same number of segments as input, same order, identical `startMs` values.
- For every segment with no edits, `text` is byte-identical to input.
- Re-joining the output and diffing against the input shows only the logged edits.

### 9.4 Outputs
- `out/corrected/<same filename>.json` — corrected segments.
- `out/logs/edits.jsonl` — one line per applied edit:
  `file, item_id, segment_indices, original_text, new_text, canonical_introduced, match_method, string_sim, phon_sim, route (auto/llm), llm_choice, llm_confidence, llm_evidence, prompt_version, model`
- `out/logs/rejected.jsonl` — same fields for items the LLM kept, plus invalid and unresolved items. This file is needed to measure recall losses.

---

## 10. Evaluate and tune (dev set only)

### 10.1 Metrics
Compute on the dev files:
- **Name precision** = (edits whose span and new text match a gold `ERROR` hit's `correct_form`) ÷ (all edits that overlap any gold hit).
- **Name recall** = (gold `ERROR` hits correctly fixed) ÷ (all gold `ERROR` hits).
- **False-correction rate** = (gold `CORRECT` / trap hits that were changed) ÷ (all trap hits). Report it also per word (cloud, rack, for, quad, Jason, Grok, Groq, VLM, vLLM, JSON).
- **WER guardrail**: using `jiwer.wer(reference, hypothesis)` on the hand-corrected segments from Step 3.4, compare WER of the original text vs corrected text. Corrected WER must not be higher.
- Break down precision and recall by error type: proper noun, acronym, spacing/casing, version string.
- If accent notes exist, report all metrics separately for accented speakers.
- Cost: LLM calls, tokens, and estimated cost per transcript.

Note: the dev set only covers words found in Step 3, so recall is measured only for those words. Edits elsewhere are checked in Step 11.

### 10.2 Diagnosing misses
For each missed gold `ERROR`, find which stage lost it:
- not in the name list → Step 4;
- no candidate generated → Step 5 thresholds or n-gram size;
- candidate generated but LLM chose keep or medium/low confidence → Step 8 prompt or accept rule;
- rejected as invalid → Step 8.4.

### 10.3 Diagnosing false corrections
For each changed trap hit, look at the LLM evidence. Typical fixes, in this order: improve the canonical's `description`; add the trap phrase pattern as a "must stay unchanged" example in the system prompt; turn on the stricter two-run mode for that risk class; raise thresholds for that entry.

### 10.4 Tuning loop
Change one thing at a time, re-run on dev, and record every run's config and metrics in `out/logs/tuning_runs.csv`. **HUMAN**: ask the owner for target values (for example a maximum false-correction rate and a minimum recall). If they give none, do not choose targets yourself; report the trade-off table and let them pick a configuration.

Also decide here whether the **auto** route (Step 5.5) is allowed: only if it produced zero false corrections on dev.

### 10.5 Final check
Run the chosen configuration once on the **test** set. Report its metrics next to the dev metrics. Do not tune after looking at test results; if test results are unacceptable, report that to the owner rather than tuning on test.

---

## 11. Full corpus run and audit

1. Run the pipeline on all transcripts with the chosen config.
2. Produce a summary: edits per transcript, edits per canonical, edits per match method, LLM cost, invalid/unresolved counts.
3. **HUMAN audit**: randomly sample 100 edits from `edits.jsonl` (starting value, tune), stratified so every canonical with at least 5 edits appears. Show original context and new text. The owner marks each correct or wrong. Report the audited precision overall and per canonical.
4. For any canonical with a poor audited precision, revert its edits (the log makes this mechanical), fix its name-list entry, and re-run for affected files only.
5. When the name list changes later, re-run the whole pipeline from the raw inputs, not on already-corrected outputs.

---

## 12. Deliverables checklist
- `requirements.txt` with pinned versions
- `config.yaml` (final) and every tuning run's config
- `data/names/names.csv` (owner-approved)
- `data/eval/` gold files
- `out/corrected/` transcripts
- `out/logs/edits.jsonl`, `rejected.jsonl`, LLM request logs
- Evaluation report: dev metrics, test metrics, per-word false-correction rates, per-type breakdown, cost, audit results
- A short README explaining how to re-run after the name list changes

## 13. Stop and ask the owner when
- the speaker list or any HUMAN step's input is missing;
- a package with a copyleft license (e.g. GPL) seems necessary;
- the estimated LLM cost for the full run is known (report it before running on all files);
- test-set results miss the owner's targets;
- more than a small fraction of files are malformed;
- a fix would require changing `startMs`, adding or removing segments, or editing non-name text.

## 14. Known weak points (so you do not over-trust results)
- No published evaluation exists for this kind of pipeline on accented English tech-talk transcripts; the owner's gold set is the only evidence that it works here.
- Context-only pairs (Grok/Groq, VLM/vLLM, Jason/JSON) may often be undecidable from text; keeping them unchanged is an acceptable outcome.
- Single Metaphone is crude for names from non-English languages; misses on such names may need aliases added by hand, or Double Metaphone (see the license note in 1.1).
- `wordfreq` data is no longer updated, so newer tech words may have odd frequencies. Use it only as a routing signal, never to decide a correction.
- The LLM may know a name exists yet still pick wrongly when context is thin; the default-KEEP rule and the trap-set metric are the safeguards.
