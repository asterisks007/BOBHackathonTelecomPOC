# Telecom Outage Resolution BOB — Implementation Plan

**Event**: IBM BOB Hackathon 2026 (July 22–23)
**Project**: 7-Agent Agentic Orchestration for Telecom Outage Resolution
**Status**: Phase 0 ✅ Complete → Sub-Task 0 verification is NEXT

**Confirmed Layout**:
```
BOBHackathonTelecomPOC/
├── bobCode/          ← FastAPI backend (built from scratch)
├── frontend/         ← React UI (Vite + React + TypeScript, separate root folder)
└── mydocs/           ← Planning documents
```

---

## Top-Level Overview

Build a **FastAPI-backed, agentic AI BOB** that resolves telecom outages end-to-end. A customer
reports an outage in free-text; the system routes it through 7 specialized agents (Intent → Ticket →
RCA → Escalation + Parallel Analysis → Response → Feedback) coordinated by a Master Orchestrator. The
demo culminates with Watson Orchestrate + IBM BOB automating ticket creation and a React UI showing the
live agent flow.

**Key constraints**:
- IBM Lite Plan: ≤100 watsonx.ai calls/month → **mock-first** (≤10 real calls total for the entire POC)
- 2-day hackathon window → phases must be independently deliverable checkpoints
- **No phase exists if its test gate fails** — zero exceptions
- **Documentation is mandatory per sub-task** — not a post-step
- **Security is Foundation #1** — PII guardrails, input/output validation, and audit trail are built in ST-1G before any agent code
- Zero credential commits; `.env` only; `.env.example` as template
- All seed/fixture data is synthetic — no real customer records, no real PII

**Scope boundary**: POC only — single instance, no HA, no multi-language, no distributed cache.

**Competitive differentiators**:
- Security-first guardrails (PII, injection, output validation) run before every agent
- Real-time SSE streaming makes agentic flow visible to judges
- Confidence scores on every agent output, displayed in UI
- Graceful degradation: system always returns useful output even when IBM services are unavailable
- Immutable audit trail in Cloudant for every orchestration run
- `/health` endpoint exposes real-time token budget consumed vs. Lite Plan limit

---

## Architecture Diagram (Text)

