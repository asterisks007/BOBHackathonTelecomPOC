"""
E2E smoke tests for the 3 judge demo scenarios.

All tests run 100% mocked (USE_MOCK=True) — safe for CI, zero real API calls.

Demo routes tested:
  POST /orchestrate        → OrchestrationResult (nested summaries)
  POST /webhook/orchestrate → WatsonSkillResponse (flat fields for judges)

Scenarios:
  A — '4G outage fiber cut New York' (P1, RCA fiber, escalated)
  B — 'Fiber cut 50k customers'      (P1, escalated, parallel analysis)
  C — 'Billing system down city-wide' (P1/P2, billing domain, resolution steps)

Gate: ST-6 — ≥5 smoke tests, all green, 0 real API calls.
"""

import os
import time
import uuid

import pytest

os.environ["USE_MOCK"] = "true"

from agents.rca_agent import RCAAgent
from core.cloudant_client import clear_mock_store, get_mock_store
from core.granite_client import GraniteClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_state():
    """Ensure clean state before every test — no cross-test bleed."""
    clear_mock_store()
    RCAAgent.clear_cache()
    GraniteClient.reset_call_count()
    yield
    clear_mock_store()
    RCAAgent.clear_cache()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _orchestrate(sync_client, message: str, customer_id: str = "DEMO-001") -> dict:
    """POST to /orchestrate and return parsed JSON."""
    resp = sync_client.post(
        "/orchestrate",
        json={
            "session_id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "message": message,
        },
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


def _webhook(sync_client, message: str, customer_id: str = "DEMO-001") -> dict:
    """POST to /webhook/orchestrate (WatsonSkillResponse flat schema)."""
    resp = sync_client.post(
        "/webhook/orchestrate",
        json={
            "session_id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "message": message,
        },
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


# ── Scenario A: 4G Outage / Fiber Cut P1 ─────────────────────────────────────

class TestScenarioA_FiberCutP1:
    """
    Scenario A — '4G outage in New York, fiber cut at junction box BX-42'
    Expected:
      - ticket_id starts with INC-
      - severity = P1
      - RCA root_cause mentions fiber / cut / route / repair
      - at least 1 resolution step
      - non-empty customer message
      - ticket written to Cloudant
      - zero real API calls
    """

    MSG = (
        "4G outage in New York sector north. Fiber cut at junction box BX-42. "
        "Approximately 47000 customers affected. Service completely down."
    )

    def test_a_orchestrate_returns_200(self, sync_client):
        """POST /orchestrate must return HTTP 200 for Scenario A."""
        resp = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "DEMO-A-001",
                "message": self.MSG,
            },
        )
        assert resp.status_code == 200

    def test_a_ticket_id_format(self, sync_client):
        """ticket_id in OrchestrationResult must follow INC- prefix."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-A-001")
        ticket_id = data.get("ticket_id") or ""
        assert ticket_id.startswith("INC-"), f"Unexpected ticket_id: {ticket_id!r}"

    def test_a_severity_is_p1(self, sync_client):
        """Fiber cut with 47 k customers must classify as P1."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-A-001")
        severity = (data.get("ticket_summary") or {}).get("severity")
        assert severity == "P1", f"Expected P1, got {severity!r}"

    def test_a_rca_mentions_fiber(self, sync_client):
        """RCA root cause must reference the fiber scenario."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-A-001")
        rca_text = (
            str((data.get("rca_summary") or {}).get("root_cause", "")).lower()
        )
        assert any(kw in rca_text for kw in ("fiber", "cut", "route", "junction", "repair")), (
            f"RCA should reference fiber root cause: {rca_text!r}"
        )

    def test_a_resolution_steps_present(self, sync_client):
        """At least one resolution step must be returned."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-A-001")
        steps = (data.get("resolution_summary") or {}).get("resolution_steps") or []
        assert len(steps) >= 1, "Expected ≥1 resolution step"

    def test_a_customer_message_non_empty(self, sync_client):
        """Customer-facing message must be non-empty and human-readable."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-A-001")
        msg = str((data.get("resolution_summary") or {}).get("customer_message", ""))
        assert len(msg) >= 20, f"Customer message too short: {msg!r}"

    def test_a_seven_agents_completed(self, sync_client):
        """All 7 agents must complete successfully for Scenario A."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-A-001")
        completed = data.get("agents_completed") or []
        failed = data.get("agents_failed") or []
        assert len(completed) == 7, f"Expected 7 completed, got {completed}"
        assert len(failed) == 0, f"Expected 0 failed, got {failed}"

    def test_a_ticket_written_to_cloudant_via_webhook(self, sync_client):
        """Webhook route must persist a ticket document to Cloudant mock store."""
        _webhook(sync_client, self.MSG, "DEMO-A-001")
        store = get_mock_store()
        assert "tickets" in store, "No 'tickets' collection in mock Cloudant store"
        assert len(store["tickets"]) >= 1, "No tickets written after Scenario A webhook"

    def test_a_no_pii_in_webhook_response(self, sync_client):
        """PII injected into message must not appear in webhook response body."""
        msg_pii = self.MSG + " Contact john.smith@telecom.com or call 555-099-8877."
        resp = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "DEMO-A-001",
                "message": msg_pii,
            },
        )
        assert resp.status_code == 200
        body = resp.text
        assert "555-099-8877" not in body, "Phone number leaked into response"
        assert "john.smith@telecom.com" not in body, "Email leaked into response"

    def test_a_zero_real_api_calls(self, sync_client):
        """Smoke test must consume zero real watsonx.ai API calls."""
        GraniteClient.reset_call_count()
        _orchestrate(sync_client, self.MSG, "DEMO-A-001")
        assert GraniteClient.get_real_call_count() == 0, (
            f"Real API call detected during mocked E2E: {GraniteClient.get_real_call_count()}"
        )


