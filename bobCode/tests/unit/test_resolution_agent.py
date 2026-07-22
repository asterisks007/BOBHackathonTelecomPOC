"""
Unit tests for Agent 6 — Response Generation Agent.
Gate: ≥40 tests. SLA target: <1500ms. Zero real LLM calls.
"""
import os, uuid
import pytest
os.environ["USE_MOCK"] = "true"

from agents.resolution_agent import (
    ResolutionAgent, _RESOLUTION_TEMPLATES, _AUTOMATION_SCORES, _CUSTOMER_MESSAGE_TEMPLATE,
)
from api.models import AgentContext, AgentRequest, AgentStatus


def make_request(issue_type="fiber_cut", service="4G_LTE", severity="P1",
                 ticket_id="INC-2024-000001", eta=120, with_upstream=True) -> AgentRequest:
    upstream = {}
    if with_upstream:
        upstream = {
            "intent_recognition": {"issue_type": issue_type, "service": service,
                                   "priority": "Critical"},
            "ticket_classification": {"severity": severity, "ticket_id": ticket_id},
            "rca_analysis": {"root_cause": "Fiber cut at BX-42",
                             "estimated_resolution_minutes": eta, "confidence": 0.88},
            "escalation": {"escalate": True, "escalation_level": "Management"},
            "parallel_analysis": {"customer_impact": {"affected_customers": 47000}},
        }
    return AgentRequest(
        request_id=str(uuid.uuid4()), customer_id="CUST-RES-001",
        payload={"message": f"{issue_type} resolution needed", "issue_type": issue_type,
                 "service": service, "ticket_id": ticket_id},
        context=AgentContext(session_id="sess-res", upstream_results=upstream),
    )


class TestResolutionTemplates:
    def test_all_issue_types_have_steps(self):
        for k, v in _RESOLUTION_TEMPLATES.items():
            assert len(v) > 0

    def test_fiber_cut_has_bgp_step(self):
        steps = _RESOLUTION_TEMPLATES["fiber_cut"]
        assert any("BGP" in s or "backup" in s.lower() for s in steps)

    def test_dns_failure_has_disk_step(self):
        steps = _RESOLUTION_TEMPLATES["dns_failure"]
        assert any("disk" in s.lower() for s in steps)

    def test_steps_are_numbered(self):
        for issue_type, steps in _RESOLUTION_TEMPLATES.items():
            for i, step in enumerate(steps, 1):
                assert step.startswith(str(i)), f"{issue_type} step {i} missing number"


class TestAutomationScores:
    def test_dns_has_highest_automation(self):
        assert _AUTOMATION_SCORES["dns_failure"] >= 0.85

    def test_fiber_cut_has_low_automation(self):
        assert _AUTOMATION_SCORES["fiber_cut"] < 0.40

    def test_all_scores_in_range(self):
        for k, v in _AUTOMATION_SCORES.items():
            assert 0.0 <= v <= 1.0


class TestResolutionAgentProcess:
    @pytest.mark.asyncio
    async def test_fiber_cut_returns_success(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request("fiber_cut"))
        assert response.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_required_fields_present(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        for field in ("resolution_steps", "customer_message", "automation_score",
                      "automation_possible", "internal_notes", "estimated_resolution_time"):
            assert field in response.result, f"Missing: {field}"

    @pytest.mark.asyncio
    async def test_resolution_steps_is_list(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        assert isinstance(response.result["resolution_steps"], list)
        assert len(response.result["resolution_steps"]) > 0

    @pytest.mark.asyncio
    async def test_customer_message_is_nonempty(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        msg = response.result["customer_message"]
        assert isinstance(msg, str) and len(msg) > 20

    @pytest.mark.asyncio
    async def test_automation_score_in_range(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        assert 0.0 <= response.result["automation_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_dns_has_automation_possible_true(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request("dns_failure"))
        assert response.result["automation_possible"] is True

    @pytest.mark.asyncio
    async def test_fiber_cut_automation_possible_false(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request("fiber_cut"))
        assert response.result["automation_possible"] is False

    @pytest.mark.asyncio
    async def test_ticket_id_in_result(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request(ticket_id="INC-2024-TEST"))
        assert response.result["ticket_id"] == "INC-2024-TEST"

    @pytest.mark.asyncio
    async def test_estimated_resolution_time_from_rca(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request(eta=90))
        assert response.result["estimated_resolution_time"] == 90

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        assert 0.0 <= response.result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_execution_time_within_sla(self):
        """Response Generation SLA: <1500ms"""
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        assert response.metadata.execution_time_ms < 1500

    @pytest.mark.asyncio
    async def test_agent_name_correct(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        assert response.agent_name == "response_generation"

    @pytest.mark.asyncio
    async def test_pii_not_in_customer_message(self):
        agent = ResolutionAgent()
        req = make_request()
        req.payload["message"] = "fiber cut, call 555-012-3456 for updates"
        response = await agent.process(req)
        assert "555-012-3456" not in response.result.get("customer_message", "")

    @pytest.mark.asyncio
    async def test_sql_injection_rejected(self):
        req = AgentRequest(
            request_id=str(uuid.uuid4()), customer_id="CUST-RES-001",
            payload={"message": "SELECT * FROM resolution_steps"},
            context=AgentContext(session_id="sess-res"),
        )
        agent = ResolutionAgent()
        response = await agent.process(req)
        assert response.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_no_upstream_still_works(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request(with_upstream=False))
        assert response.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)

    @pytest.mark.asyncio
    async def test_internal_notes_present(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        notes = response.result["internal_notes"]
        assert isinstance(notes, str) and len(notes) > 10

    @pytest.mark.asyncio
    async def test_billing_resolution_steps_different_from_fiber(self):
        agent = ResolutionAgent()
        r_fiber = await agent.process(make_request("fiber_cut"))
        r_billing = await agent.process(make_request("billing_system_outage"))
        assert r_fiber.result["resolution_steps"] != r_billing.result["resolution_steps"]

    @pytest.mark.asyncio
    async def test_mock_used_flag_true(self):
        agent = ResolutionAgent()
        response = await agent.process(make_request())
        assert response.metadata.mock_used is True

    @pytest.mark.asyncio
    async def test_request_id_echoed(self):
        agent = ResolutionAgent()
        req = make_request()
        response = await agent.process(req)
        assert response.request_id == req.request_id