```
React UI (Chat + Agent Visualization)
        │  HTTP / WebSocket
        ▼
FastAPI Backend
  └── Master Orchestration Engine
        ├── Sequential coordination + conditional branching
        ├── Error recovery + fallbacks
        └── SSE streaming to UI

        │ dispatches to 7 agents
        ▼
[IA] → [TA] → [RA] → [EA]+[PA] → [RGA] → [FA]
  IA = Intent Agent        PA  = Parallel Analysis Agent
  TA = Ticket Agent        RGA = Response Generation Agent
  RA = RCA Agent           FA  = Feedback Agent
  EA = Escalation Agent

External services per agent:
  watsonx.ai (Granite 13B) — RCA + Response Generation
  IBM NLU                  — Intent Recognition
  Cloudant                 — Ticket / Incident / Audit storage
  ChromaDB (local)         — RAG knowledge base
  Watson Orchestrate       — Skill orchestration (Phase 3)
  IBM BOB                  — Ticket automation (Phase 3)

**IBM Cloud Deployment & Execution Strategies**:
- [Option 1: Full IBM Cloud Code Engine Container Deployment](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/mydocs/option-1-ibm-code-engine-deployment.md) (Serverless Containers)
- [Option 2: Laptop Execution + ngrok Tunnel + watsonx Orchestrate](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/mydocs/option-2-local-laptop-ngrok-watsonx-orchestrate-guide.md) (Recommended Hackathon Strategy)

---

## Sub-Tasks

---

### Sub-Task 0 — Scaffold & Bootstrap `bobCode/` Project
**Status**: [x] done

**Intent**
The `bobCode/` directory does not yet exist. Create the full project skeleton — directory tree,
dependency files, FastAPI entrypoint, and initial health-check tests — so that Sub-Tasks 1–6
have a working, tested foundation to build on.

**Expected Outcomes**
- Full `bobCode/` directory tree created (agents/, core/, api/, data/seed_data/, tests/{unit,integration,fixtures}, scripts/, openapi/)
- `requirements.txt`, `requirements-dev.txt`, `requirements-test.txt` present with correct deps
- `.env.example` committed; `.env` git-ignored
- `bobCode/api/main.py` has `GET /` and `GET /health` endpoints
- `bobCode/tests/unit/test_health.py` has ≥5 passing health-check tests
- `pytest tests/ -v` exits 0
- FastAPI server starts: `uvicorn api.main:app --reload --port 8000` → `GET /health` returns 200

**Todo List**
1. Create directory tree: `bobCode/{agents,core,api,data/seed_data,tests/{unit,integration,fixtures},scripts,openapi}`
2. Create `bobCode/requirements.txt` — `fastapi, uvicorn, pydantic, chromadb, ibm-watson, ibm-watsonx-ai, cloudant, python-dotenv, sentence-transformers`
3. Create `bobCode/requirements-dev.txt` — `black, flake8, isort, mypy`
4. Create `bobCode/requirements-test.txt` — `pytest, pytest-asyncio, pytest-cov, pytest-mock, httpx`
5. Create `bobCode/pytest.ini` and `bobCode/pyproject.toml`
6. Create `bobCode/.env.example` — template with all IBM credential keys (empty values)
7. Create `bobCode/api/__init__.py`, `bobCode/api/main.py` — FastAPI app with `/` and `/health` endpoints
8. Create `bobCode/api/models.py` — placeholder Pydantic models
9. Create `bobCode/core/__init__.py`, `bobCode/core/config.py` — env-based settings with `USE_MOCK=true` default
10. Create `bobCode/tests/__init__.py`, `bobCode/tests/conftest.py`, `bobCode/tests/unit/__init__.py`
11. Write `bobCode/tests/unit/test_health.py` — ≥5 health-check tests using `httpx.AsyncClient`
12. Run `pip install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt`
13. Run `pytest tests/ -v` — all tests pass
14. Run `uvicorn api.main:app --reload --port 8000` — server starts, `/health` returns 200

**Relevant Context**
- Project structure spec: `mydocs/planning.md` lines 700–748
- Architecture Section 9 for environment config pattern
- Architecture Section 10: `USE_MOCK=true` default must be set from day 0

**Completion Notes (ST-0)**
- Tests: 20 passed (gate was ≥5) ✅
- Python 3.14.0, FastAPI 0.111, Pydantic v2, pytest-asyncio auto mode
- Files created: `core/config.py`, `api/main.py`, `api/models.py`, `tests/conftest.py`, `tests/unit/test_health.py`, all `__init__.py`, `requirements*.txt`, `pytest.ini`, `pyproject.toml`, `.env.example`, `.gitignore`
- No real API calls: 0 ✅

---

### Sub-Task 1G — Security Guardrails Foundation
**Status**: [x] done

**Intent**
Security is Priority #1. Before any agent code is written, the full guardrail layer must exist,
be tested, and be proven correct. This sub-task implements the three guardrail classes used by
every subsequent agent: `PIIGuardrails`, `InputGuardrails`, and `OutputGuardrails`. It also
establishes the audit logging pattern and the synthetic data contract.

This sub-task gates Sub-Task 1. If guardrail tests fail, Sub-Task 1 does not start.

**Expected Outcomes**
- `PIIGuardrails.mask_input(text)` redacts phone, email, SSN, credit-card patterns with `[REDACTED]`
- `PIIGuardrails.log_sanitised(data)` never logs raw PII; safe for audit trail
- `InputGuardrails.validate(message)` enforces: max 2000 chars, SQL injection block, prompt injection block
- `OutputGuardrails.validate(response)` enforces: confidence ≥ 0.5, Pydantic schema match, no leaked PII
- All guardrail classes have 100% branch coverage (every pattern, every rejection path tested)
- `bobCode/core/audit.py` — `AuditLogger` writes sanitised events to Cloudant `audit_trail/` collection
- `bobCode/docs/SECURITY.md` — documents all guardrail rules, patterns, and enforcement points
- ≥30 unit tests, all passing

**Todo List**
1. Create `bobCode/core/guardrails.py`:
   - `PIIGuardrails`: regex patterns for phone, email, SSN, credit card; `mask_input()`, `log_sanitised()`
   - `InputGuardrails`: length check (≤2000), SQL injection patterns, prompt-injection heuristics, `validate()`
   - `OutputGuardrails`: Pydantic schema check, confidence threshold (≥0.5), PII scan on output, `validate()`
2. Create `bobCode/core/audit.py`:
   - `AuditLogger.log_event(event_type, sanitised_payload, request_id)` — async write to Cloudant `audit_trail/`
   - In mock mode: write to in-memory list for test inspection
   - Timestamp, request_id, agent_name, status — never raw user text
3. Create `bobCode/docs/SECURITY.md` — document every guardrail rule with examples of what is blocked
4. Write `bobCode/tests/unit/test_guardrails.py` — ≥30 tests covering:
   - PII masking: phone (US/international), email, SSN, credit card, combined
   - PII boundary: ensure non-PII text is unchanged
   - Input validation: over-length input, SQL fragments, prompt injection attempts, valid input
   - Output validation: schema pass, schema fail, confidence too low, PII in output blocked
   - Audit logger: events written, no raw PII in logged payload
5. Run `pytest tests/unit/test_guardrails.py -v --cov=core/guardrails --cov=core/audit --cov-report=term-missing`
6. Confirm 100% branch coverage on guardrails.py; fix any gap before proceeding
7. Update `mydocs/telecom-bob-plan.md` status to `[x] done` with test count

**Relevant Context**
- Architecture Section 5 (`mydocs/planning.md`) — PII patterns, input/output validation rules
- Guardrail pattern to use in every agent (see skill `SKILL.md` Step 5 Guardrails Quick-Reference)
- `bobCode/core/config.py` (from ST-0) — `USE_MOCK` flag used by `AuditLogger`

**Completion Notes (ST-1G)**
- Tests: 56 passed (gate was ≥30) ✅
- Coverage: guardrails.py = 100% branch coverage ✅ | audit.py = 96% (live Cloudant path excluded by design)
- Files created: `core/guardrails.py`, `core/audit.py`, `docs/SECURITY.md`, `tests/unit/test_guardrails.py`
- No real API calls: 0 ✅
- SECURITY.md documents all 4 PII patterns, SQL/prompt injection blocks, output validation, credential rules

**Documentation Required**
- `bobCode/docs/SECURITY.md` — guardrail rules, enforcement points, what is blocked and why ✅ DONE
- Inline docstrings on every guardrail class and method ✅ DONE

---

### Sub-Task 1 — Core Infrastructure & Shared Utilities
**Status**: [x] done

**Intent**  
Build the reusable foundation that every agent depends on: abstract base class, Pydantic schemas,
mock clients for IBM services, and the ChromaDB RAG pipeline. Doing this first means each agent
can be developed and tested independently without duplicating boilerplate.

**Expected Outcomes**
- `BaseAgent` abstract class with `process(request) → AgentResponse` method
- Standardised `AgentRequest` / `AgentResponse` Pydantic models
- `GraniteClient`, `NLUClient`, `CloudantClient` — each with a `use_mock: bool` switch
- ChromaDB ingestion script loads ≥50 synthetic telecom incidents into `telecom_knowledge_base/`
- `SimilaritySearch.query(text, k=5)` returns ranked results
- `PIIGuardrails.mask_input()` and `InputGuardrails.validate()` working
- All unit tests for core utilities green (≥20 tests)

**Todo List**
1. Create `bobCode/core/base_agent.py` — abstract `BaseAgent` with request validation + response formatting
2. Create/update `bobCode/api/models.py` — `AgentRequest`, `AgentResponse`, `AgentMetadata` Pydantic models
3. Create `bobCode/core/granite_client.py` — `GraniteClient(use_mock=True)` returning deterministic mock responses
4. Create `bobCode/core/nlu_client.py` — `NLUClient(use_mock=True)` returning mock entity/intent JSON
5. Create `bobCode/core/cloudant_client.py` — `CloudantClient(use_mock=True)` with in-memory dict fallback
6. Create `bobCode/core/vectorstore.py` — ChromaDB wrapper with `ingest()` and `query(text, k)` methods
7. Create `bobCode/data/seed_data/outages.json` — 50+ synthetic outage scenarios
8. Create `bobCode/data/seed_data/incidents.json` — historic incident records with RCA notes
9. Create `bobCode/data/seed_data/knowledge_base.txt` — resolution patterns + troubleshooting guides
10. Create `bobCode/data/ingest.py` — script that loads seed data into ChromaDB
11. Create `bobCode/core/guardrails.py` — `PIIGuardrails`, `InputGuardrails`, `OutputGuardrails`
12. Write `bobCode/tests/unit/test_core_*.py` — ≥20 unit tests covering all core utilities
13. Run `pytest tests/unit/ -v` and confirm green

**Completion Notes (ST-1)**
- Tests: 30 passed (gate was ≥20) ✅ | Running total: 106 unit tests
- Files created: `core/base_agent.py`, `core/granite_client.py`, `core/nlu_client.py`, `core/cloudant_client.py`, `core/vectorstore.py`, `data/seed_data/{incidents.json,knowledge_base.txt}`, `data/ingest.py`, `docs/CORE_INFRA.md`
- BaseAgent lifecycle: input validate → PII mask → process → output validate → audit log
- No real API calls: 0 ✅

**Documentation Required**
- `bobCode/docs/CORE_INFRA.md` — describes BaseAgent contract, mock client switch, RAG pipeline ✅ DONE
- Docstrings on every class and public method ✅ DONE

**Relevant Context**
- Architecture Section 2 defines exact input/output JSON shapes for each agent
- Architecture Section 3 defines the standardised request/response envelope
- Architecture Section 4 defines Cloudant collections and ChromaDB collection names
- `bobCode/core/guardrails.py` (from ST-1G) — import and use, do not re-implement

---

### Sub-Task 2 — Implement All 7 Agents (Mocked Services)
**Status**: [x] done

**Intent**  
Implement each agent as a standalone FastAPI router + `BaseAgent` subclass. At this stage, all IBM
service calls use mock clients (zero real API calls). This allows 280+ unit tests to be written and
run fast, validating business logic in isolation.

**Expected Outcomes**
- 7 agent modules in `bobCode/agents/`, each with its own `POST /agents/{name}` endpoint
- Each agent returns a valid `AgentResponse` matching the schema in architecture Section 2
- ≥40 unit tests per agent (280+ total), all passing
- SLA targets validated via test fixtures (asserts on `metadata.execution_time_ms`)

**Todo List**

#### Intent Recognition Agent (`intent_agent.py`)
1. Implement `IntentAgent(BaseAgent)` — calls `NLUClient.analyze()` → returns `issue_type, service, location, priority, confidence, entities`
2. Add rule-based priority assignment (Critical/High/Medium/Low from location + service keywords)
3. Register `POST /agents/intent` route in `bobCode/api/routes.py`
4. Write `tests/unit/test_intent_agent.py` (≥40 tests): valid input, invalid input, schema validation, error handling, performance, mocking

#### Ticket Classification Agent (`ticket_agent.py`)
5. Implement `TicketAgent(BaseAgent)` — lookup table `issue_type → queue + severity + SLA minutes`
6. Generate `ticket_id` pattern `INC-{YYYY}-{NNNNNN}`
7. Register `POST /agents/ticket` route
8. Write `tests/unit/test_ticket_agent.py` (≥40 tests)

#### RCA Agent (`rca_agent.py`)
9. Implement `RCAAgent(BaseAgent)` — query ChromaDB for top-5 similar incidents → pass context + ticket to `GraniteClient.generate()` → return `root_cause, confidence, evidence, affected_services, recommendation`
10. Add caching: if same `issue_type + location` seen before, return cached result
11. Register `POST /agents/rca` route
12. Write `tests/unit/test_rca_agent.py` (≥40 tests)

#### Escalation Agent (`escalation_agent.py`)
13. Implement `EscalationAgent(BaseAgent)` — decision tree: `severity + scope → escalation_level + notify list + cost estimate`
14. Register `POST /agents/escalation` route
15. Write `tests/unit/test_escalation_agent.py` (≥40 tests)

#### Parallel Analysis Agent (`parallel_agent.py`)
16. Implement `ParallelAgent(BaseAgent)` — async queries to `CloudantClient` for customer count, traffic, revenue impact; aggregate `customer_impact + network_impact + operational_impact`
17. Register `POST /agents/parallel` route
18. Write `tests/unit/test_parallel_agent.py` (≥40 tests)

#### Response Generation Agent (`resolution_agent.py`)
19. Implement `ResolutionAgent(BaseAgent)` — template-based resolution steps + `GraniteClient` for personalised customer message; compute `automation_score` via rule engine
20. Register `POST /agents/resolution` route
21. Write `tests/unit/test_resolution_agent.py` (≥40 tests)

#### Feedback Agent (`feedback_agent.py`)
22. Implement `FeedbackAgent(BaseAgent)` — compute MTTR, `customer_satisfaction` score, `preventive_action` recommendation, `learning_points`
23. Register `POST /agents/feedback` route
24. Write `tests/unit/test_feedback_agent.py` (≥40 tests)

25. Run `pytest tests/unit/ -v --tb=short` — all 280+ tests must pass

**Documentation Required**
- `bobCode/docs/agents/{intent,ticket,rca,escalation,parallel,resolution,feedback}.md` — one file per agent with input schema, output schema, SLA target, and fallback behaviour

**Relevant Context**
- Architecture Section 2 (`mydocs/planning.md`) — exact output JSON for every agent
- `bobCode/core/base_agent.py` (from ST-1) — inherit from here
- `bobCode/core/guardrails.py` (from ST-1G) — PIIGuardrails + InputGuardrails + OutputGuardrails called in every `process()` method
- Architecture Section 8 — SLA targets per agent (use as assertion upper bounds in tests)
- Architecture Section 10 — zero real API calls in this phase

---

### Sub-Task 3 — Master Orchestration Engine
**Status**: [x] done

**Intent**  
Wire the 7 agents into a single `POST /orchestrate` endpoint with sequential coordination,
conditional branching, parallel execution where applicable, error recovery, and SSE streaming.
This is the core demo flow that judges will see.

**Expected Outcomes**
- `POST /orchestrate` accepts free-text customer complaint → returns full orchestration result
- Sequential flow: Intent → Ticket → RCA → (Escalation ∥ Parallel Analysis) → Response → Feedback
- Conditional branching: high-priority triggers escalation; known pattern skips to cached RCA
- Error recovery: failed agent uses fallback mock; LLM timeout escalates to human flag
- SSE stream endpoint `GET /orchestrate/stream` emits per-agent progress events
- ≥20 integration tests covering happy path, high-priority path, error recovery path
- End-to-end latency ≤8s in mock mode

**Todo List**
1. Create `bobCode/api/orchestrator.py` — `MasterOrchestrator.run(customer_input)` method
2. Implement sequential chain: call agents in order, pass `context.upstream_results` forward
3. Implement conditional branch: if `intent.priority == Critical` → run EscalationAgent
4. Implement parallel execution: run EscalationAgent + ParallelAgent concurrently with `asyncio.gather`
5. Implement caching layer: hash `(issue_type, location)` → store/retrieve RCA result
6. Implement fallback chain (from Architecture Section 6): `LLM fail → cache → keyword match → human escalation flag`
7. Add SSE streaming in `POST /orchestrate` — emit `{stage, agent, status, partial_result}` events
8. Expose `GET /openapi.json` and export as `bobCode/openapi/skills_spec.json`
9. Write `tests/integration/test_orchestration_flow.py` — happy path, high-priority, cached RCA
10. Write `tests/integration/test_error_recovery.py` — agent failure, LLM timeout, NLU fail
11. Write `tests/integration/test_rag_pipeline.py` — ChromaDB similarity search accuracy
12. Run `pytest tests/ -v` — all unit + integration tests pass

**Documentation Required**
- `bobCode/docs/ORCHESTRATION.md` — flow diagram, branching rules, SSE event schema, fallback chain

**Relevant Context**
- Architecture Section 3 (`mydocs/planning.md`) — communication patterns and sequential/parallel flow diagram
- Architecture Section 6 — error categories and fallback strategy code sketch
- Architecture Section 8 — latency targets (end-to-end ≤8s)
- `bobCode/api/main.py` — plug the orchestrator in here
- `bobCode/core/audit.py` (from ST-1G) — log every orchestration run start and completion

---

### Sub-Task 4 — Watson Orchestrate & IBM BOB Integration
**Status**: [x] done

**Intent**  
Register the 7 agent endpoints as Watson Orchestrate skills and wire IBM BOB to auto-create
Cloudant incident tickets from orchestration results. This is the IBM-specific differentiator for
the hackathon judges.

**Expected Outcomes**
- OpenAPI `skills_spec.json` registered in Watson Orchestrate
- 7 skills callable from Watson Orchestrate UI
- IBM BOB workflow: `orchestrate → create Cloudant ticket → return ticket_id`
- End-to-end test: customer message in → Cloudant document written → `ticket_id` returned
- ≤5 real API calls consumed (stay within Lite Plan budget)

**Todo List**
1. Review and clean up `bobCode/openapi/skills_spec.json` (generated in Sub-Task 3)
2. Import the skills spec into Watson Orchestrate console; verify all 7 skills appear
3. Create Watson Orchestrate flow: `receive_complaint → run_orchestrate_skill → log_result`
4. Configure IBM BOB to trigger on orchestration completion: write to Cloudant `tickets/` collection
5. Test BOB flow with 3 synthetic incidents (real API calls — stay within 5-call budget)
6. Write `tests/integration/test_end_to_end.py` — mocked BOB flow for CI
7. Document Watson Orchestrate skill parameters in `bobCode/openapi/README.md`

**Documentation Required**
- `bobCode/openapi/README.md` — skill parameters, invocation examples, BOB workflow description

**Relevant Context**
- Architecture Section 9 (`mydocs/planning.md`) — credential management (`.env` only, rotate keys)
- Architecture Section 10 — budget: only 5 real calls in Phase 3
- `bobCode/openapi/skills_spec.json` — exported from ST-3
- `bobCode/core/audit.py` (from ST-1G) — confirm audit events reach Cloudant in live mode

---

### Sub-Task 5 — React Frontend
**Status**: [ ] pending

**Intent**  
Build the React UI that judges interact with during the demo. It shows the live agent pipeline
visually as the orchestration progresses via SSE, making the agentic architecture immediately
tangible.

**Expected Outcomes**
- Chat input form that POSTs to `POST /orchestrate`
- Real-time agent progress visualization (7 nodes, each lighting up as the agent completes)
- Confidence meter per agent shown as progress bar
- Final resolution steps rendered as numbered list with copy button
- Incident timeline panel: timestamps + ticket ID link
- Error state UI: user-visible error message + retry button
- Responsive layout (desktop-first, 1280px min)

**Todo List**
1. Scaffold React app at workspace root: `npm create vite@latest frontend -- --template react-ts` (creates `frontend/` alongside `bobCode/`)
2. Create `src/components/ChatInput.tsx` — free-text input + submit
3. Create `src/components/AgentPipeline.tsx` — 7-node SVG/CSS pipeline visualization, SSE-driven state
4. Create `src/components/ResolutionPanel.tsx` — numbered resolution steps + customer message
5. Create `src/components/IncidentTimeline.tsx` — chronological agent events with timestamps
6. Create `src/hooks/useOrchestration.ts` — SSE event stream → React state
7. Create `src/pages/Dashboard.tsx` — compose all components
8. Wire API base URL from env var `VITE_API_URL=http://localhost:8000`
9. Add error boundary + retry button for failed orchestration
10. Run `npm run build` — no TypeScript errors, bundle builds cleanly

