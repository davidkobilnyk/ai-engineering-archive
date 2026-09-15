# Test fixtures

Real responses from the ai.engineer public data endpoints, captured on
2026-09-14 (corpus version `575e4c56…0dc24`, published 2026-09-03) and
trimmed to three talks:

| slug | event string as published | edition |
|---|---|---|
| `harness-engineering` | `AI Engineer Europe 2026` | europe 2026 |
| `graphrag` | `worldsfair-2024` | worldsfair 2024 |
| `structured-llm-outputs-with-pydantic` | `AI Engineer Summit 2023` | summit 2023 |

Files mirror the endpoint they came from:

| file | endpoint |
|---|---|
| `status.json` | `/api/data/status` (untrimmed) |
| `talks.json` | `/api/data/talks?format=json`, filtered to the three slugs |
| `speakers.json` | `/api/data/speakers?format=json`, the three speakers, `talkSlugs` filtered |
| `topics.json` | `/api/data/topics?format=json`, the two topics used, `talkSlugs` filtered |
| `organizations.json` | `/api/data/organizations?format=json`, OpenAI and Neo4j, `speakerSlugs` filtered |
| `chapters.json` | `/api/data/chapters?format=json`, filtered to the three slugs |
| `transcripts.json` | `/api/data/transcripts?format=json`, filtered to the three slugs |
| `transcripts/<slug>.json` | `/api/data/transcript?slug=<slug>&format=json`, untrimmed |

Tests take their expected values as literals read from these files.
Do not regenerate them casually: the literals in `tests/test_cli.py` are
tied to this capture.
