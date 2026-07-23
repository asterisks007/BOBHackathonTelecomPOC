# Demo Script — Telecom Outage Resolution BOB
## IBM BOB Hackathon 2026 · Judge Walkthrough Guide

> **Presenter**: Follow each step in order. Expected outputs are shown after every command.  
> **Recovery**: If anything deviates, jump to the [Recovery Playbook](#recovery-playbook) at the bottom.  
> **Runtime mode**: `USE_MOCK=True` (default) — zero real API calls consumed during demo.

---

## Pre-Demo Checklist (5 minutes before judges arrive)

```powershell
# 1. Start the backend (from bobCode/)
cd bobCode
uvicorn api.main:app --reload --port 8000

# 2. Start the frontend (from frontend/)
cd ../frontend
npm run dev
```

Verify:
- [ ] `http://localhost:8000/health` returns `{"status":"ok","use_mock":true}`
- [ ] `http://localhost:5173` shows the Telecom BOB dashboard
- [ ] Browser console has no red errors

---

## Demo Overview

| # | Scenario | Type | Severity | Key Points |
|---|----------|------|----------|------------|
| A | "4G outage — fiber cut New York" | Network | **P1** | RCA, BGP failover, repair crew |
| B | "Fiber cut — 50k customers" | Critical | **P1** | Escalation triggered, parallel analysis |
| C | "Billing system down city-wide" | Application | **P2** | Database pool fix, ops handoff |

---

## Scenario A — 4G Outage / Fiber Cut (P1) · ~2 minutes

### What it demonstrates
- Natural language intake → 7-agent pipeline in real time
- Intent Recognition picks up "fiber cut" + "New York"
- Ticket Classification assigns P1 severity
- RCA Agent pulls BGP failover pattern from ChromaDB knowledge base
- Resolution Agent generates actionable steps + customer message
- Full audit trail written to Cloudant

### Step A-1: Submit via React Frontend

1. Open `http://localhost:5173` in the browser.
2. In the **Chat Input** box, type (or click **Load Demo**):

   ```
   4G outage in New York sector north. Fiber cut at junction box BX-42.
   Approximately 47000 customers affected. Service completely down.
   ```

3. Click **Submit / Enter**.

**Expected**: The 7-node pipeline visualisation lights up left to right, each node turning green as it completes. Total time ≤ 2 seconds.

### Step A-2: Point out the Resolution Panel

Highlight to judges:
- **Ticket ID**: `INC-XXXX-XXXX` (auto-generated)
- **Severity**: `P1`
- **Resolution Steps**: "Activate BGP failover", "Dispatch fiber repair crew", …
- **Customer Message**: Professional, jargon-free notification

### Step A-3: API evidence (optional, for technical judges)

```bash
curl -s -X POST http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-A-001",
    "customer_id": "CUST-A-001",
    "message": "4G outage New York fiber cut junction box BX-42 47000 customers affected"
  }' | python -m json.tool
```

**Expected fields in response**:
```json
{
  "ticket_id": "INC-...",
  "ticket_summary": { "severity": "P1", "queue": "Network Operations" },
  "rca_summary": { "root_cause": "Physical fiber cut at junction box BX-42..." },
  "escalation_summary": { "escalate": true, "escalation_level": "L2" },
  "resolution_summary": { "resolution_steps": [...], "customer_message": "..." },
  "agents_completed": ["intent_recognition","ticket_classification","rca_analysis",
                       "escalation","parallel_analysis","response_generation","feedback"],
  "agents_failed": []
}
```

---

## Scenario B — Fiber Cut 50 000 Customers (Critical Escalation) · ~2 minutes

### What it demonstrates
- Critical path: large-scale outage → mandatory escalation
- Parallel Analysis Agent runs concurrent customer + network + operational impact
- Escalation Agent fires `escalate: true` with level `Critical`
- Watson Orchestrate webhook integration

### Step B-1: Submit via Webhook (simulating Watson Orchestrate)

```bash
curl -s -X POST http://localhost:8000/webhook/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-B-001",
    "customer_id": "CUST-B-001",
    "message": "CRITICAL: Fiber cut affecting 50000 customers in downtown district. Complete service outage. Emergency escalation required immediately.",
    "source": "watson_orchestrate"
  }' | python -m json.tool
```

**Expected fields**:
```json
{
  "ticket_id": "INC-...",
  "severity": "P1",
  "escalated": true,
  "root_cause_summary": "Physical fiber cut...",
  "resolution_steps_count": 4,
  "customer_message": "We are aware of a critical service disruption...",
  "status": "success",
  "total_execution_ms": ...
}
```

### Step B-2: Show Cloudant ticket (mock store inspection)

```bash
# Retrieve the ticket just created
curl -s http://localhost:8000/webhook/tickets/INC-XXXX-XXXX | python -m json.tool
```

Highlight:
- **No PII** in the stored document
- `escalated: true`, `escalation_level: "Critical"` or `"L2"`
- `affected_customers` populated from parallel analysis

### Step B-3: Frontend walkthrough

- Switch back to `http://localhost:5173`
- Paste the Scenario B message into Chat Input
- Show **Agent Pipeline** — nodes for Escalation and Parallel Analysis light up simultaneously (asyncio.gather)

---

## Scenario C — Billing System Down City-Wide (P2) · ~2 minutes

### What it demonstrates
- Application-layer outage (not network hardware)
- Intent Agent distinguishes billing from fiber/signal issues
- RCA identifies database connection pool exhaustion
- Resolution includes billing-specific remediation steps
- Feedback Agent estimates CSAT impact and SLA compliance

### Step C-1: Submit via Frontend

Paste into Chat Input:

```
Billing system down city-wide. Customers cannot pay their bills.
Self-service portal unresponsive. New activations blocked. Affecting all customers.
```

**Expected**:
- **Ticket Severity**: `P2`
- **Issue Type**: `billing_system_outage` or `application_outage`
- **RCA**: "Billing system database connection pool exhausted…"
- **Resolution Steps**: "Terminate runaway batch job", "Scale connection pool", …
- **Customer Message**: Billing-specific, no technical jargon

### Step C-2: SSE Streaming demo (technical judges)

```bash
curl -s -N -X POST http://localhost:8000/orchestrate/stream \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-C-stream-001",
    "customer_id": "CUST-C-001",
    "message": "Billing system down city-wide customers cannot pay portal down"
  }'
```

**Expected output** (one SSE event per agent):
```
data: {"stage":"intent_recognition","agent":"intent_recognition","status":"success","confidence":0.9,...}
data: {"stage":"ticket_classification","agent":"ticket_classification","status":"success",...}
data: {"stage":"rca_analysis","agent":"rca_analysis","status":"success",...}
data: {"stage":"escalation","agent":"escalation","status":"success",...}
data: {"stage":"parallel_analysis","agent":"parallel_analysis","status":"success",...}
data: {"stage":"response_generation","agent":"response_generation","status":"success",...}
data: {"stage":"feedback","agent":"feedback","status":"success",...}
data: {"stage":"complete","agent":"orchestrator","status":"success","total_execution_ms":...}
```

---

## Security Guardrails Demo (bonus — 30 seconds)

Show PII masking in action:

```bash
curl -s -X POST http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-pii-001",
    "customer_id": "CUST-PII-001",
    "message": "Fiber cut. Contact jane.doe@customer.com or call 555-123-4567 for updates."
  }' | python -m json.tool | grep -i "jane\|555-123"
```

**Expected**: No output — PII masked to `[EMAIL]` / `[PHONE]` before any agent processes it.

---

## Budget Status

```bash
curl -s http://localhost:8000/health | python -m json.tool | grep api_calls
```

**Expected**:
```json
"api_calls_used": 0,
"api_calls_budget": 100
```

> **Key message**: The entire demo runs on zero real IBM API calls — 100% of the 100-call Lite Plan budget remains intact.

---

## Architecture Summary Talking Points

| Layer | Technology | Role |
|-------|-----------|------|
| **LLM** | IBM watsonx.ai Granite 13B | RCA + resolution generation |
| **NLU** | IBM Watson NLU | Entity/intent extraction |
| **Vector DB** | ChromaDB (local) | Knowledge base RAG |
| **Document DB** | IBM Cloudant | Tickets, incidents, audit trail |
| **Orchestration** | Watson Orchestrate + IBM BOB | Skill coordination, automation |
| **API** | FastAPI (Python) | 7-agent pipeline, SSE streaming |
| **UI** | React 19 + Vite | Real-time agent pipeline visualisation |

---

## Recovery Playbook

| Problem | Fix |
|---------|-----|
| Backend not starting | `cd bobCode && pip install -r requirements.txt && uvicorn api.main:app --port 8000` |
| Frontend not starting | `cd frontend && npm install && npm run dev` |
| `/health` returns error | Check `USE_MOCK=True` in `bobCode/.env`; restart backend |
| `ticket_id` is null | Message too short — add more context keywords (fiber/billing/signal) |
| Response takes >3s | Normal for first call (ChromaDB init); subsequent calls are faster |
| RCA returns generic text | Expected for novel queries — mock returns deterministic "default" fallback |
| Escalation not triggered | Add "50000 customers" or "critical emergency" to message |

---

## Scoring Criteria Alignment

| Criterion | Demonstrated By |
|-----------|----------------|
| **Innovation** | 7-agent async pipeline with concurrent Stage 4; SSE real-time streaming |
| **Technical Depth** | BaseAgent security lifecycle, PII guardrails, ChromaDB RAG, asyncio.gather |
| **IBM Services** | watsonx.ai Granite, Watson NLU, Cloudant, Watson Orchestrate, IBM BOB |
| **Business Value** | P1/P2 auto-triage, MTTR reduction, customer message generation |
| **Demo Quality** | 3 distinct scenarios, <2s response, live audit trail, zero real API spend |

---

*Demo script last updated: 2026-07-22 | Version: ST-6 Final*
