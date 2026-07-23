# Security Model — Telecom Outage Resolution BOB

**Version**: 1.0  
**Owner**: Telecom BOB Team — IBM BOB Hackathon 2026  
**Status**: ACTIVE — enforced from Sub-Task 1G onwards

---

## Overview

Security is Priority #1 and is built into the system's foundation, not bolted on afterwards.
Three guardrail classes in [`core/guardrails.py`](../core/guardrails.py) enforce security at every
data boundary. The audit logger in [`core/audit.py`](../core/audit.py) provides an immutable,
sanitised event trail.

---

## 1. PII Protection — `PIIGuardrails`

### What is blocked

| Pattern Type | Example Input | After Masking |
|---|---|---|
| US/International Phone | `Call me at +1 555-012-3456` | `Call me at [REDACTED]` |
| Email Address | `Contact john.doe@example.com` | `Contact [REDACTED]` |
| US Social Security Number | `SSN: 123-45-6789` | `SSN: [REDACTED]` |
| Credit Card Number | `Card: 4111 1111 1111 1111` | `Card: [REDACTED]` |

### Where it is applied

1. **Before any processing** — `PIIGuardrails.mask_input()` is called on raw user text in every
   agent's `process()` method before any IBM service is called or any logging occurs.
2. **Before any logging** — `PIIGuardrails.log_sanitised()` is called on all audit event payloads.
3. **On agent output** — `OutputGuardrails.scan_for_pii()` checks LLM-generated text before
   it is returned to the client.

### What is NOT redacted

- Network technical terms that happen to look like IP addresses (`10.0.0.1`) — these are not PII
- Generic numeric references that don't match PII patterns
- Ticket IDs, session IDs, request IDs

---

## 2. Input Validation — `InputGuardrails`

### Validation rules (in order of application)

| Rule | Limit | Rejection reason |
|---|---|---|
| Non-empty | Required | "Input must not be empty" |
| Maximum length | 2000 characters | "Input exceeds maximum length of 2000 characters" |
| SQL injection | Pattern match | "Input contains disallowed content" |
| Prompt injection | Pattern match | "Input contains disallowed content" |

### SQL injection patterns blocked

- `UNION SELECT`
- `DROP TABLE`
- `INSERT INTO`
- `DELETE FROM`
- `SELECT * FROM`
- `EXEC(`
- SQL line comment (`--`)
- SQL block comment (`/* */`)

### Prompt injection patterns blocked

- `ignore all previous instructions`
- `you are now a`
- `system: you`
- `forget everything`
- Instruction tags: `[INST]`, `<|im_start|>`, `### Human:`
- `act as if you are`

### Safe error messages

Rejections never expose which specific pattern matched. The client always receives the generic
message `"Input contains disallowed content"` so attackers cannot probe for pattern boundaries.

---

## 3. Output Validation — `OutputGuardrails`

### Checks applied before every agent response is returned

| Check | Rule | Action on failure |
|---|---|---|
| Confidence threshold | `confidence >= 0.5` | Reject; escalate to fallback |
| Required fields | Agent-specific | Reject with schema error |
| PII scan | All string values checked | Reject; log warning |

---

## 4. Audit Trail — `AuditLogger`

Every orchestration run produces an immutable audit trail:

- **What is logged**: event type, request ID, agent name, status, timestamp, sanitised payload
- **What is NEVER logged**: raw user text, unmasked PII, stack traces, credentials
- **Mock mode**: events written to in-memory list (test-inspectable)
- **Live mode**: events written to Cloudant `audit_trail` collection (append-only)

---

## 5. Credential Management

- All IBM credentials stored in `.env` only (local development)
- `.env` is in `.gitignore` — never committed
- `.env.example` contains only key names with empty values
- In CI/CD: credentials injected as environment variables, never in code
- `Settings.validate_live_credentials()` checks for missing credentials on startup when `USE_MOCK=False`

---

## 6. Network Security

- CORS restricted to `http://localhost:5173` (Vite dev) and demo URL — never `*`
- API methods restricted to `GET` and `POST` only
- No credentials in CORS-preflight headers

---

## 7. Data Handling

- All seed data in `data/seed_data/` is **synthetic** — no real customer records
- Synthetic data rules:
  - Names: fictional (e.g. "Alice B.", "CUST-0042")
  - Addresses: fictional street names or grid coordinates
  - Phone/email: clearly fake patterns (`555-0100`, `user@example.com`)
  - Companies: `TelecomCo`, `NetworkCorp`, `CellProvider-X`
  - Incident IDs: sequential synthetic IDs (`INC-2024-000001`)
- ChromaDB knowledge base: publicly available telecom troubleshooting patterns only

---

## 8. Token / API Budget Security

Unauthorised LLM usage is a cost and data risk:
- `USE_MOCK=True` is the default — enforced in `core/config.py`
- `GraniteClient` and `NLUClient` check `settings.use_mock` before every HTTP call
- `GET /health` exposes `api_calls_used` vs `api_calls_budget` for transparency
- `BUDGET_LOG.md` tracks every real call by timestamp, agent, and purpose (created in ST-6)
