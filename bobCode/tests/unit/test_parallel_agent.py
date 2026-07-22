"""
Unit tests for Agent 5 — Parallel Analysis Agent.
Gate: ≥40 tests. SLA target: <1s. Async queries via mocked CloudantClient.
"""
import os, uuid
import pytest
os.environ["USE_MOCK"] = "true"

from agents.parallel_agent import (
    ParallelAgent, _get_customer_data, _get_network_data, _get_operational_data,
    _CUSTOMER_IMPACT_TABLE, _NETWORK_IMPACT_TABLE, _OPERATIONAL_IMPACT_TABLE,
)
from core.cloudant_client import CloudantClient
from api.models import AgentContext, AgentRequest, AgentStatus


def make_request(issue_type="fiber_cut", severity="P1", with_upstream=True) -> AgentRequest:
    upstream = {}
    if with_upstream:
        upstream = {
            "intent_recognition": {"issue_type": issue_type, "priority": "Critical",
                                   "affected_count_estimate": 47000},
            "ticket_classification": {"severity": severity},
        }
    return AgentRequest(
        request_id=str(uuid.uuid4()), customer_id="CUST-PA-001",
        payload={"message": f"{issue_type} analysis", "issue_type": issue_type},
        context=AgentContext(session_id="sess-pa", upstream_results=upstream),
    )


class TestCustomerImpactTable:
    def test_all_issue_types_have_base_customers(self):
        for k, v in _CUSTOMER_IMPACT_TABLE.items():
            assert "base_customers" in v

    def test_fiber_cut_customer_count_significant(self):
        assert _CUSTOMER_IMPACT_TABLE["fiber_cut"]["base_customers"] > 0

    def test_revenue_impact_is_string(self):
        for v in _CUSTOMER_IMPACT_TABLE.values():
            assert isinstance(v["revenue_per_min"], str)


class TestNetworkImpactTable:
    def test_all_have_sites(self):
        for k, v in _NETWORK_IMPACT_TABLE.items():
            assert "sites" in v

    def test_power_failure_100_pct_traffic_loss(self):
        assert _NETWORK_IMPACT_TABLE["power_failure"]["traffic_loss"] == "100%"

    def test_billing_no_site_impact(self):
        assert _NETWORK_IMPACT_TABLE["billing_system_outage"]["sites"] == 0


class TestOperationalImpactTable:
    def test_all_have_risk_level(self):
        for k, v in _OPERATIONAL_IMPACT_TABLE.items():
            assert "risk" in v

    def test_fiber_cut_high_risk(self):
        assert _OPERATIONAL_IMPACT_TABLE["fiber_cut"]["risk"] == "High"

    def test_tools_is_list(self):
        for v in _OPERATIONAL_IMPACT_TABLE.values():
            assert isinstance(v["tools"], list)


class TestAsyncQueryHelpers:
    @pytest.mark.asyncio
    async def test_get_customer_data_returns_dict(self):
        client = CloudantClient(use_mock=True)
        result = await _get_customer_data(client, "fiber_cut")
        assert "affected_customers" in result
        assert "revenue_impact" in result

    @pytest.mark.asyncio
    async def test_get_network_data_returns_dict(self):
        client = CloudantClient(use_mock=True)
        result = await _get_network_data(client, "fiber_cut")
        assert "affected_sites" in result
        assert "traffic_loss" in result

    @pytest.mark.asyncio
    async def test_get_operational_data_returns_dict(self):
        result = await _get_operational_data("fiber_cut")
        assert "team_hours" in result
        assert "tools_required" in result
        assert "risk_level" in result


class TestParallelAgentProcess:
    @pytest.mark.asyncio
    async def test_fiber_cut_returns_success(self):
        agent = ParallelAgent()
        response = await agent.process(make_request("fiber_cut"))
        assert response.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_required_fields_present(self):
        agent = ParallelAgent()
        response = await agent.process(make_request())
        for field in ("customer_impact", "network_impact", "operational_impact"):
            assert field in response.result, f"Missing: {field}"

    @pytest.mark.asyncio
    async def test_customer_impact_has_subfields(self):
        agent = ParallelAgent()
        response = await agent.process(make_request())
        ci = response.result["customer_impact"]
        for field in ("affected_customers", "affected_percentage", "revenue_impact"):
            assert field in ci

    @pytest.mark.asyncio
    async def test_network_impact_has_subfields(self):
        agent = ParallelAgent()
        response = await agent.process(make_request())
        ni = response.result["network_impact"]
        for field in ("affected_sites", "traffic_loss", "latency_increase_ms"):
            assert field in ni

    @pytest.mark.asyncio
    async def test_operational_impact_has_subfields(self):
        agent = ParallelAgent()
        response = await agent.process(make_request())
        oi = response.result["operational_impact"]
        for field in ("team_hours", "tools_required", "risk_level"):
            assert field in oi

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self):
        agent = ParallelAgent()
        response = await agent.process(make_request())
        assert 0.0 <= response.result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_execution_time_within_sla(self):
        """Parallel agent SLA: <1000ms"""
        agent = ParallelAgent()
        response = await agent.process(make_request())
        assert response.metadata.execution_time_ms < 1000

    @pytest.mark.asyncio
    async def test_agent_name_correct(self):
        agent = ParallelAgent()
        response = await agent.process(make_request())
        assert response.agent_name == "parallel_analysis"

    @pytest.mark.asyncio
    async def test_billing_outage_no_site_impact(self):
        agent = ParallelAgent()
        response = await agent.process(make_request("billing_system_outage"))
        assert response.result["network_impact"]["affected_sites"] == 0

    @pytest.mark.asyncio
    async def test_fiber_cut_high_risk(self):
        agent = ParallelAgent()
        response = await agent.process(make_request("fiber_cut"))
        assert response.result["operational_impact"]["risk_level"] == "High"

    @pytest.mark.asyncio
    async def test_no_upstream_still_works(self):
        agent = ParallelAgent()
        response = await agent.process(make_request(with_upstream=False))
        assert response.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)

    @pytest.mark.asyncio
    async def test_sql_injection_rejected(self):
        req = AgentRequest(
            request_id=str(uuid.uuid4()), customer_id="CUST-PA-001",
            payload={"message": "INSERT INTO incidents VALUES (1)"},
            context=AgentContext(session_id="sess-pa"),
        )
        agent = ParallelAgent()
        response = await agent.process(req)
        assert response.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_mock_used_flag_true(self):
        agent = ParallelAgent()
        response = await agent.process(make_request())
        assert response.metadata.mock_used is True

    @pytest.mark.asyncio
    async def test_request_id_echoed(self):
        agent = ParallelAgent()
        req = make_request()
        response = await agent.process(req)
        assert response.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_dns_failure_high_latency_impact(self):
        agent = ParallelAgent()
        response = await agent.process(make_request("dns_failure"))
        assert response.result["network_impact"]["latency_increase_ms"] > 100
