"""Seam tests for the aie CLI. Every test runs the real command in a subprocess.

Expected values are literals copied from tests/fixtures (see its README).
"""
import json
import time

from conftest import run_aie

STATUS_PATH = "/api/data/status"
GRAPHRAG_PATH = "/api/data/transcript?slug=graphrag&format=json"
PYDANTIC_PATH = "/api/data/transcript?slug=structured-llm-outputs-with-pydantic&format=json"
HARNESS_PATH = "/api/data/transcript?slug=harness-engineering&format=json"


def search_json(data_dir, *args):
    result = run_aie("search", *args, "--json", data_dir=data_dir)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# ---------------------------------------------------------------- tracer bullet

def test_tracer_sync_index_search(fake_site, tmp_path):
    data = tmp_path / "data"

    synced = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    assert synced.returncode == 0, synced.stderr

    indexed = run_aie("index", data_dir=data)
    assert indexed.returncode == 0, indexed.stderr

    found = run_aie("search", '"strapping my laptop"', data_dir=data)
    assert found.returncode == 0, found.stderr
    assert "slug: harness-engineering" in found.stdout
    assert "[11:21] https://www.youtube.com/watch?v=am_oeAoUhew&t=681" in found.stdout


# ---------------------------------------------------------------- sync

def test_sync_second_run_is_up_to_date_and_only_checks_status(fake_site, tmp_path):
    data = tmp_path / "data"
    first = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    assert first.returncode == 0, first.stderr
    fake_site.requests.clear()

    second = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert second.returncode == 0
    assert "up to date" in second.stdout
    assert fake_site.requests == [STATUS_PATH]


def test_sync_force_redownloads_every_transcript(fake_site, tmp_path):
    data = tmp_path / "data"
    run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    fake_site.requests.clear()

    forced = run_aie("sync", "--delay", "0", "--force", data_dir=data, base_url=fake_site.url)

    assert forced.returncode == 0
    assert {GRAPHRAG_PATH, PYDANTIC_PATH, HARNESS_PATH} <= set(fake_site.requests)


