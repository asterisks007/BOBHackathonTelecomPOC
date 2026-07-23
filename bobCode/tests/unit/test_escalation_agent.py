"""
Unit tests for Agent 4 — Escalation Agent.
Gate: ≥40 tests. SLA target: <500ms. Zero external calls.
"""
import os, uuid
import pytest
os.environ["USE_MOCK"] = "true"

from agents.escalation_agent import EscalationAgent, _extract_affected_count, _ESCALATION_RULES
from api.models import AgentContext, AgentRequest, AgentStatus


def make_request(severity="P1", issue_type="fiber_cut", count=60000,
                 scope="~60k customers", with_upstream=True) -> AgentRequest:
    upstream = {}
    if with_upstream:
        upstream = {
            "intent_recognition": {"issue_type": issue_type, "priority": "Critical",
                                   "affected_count_estimate": count},
            "ticket_classification": {"severity": severity},
            "rca_analysis": {"estimated_scope": scope, "confidence": 0.88},
        }
    return AgentRequest(
        request_id=str(uuid.uuid4()), customer_id="CUST-ESC-001",
        payload={"message": "network outage", "severity": severity, "issue_type": issue_type},
        context=AgentContext(session_id="sess-esc", upstream_results=upstream),
    )


class TestExtractAffectedCount:
    def test_k_suffix(self):
        assert _extract_affected_count("~47k customers") == 47000

    def test_plain_number(self):
        assert _extract_affected_count("3 cell sites, ~50000 customers") == 50000

    def test_no_match_returns_zero(self):
        assert _extract_affected_count("scope unknown") == 0


class TestEscalationRules:
    def test_all_rules_have_level(self):
        for rule in _ESCALATION_RULES:
            assert "level" in rule

    def test_all_rules_have_notify(self):
        for rule in _ESCALATION_RULES:
            assert "notify" in rule and isinstance(rule["notify"], list)


class TestEscalationAgentProcess:
    @pytest.mark.asyncio
    async def test_p1_large_count_escalates_to_executive(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P1", count=60000, scope="~60k customers"))
        assert response.result["escalate"] is True
        assert response.result["escalation_level"] == "Executive"

    @pytest.mark.asyncio
    async def test_p1_small_count_escalates_to_management(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P1", count=5000, scope="~5k customers"))
        assert response.result["escalate"] is True
        assert response.result["escalation_level"] == "Management"

    @pytest.mark.asyncio
    async def test_p2_large_count_escalates_to_operational(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P2", count=15000, scope="~15k customers"))
        assert response.result["escalate"] is True
        assert response.result["escalation_level"] == "Operational"

    @pytest.mark.asyncio
    async def test_p3_no_escalation(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P3", count=500, scope="~500 customers"))
        assert response.result["escalate"] is False
        assert response.result["escalation_level"] == "None"

    @pytest.mark.asyncio
    async def test_p4_no_escalation(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P4", count=100, scope="~100 customers"))
        assert response.result["escalate"] is False

    @pytest.mark.asyncio
    async def test_required_fields_present(self):
        agent = EscalationAgent()
        response = await agent.process(make_request())
        for field in ("escalate", "escalation_level", "urgency", "notify", "reason"):
            assert field in response.result, f"Missing: {field}"

    @pytest.mark.asyncio
    async def test_notify_is_list(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P1"))
        assert isinstance(response.result["notify"], list)

    @pytest.mark.asyncio
    async def test_urgency_critical_for_p1(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P1"))
        assert response.result["urgency"] == "Critical"

    @pytest.mark.asyncio
    async def test_urgency_standard_for_p3(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P3", count=200, scope="~200 customers"))
        assert response.result["urgency"] == "Standard"

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self):
        agent = EscalationAgent()
        response = await agent.process(make_request())
        assert 0.0 <= response.result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_execution_time_within_sla(self):
        """Escalation SLA: <500ms"""
        agent = EscalationAgent()
        response = await agent.process(make_request())
        assert response.metadata.execution_time_ms < 500

    @pytest.mark.asyncio
    async def test_agent_name_correct(self):
        agent = EscalationAgent()
        response = await agent.process(make_request())
        assert response.agent_name == "escalation"

    @pytest.mark.asyncio
    async def test_no_upstream_still_works(self):
        agent = EscalationAgent()
        response = await agent.process(make_request(with_upstream=False))
        assert response.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)

    @pytest.mark.asyncio
    async def test_estimated_cost_present(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P1"))
        assert "estimated_cost" in response.result

    @pytest.mark.asyncio
    async def test_mock_used_flag_true(self):
        agent = EscalationAgent()
        response = await agent.process(make_request())
        assert response.metadata.mock_used is True

    @pytest.mark.asyncio
    async def test_sql_injection_rejected(self):
        req = AgentRequest(
            request_id=str(uuid.uuid4()), customer_id="CUST-ESC-001",
            payload={"message": "UNION SELECT * FROM audit_trail"},
            context=AgentContext(session_id="sess-esc"),
        )
        agent = EscalationAgent()
        response = await agent.process(req)
        assert response.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_p1_executive_notify_has_multiple_groups(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P1", count=60000))
        assert len(response.result["notify"]) >= 2

    @pytest.mark.asyncio
    async def test_affected_count_in_result(self):
        agent = EscalationAgent()
        response = await agent.process(make_request("P1", count=60000))
        assert "affected_count" in response.result

    @pytest.mark.asyncio
    async def test_request_id_echoed(self):
        agent = EscalationAgent()
        req = make_request()
        response = await agent.process(req)
        assert response.request_id == req.request_id