# ── Scenario B: Fiber Cut 50k Customers (Critical Escalation) ─────────────────

class TestScenarioB_FiberCut50k:
    """
    Scenario B — 'Fiber cut affecting 50000 customers. Critical emergency.'
    Expected: P1, escalated=True, parallel analysis present, latency <8s.
    """

    MSG = (
        "CRITICAL: Fiber cut affecting 50000 customers in the downtown district. "
        "Complete service outage. Emergency escalation required immediately."
    )

    def test_b_returns_200(self, sync_client):
        resp = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "DEMO-B-001",
                "message": self.MSG,
            },
        )
        assert resp.status_code == 200

    def test_b_severity_p1(self, sync_client):
        """Critical 50k-customer fiber cut must produce P1."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-B-001")
        severity = (data.get("ticket_summary") or {}).get("severity")
        assert severity == "P1", f"Expected P1, got {severity!r}"

    def test_b_escalated(self, sync_client):
        """P1 critical fiber cut must trigger escalation."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-B-001")
        escalation = data.get("escalation_summary") or {}
        assert escalation.get("escalate") is True, (
            f"Expected escalate=True, got escalation_summary={escalation}"
        )

    def test_b_parallel_analysis_present(self, sync_client):
        """analysis_summary (parallel agent) must be populated."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-B-001")
        analysis = data.get("analysis_summary") or {}
        assert len(analysis) >= 1, "Expected non-empty analysis_summary from parallel agent"

    def test_b_latency_under_8s(self, sync_client):
        """End-to-end orchestration must complete within 8 seconds (mocked)."""
        start = time.time()
        resp = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "DEMO-B-001",
                "message": self.MSG,
            },
        )
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 8.0, f"E2E latency {elapsed:.2f}s exceeds 8s target"

    def test_b_webhook_severity_p1(self, sync_client):
        """Webhook (WatsonSkillResponse) must also report P1 for Scenario B."""
        data = _webhook(sync_client, self.MSG, "DEMO-B-001")
        assert data.get("severity") == "P1", f"Webhook severity: {data.get('severity')!r}"

    def test_b_webhook_escalated(self, sync_client):
        """Webhook response must have escalated=True for P1 fiber cut."""
        data = _webhook(sync_client, self.MSG, "DEMO-B-001")
        assert data.get("escalated") is True, (
            f"Expected webhook escalated=True, got {data.get('escalated')}"
        )

    def test_b_execution_ms_in_result(self, sync_client):
        """total_execution_ms must be reported and non-negative."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-B-001")
        ms = data.get("total_execution_ms", -1)
        assert ms >= 0, f"total_execution_ms should be >= 0, got {ms}"


# ── Scenario C: Billing System Down City-Wide ─────────────────────────────────

