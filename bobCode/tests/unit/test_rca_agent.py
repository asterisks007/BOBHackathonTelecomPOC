"""
Unit tests for Agent 3 — RCA Agent.
Gate: ≥40 tests. SLA target: <2s. Zero real LLM calls.
"""
import os, uuid
import pytest
os.environ["USE_MOCK"] = "true"

from agents.rca_agent import RCAAgent, _cache_key, _build_llm_prompt, _extract_evidence
from api.models import AgentContext, AgentRequest, AgentStatus


def make_request(issue_type="fiber_cut", service="4G_LTE", location="Sector-BX-North",
                 severity="P1", with_upstream=True) -> AgentRequest:
    upstream = {}
    if with_upstream:
        upstream = {
            "intent_recognition": {"issue_type": issue_type, "service": service,
                                   "location": location, "priority": "Critical"},
            "ticket_classification": {"severity": severity, "ticket_id": "INC-2024-000001"},
        }
    return AgentRequest(
        request_id=str(uuid.uuid4()), customer_id="CUST-RCA-001",
        payload={"message": f"{issue_type} at {location}", "issue_type": issue_type,
                 "service": service, "location": location},
        context=AgentContext(session_id="sess-rca", upstream_results=upstream),
    )


class TestRCACacheKey:
    def test_same_inputs_same_key(self):
        assert _cache_key("fiber_cut", "Sector-BX") == _cache_key("fiber_cut", "Sector-BX")

    def test_different_location_different_key(self):
        assert _cache_key("fiber_cut", "North") != _cache_key("fiber_cut", "South")

    def test_case_insensitive(self):
        assert _cache_key("FIBER_CUT", "SECTOR-BX") == _cache_key("fiber_cut", "sector-bx")


class TestBuildLLMPrompt:
    def test_prompt_contains_issue_type(self):
        prompt = _build_llm_prompt("fiber_cut", "4G_LTE", "Sector-BX", [])
        assert "fiber_cut" in prompt

    def test_prompt_no_similar_docs_has_fallback(self):
        prompt = _build_llm_prompt("fiber_cut", "4G", "Sector-BX", [])
        assert "No similar incidents" in prompt

    def test_prompt_uses_at_most_3_docs(self):
        docs = [{"document": f"doc {i}"*10, "id": f"INC-{i}", "metadata": {}} for i in range(5)]
        prompt = _build_llm_prompt("fiber_cut", "4G", "BX", docs)
        # Only top-3 docs included — fourth doc text should not appear
        assert "doc 3" not in prompt or prompt.count("doc ") <= 3


class TestExtractEvidence:
    def test_returns_list(self):
        result = _extract_evidence([], "fiber_cut")
        assert isinstance(result, list) and len(result) > 0

    def test_matching_type_included(self):
        docs = [{"id": "INC-001", "document": "fiber cut",
                 "metadata": {"type": "fiber_cut", "severity": "P1", "mttr_minutes": 112}}]
        ev = _extract_evidence(docs, "fiber_cut")
        assert any("fiber_cut" in e for e in ev)

    def test_non_matching_type_gives_fallback(self):
        docs = [{"id": "INC-002", "document": "signal",
                 "metadata": {"type": "signal_degradation", "severity": "P2", "mttr_minutes": 45}}]
        ev = _extract_evidence(docs, "fiber_cut")
        assert len(ev) > 0  # fallback line


class TestRCAAgentProcess:
    def setup_method(self):
        RCAAgent.clear_cache()

    @pytest.mark.asyncio
    async def test_fiber_cut_returns_success(self):
        agent = RCAAgent()
        response = await agent.process(make_request("fiber_cut"))
        assert response.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_required_fields_present(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        for field in ("root_cause", "recommendation", "confidence", "evidence",
                      "estimated_resolution_minutes", "similar_incidents"):
            assert field in response.result, f"Missing: {field}"

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert 0.0 <= response.result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_evidence_is_list(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert isinstance(response.result["evidence"], list)

    @pytest.mark.asyncio
    async def test_similar_incidents_is_list(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert isinstance(response.result["similar_incidents"], list)

    @pytest.mark.asyncio
    async def test_root_cause_is_nonempty_string(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert isinstance(response.result["root_cause"], str)
        assert len(response.result["root_cause"]) > 10

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_identical_call(self):
        agent = RCAAgent()
        await agent.process(make_request("fiber_cut", location="Sector-BX-North"))
        response2 = await agent.process(make_request("fiber_cut", location="Sector-BX-North"))
        assert response2.result.get("cache_hit") is True

    @pytest.mark.asyncio
    async def test_cache_miss_on_different_location(self):
        agent = RCAAgent()
        await agent.process(make_request("fiber_cut", location="North"))
        response2 = await agent.process(make_request("fiber_cut", location="South"))
        assert response2.result.get("cache_hit") is False

    @pytest.mark.asyncio
    async def test_estimated_resolution_minutes_positive(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert response.result["estimated_resolution_minutes"] > 0

    @pytest.mark.asyncio
    async def test_execution_time_within_sla(self):
        """RCA SLA: <2000ms"""
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert response.metadata.execution_time_ms < 2000

    @pytest.mark.asyncio
    async def test_agent_name_correct(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert response.agent_name == "rca_analysis"

    @pytest.mark.asyncio
    async def test_pii_not_in_output(self):
        agent = RCAAgent()
        req = make_request()
        req.payload["message"] = "fiber cut, contact 555-012-3456 for info"
        response = await agent.process(req)
        assert "555-012-3456" not in str(response.result)

    @pytest.mark.asyncio
    async def test_sql_injection_rejected(self):
        agent = RCAAgent()
        req = AgentRequest(
            request_id=str(uuid.uuid4()), customer_id="CUST-RCA-001",
            payload={"message": "DROP TABLE incidents"},
            context=AgentContext(session_id="sess-rca"),
        )
        response = await agent.process(req)
        assert response.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_no_upstream_context_still_works(self):
        agent = RCAAgent()
        response = await agent.process(make_request(with_upstream=False))
        assert response.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)

    @pytest.mark.asyncio
    async def test_mock_used_flag_true(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert response.metadata.mock_used is True

    @pytest.mark.asyncio
    async def test_billing_rca_returns_success(self):
        agent = RCAAgent()
        response = await agent.process(make_request("billing_system_outage"))
        assert response.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_estimated_scope_in_result(self):
        agent = RCAAgent()
        response = await agent.process(make_request())
        assert "estimated_scope" in response.result

    @pytest.mark.asyncio
    async def test_request_id_echoed(self):
        agent = RCAAgent()
        req = make_request()
        response = await agent.process(req)
        assert response.request_id == req.request_id
