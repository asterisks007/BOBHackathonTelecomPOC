# Core Infrastructure — Technical Reference

**Status**: Active — built in ST-1  
**Updated**: 2026-07-22

---

## Overview

The `core/` package contains all shared infrastructure used by the 7 agents. It enforces the
security-first pattern (guardrails) and the mock-first pattern (zero real API calls during
development and testing).

---

## BaseAgent (`core/base_agent.py`)

All 7 agents inherit from `BaseAgent`. The base class enforces the full security lifecycle
automatically — agents only need to implement `_process_internal()`.

### Execution Lifecycle (enforced by `process()`)

```
AgentRequest
    │
    ▼
1. InputGuardrails.validate(message)
    │ — reject if over-length / SQL-injection / prompt-injection
    ▼
2. PIIGuardrails.mask_input(message)
    │ — safe_text is used for all downstream processing
    ▼
3. _process_internal(safe_text, request)   ← agent-specific logic
    │
    ▼
4. OutputGuardrails.validate(result, confidence, required_fields)
    │ — confidence ≥ 0.5, required fields present, no PII in output
    ▼
5. AuditLogger.log_event(...)
    │ — sanitised payload only
    ▼
AgentResponse
```

### Contract

| Method | Required | Description |
|---|---|---|
| `agent_name` (class attr) | ✅ | Snake-case agent identifier |
| `required_output_fields` (class attr) | ✅ | Fields that must appear in result |
| `_process_internal(safe_text, request)` | ✅ | Returns `(result_dict, confidence_float)` |

### Error Handling

- `_process_internal` raises → `_fallback_response()` returned (status=`fallback`)
- Input validation fails → `_error_response()` returned (status=`error`)
- Output validation fails → result sanitised, confidence reduced, status=`partial`

---

## Mock Client Switch

All IBM service clients respect `settings.use_mock` (from `core/config.py`):

```python
# In .env (development)
USE_MOCK=true   # default — no real API calls

# In .env (live demo only — ST-6)
USE_MOCK=false  # activates real IBM services
```

| Client | Mock behaviour |
|---|---|
| `GraniteClient` | Keyword-matched deterministic text responses |
| `NLUClient` | Keyword-matched entity/keyword/sentiment dicts |
| `CloudantClient` | In-memory dict (`_MOCK_STORE`) |
| `VectorStore` | Always real (local ChromaDB — no API cost) |

---

## VectorStore / RAG Pipeline

ChromaDB runs locally. No API calls. No credentials.

### Collections

| Collection | Content | Used by |
|---|---|---|
| `telecom_knowledge_base` | Incidents + KB chunks | RCA Agent |
| `outage_patterns` | Outage signatures | Parallel Analysis Agent |

### Ingestion

```bash
cd bobCode
python data/ingest.py
```

### Query

```python
store = VectorStore()
results = store.query("fiber cut junction box", k=3)
# Returns list of {id, document, metadata, distance}
```

---

## Seed Data Contract

All files in `data/seed_data/` are **synthetic**. Compliance rules:

- No real customer names, addresses, phone numbers, or emails
- No real company names — use `TelecomCo`, `NetworkCorp`, `CellProvider-X`
- No real geographic coordinates — use fictional sector/grid references
- Incident IDs are sequential synthetic IDs: `INC-2024-000001`

---

## Settings Reference (`core/config.py`)

Key fields:

| Setting | Default | Description |
|---|---|---|
| `USE_MOCK` | `true` | Master mock switch |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS whitelist |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | Local ChromaDB storage |
| `WATSONX_API_KEY` | `""` | Filled in `.env` for live mode only |

Call `get_settings()` (cached singleton) to access settings anywhere.
