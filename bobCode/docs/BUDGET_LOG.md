# API Budget Log — IBM Lite Plan Tracker

**Monthly Budget**: 100 watsonx.ai calls  
**POC Allocation**: ≤10 real calls total  
**Updated**: 2026-07-22 (ST-6 Final)

---

## Real API Call Register

| # | Timestamp (UTC) | Sub-Task | Agent | Service | Purpose | Calls Used |
|---|---|---|---|---|---|---|
| — | ST-0 → ST-5 | All | All | All | Development + unit/integration/e2e testing (100% mocked, `USE_MOCK=True`) | **0** |
| — | ST-6 Demo | — | — | — | Demo scenarios A/B/C run mocked (`USE_MOCK=True`) — no real calls consumed | **0** |

**Total real calls consumed across entire POC: 0 / 10 budget**

> **Note**: All development, testing, and demo scenarios ran 100% mocked.  
> If judges request a live IBM API demonstration, activate real calls via  
> `USE_MOCK=False` in `.env` — maximum 10 calls may be used.

---

## Current Budget Status

| Phase | Planned | Actual | Remaining |
|---|---|---|---|
| ST-0 → ST-3 | 0 | **0** | 100 |
| ST-4 (Watson + BOB) | ≤5 | **0** | 100 |
| ST-5 (Frontend) | 0 | **0** | 100 |
| ST-6 (Demo) | ≤5 | **0** | 100 |
| **Total** | **≤10** | **0** | **100 (100%)** |

---

## Budget Rules

1. `USE_MOCK=true` is the **default** — never change without a specific reason
2. Before every real call, confirm remaining budget from `GET /health` → `api_calls_used`
3. Each real Granite call costs **1 watsonx.ai call** from the Lite Plan quota
4. NLU calls are **free** up to 30,000/month — no budget concern
5. Cloudant calls are **unlimited** on Lite Plan — no budget concern
6. If `api_calls_used >= 8`, freeze real API usage and finish demo with mocks only
7. **ST-6 gate**: demo passed at 0 real calls — Lite Plan intact

---

## How to Check Current Usage

```bash
# Start the server
uvicorn api.main:app --reload --port 8000

# Check budget (expects 0 in mock mode)
curl http://localhost:8000/health | python -m json.tool | grep api_calls
```

Expected (mock mode):
```json
"api_calls_used": 0,
"api_calls_budget": 100
```

---

## Live Activation (Post-Demo / Optional)

To switch to real IBM APIs (consumes real budget):

1. Copy `.env.example` to `.env`
2. Fill in `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `NLU_API_KEY`, `CLOUDANT_URL`, `CLOUDANT_API_KEY`
3. Set `USE_MOCK=False`
4. Restart the server
5. Run a single scenario — verify `api_calls_used` increments in `/health`
6. Record the call in this log immediately

> **Budget ceiling**: Stop at `api_calls_used = 8` to keep a 2-call safety margin.
