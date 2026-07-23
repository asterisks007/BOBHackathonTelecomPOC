# Orchestration Architecture — Technical Reference

**Status**: Active — built in ST-3  
**Updated**: 2026-07-22

---

## Pipeline Flow

```
OrchestrateRequest (message, session_id, customer_id)
        │
        ▼  POST /orchestrate  or  POST /orchestrate/stream
┌─────────────────────────────────────────────────────┐
│           MasterOrchestrator.run()                  │
│                                                      │
│  Stage 1 ── IntentAgent                             │
│      │   issue_type, service, location, priority    │
│      ▼                                              │
│  Stage 2 ── TicketAgent                             │
│      │   ticket_id, severity, queue, sla_minutes    │
│      ▼                                              │
│  Stage 3 ── RCAAgent  (cache-aware + RAG + LLM)    │
│      │   root_cause, evidence, recommendation, eta  │
│      ▼                                              │
│  Stage 4 ── asyncio.gather ──────────────────────  │
│      ├── EscalationAgent                           │
│      │     escalate, level, notify, cost           │
│      └── ParallelAgent                             │
│            customer/network/operational impact     │
│      ▼                                              │
│  Stage 5 ── ResolutionAgent                        │
│      │   resolution_steps, customer_message, score  │
│      ▼                                              │
│  Stage 6 ── FeedbackAgent                          │
│            sla_met, csat, learning_points          │
└─────────────────────────────────────────────────────┘
        │
        ▼
OrchestrationResult
```

> [!NOTE]
> This pipeline flow can be orchestrated locally via `MasterOrchestrator.run()` OR in production via **watsonx Orchestrate Agent Builder**, where watsonx Orchestrate serves as the Master Agent invoking each stage as a containerized skill. For the complete deployment guide, see [IBM Cloud Deployment Guide](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/mydocs/ibm-cloud-deployment-guide.md).

---

## Conditional Branching Rules

| Condition | Behaviour |
|---|---|
| `priority == Critical` | EscalationAgent always runs (Stage 4, concurrent with Parallel) |
| `priority == High/Medium/Low` | EscalationAgent still runs (may return `escalate: false`) |
| `(issue_type, location)` cache hit in RCAAgent | LLM call skipped; `cache_hit: true` in response |
| Agent raises exception | `BaseAgent._fallback_response()` catches it; pipeline continues |
| All agents fail | `OrchestrationResult.agents_failed` lists all; partial result returned |

---

## Error Recovery Chain

```
Agent exception raised
    └── BaseAgent catches → returns AgentResponse(status=FALLBACK)
                                │
                                ├── Orchestrator logs warning
                                ├── Adds agent to agents_failed list
                                └── Continues to next stage with empty upstream result

GraniteClient live call fails
    └── Falls back to mock response (deterministic keyword-based)

NLUClient live call fails
    └── Falls back to mock entity/keyword response

Entire orchestration panics
    └── HTTPException(500) with safe generic message (no internals exposed)
```

---

## SSE Event Schema

Each agent emits one event as it completes. Format: `data: {JSON}\n\n`

```json
{
  "stage": "rca_analysis",
  "agent": "rca_analysis",
  "status": "success",
  "confidence": 0.88,
  "partial_result": {
    "root_cause": "Physical fiber cut at junction box BX-42..."
  }
}
```

Final event when pipeline completes:
```json
{
  "stage": "complete",
  "agent": "orchestrator",
  "status": "success",
  "total_execution_ms": 412.3,
  "ticket_id": "INC-2026-042871",
  "agents_completed": ["intent_recognition", "ticket_classification", "..."],
  "agents_failed": []
}
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/orchestrate` | Full pipeline, blocking, returns `OrchestrationResult` |
| `POST` | `/orchestrate/stream` | Full pipeline, SSE streaming |
| `POST` | `/agents/intent` | Intent agent standalone |
| `POST` | `/agents/ticket` | Ticket agent standalone |
| `POST` | `/agents/rca` | RCA agent standalone |
| `POST` | `/agents/escalation` | Escalation agent standalone |
| `POST` | `/agents/parallel` | Parallel analysis standalone |
| `POST` | `/agents/resolution` | Resolution generation standalone |
| `POST` | `/agents/feedback` | Feedback agent standalone |
| `GET`  | `/health` | System health + live API call count vs. budget |
| `GET`  | `/docs` | Swagger UI (auto-generated) |

---

## Context Propagation

Each agent receives the full `upstream_results` dict containing all prior agent outputs:

```python
upstream_results = {
    "intent_recognition":    { "issue_type": "fiber_cut", ... },
    "ticket_classification": { "ticket_id": "INC-2026-...", "severity": "P1", ... },
    "rca_analysis":          { "root_cause": "...", "confidence": 0.88, ... },
    # ... etc
}
```

Agents access this via `request.context.upstream_results.get("intent_recognition", {})`.
Every agent falls back gracefully if upstream results are missing.

---

## Performance

| Stage | Target | Mode |
|---|---|---|
| Intent | <500ms | Mock NLU |
| Ticket | <200ms | Rules only |
| RCA | <2s | Mock LLM + local ChromaDB |
| Escalation + Parallel | <1s | Concurrent; rules + mock Cloudant |
| Resolution | <1.5s | Mock LLM |
| Feedback | <500ms | Mock Cloudant write |
| **End-to-end** | **<8s** | All mock |

Parallelisation at Stage 4 saves ~500ms vs. sequential execution.
RCA cache eliminates the LLM call on repeated identical incidents (saves ~1.5s each).

---

## Security

- Input validated by `OrchestrateRequest` Pydantic model (`max_length=2000`) before pipeline starts
- PII masking applied inside `IntentAgent` (first in chain) — subsequent agents receive safe text
- SSE events contain only structured metadata — no raw user text is ever streamed to the client
- Every orchestration run produces an immutable audit trail entry in Cloudant `audit_trail`
- CORS restricted to `http://localhost:5173` and demo URL (configured in `main.py`)