def test_sync_failed_transcript_means_exit_1_and_no_version_file(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(PYDANTIC_PATH, 404)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 1
    assert "failed: transcript:structured-llm-outputs-with-pydantic" in result.stdout
    assert not (data / "raw" / "version.json").exists()
    assert (data / "raw" / "transcripts" / "graphrag.json").exists()
    assert (data / "raw" / "transcripts" / "harness-engineering.json").exists()
    assert not (data / "raw" / "transcripts" / "structured-llm-outputs-with-pydantic.json").exists()


def test_sync_resumes_by_fetching_only_the_missing_transcript(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(PYDANTIC_PATH, 404)
    run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)
    fake_site.requests.clear()

    resumed = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert resumed.returncode == 0, resumed.stderr
    transcript_requests = [p for p in fake_site.requests if "/api/data/transcript?" in p]
    assert transcript_requests == [PYDANTIC_PATH]
    assert "skipped 2" in resumed.stdout
    assert (data / "raw" / "version.json").exists()


def test_sync_retries_after_429_then_succeeds(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(GRAPHRAG_PATH, 429, 429)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 0, result.stderr
    assert fake_site.requests.count(GRAPHRAG_PATH) == 3
    assert (data / "raw" / "transcripts" / "graphrag.json").exists()


def test_sync_retries_a_truncated_body(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.body(HARNESS_PATH, b'[{"startMs": 15030, "text": "Our next spea')

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 0, result.stderr
    assert fake_site.requests.count(HARNESS_PATH) == 2
    saved = (data / "raw" / "transcripts" / "harness-engineering.json").read_text()
    assert saved.startswith("[") and saved.rstrip().endswith("]")


def test_sync_gives_up_on_a_file_after_three_retries(fake_site, tmp_path):
    data = tmp_path / "data"
    fake_site.fail(GRAPHRAG_PATH, 500, 500, 500, 500)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 1
    assert fake_site.requests.count(GRAPHRAG_PATH) == 4
    assert "failed: transcript:graphrag" in result.stdout
    assert (data / "raw" / "transcripts" / "harness-engineering.json").exists()


def test_sync_aborts_after_three_consecutive_failed_files(fake_site, tmp_path):
    data = tmp_path / "data"
    for name in ["talks", "speakers", "topics"]:
        fake_site.fail(f"/api/data/{name}?format=json", 503, 503, 503, 503)

    result = run_aie("sync", "--delay", "0", data_dir=data, base_url=fake_site.url)

    assert result.returncode == 1
    assert "aborted after 3 consecutive failures" in result.stdout
    assert "failed: talks, speakers, topics" in result.stdout
    assert not any("organizations" in p for p in fake_site.requests)
    assert not (data / "raw" / "version.json").exists()


def test_sync_waits_delay_between_requests(fake_site, tmp_path):
    data = tmp_path / "data"
    started = time.monotonic()
    result = run_aie("sync", "--delay", "0.2", data_dir=data, base_url=fake_site.url)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert len(fake_site.requests) == 10
    assert elapsed >= 10 * 0.2


# ---------------------------------------------------------------- index

def test_index_reports_counts(synced_dir):
    result = run_aie("index", data_dir=synced_dir)

    assert result.returncode == 0, result.stderr
    assert "talks 3 · segments 108 · chapters 31 · editions 10" in result.stdout


def test_index_resolves_both_event_string_styles_to_edition_dates(indexed_dir):
    display_style = run_aie("search", '"strapping my laptop"', data_dir=indexed_dir)
    slug_style = run_aie("search", '"apples and oranges"', data_dir=indexed_dir)

    assert "AI Engineer Europe 2026 (Apr 8-10, 2026)" in display_style.stdout
    assert "AI Engineer World's Fair 2024 (Jun 25-27, 2024)" in slug_style.stdout


def test_index_reports_unresolved_event_strings(synced_dir):
    talks_file = synced_dir / "raw" / "talks.json"
    talks = json.loads(talks_file.read_text())
    next(t for t in talks if t["slug"] == "graphrag")["event"] = "mystery-conf"
    talks_file.write_text(json.dumps(talks))

    result = run_aie("index", data_dir=synced_dir)

    assert result.returncode == 0, result.stderr
    assert "unresolved events: graphrag: 'mystery-conf'" in result.stdout
    found = run_aie("search", '"apples and oranges"', data_dir=synced_dir)
    assert "slug: graphrag" in found.stdout
    assert "unknown edition" in found.stdout


def test_index_skips_a_malformed_transcript_and_continues(synced_dir):
    bad = synced_dir / "raw" / "transcripts" / "structured-llm-outputs-with-pydantic.json"
    bad.write_text('[{"startMs": 14790, "text": "Hey guys')

    result = run_aie("index", data_dir=synced_dir)

    assert result.returncode == 0, result.stderr
    assert "talks 3 · segments 89 · chapters 31 · editions 10" in result.stdout
    assert "skipped files: structured-llm-outputs-with-pydantic.json" in result.stdout
    found = run_aie("search", '"apples and oranges"', data_dir=synced_dir)
    assert "slug: graphrag" in found.stdout


def test_index_failure_leaves_previous_index_intact(indexed_dir):
    (indexed_dir / "raw" / "talks.json").write_text("{not json")

    result = run_aie("index", data_dir=indexed_dir)

    assert result.returncode == 1
    assert "talks.json" in result.stderr
    assert not (indexed_dir / "aie.db.tmp").exists()
    found = run_aie("search", '"strapping my laptop"', data_dir=indexed_dir)
    assert found.returncode == 0
    assert "slug: harness-engineering" in found.stdout


def test_index_without_raw_data_exits_1(tmp_path):
    result = run_aie("index", data_dir=tmp_path / "data")

    assert result.returncode == 1
    assert "Run `aie sync` first" in result.stderr


# ---------------------------------------------------------------- search

def test_search_json_carries_every_documented_field(indexed_dir):
    hits = search_json(indexed_dir, '"strapping my laptop"')

    assert len(hits) == 1
    hit = hits[0]
    assert set(hit) >= {"talk_slug", "title", "speakers", "event", "start_date", "end_date",
                        "start_ms", "end_ms", "url", "text", "kind", "score"}
    assert hit["talk_slug"] == "harness-engineering"
    assert hit["speakers"] == ["Ryan Lopopolo"]
    assert hit["event"] == "AI Engineer Europe 2026"
    assert hit["start_date"] == "2026-04-08"
    assert hit["end_date"] == "2026-04-10"
    assert hit["start_ms"] == 681270
    assert hit["end_ms"] == 746250
    assert hit["url"] == "https://www.youtube.com/watch?v=am_oeAoUhew&t=681"
    assert hit["kind"] == "segment"
    assert "strapping my laptop" in hit["text"]


def test_search_surfaces_summary_only_matches_as_metadata_hits(indexed_dir):
    plain = run_aie("search", "urging", data_dir=indexed_dir)
    hits = search_json(indexed_dir, "urging")

    assert "slug: graphrag" in plain.stdout
    assert "[metadata] https://www.youtube.com/watch?v=knDDGYHnnSI" in plain.stdout
    assert [h["kind"] for h in hits] == ["metadata"]
    assert hits[0]["start_ms"] == 0


def test_search_collapses_adjacent_matching_segments(indexed_dir):
    hits = search_json(indexed_dir, "pagerank OR moscone")

    segment_hits = [h for h in hits if h["kind"] == "segment"]
    assert {h["talk_slug"] for h in segment_hits} == {"graphrag"}
    assert sorted((h["start_ms"], h["end_ms"]) for h in segment_hits) == [(115050, 259350), (460050, 533910)]


def test_search_stems_query_terms(indexed_dir):
    hits = search_json(indexed_dir, "hallucination")

    assert {h["talk_slug"] for h in hits} == {"structured-llm-outputs-with-pydantic"}
    assert sorted(h["start_ms"] for h in hits) == [184710, 928770]


def test_search_filters_by_speaker_topic_and_talk(indexed_dir):
    by_speaker = search_json(indexed_dir, "prompts", "--speaker", "jason liu")
    by_topic = search_json(indexed_dir, "prompts", "--topic", "agent-engineering")
    by_talk = search_json(indexed_dir, "knowledge", "--talk", "graphrag")

    assert by_speaker and {h["talk_slug"] for h in by_speaker} == {"structured-llm-outputs-with-pydantic"}
    assert by_topic and {h["talk_slug"] for h in by_topic} == {"harness-engineering"}
    assert by_talk and {h["talk_slug"] for h in by_talk} == {"graphrag"}


def test_search_filters_by_edition_and_date(indexed_dir):
    by_series = search_json(indexed_dir, '"knowledge graph"', "--event", "worldsfair")
    by_title = search_json(indexed_dir, '"knowledge graph"', "--event", "AI Engineer Summit 2023")
    after = search_json(indexed_dir, '"knowledge graph"', "--after", "2024-01-01")
    before = search_json(indexed_dir, '"knowledge graph"', "--before", "2024-01-01")

    assert by_series and {h["talk_slug"] for h in by_series} == {"graphrag"}
    assert by_title and {h["talk_slug"] for h in by_title} == {"structured-llm-outputs-with-pydantic"}
    assert after and {h["talk_slug"] for h in after} == {"graphrag"}
    assert before and {h["talk_slug"] for h in before} == {"structured-llm-outputs-with-pydantic"}


def test_search_limit_is_honoured_and_capped(indexed_dir):
    two = search_json(indexed_dir, "prompts", "--limit", "2")
    too_many = run_aie("search", "prompts", "--limit", "51", data_dir=indexed_dir)

    assert len(two) == 2
    assert too_many.returncode == 2


def test_search_with_no_hits_says_so_and_exits_0(indexed_dir):
    result = run_aie("search", "zzqxv", data_dir=indexed_dir)

    assert result.returncode == 0
    assert result.stdout.strip() == "No results"


def test_search_bad_syntax_exits_2(indexed_dir):
    result = run_aie("search", "AND", data_dir=indexed_dir)

    assert result.returncode == 2
    assert "invalid query syntax" in result.stderr


def test_search_unknown_speaker_gets_a_hint(indexed_dir):
    result = run_aie("search", "prompts", "--speaker", "Ryan", data_dir=indexed_dir)

    assert result.returncode == 0
    assert "No results" in result.stdout
    assert "Ryan Lopopolo" in result.stdout


# ---------------------------------------------------------------- show

def test_show_prints_header_chapters_and_the_requested_range(indexed_dir):
    result = run_aie("show", "harness-engineering", "--from", "11:00", "--to", "12:30", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert out.startswith("Harness Engineering: How to Build Software When Humans Steer, Agents Execute")
    assert "Ryan Lopopolo · AI Engineer Europe 2026 (Apr 8-10, 2026) · 46:21" in out
    assert "slug: harness-engineering" in out
    assert "https://www.youtube.com/watch?v=am_oeAoUhew" in out
    assert "[05:11] Scarce Resources" in out
    assert "\n[11:21] " in out
    assert "\n[12:26] " in out
    assert "[00:15] Our next speaker" not in out


def test_show_without_a_range_returns_the_whole_talk_as_json(indexed_dir):
    result = run_aie("show", "harness-engineering", "--json", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["talk"]["slug"] == "harness-engineering"
    assert payload["talk"]["video_id"] == "am_oeAoUhew"
    assert payload["talk"]["duration_ms"] == 2781000
    assert len(payload["chapters"]) == 11
    assert len(payload["segments"]) == 69
    assert payload["segments"][0]["start_ms"] == 15030
    assert payload["segments"][0]["text"].startswith("Our next speaker is here to speak about Harness Engineering")


def test_show_accepts_minutes_past_59(indexed_dir):
    result = run_aie("show", "harness-engineering", "--from", "65:00", "--json", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["segments"] == []


def test_show_unknown_slug_exits_1(indexed_dir):
    result = run_aie("show", "no-such-talk", data_dir=indexed_dir)

    assert result.returncode == 1
    assert "no talk with slug 'no-such-talk'" in result.stderr


def test_show_from_after_to_is_a_usage_error(indexed_dir):
    result = run_aie("show", "harness-engineering", "--from", "20:00", "--to", "10:00", data_dir=indexed_dir)

    assert result.returncode == 2


# ---------------------------------------------------------------- talks / status

def test_talks_lists_every_talk_oldest_edition_first(indexed_dir):
    plain = run_aie("talks", data_dir=indexed_dir)
    as_json = run_aie("talks", "--json", data_dir=indexed_dir)

    assert plain.returncode == 0, plain.stderr
    lines = plain.stdout.strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("structured-llm-outputs-with-pydantic")
    assert "AI Engineer Summit 2023 (Oct 8-10, 2023)" in lines[0]
    assert lines[1].startswith("graphrag")
    assert lines[2].startswith("harness-engineering")
    assert [t["slug"] for t in json.loads(as_json.stdout)] == [
        "structured-llm-outputs-with-pydantic", "graphrag", "harness-engineering"]


def test_talks_accepts_the_search_filters(indexed_dir):
    by_speaker = run_aie("talks", "--speaker", "emil eifrem", "--json", data_dir=indexed_dir)
    after = run_aie("talks", "--after", "2026-01-01", "--json", data_dir=indexed_dir)

    assert [t["slug"] for t in json.loads(by_speaker.stdout)] == ["graphrag"]
    assert [t["slug"] for t in json.loads(after.stdout)] == ["harness-engineering"]


def test_status_reports_version_and_counts(indexed_dir):
    result = run_aie("status", data_dir=indexed_dir)

    assert result.returncode == 0, result.stderr
    assert "corpus version: 575e4c565354bf07b7d567ab08376f4176910a799bf0ef29ed41868192e0dc24" in result.stdout
    assert "synced: 2026-09-14T00:00:00+00:00" in result.stdout
    assert "indexed:" in result.stdout
    assert "talks: 3 · segments: 108 · chapters: 31 · editions: 10" in result.stdout


def test_status_on_an_empty_data_dir(tmp_path):
    result = run_aie("status", data_dir=tmp_path / "data")

    assert result.returncode == 0
    assert "not synced" in result.stdout
    assert "not indexed" in result.stdout


def test_query_commands_without_an_index_exit_1(synced_dir):
    for command in (["search", "prompts"], ["show", "graphrag"], ["talks"]):
        result = run_aie(*command, data_dir=synced_dir)
        assert result.returncode == 1, command
        assert "Run `aie sync` then `aie index`" in result.stderr, command
