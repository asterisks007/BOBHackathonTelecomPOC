"""
Integration tests — error recovery and RAG pipeline quality.
"""
import os, uuid, json
import pytest
os.environ["USE_MOCK"] = "true"

from api.models import OrchestrateRequest
from api.orchestrator import MasterOrchestrator
from agents.rca_agent import RCAAgent
from core.audit import clear_mock_audit_log
from core.cloudant_client import clear_mock_store


def make_req(message: str) -> OrchestrateRequest:
    return OrchestrateRequest(
        session_id=str(uuid.uuid4()),
        customer_id="CUST-ERR-001",
        message=message,
    )


class TestErrorRecoveryIntegration:
    def setup_method(self):
        clear_mock_audit_log()
        clear_mock_store()
        RCAAgent.clear_cache()

    @pytest.mark.asyncio
    async def test_unknown_issue_type_completes_pipeline(self):
        """Unclassified issue type still completes all 7 agents."""
        orch = MasterOrchestrator()
        result = await orch.run(make_req("some unusual network problem we have never seen"))
        assert len(result.agents_completed) + len(result.agents_failed) == 7

    @pytest.mark.asyncio
    async def test_multiple_sequential_sessions_independent(self):
        """Two back-to-back sessions produce independent results."""
        orch = MasterOrchestrator()
        r1 = await orch.run(make_req("fiber cut in sector north"))
        r2 = await orch.run(make_req("billing system down"))
        assert r1.ticket_id != r2.ticket_id
        assert r1.intent_summary["issue_type"] != r2.intent_summary["issue_type"]

    @pytest.mark.asyncio
    async def test_all_issue_types_complete_pipeline(self):
        """Every known issue type successfully runs the full pipeline."""
        orch = MasterOrchestrator()
        issue_messages = [
            "signal degradation on 4G network",
            "DNS failure affecting all customers",
            "power failure at cell site",
            "5G core network element crashed",
            "billing system database unresponsive",
        ]
        for msg in issue_messages:
            RCAAgent.clear_cache()
            result = await orch.run(make_req(msg))
            total = len(result.agents_completed) + len(result.agents_failed)
            assert total == 7, f"Pipeline incomplete for: {msg}"

    @pytest.mark.asyncio
    async def test_audit_trail_grows_per_session(self):
        """Each orchestration run appends distinct audit events."""
        clear_mock_audit_log()
        orch = MasterOrchestrator()
        await orch.run(make_req("fiber cut sector A"))
        count_after_1 = len(get_mock_audit_log())
        await orch.run(make_req("signal loss sector B"))
        count_after_2 = len(get_mock_audit_log())
        assert count_after_2 > count_after_1


class TestRAGPipelineIntegration:
    def setup_method(self):
        RCAAgent.clear_cache()

    @pytest.mark.asyncio
    async def test_rca_fiber_cut_returns_meaningful_result(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_req("fiber cut affecting backhaul and cell sites"))
        rca = result.rca_summary
        assert isinstance(rca.get("root_cause"), str)
        assert len(rca["root_cause"]) > 20

    @pytest.mark.asyncio
    async def test_rca_evidence_list_not_empty(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_req("signal degradation in 4G sector east"))
        assert isinstance(result.rca_summary.get("evidence"), list)
        assert len(result.rca_summary["evidence"]) > 0

    @pytest.mark.asyncio
    async def test_rca_returns_resolution_eta(self):
        orch = MasterOrchestrator()
        result = await orch.run(make_req("fiber cut at junction box BX-42"))
        assert result.rca_summary.get("estimated_resolution_minutes") > 0

    @pytest.mark.asyncio
    async def test_resolution_steps_match_issue_type(self):
        """Fiber cut steps differ from billing steps."""
        orch = MasterOrchestrator()
        RCAAgent.clear_cache()
        r_fiber = await orch.run(make_req("fiber cut affecting backhaul"))
        RCAAgent.clear_cache()
        r_billing = await orch.run(make_req("billing system completely down"))
        fiber_steps = r_fiber.resolution_summary.get("resolution_steps", [])
        billing_steps = r_billing.resolution_summary.get("resolution_steps", [])
        assert fiber_steps != billing_steps


# Import needed for test_audit_trail_grows_per_session
from core.audit import get_mock_audit_log
