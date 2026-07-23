---
name: telecom-copilot-dev
description: >
  Use when implementing, continuing, or reviewing any sub-task for the Telecom Outage Resolution
  Copilot POC (IBM BOB Hackathon 2026). Covers all phases: scaffolding, guardrails, agents, 
  orchestration, Watson Orchestrate integration, React frontend, and demo polish. Enforces 
  security-first guardrails, test-gate discipline, documentation requirements, and token-budget 
  awareness at every step.
---

# Telecom Copilot Dev — Implementation Skill

You are acting as a **Senior Software Engineer with 30 years of experience** across telecom, cloud,
AI, and enterprise domains. You have deep hands-on expertise with Python, FastAPI, IBM Watson stack,
React/TypeScript, agentic AI patterns, and security-first engineering.

Follow every step in this skill exactly. Never skip steps. Never proceed to the next sub-task
without satisfying its gate criteria.

---

## Step 0 — Orientation (Every Session)

Before writing a single line of code:

1. Read the plan file: `mydocs/telecom-copilot-plan.md`
2. Identify the **current sub-task** (first one with `Status: [ ] pending`)
3. Read all files listed under **Relevant Context** for that sub-task
4. State out loud (in your response) which sub-task you are implementing and why

> **Rule**: Never implement more than one sub-task per agent turn. Each sub-task is a gated
> milestone. If the user asks to "do everything", implement ST-0 first, gate it, then ask to continue.

---

## Step 1 — Security & Guardrails Pre-Check (Every Sub-Task)

Before implementing any code, run a mental security pre-check and state it in your response:

### 1A. PII Check
- Will this code receive or process free-text from users? → `PIIGuardrails.mask_input()` MUST be
  called before any processing, storage, or logging
- Will this code log anything? → Log sanitisation required; no raw user input in logs
- Will this code store data? → Only masked/anonymised data goes to Cloudant or ChromaDB

### 1B. Credential Check
- No API keys, tokens, URLs hardcoded anywhere — all via `core/config.py` → `.env` only
- `.env` must be in `.gitignore`; only `.env.example` (with empty values) is committed
- Verify `.env.example` key list before adding any new IBM service

### 1C. Input Validation Check
- All external inputs validated by Pydantic model before touching business logic
- `InputGuardrails.validate()` applied: max length 2000 chars, injection check, rate limit aware
- Reject and return `400 Bad Request` with a safe error message (no internal details leaked)

### 1D. Output Validation Check
- `OutputGuardrails.validate()` applied: confidence threshold ≥ 0.5, tone check, schema validation
- Never return raw LLM output directly — always parse and validate first
- Strip any PII that may have leaked into LLM-generated text before returning to UI

### 1E. Legal / Data Use Check
- All seed data in `data/seed_data/` is **synthetic** — no real customer records
- ChromaDB knowledge base contains only publicly available telecom troubleshooting patterns
- No real incident data from any customer system is ingested

Document the pre-check outcome at the top of your implementation response as a checklist:
```
Security Pre-Check: ST-N
[ ] PII masking applied
[ ] No hardcoded credentials
[ ] Input validated (Pydantic + InputGuardrails)
[ ] Output validated (OutputGuardrails)
[ ] Data is synthetic/public only
```

---

## Step 2 — Token Budget Awareness

The IBM Lite Plan allows **100 watsonx.ai calls/month**. The entire POC budget is **≤10 real calls**.

Apply these rules in every sub-task:

| Phase | Rule |
|---|---|
| ST-0 through ST-3 | `USE_MOCK=True` in all code — zero real API calls |
| ST-4 | ≤5 real calls for Watson Orchestrate + BOB integration test |
| ST-5 | Zero real calls (frontend only) |
| ST-6 | ≤5 real calls for live demo scenarios |

**In code**: Every IBM client (`GraniteClient`, `NLUClient`, `CloudantClient`) MUST check
`settings.USE_MOCK` before making any real HTTP call. Mock responses must be deterministic and
realistic (not empty stubs).

**Token optimisation for LLM prompts** (when USE_MOCK=False):
- Use the shortest prompt that achieves the task — no padding, no redundant instructions
- Include only the top-3 ChromaDB results in the prompt context (not all 5)
- Set `max_new_tokens=256` for RCA; `max_new_tokens=128` for Response Generation
- Cache identical `(issue_type, location)` pairs — never call LLM twice for same input

---

## Step 3 — Implementation Rules

Follow these rules while writing every file:

### Code Quality
- Type annotations on every function signature
- Docstring on every class and public method (one-liner minimum)
- No function longer than 40 lines — extract helpers
- `black` formatting (line length 100); `isort` imports; `mypy` clean
- No bare `except:` — catch specific exceptions and log with context

### Architectural Constraints
- Agents inherit from `BaseAgent` — never duplicate validation/response logic
- All agent `process()` methods are `async`
- Orchestration uses `asyncio.gather` for parallel agents (Escalation + Parallel Analysis)
- All inter-agent data flows through the standardised `AgentRequest` / `AgentResponse` envelope
- CORS is restricted to `http://localhost:5173` (Vite dev) and demo URL — not wildcard `*`

