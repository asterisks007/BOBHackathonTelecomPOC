"""
Unit tests for Agent 7 — Feedback Agent.
Gate: ≥40 tests. SLA target: <500ms. Async Cloudant write (mocked).
"""
import os, uuid
import pytest
os.environ["USE_MOCK"] = "true"

from agents.feedback_agent import (
    FeedbackAgent, _estimate_csat, _build_learning_points,
    _build_recommended_changes, _PREVENTIVE_ACTIONS, _CSAT_TABLE,
)
from core.cloudant_client import clear_mock_store, get_mock_store
from api.models import AgentContext, AgentRequest, AgentStatus


def make_request(issue_type="fiber_cut", severity="P1", sla_minutes=240,
                 eta=112, rca_confidence=0.88, escalation_level="Management",
                 ticket_id="INC-2024-000001", with_upstream=True) -> AgentRequest:
    upstream = {}
    if with_upstream:
        upstream = {
            "intent_recognition": {"issue_type": issue_type, "priority": "Critical"},
            "ticket_classification": {"severity": severity, "sla_minutes": sla_minutes,
                                      "ticket_id": ticket_id},
            "rca_analysis": {"confidence": rca_confidence,
                             "estimated_resolution_minutes": eta,
                             "root_cause": "Fiber cut at BX-42"},
            "escalation": {"escalation_level": escalation_level, "escalate": True},
            "parallel_analysis": {"customer_impact": {"affected_customers": 47000}},
        }
    return AgentRequest(
        request_id=str(uuid.uuid4()), customer_id="CUST-FB-001",
        payload={"message": "resolution feedback", "issue_type": issue_type,
                 "ticket_id": ticket_id},
        context=AgentContext(session_id="sess-fb", upstream_results=upstream),
    )


class TestEstimateCsat:
    def test_p1_executive_lowest_csat(self):
        assert _estimate_csat("P1", "Executive") < 3.0

    def test_p4_none_highest_csat(self):
        assert _estimate_csat("P4", "None") > 4.0

    def test_p3_no_escalation_good_csat(self):
        assert _estimate_csat("P3", "None") >= 4.0

    def test_unknown_combo_returns_default(self):
        score = _estimate_csat("P99", "Unknown")
        assert 1.0 <= score <= 5.0


class TestBuildLearningPoints:
    def test_high_rca_confidence_positive_note(self):
        points = _build_learning_points("fiber_cut", 0.90, 4.0, True)
        assert any("well-understood" in p for p in points)

    def test_low_rca_confidence_improvement_note(self):
        points = _build_learning_points("fiber_cut", 0.60, 4.0, True)
        assert any("enrich" in p.lower() for p in points)

    def test_sla_missed_adds_note(self):
        points = _build_learning_points("fiber_cut", 0.85, 4.0, False)
        assert any("SLA" in p for p in points)

    def test_low_csat_adds_communication_note(self):
        points = _build_learning_points("fiber_cut", 0.85, 2.9, True)
        assert any("communication" in p.lower() for p in points)

    def test_issue_type_logged_in_points(self):
        points = _build_learning_points("billing_system_outage", 0.85, 4.0, True)
        assert any("billing_system_outage" in p for p in points)


class TestBuildRecommendedChanges:
    def test_preventive_action_included(self):
        changes = _build_recommended_changes("fiber_cut", "None")
        assert len(changes) > 0

    def test_executive_escalation_triggers_matrix_review(self):
        changes = _build_recommended_changes("fiber_cut", "Executive")
        assert any("escalation matrix" in c.lower() for c in changes)

    def test_runbook_update_always_included(self):
        changes = _build_recommended_changes("signal_degradation", "None")
        assert any("runbook" in c.lower() for c in changes)


class TestPreventiveActions:
    def test_all_issue_types_have_actions(self):
        issue_types = ["fiber_cut", "signal_degradation", "core_network_failure",
                       "billing_system_outage", "backhaul_degradation", "dns_failure",
                       "power_failure", "capacity_exhaustion", "software_bug"]
        for it in issue_types:
            assert it in _PREVENTIVE_ACTIONS


class TestFeedbackAgentProcess:
    def setup_method(self):
        clear_mock_store()

    @pytest.mark.asyncio
    async def test_returns_success(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        assert response.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_required_fields_present(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        for field in ("resolution_effective", "customer_satisfaction", "sla_met",
                      "time_to_resolution", "preventive_action", "learning_points",
                      "recommended_changes"):
            assert field in response.result, f"Missing: {field}"

    @pytest.mark.asyncio
    async def test_csat_in_1_to_5_range(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        assert 1.0 <= response.result["customer_satisfaction"] <= 5.0

    @pytest.mark.asyncio
    async def test_sla_met_true_when_eta_within_sla(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request(eta=100, sla_minutes=240))
        assert response.result["sla_met"] is True

    @pytest.mark.asyncio
    async def test_sla_met_false_when_eta_exceeds_sla(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request(eta=300, sla_minutes=240))
        assert response.result["sla_met"] is False

    @pytest.mark.asyncio
    async def test_resolution_effective_true_for_high_rca_confidence(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request(rca_confidence=0.90))
        assert response.result["resolution_effective"] is True

    @pytest.mark.asyncio
    async def test_resolution_effective_false_for_low_rca_confidence(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request(rca_confidence=0.55))
        assert response.result["resolution_effective"] is False

    @pytest.mark.asyncio
    async def test_learning_points_is_list(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        assert isinstance(response.result["learning_points"], list)
        assert len(response.result["learning_points"]) > 0

    @pytest.mark.asyncio
    async def test_recommended_changes_is_list(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        assert isinstance(response.result["recommended_changes"], list)

    @pytest.mark.asyncio
    async def test_feedback_record_written_to_cloudant(self):
        agent = FeedbackAgent()
        await agent.process(make_request())
        store = get_mock_store()
        assert "audit_trail" in store
        records = list(store["audit_trail"].values())
        feedback_records = [r for r in records if r.get("type") == "feedback_record"]
        assert len(feedback_records) >= 1

    @pytest.mark.asyncio
    async def test_execution_time_within_sla(self):
        """Feedback SLA: <500ms"""
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        assert response.metadata.execution_time_ms < 500

    @pytest.mark.asyncio
    async def test_agent_name_correct(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        assert response.agent_name == "feedback"

    @pytest.mark.asyncio
    async def test_no_upstream_still_works(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request(with_upstream=False))
        assert response.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)

    @pytest.mark.asyncio
    async def test_sql_injection_rejected(self):
        req = AgentRequest(
            request_id=str(uuid.uuid4()), customer_id="CUST-FB-001",
            payload={"message": "DELETE FROM feedback WHERE 1=1"},
            context=AgentContext(session_id="sess-fb"),
        )
        agent = FeedbackAgent()
        response = await agent.process(req)
        assert response.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_mock_used_flag_true(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request())
        assert response.metadata.mock_used is True

    @pytest.mark.asyncio
    async def test_request_id_echoed(self):
        agent = FeedbackAgent()
        req = make_request()
        response = await agent.process(req)
        assert response.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_ticket_id_in_result(self):
        agent = FeedbackAgent()
        response = await agent.process(make_request(ticket_id="INC-2024-999999"))
        assert response.result["ticket_id"] == "INC-2024-999999"