**Documentation Required**
- `frontend/README.md` — setup instructions, env vars, how to point at backend

**Relevant Context**
- Architecture Section 1 (`mydocs/planning.md`) — high-level UI description
- ST-3 SSE stream schema: `{stage, agent, status, partial_result, confidence}`
- `bobCode/api/main.py` CORS config must allow `http://localhost:5173` (not wildcard)
- No customer data is ever stored in browser localStorage or sessionStorage

---

### Sub-Task 6 — Demo Polish & Live API Activation
**Status**: [x] **DONE** ✅ — 2026-07-22

**Intent**  
Switch from mock clients to real IBM services for the demo run, prepare 3-5 scripted demo scenarios,
measure end-to-end latency, and verify the system stays within Lite Plan budget. This is the final
go/no-go gate before judges see it.

**Expected Outcomes**
- `USE_MOCK=false` in `.env` activates real watsonx.ai + NLU calls
- 3 demo scenarios produce believable results end-to-end (e.g. fiber cut, signal degradation, billing)
- End-to-end latency measured ≤8s for each demo scenario
- Total real API calls ≤10 across all testing + demo
- Smoke tests pass (`pytest tests/e2e/ -v`)
- `bobCode/scripts/demo.md` documents each demo scenario step-by-step

**Todo List**
1. Add `USE_MOCK` flag to `bobCode/core/config.py`; all clients respect it
2. Update `GraniteClient` and `NLUClient` to switch to real IBM SDK calls when `USE_MOCK=false`
3. Seed Cloudant with 3 representative incidents for demo
4. Run Scenario A: "4G outage in New York" — verify RCA + ticket creation
5. Run Scenario B: "Fiber cut affecting 50k customers" — verify Critical escalation path
6. Run Scenario C: "Billing system down city-wide" — verify parallel analysis metrics
7. Measure latency for each scenario; optimize any path exceeding 8s
8. Write `tests/e2e/test_demo_scenarios.py` — 5 smoke tests (mocked, safe for CI)
9. Update `bobCode/scripts/demo.md` with exact judge demo script
10. Final `pytest tests/ -v` — all tests green

