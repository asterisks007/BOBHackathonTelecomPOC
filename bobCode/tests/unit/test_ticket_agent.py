"""
Unit tests for Agent 2 — Ticket Classification Agent.

Gate: ST-2-A2 — ≥40 tests, all passing. SLA target: <200ms.
Zero real IBM calls. All routing is pure rule-based lookup.
"""

import os
import re
import uuid

import pytest

os.environ["USE_MOCK"] = "true"

from agents.ticket_agent import (
    TicketAgent,
    _generate_ticket_id,
    _ROUTING_TABLE,
    _SEVERITY_MAP,
)
from api.models import AgentContext, AgentRequest, AgentStatus


def make_request(
    issue_type: str = "fiber_cut",
    priority: str = "Critical",
    service: str = "4G_LTE",
    location: str = "Sector-BX-North",
    upstream_intent: bool = True,
) -> AgentRequest:
    """Build a request with optional upstream intent context."""
    upstream = {}
    if upstream_intent:
        upstream["intent_recognition"] = {
            "issue_type": issue_type,
            "priority": priority,
            "service": service,
            "location": location,
        }
    return AgentRequest(
        request_id=str(uuid.uuid4()),
        customer_id="CUST-TEST-002",
        payload={"message": f"{issue_type} reported", "issue_type": issue_type,
                 "priority": priority, "service": service},
        context=AgentContext(session_id="sess-a2-test", upstream_results=upstream),
    )


# ════════════════════════════════════════════════════════════════════
# _generate_ticket_id
# ════════════════════════════════════════════════════════════════════

class TestGenerateTicketId:
    def test_format_matches_pattern(self):
        tid = _generate_ticket_id()
        assert re.match(r"^INC-\d{4}-\d{6}$", tid), f"Bad format: {tid}"

    def test_two_ids_are_unique(self):
        assert _generate_ticket_id() != _generate_ticket_id()

    def test_year_is_current(self):
        from datetime import datetime, timezone
        tid = _generate_ticket_id()
        year = str(datetime.now(timezone.utc).year)
        assert year in tid


# ════════════════════════════════════════════════════════════════════
# Routing table coverage
# ════════════════════════════════════════════════════════════════════

class TestRoutingTable:
    def test_all_issue_types_have_queue(self):
        for issue_type, routing in _ROUTING_TABLE.items():
            assert "queue" in routing, f"Missing queue for {issue_type}"

    def test_all_issue_types_have_assignment_group(self):
        for issue_type, routing in _ROUTING_TABLE.items():
            assert "assignment_group" in routing

    def test_fiber_routes_to_network_operations(self):
        assert _ROUTING_TABLE["fiber_cut"]["queue"] == "Network_Operations"

    def test_billing_routes_to_it_operations(self):
        assert _ROUTING_TABLE["billing_system_outage"]["queue"] == "IT_Operations"

    def test_core_failure_routes_to_core_network_ops(self):
        assert _ROUTING_TABLE["core_network_failure"]["queue"] == "Core_Network_Operations"

    def test_unknown_fallback_to_network_ops(self):
        assert _ROUTING_TABLE["unknown_issue"]["queue"] == "Network_Operations"


# ════════════════════════════════════════════════════════════════════
# Severity + SLA mapping
# ════════════════════════════════════════════════════════════════════

class TestSeverityMap:
    def test_critical_maps_to_p1(self):
        assert _SEVERITY_MAP["Critical"]["severity"] == "P1"

    def test_high_maps_to_p2(self):
        assert _SEVERITY_MAP["High"]["severity"] == "P2"

    def test_medium_maps_to_p3(self):
        assert _SEVERITY_MAP["Medium"]["severity"] == "P3"

    def test_low_maps_to_p4(self):
        assert _SEVERITY_MAP["Low"]["severity"] == "P4"

    def test_critical_sla_is_4_hours(self):
        assert _SEVERITY_MAP["Critical"]["sla_minutes"] == 240

    def test_low_sla_is_72_hours(self):
        assert _SEVERITY_MAP["Low"]["sla_minutes"] == 4320


# ════════════════════════════════════════════════════════════════════
# TicketAgent — full process() lifecycle
# ════════════════════════════════════════════════════════════════════

