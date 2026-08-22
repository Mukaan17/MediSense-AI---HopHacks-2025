# Prompt registry

Prompts are code: version them, and refresh the recorded fixtures whenever
one changes (`python scripts/record_llm_fixtures.py`, needs API keys), so
the replay tests (`tests/test_llm_replay.py`) exercise real model output
against the real post-processing.

| Prompt | Where | Version | Last change |
|---|---|---|---|
| `answer.j2` | `core/answer.py` | v2 | Jinja2 StrictUndefined rendering (R2); JSON response mode (I11) |
| `structured_diagnosis.j2` | `core/diagnosis/differential.py` | v2 | Jinja2 rendering (R2); JSON response mode (I11) |
| questioner JSON prompt (inline) | `core/questioner_llm.py` | v2 | JSON response mode (I11) |
| coach stream prompt (inline) | `core/questioner_llm.py` | v1 | [red-flag] tag contract (P3) |
| final report prompt (inline) | `api/pipeline.py` | v1 | P3 |

## Structured outputs & JSON mode (I11)

- Gemini paths use JSON response mode (`invoke_json` /
  `responseMimeType: application/json`): the API returns syntactically
  valid JSON, demoting `parse_llm_json` to a safety net. A response
  *schema* is deliberately not sent - Gemini's schema dialect is a subset,
  and a rejected schema would fail the whole call.
- Claude offers full schema-constrained output via
  `core.llm_client.invoke_claude_json(prompt, schema)` (structured
  outputs); adopt it per-path when a Claude-primary JSON path exists.

## Prompt caching (I11)

Claude system prompts go up as content blocks with a `cache_control`
breakpoint (`_system_blocks`). Caching is a prefix match and only
prefixes of roughly >=1024 tokens cache, so today's short system prompts
won't hit - the hook costs nothing and long stable prompts (e.g. a future
guideline preamble) start caching with no code change. Verifying real
cache hits (`usage.cache_read_input_tokens > 0`) requires live keys and
belongs to the owner-run recording session.