**Documentation Required**
- `bobCode/scripts/demo.md` — exact judge demo script with 3 scenarios, expected outputs, and recovery steps
- `bobCode/docs/BUDGET_LOG.md` — record of every real API call made, timestamp, agent, purpose

**Relevant Context**
- Architecture Section 10 (`mydocs/planning.md`) — budget: 5 real calls ST-4 + 5 ST-6 = 10 total
- Architecture Section 8 — latency targets and optimization strategies
- Architecture Section 9 — environment config (Development / Staging / Production)
- Risk mitigation: if Granite latency > 2s, use ChromaDB similarity result directly as RCA summary
- `bobCode/core/audit.py` — confirm all demo runs produce audit trail entries

---

## IBM Service Integration Summary

| Service | Free Tier | Mock Until | Real Calls Budget |
|---|---|---|---|
| watsonx.ai Granite 13B | 100/month | Sub-Task 5 | 5 (demo only) |
| IBM NLU | 30,000/month | Sub-Task 3 | 5 (Phase 3 test) |
| Cloudant | Unlimited | Sub-Task 3 | Unlimited |
| ChromaDB (local) | N/A — local | Never mocked | 0 cost |
| Watson Orchestrate | BOB plan | Sub-Task 3 | Per BOB plan |

**Budget safety margin**: ≥90 watsonx.ai calls remaining after POC.