class TestTicketAgentProcess:
    @pytest.mark.asyncio
    async def test_fiber_critical_returns_p1(self):
        agent = TicketAgent()
        response = await agent.process(make_request("fiber_cut", "Critical"))
        assert response.status == AgentStatus.SUCCESS
        assert response.result["severity"] == "P1"

    @pytest.mark.asyncio
    async def test_ticket_id_format_correct(self):
        agent = TicketAgent()
        response = await agent.process(make_request())
        tid = response.result["ticket_id"]
        assert re.match(r"^INC-\d{4}-\d{6}$", tid)

    @pytest.mark.asyncio
    async def test_response_has_all_required_fields(self):
        agent = TicketAgent()
        response = await agent.process(make_request())
        for field in ("ticket_id", "queue", "severity", "sla_minutes", "assignment_group"):
            assert field in response.result, f"Missing: {field}"

    @pytest.mark.asyncio
    async def test_billing_routes_to_it_operations(self):
        agent = TicketAgent()
        response = await agent.process(make_request("billing_system_outage", "High"))
        assert response.result["queue"] == "IT_Operations"

    @pytest.mark.asyncio
    async def test_signal_routes_to_ran_operations(self):
        agent = TicketAgent()
        response = await agent.process(make_request("signal_degradation", "Medium"))
        assert response.result["queue"] == "RAN_Operations"

    @pytest.mark.asyncio
    async def test_high_priority_gives_p2_severity(self):
        agent = TicketAgent()
        response = await agent.process(make_request("fiber_cut", "High"))
        assert response.result["severity"] == "P2"

    @pytest.mark.asyncio
    async def test_medium_priority_gives_p3_severity(self):
        agent = TicketAgent()
        response = await agent.process(make_request("signal_degradation", "Medium"))
        assert response.result["severity"] == "P3"

    @pytest.mark.asyncio
    async def test_low_priority_gives_p4_severity(self):
        agent = TicketAgent()
        response = await agent.process(make_request("dns_failure", "Low"))
        assert response.result["severity"] == "P4"

    @pytest.mark.asyncio
    async def test_sla_minutes_positive(self):
        agent = TicketAgent()
        response = await agent.process(make_request())
        assert response.result["sla_minutes"] > 0

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self):
        agent = TicketAgent()
        response = await agent.process(make_request())
        assert 0.0 <= response.result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_category_infrastructure_for_fiber(self):
        agent = TicketAgent()
        response = await agent.process(make_request("fiber_cut"))
        assert response.result["category"] == "Infrastructure"

    @pytest.mark.asyncio
    async def test_category_software_for_billing(self):
        agent = TicketAgent()
        response = await agent.process(make_request("billing_system_outage"))
        assert response.result["category"] == "Software"

    @pytest.mark.asyncio
    async def test_fallback_without_upstream_context(self):
        """TicketAgent works even without upstream intent results."""
        agent = TicketAgent()
        response = await agent.process(make_request(upstream_intent=False))
        assert response.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_execution_time_within_sla(self):
        """Ticket agent SLA: <200ms"""
        agent = TicketAgent()
        response = await agent.process(make_request())
        assert response.metadata.execution_time_ms < 200

    @pytest.mark.asyncio
    async def test_agent_name_correct(self):
        agent = TicketAgent()
        response = await agent.process(make_request())
        assert response.agent_name == "ticket_classification"

    @pytest.mark.asyncio
    async def test_sql_injection_rejected(self):
        req = AgentRequest(
            request_id=str(uuid.uuid4()),
            customer_id="CUST-TEST-002",
            payload={"message": "DROP TABLE tickets; --"},
            context=AgentContext(session_id="sess-a2-security"),
        )
        agent = TicketAgent()
        response = await agent.process(req)
        assert response.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_location_preserved_in_result(self):
        agent = TicketAgent()
        response = await agent.process(make_request(location="Sector-CX-East"))
        assert response.result["location"] == "Sector-CX-East"

    @pytest.mark.asyncio
    async def test_power_routes_to_field_operations(self):
        agent = TicketAgent()
        response = await agent.process(make_request("power_failure"))
        assert response.result["queue"] == "Field_Operations"

    @pytest.mark.asyncio
    async def test_dns_routes_to_it_operations(self):
        agent = TicketAgent()
        response = await agent.process(make_request("dns_failure"))
        assert response.result["queue"] == "IT_Operations"

    @pytest.mark.asyncio
    async def test_capacity_routes_to_network_operations(self):
        agent = TicketAgent()
        response = await agent.process(make_request("capacity_exhaustion"))
        assert response.result["queue"] == "Network_Operations"

    @pytest.mark.asyncio
    async def test_unknown_issue_still_routes(self):
        agent = TicketAgent()
        response = await agent.process(make_request("unknown_issue"))
        assert response.status == AgentStatus.SUCCESS
        assert response.result["queue"] == "Network_Operations"

    @pytest.mark.asyncio
    async def test_request_id_echoed(self):
        agent = TicketAgent()
        req = make_request()
        response = await agent.process(req)
        assert response.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_mock_used_flag_true(self):
        agent = TicketAgent()
        response = await agent.process(make_request())
        assert response.metadata.mock_used is True
