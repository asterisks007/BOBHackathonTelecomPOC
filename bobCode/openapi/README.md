# Watson Orchestrate & IBM BOB Integration — Operations Guide

**Version**: 1.0 | **Status**: Active — ST-4 | **Updated**: 2026-07-22

---

## Overview

The Telecom BOB exposes a webhook at `POST /webhook/orchestrate` that Watson Orchestrate
calls when a skill is invoked. IBM BOB then writes the resulting ticket to Cloudant automatically.

```
Customer message
    → Watson Orchestrate (skill invoked)
        → POST /webhook/orchestrate  (this service)
            → 7-agent pipeline
            → Cloudant tickets/ write  (IBM BOB)
            → WatsonSkillResponse
        → Watson Orchestrate returns response to user
```

---

## Step 1 — Import the OpenAPI Specification

1. Open [Watson Orchestrate console](https://www.ibm.com/products/watson-orchestrate)
2. Navigate to **Skills** → **Add skill** → **From OpenAPI file**
3. Upload `bobCode/openapi/skills_spec.json`
4. Verify all 12 endpoints appear in the skill list

**Key skills to verify:**

| Skill | Endpoint | Method |
|---|---|---|
| `orchestrate` | `/orchestrate` | POST |
| `orchestrate_stream` | `/orchestrate/stream` | POST |
| `watson_orchestrate_webhook` | `/webhook/orchestrate` | POST |
| `intent_agent` | `/agents/intent` | POST |
| `ticket_agent` | `/agents/ticket` | POST |
| `rca_agent` | `/agents/rca` | POST |
| `escalation_agent` | `/agents/escalation` | POST |
| `parallel_agent` | `/agents/parallel` | POST |
| `resolution_agent` | `/agents/resolution` | POST |
| `feedback_agent` | `/agents/feedback` | POST |

---

## Step 2 — Configure Skill Parameters

For the `watson_orchestrate_webhook` skill, set these input parameters:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | ✅ | Watson Orchestrate session ID |
| `customer_id` | string | ✅ | Anonymised customer identifier |
| `message` | string | ✅ | Customer complaint (max 2000 chars) |
| `source` | string | — | Default: `watson_orchestrate` |

**Authorization**: Set `Authorization: Bearer {WATSON_ORCHESTRATE_API_KEY}` in skill headers.

---

## Step 3 — Build the Watson Orchestrate Flow

1. Navigate to **Automations** → **New automation**
2. Add trigger: **Conversational skill** (NLP-triggered on telecom outage keywords)
3. Add step: **Run skill** → `watson_orchestrate_webhook`
   - Map `session_id` from conversation context
   - Map `customer_id` from authenticated user profile
   - Map `message` from user input
4. Add step: **Return response** → Display `customer_message` from skill output
5. Add condition: If `escalated == true` → notify `network-ops@telecomco.internal`

---

## Step 4 — IBM BOB Workflow Configuration

IBM BOB is the automation layer that triggers on skill completion.

### BOB Automation Steps

1. Open **IBM BOB** workspace
2. Create new workflow: **Telecom Outage Ticket Creation**
3. Add trigger: **Watson Orchestrate skill completion** (`watson_orchestrate_webhook`)
4. Add action: **Cloudant document write**
   - URL: `{CLOUDANT_URL}/{CLOUDANT_DB_TICKETS}`
   - Document: skill output mapped to `BOBTicketDocument` schema
   - Auth: IAM API key from `CLOUDANT_API_KEY`
5. Add action: **Return ticket_id** to originating skill

### Ticket Document Schema (Cloudant)

```json
{
  "ticket_id":           "INC-2026-042871",
  "session_id":          "sess-...",
  "source":              "ibm_bob",
  "severity":            "P1",
  "queue":               "Network_Operations",
  "issue_type":          "fiber_cut",
  "root_cause_summary":  "Physical fiber cut at junction box BX-42...",
  "resolution_steps":    ["1. Verify fiber cut...", "2. Activate BGP..."],
  "escalated":           true,
  "escalation_level":    "Management",
  "sla_minutes":         240,
  "affected_customers":  47000,
  "automation_score":    0.30,
  "created_at":          "2026-07-22T14:30:00Z",
  "status":              "open"
}
```

**Security**: `root_cause_summary` is PII-masked before write. No raw customer text is stored.

---

## Step 5 — Live Validation (≤5 Real API Calls)

Run these 3 test scenarios manually. Each consumes 1 real Granite + 1 real NLU call.

### Scenario A — Fiber Cut (P1)
```
POST /webhook/orchestrate
{
  "session_id": "live-test-001",
  "customer_id": "LIVE-CUST-001",
  "message": "Complete fiber cut at junction box sector north, thousands of customers affected",
  "source": "manual_test"
}
Expected: severity=P1, queue=Network_Operations, escalated=true
```

### Scenario B — Billing Outage (P2)
```
POST /webhook/orchestrate
{
  "session_id": "live-test-002",
  "customer_id": "LIVE-CUST-002",
  "message": "Billing system is completely down, customers cannot make payments",
  "source": "manual_test"
}
Expected: severity=P2, queue=IT_Operations, escalated=false
```

### Scenario C — Signal Degradation (P2)
```
POST /webhook/orchestrate
{
  "session_id": "live-test-003",
  "customer_id": "LIVE-CUST-003",
  "message": "4G signal degradation in eastern sector, call drops reported",
  "source": "manual_test"
}
Expected: severity=P2/P3, queue=RAN_Operations
```

**After each test**: Verify ticket appears in Cloudant `tickets/` collection and confirm no PII leaked.

---

## Step 6 — Verify Budget Compliance

```bash
GET /health
# Expected: api_calls_used <= 5 after all live tests
```

Update `bobCode/docs/BUDGET_LOG.md` with each real call made.

---

## Credential Requirements

Set these in `.env` before enabling live mode (`USE_MOCK=false`):

```
WATSON_ORCHESTRATE_URL=https://...
WATSON_ORCHESTRATE_API_KEY=...
CLOUDANT_URL=https://...
CLOUDANT_API_KEY=...
CLOUDANT_DB_TICKETS=tickets
```

All credentials validated at startup by `Settings.validate_live_credentials()`.
Missing credentials log a warning and prevent live-mode activation.

---

## Troubleshooting

| Issue | Check |
|---|---|
| Skill not appearing in Watson Orchestrate | Re-export `skills_spec.json` via `python scripts/export_openapi.py` and re-import |
| 401 on webhook call | Add `Authorization: Bearer {key}` header |
| Ticket not in Cloudant | Check `USE_MOCK=false` and `CLOUDANT_API_KEY` is set |
| Pipeline times out | Check `GET /health` — if real LLM calls slow, fallback to mock mode |
| PII in ticket document | Should never happen — `PIIGuardrails.mask_input()` runs before every Cloudant write |