---

## Testing Coverage Targets

| Level | Count Target | When |
|---|---|---|
| Unit (per agent) | ≥40 × 7 = 280+ | Sub-Tasks 1–2 |
| Integration (orchestration) | ≥20 | Sub-Task 3 |
| E2E smoke tests | ≥5 | Sub-Task 6 |
| **Total** | **305+** | All phases |

---

## Risk Register

| Risk | Mitigation |
|---|---|
| Granite LLM rate limit hit | Cap at 5 calls; mock fallback for all other paths |
| Granite latency > 2s | Query ChromaDB similarity first; use LLM only if no cache hit |
| NLU service unavailable | Keyword-based fallback in `IntentAgent` |
| Cloudant connection fails | In-memory dict fallback; SQLite secondary backup |
| React build fails | Use Swagger `/docs` for demo if needed |
| Watson Orchestrate skill import fails | Fall back to direct `POST /orchestrate` in demo |

---

## Test Gate Summary (Hard Rules)

**No sub-task is complete until its test gate passes. No exceptions.**

| Sub-Task | Test Command | Minimum Pass Count | Documentation Gate |
|---|---|---|---|
| ST-0 | `pytest tests/unit/test_health.py -v` | ≥5 | None (scaffolding only) |
| ST-1G | `pytest tests/unit/test_guardrails.py -v --cov` | ≥30 + 100% branch | `SECURITY.md` present |
| ST-1 | `pytest tests/unit/test_core*.py -v` | ≥20 | `CORE_INFRA.md` present |
| ST-2 | `pytest tests/unit/ -v --tb=short` | ≥280 | 7 agent docs present |
| ST-3 | `pytest tests/ -v --tb=short` | ≥300 | `ORCHESTRATION.md` present |
| ST-4 | `pytest tests/integration/test_end_to_end.py -v` | ≥5 | `openapi/README.md` present |
| ST-5 | `npm run build` + `npm test` | 0 TS errors | `frontend/README.md` present |
| ST-6 | `pytest tests/ -v` (full suite) | ≥305 | `demo.md` + `BUDGET_LOG.md` present |