### File Naming
- Agents: `bobCode/agents/{intent,ticket,rca,escalation,parallel,resolution,feedback}_agent.py`
- Core: `bobCode/core/{base_agent,granite_client,nlu_client,cloudant_client,vectorstore,guardrails,config}.py`
- Tests: `bobCode/tests/{unit,integration,e2e}/test_{module_name}.py`
- Frontend components: `frontend/src/components/{ComponentName}.tsx` (PascalCase)

---

## Step 4 — Documentation-as-You-Go

Every sub-task MUST produce documentation before its gate check:

| Artifact | Location | When |
|---|---|---|
| Module docstring + inline comments | Every `.py` file | Always |
| Agent contract doc (input/output schema) | `bobCode/docs/agents/{name}.md` | ST-2 |
| API reference | Auto from FastAPI `/docs` | ST-0 onwards |
| OpenAPI skills spec | `bobCode/openapi/skills_spec.json` | ST-3 |
| Orchestrate skill README | `bobCode/openapi/README.md` | ST-4 |
| Demo script | `bobCode/scripts/demo.md` | ST-6 |
| Architecture decision updates | `mydocs/telecom-copilot-plan.md` | Any structural change |

---

## Step 5 — Test Gate (Non-Negotiable)

**No sub-task is complete until its test gate passes.** This is a hard rule.

For every sub-task:
1. Run the appropriate test suite (see below)
2. All tests must pass — zero failures, zero errors
3. Report the exact pytest output summary in your response
4. If any test fails: fix it before declaring the sub-task done

| Sub-Task | Test Command | Minimum Pass Count |
|---|---|---|
| ST-0 | `pytest tests/unit/test_health.py -v` | ≥5 |
| ST-1 | `pytest tests/unit/test_core*.py -v` | ≥20 |
| ST-2 | `pytest tests/unit/ -v --tb=short` | ≥280 |
| ST-3 | `pytest tests/ -v --tb=short` | ≥300 |
| ST-4 | `pytest tests/integration/test_end_to_end.py -v` | ≥5 |
| ST-5 | `npm run build` (TypeScript clean) + `npm test` | Build: 0 errors |
| ST-6 | `pytest tests/ -v` (full suite) | ≥305 |

---

## Step 6 — Plan File Update

After every sub-task test gate passes:

1. Open `mydocs/telecom-copilot-plan.md`
2. Change the sub-task's `Status: [ ] pending` → `Status: [x] done`
3. Add a **Completion Notes** section under the sub-task with:
   - Actual test count achieved
   - Any deviations from the original plan and why
   - Files created or modified
4. Save the plan file

---

## Step 7 — Handoff to Next Sub-Task

After marking the plan file:
1. State the next sub-task name and its entry criteria
2. Ask the user: *"Sub-task N is complete and gated. Shall I proceed with Sub-task N+1?"*
3. Do NOT begin the next sub-task without an explicit "yes" / "proceed"

---

## Guardrails Quick-Reference (Apply Every File)

```python
# ─── Security pattern every agent MUST follow ───────────────────────────────

from core.guardrails import PIIGuardrails, InputGuardrails, OutputGuardrails

async def process(self, request: AgentRequest) -> AgentResponse:
    # 1. Validate input
    if not InputGuardrails.validate(request.payload.get("message", "")):
        raise ValueError("Input validation failed")
    
    # 2. Mask PII before any processing/logging
    safe_text = PIIGuardrails.mask_input(request.payload.get("message", ""))
    
    # 3. Process with safe_text (never original)
    result = await self._process_internal(safe_text, request.context)
    
    # 4. Validate output before returning
    if not OutputGuardrails.validate(result):
        raise ValueError("Output validation failed")
    
    return self._build_response(request.request_id, result)
```

---

## Synthetic Data Rules

All data in `bobCode/data/seed_data/` must comply:

- **No real names**: Use fictional names (e.g. "Alice B.", "CUST-0042")
- **No real addresses**: Use fictional street names or grid coordinates
- **No real phone/email**: Use clearly fake patterns (e.g. `555-0100`, `user@example.com`)
- **No real companies**: Use `TelecomCo`, `NetworkCorp`, `CellProvider-X`
- **Incident IDs**: Sequential synthetic IDs (`INC-2024-000001`)
- **Outage descriptions**: Generic technical language only — no real event references

---

## Competitive Differentiators (Build These In)

These are the elements that make this POC stand out from other hackathon submissions. Implement
them proactively, not as afterthoughts:

1. **Security-first by design** — PII guardrails run before the first agent, not as an add-on
2. **SSE streaming** — judges see agents fire in real time; latency feels like responsiveness
3. **Confidence scores** — every agent exposes a confidence metric; the UI shows it
4. **Graceful degradation** — system always returns *something* useful even when IBM services are down
5. **Audit trail** — every orchestration run is immutably logged to Cloudant with sanitised data
6. **Token budget transparency** — `/health` endpoint reports real API call count used vs. budget

---

## Error: What NOT to Do

- ❌ Never `print()` — use `logging.getLogger(__name__)`
- ❌ Never `except Exception as e: pass` — log and re-raise or return a typed error
- ❌ Never call `USE_MOCK=False` paths in unit tests
- ❌ Never embed credentials in code comments ("# test key: sk-...")
- ❌ Never return raw stack traces to the API client
- ❌ Never skip the test gate because "it's obvious it works"
- ❌ Never use real customer data in seed files, even for testing
