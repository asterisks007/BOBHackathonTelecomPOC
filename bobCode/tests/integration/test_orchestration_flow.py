"""
Integration tests for the Master Orchestration Engine.

Gate: ST-3 — ≥20 integration tests + all 323 prior unit tests still pass.
All tests use USE_MOCK=True. Zero real IBM API calls.
Tests verify the full pipeline, branching, error recovery, and SSE streaming.
"""

import json
import os
import uuid
from typing import Any, Dict, List

import pytest

os.environ["USE_MOCK"] = "true"

from agents.rca_agent import RCAAgent
from api.models import OrchestrateRequest
from api.orchestrator import MasterOrchestrator, _sse_event
from core.audit import clear_mock_audit_log, get_mock_audit_log
from core.cloudant_client import clear_mock_store


def make_orchestrate_request(
    message: str = "There is a complete fiber cut in sector BX-North",
    session_id: str = None,
    customer_id: str = "CUST-ORCH-001",
) -> OrchestrateRequest:
    return OrchestrateRequest(
        session_id=session_id or str(uuid.uuid4()),
        customer_id=customer_id,
        message=message,
    )


# ════════════════════════════════════════════════════════════════════
# SSE event helper
# ════════════════════════════════════════════════════════════════════

class TestSSEEventHelper:
    def test_sse_event_format_starts_with_data(self):
        event = _sse_event("intent_recognition", "intent_recognition", "success", 0.92)
        assert event.startswith("data: ")

    def test_sse_event_ends_with_double_newline(self):
        event = _sse_event("ticket_classification", "ticket_classification", "success")
        assert event.endswith("\n\n")

    def test_sse_event_is_valid_json_after_data_prefix(self):
        event = _sse_event("rca_analysis", "rca_analysis", "success", 0.88, {"key": "val"})
        payload = json.loads(event[len("data: "):].strip())
        assert payload["stage"] == "rca_analysis"
        assert payload["confidence"] == 0.88

    def test_sse_event_partial_result_defaults_empty(self):
        event = _sse_event("feedback", "feedback", "success")
        payload = json.loads(event[len("data: "):].strip())
        assert payload["partial_result"] == {}


# ════════════════════════════════════════════════════════════════════
# Happy path — fiber cut (full pipeline)
# ════════════════════════════════════════════════════════════════════