class TestScenarioC_BillingOutage:
    """
    Scenario C — 'Billing system down city-wide, customers cannot pay bills'
    Expected: billing issue_type, P1/P2, RCA references billing root cause,
              resolution steps present, ticket_id INC- format.
    """

    MSG = (
        "Billing system down city-wide. Customers cannot pay their bills. "
        "Self-service portal unresponsive. New activations blocked. Affecting all customers."
    )

    def test_c_returns_200(self, sync_client):
        resp = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "DEMO-C-001",
                "message": self.MSG,
            },
        )
        assert resp.status_code == 200

    def test_c_billing_issue_type(self, sync_client):
        """Intent agent must recognise billing/application domain."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-C-001")
        issue = str((data.get("intent_summary") or {}).get("issue_type", "")).lower()
        assert any(kw in issue for kw in ("billing", "application", "service", "system", "outage")), (
            f"Unexpected issue_type for billing scenario: {issue!r}"
        )

    def test_c_severity_p1_or_p2(self, sync_client):
        """City-wide billing outage must be P1 or P2."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-C-001")
        severity = (data.get("ticket_summary") or {}).get("severity")
        assert severity in ("P1", "P2"), (
            f"Expected P1 or P2 for city-wide billing outage, got {severity!r}"
        )

    def test_c_rca_is_non_empty(self, sync_client):
        """RCA summary must produce a non-empty root cause string."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-C-001")
        rca_text = str((data.get("rca_summary") or {}).get("root_cause", ""))
        assert len(rca_text) >= 20, f"RCA root_cause too short: {rca_text!r}"

    def test_c_resolution_steps_non_empty(self, sync_client):
        """At least one actionable resolution step required."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-C-001")
        steps = (data.get("resolution_summary") or {}).get("resolution_steps") or []
        assert len(steps) >= 1, "Expected ≥1 resolution step for billing scenario"

    def test_c_ticket_id_format(self, sync_client):
        """Ticket ID must follow INC- prefix convention."""
        data = _orchestrate(sync_client, self.MSG, "DEMO-C-001")
        ticket_id = data.get("ticket_id") or ""
        assert ticket_id.startswith("INC-"), f"Unexpected ticket_id: {ticket_id!r}"

    def test_c_webhook_status_success(self, sync_client):
        """Webhook WatsonSkillResponse status must be 'success'."""
        data = _webhook(sync_client, self.MSG, "DEMO-C-001")
        assert data.get("status") == "success", f"Webhook status: {data.get('status')!r}"

    def test_c_webhook_resolution_steps_count(self, sync_client):
        """Webhook must report at least 1 resolution step in the count field."""
        data = _webhook(sync_client, self.MSG, "DEMO-C-001")
        count = data.get("resolution_steps_count", 0)
        assert count >= 1, f"Webhook resolution_steps_count should be ≥1, got {count}"

    def test_c_cloudant_ticket_has_no_pii(self, sync_client):
        """PII in customer message must not reach Cloudant ticket document."""
        msg_pii = self.MSG + " Ref: customer@example.com, account 555-111-2222."
        _webhook(sync_client, msg_pii, "DEMO-C-001")
        store = get_mock_store()
        ticket = list((store.get("tickets") or {}).values())[0]
        doc_str = str(ticket)
        assert "555-111-2222" not in doc_str, "Phone number found in Cloudant ticket"
        assert "customer@example.com" not in doc_str, "Email found in Cloudant ticket"


# ── Cross-Scenario: Budget & Security ────────────────────────────────────────

class TestBudgetAndSecurity:
    """Guards that must hold across all 3 demo scenarios."""

    SCENARIO_MESSAGES = [
        ("DEMO-BG-001", "4G outage fiber cut junction box BX-42 New York 47000 customers"),
        ("DEMO-BG-002", "Fiber cut 50000 customers critical emergency escalation required"),
        ("DEMO-BG-003", "Billing system down city-wide customers cannot pay portal down"),
    ]

    def test_zero_real_api_calls_across_all_three_scenarios(self, sync_client):
        """Running all 3 scenario messages must consume zero real Granite calls."""
        GraniteClient.reset_call_count()
        for cust_id, msg in self.SCENARIO_MESSAGES:
            sync_client.post(
                "/orchestrate",
                json={
                    "session_id": str(uuid.uuid4()),
                    "customer_id": cust_id,
                    "message": msg,
                },
            )
        assert GraniteClient.get_real_call_count() == 0, (
            f"Expected 0 real calls, got {GraniteClient.get_real_call_count()}"
        )

    def test_three_scenarios_complete_under_8s_total(self, sync_client):
        """All 3 demo scenarios combined must complete in under 8 seconds."""
        start = time.time()
        for cust_id, msg in self.SCENARIO_MESSAGES:
            resp = sync_client.post(
                "/orchestrate",
                json={
                    "session_id": str(uuid.uuid4()),
                    "customer_id": cust_id,
                    "message": msg,
                },
            )
            assert resp.status_code == 200
        elapsed = time.time() - start
        assert elapsed < 8.0, f"3 scenarios combined took {elapsed:.2f}s (>8s limit)"

    def test_health_reports_mock_mode(self, sync_client):
        """Health endpoint must confirm USE_MOCK=True in CI."""
        resp = sync_client.get("/health")
        assert resp.status_code == 200
        assert resp.json().get("use_mock") is True

    def test_health_api_calls_zero_after_mocked_runs(self, sync_client):
        """api_calls_used must remain 0 after mocked E2E runs."""
        GraniteClient.reset_call_count()
        _orchestrate(sync_client, "fiber cut outage 4G network down", "BUDGET-001")
        data = sync_client.get("/health").json()
        assert data.get("api_calls_used") == 0

    def test_all_scenarios_return_ticket_id(self, sync_client):
        """Every scenario must produce a ticket_id."""
        for cust_id, msg in self.SCENARIO_MESSAGES:
            data = _orchestrate(sync_client, msg, cust_id)
            ticket_id = data.get("ticket_id") or ""
            assert ticket_id.startswith("INC-"), (
                f"Missing/invalid ticket_id for '{msg[:40]}…': {ticket_id!r}"
            )

    def test_all_scenarios_have_seven_completed_agents(self, sync_client):
        """Each scenario must show exactly 7 agents completed, 0 failed."""
        for cust_id, msg in self.SCENARIO_MESSAGES:
            data = _orchestrate(sync_client, msg, cust_id)
            completed = data.get("agents_completed") or []
            failed = data.get("agents_failed") or []
            assert len(completed) == 7, (
                f"Expected 7 completed for '{msg[:40]}…', got {completed}"
            )
            assert len(failed) == 0, (
                f"Expected 0 failed for '{msg[:40]}…', got {failed}"
            )