## Milestone Checkpoints

| Checkpoint | Gate Criteria |
|---|---|
| After ST-0 | `pytest` green, server starts, `.env.example` committed |
| After ST-1G | ≥30 guardrail tests green, 100% branch coverage, `SECURITY.md` written |
| After ST-1 | ≥20 core unit tests green, ChromaDB ingestion works, `CORE_INFRA.md` written |
| After ST-2 | 280+ unit tests green, all 7 agent endpoints respond, agent docs written |
| After ST-3 | `/orchestrate` returns full result, integration tests green, `ORCHESTRATION.md` written |
| After ST-4 | Watson Orchestrate skills registered, BOB writes Cloudant ticket, `openapi/README.md` written |
| After ST-5 | React UI chat → live agent pipeline visualization working, `frontend/README.md` written |
| After ST-6 | 3 demo scenarios ≤8s, ≤10 real API calls, all 305+ tests green, `demo.md` written |

---

## Token Budget Tracker

| Phase | Planned Real Calls | Actual Real Calls | Remaining |
|---|---|---|---|
| ST-0 to ST-3 | 0 | 0 | 100 |
| ST-4 (Watson + BOB) | ≤5 | TBD | TBD |
| ST-6 (Demo) | ≤5 | TBD | TBD |
| **Total** | **≤10** | **TBD** | **≥90** |

Update this table in `BUDGET_LOG.md` after every real API call.

---

**Plan file created**: 2026-07-22
**Updated**: Added ST-1G (Guardrails), Test Gate table, Token Budget Tracker, Documentation gates
**Based on**: `mydocs/planning.md` (Architecture Decisions + Implementation Plan)
**Skill**: `.bob/skills/telecom-BOB-dev/SKILL.md`
**Status**: READY FOR IMPLEMENTATION ✅