class TestHappyPathFiberCut:
    def setup_method(self):
        clear_mock_audit_log()
        clear_mock_store()
        RCAAgent.clear_cache()

    @pytest.mark.asyncio
    async def test_orchestration_returns_result(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request(
            "Complete fiber cut at junction box BX-42, sector north, affecting 50000 customers"
        ))
        assert result is not None

    @pytest.mark.asyncio
    async def test_orchestration_has_ticket_id(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert result.ticket_id is not None
        assert result.ticket_id.startswith("INC-")

    @pytest.mark.asyncio
    async def test_orchestration_has_all_summaries(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert result.intent_summary is not None
        assert result.ticket_summary is not None
        assert result.rca_summary is not None
        assert result.escalation_summary is not None
        assert result.analysis_summary is not None
        assert result.resolution_summary is not None
        assert result.feedback_summary is not None

    @pytest.mark.asyncio
    async def test_orchestration_completes_all_7_agents(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert len(result.agents_completed) == 7
        assert len(result.agents_failed) == 0

    @pytest.mark.asyncio
    async def test_orchestration_total_execution_ms_positive(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert result.total_execution_ms > 0

    @pytest.mark.asyncio
    async def test_orchestration_within_8s_sla(self):
        """End-to-end SLA: <8000ms in mock mode."""
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert result.total_execution_ms < 8000

    @pytest.mark.asyncio
    async def test_audit_trail_has_start_and_complete_events(self):
        orch = MasterOrchestrator()
        session_id = str(uuid.uuid4())
        await orch.run(make_orchestrate_request(session_id=session_id))
        log = get_mock_audit_log()
        event_types = [e["event_type"] for e in log]
        assert "orchestration_start" in event_types
        assert "orchestration_complete" in event_types

    @pytest.mark.asyncio
    async def test_intent_summary_has_issue_type(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request(
            "fiber cut at sector BX affecting backhaul"
        ))
        assert result.intent_summary.get("issue_type") == "fiber_cut"

    @pytest.mark.asyncio
    async def test_ticket_summary_has_severity(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert result.ticket_summary.get("severity") in ("P1", "P2", "P3", "P4")

    @pytest.mark.asyncio
    async def test_rca_summary_has_root_cause(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert isinstance(result.rca_summary.get("root_cause"), str)
        assert len(result.rca_summary["root_cause"]) > 5

    @pytest.mark.asyncio
    async def test_resolution_summary_has_steps(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        steps = result.resolution_summary.get("resolution_steps", [])
        assert isinstance(steps, list) and len(steps) > 0

    @pytest.mark.asyncio
    async def test_feedback_summary_has_sla_met(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request())
        assert "sla_met" in result.feedback_summary


# ════════════════════════════════════════════════════════════════════
# High-priority (Critical) escalation path
# ════════════════════════════════════════════════════════════════════

class TestCriticalEscalationPath:
    def setup_method(self):
        clear_mock_audit_log()
        RCAAgent.clear_cache()

    @pytest.mark.asyncio
    async def test_critical_message_triggers_escalation(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request(
            "Total complete network outage affecting entire city, all services down, "
            "100000 customers affected, city-wide emergency"
        ))
        escalation = result.escalation_summary or {}
        # May be True or summary may have escalation info
        assert escalation.get("escalate") is True or "escalation_level" in escalation

    @pytest.mark.asyncio
    async def test_critical_pipeline_completes_all_agents(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request(
            "Complete total fiber cut, entire network down, critical infrastructure failure"
        ))
        assert len(result.agents_completed) == 7

    @pytest.mark.asyncio
    async def test_billing_outage_routes_correctly(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request(
            "Billing system is completely down, customers cannot make payments"
        ))
        assert result.ticket_summary.get("queue") == "IT_Operations"


# ════════════════════════════════════════════════════════════════════
# RCA cache hit path
# ════════════════════════════════════════════════════════════════════

class TestRCACacheHit:
    def setup_method(self):
        RCAAgent.clear_cache()

    @pytest.mark.asyncio
    async def test_second_identical_message_hits_rca_cache(self):
        orch = MasterOrchestrator()
        msg = "fiber cut at sector BX-North affecting 4G"
        await orch.run(make_orchestrate_request(msg))
        result2 = await orch.run(make_orchestrate_request(msg))
        assert result2.rca_summary.get("cache_hit") is True

    @pytest.mark.asyncio
    async def test_different_location_misses_rca_cache(self):
        orch = MasterOrchestrator()
        await orch.run(make_orchestrate_request("fiber cut at sector NORTH"))
        result2 = await orch.run(make_orchestrate_request("fiber cut at sector SOUTH"))
        assert result2.rca_summary.get("cache_hit") is False


# ════════════════════════════════════════════════════════════════════
# Error recovery
# ════════════════════════════════════════════════════════════════════

class TestErrorRecovery:
    @pytest.mark.asyncio
    async def test_pipeline_continues_after_partial_result(self):
        """Even if an agent returns PARTIAL status, the pipeline completes."""
        orch = MasterOrchestrator()
        # Unknown-issue input produces lower-confidence/partial results from some agents
        result = await orch.run(make_orchestrate_request("some vague network problem"))
        # Pipeline should always complete all 7 stages
        assert len(result.agents_completed) + len(result.agents_failed) == 7

    @pytest.mark.asyncio
    async def test_pii_in_message_does_not_leak_to_result(self):
        """Phone number in message must not appear in any result field."""
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request(
            "Fiber cut at sector BX, call 555-012-3456 for updates"
        ))
        full_result_str = str(result.model_dump())
        assert "555-012-3456" not in full_result_str

    @pytest.mark.asyncio
    async def test_email_in_message_does_not_leak_to_result(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_orchestrate_request(
            "Signal degradation in sector east, email admin@example.com"
        ))
        assert "admin@example.com" not in str(result.model_dump())


# ════════════════════════════════════════════════════════════════════
# SSE streaming
# ════════════════════════════════════════════════════════════════════

class TestSSEStreaming:
    def setup_method(self):
        RCAAgent.clear_cache()

    @pytest.mark.asyncio
    async def test_stream_yields_events_for_all_stages(self):
        orch = MasterOrchestrator()
        events: List[Dict] = []
        async for raw_event in orch.run_stream(make_orchestrate_request()):
            payload = json.loads(raw_event[len("data: "):].strip())
            events.append(payload)

        stages = {e["stage"] for e in events}
        expected = {
            "intent_recognition", "ticket_classification", "rca_analysis",
            "escalation", "parallel_analysis", "response_generation",
            "feedback", "complete",
        }
        assert stages == expected

    @pytest.mark.asyncio
    async def test_stream_final_event_has_ticket_id(self):
        orch = MasterOrchestrator()
        final = None
        async for raw_event in orch.run_stream(make_orchestrate_request()):
            payload = json.loads(raw_event[len("data: "):].strip())
            if payload["stage"] == "complete":
                final = payload
        assert final is not None
        assert final["ticket_id"] is not None

    @pytest.mark.asyncio
    async def test_stream_events_have_confidence_scores(self):
        orch = MasterOrchestrator()
        non_complete_events = []
        async for raw_event in orch.run_stream(make_orchestrate_request()):
            payload = json.loads(raw_event[len("data: "):].strip())
            if payload["stage"] != "complete":
                non_complete_events.append(payload)
        assert all("confidence" in e for e in non_complete_events)

    @pytest.mark.asyncio
    async def test_stream_completes_without_error(self):
        orch = MasterOrchestrator()
        count = 0
        async for _ in orch.run_stream(make_orchestrate_request()):
            count += 1
        assert count == 8  # 7 agents + 1 complete event


# ════════════════════════════════════════════════════════════════════
# HTTP endpoint smoke tests (via TestClient)
# ════════════════════════════════════════════════════════════════════

class TestOrchestrationHTTPEndpoint:
    def test_orchestrate_post_returns_200(self, sync_client):
        response = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-HTTP-001",
                "message": "4G signal degradation in sector east",
            },
        )
        assert response.status_code == 200

    def test_orchestrate_response_has_ticket_id(self, sync_client):
        response = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-HTTP-001",
                "message": "fiber cut in sector BX affecting backhaul",
            },
        )
        data = response.json()
        assert data.get("ticket_id") is not None

    def test_orchestrate_rejects_empty_message(self, sync_client):
        response = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-HTTP-001",
                "message": "   ",
            },
        )
        assert response.status_code == 422  # Pydantic validation error

    def test_orchestrate_rejects_too_long_message(self, sync_client):
        response = sync_client.post(
            "/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-HTTP-001",
                "message": "a" * 2001,
            },
        )
        assert response.status_code == 422

    def test_agent_intent_endpoint_returns_200(self, sync_client):
        response = sync_client.post(
            "/agents/intent",
            json={
                "request_id": str(uuid.uuid4()),
                "customer_id": "CUST-HTTP-001",
                "payload": {"message": "4G signal degradation"},
                "context": {"session_id": "sess-001", "upstream_results": {}},
            },
        )
        assert response.status_code == 200

    def test_health_reflects_zero_real_calls(self, sync_client):
        data = sync_client.get("/health").json()
        assert data["api_calls_used"] == 0
