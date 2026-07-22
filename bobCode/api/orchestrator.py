"""
Master Orchestration Engine — coordinates all 7 agents in sequence.

Pipeline:
  1. Intent Recognition          (always)
  2. Ticket Classification        (always)
  3. RCA Analysis                 (always; cache-aware)
  4. Escalation + Parallel        (asyncio.gather — concurrent)
  5. Response Generation          (always)
  6. Feedback                     (always)

Conditional branching:
  - Critical priority  → Escalation is mandatory regardless of P-level
  - Known RCA cache    → skip LLM call inside RCAAgent (handled internally)
  - Agent failure      → fallback response injected; pipeline continues

Error recovery:
  LLM timeout / IBM service error → GraniteClient / NLUClient fall back to mock
  Agent exception                 → BaseAgent._fallback_response() catches it
  Full pipeline failure           → OrchestrationError with safe message returned

SSE streaming:
  Each agent emits a JSON event: {stage, agent, status, confidence, partial_result}
  The final event carries the complete OrchestrationResult.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from api.models import (
    AgentContext,
    AgentRequest,
    AgentResponse,
    AgentStatus,
    OrchestrationResult,
    OrchestrateRequest,
)
from agents.intent_agent import IntentAgent
from agents.ticket_agent import TicketAgent
from agents.rca_agent import RCAAgent
from agents.escalation_agent import EscalationAgent
from agents.parallel_agent import ParallelAgent
from agents.resolution_agent import ResolutionAgent
from agents.feedback_agent import FeedbackAgent
from core.audit import AuditLogger
from core.config import get_settings

logger = logging.getLogger(__name__)

# Stage name constants used in SSE events
STAGE_INTENT      = "intent_recognition"
STAGE_TICKET      = "ticket_classification"
STAGE_RCA         = "rca_analysis"
STAGE_ESCALATION  = "escalation"
STAGE_PARALLEL    = "parallel_analysis"
STAGE_RESOLUTION  = "response_generation"
STAGE_FEEDBACK    = "feedback"


def _make_agent_request(
    session_id: str,
    customer_id: str,
    message: str,
    upstream_results: Dict[str, Any],
    extra_payload: Optional[Dict[str, Any]] = None,
) -> AgentRequest:
    """Build a standardised AgentRequest for any agent in the pipeline."""
    payload: Dict[str, Any] = {"message": message}
    if extra_payload:
        payload.update(extra_payload)
    return AgentRequest(
        request_id=str(uuid.uuid4()),
        customer_id=customer_id,
        payload=payload,
        context=AgentContext(
            session_id=session_id,
            upstream_results=upstream_results,
        ),
    )


def _sse_event(
    stage: str,
    agent: str,
    status: str,
    confidence: float = 0.0,
    partial_result: Optional[Dict[str, Any]] = None,
) -> str:
    """Serialise a pipeline progress event for Server-Sent Events."""
    data = {
        "stage": stage,
        "agent": agent,
        "status": status,
        "confidence": round(confidence, 3),
        "partial_result": partial_result or {},
    }
    return f"data: {json.dumps(data)}\n\n"


class MasterOrchestrator:
    """
    Coordinates the 7-agent pipeline for a single customer complaint.

    Usage (blocking):
        orchestrator = MasterOrchestrator()
        result = await orchestrator.run(request)

    Usage (streaming):
        async for event in orchestrator.run_stream(request):
            yield event   # send as SSE to client
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._intent     = IntentAgent()
        self._ticket     = TicketAgent()
        self._rca        = RCAAgent()
        self._escalation = EscalationAgent()
        self._parallel   = ParallelAgent()
        self._resolution = ResolutionAgent()
        self._feedback   = FeedbackAgent()

    async def run(self, request: OrchestrateRequest) -> OrchestrationResult:
        """
        Execute the full pipeline and return the aggregated result.

        Args:
            request: OrchestrateRequest with customer message and session context.

        Returns:
            OrchestrationResult with all agent outputs and execution metadata.
        """
        start_ms = time.monotonic() * 1000
        session_id   = request.session_id
        customer_id  = request.customer_id
        message      = request.message
        upstream: Dict[str, Any] = {}
        completed: List[str] = []
        failed: List[str] = []

        await AuditLogger.log_event(
            "orchestration_start",
            {"session_id": session_id, "message_len": len(message)},
            session_id,
            "orchestrator",
        )

        result = OrchestrationResult(session_id=session_id)

        # ── Stage 1: Intent Recognition ───────────────────────────────────────
        req1 = _make_agent_request(session_id, customer_id, message, upstream)
        r1 = await self._intent.process(req1)
        upstream[STAGE_INTENT] = r1.result
        result.intent_summary = _safe_result(r1)
        _track(r1, STAGE_INTENT, completed, failed)

        # ── Stage 2: Ticket Classification ────────────────────────────────────
        req2 = _make_agent_request(session_id, customer_id, message, upstream)
        r2 = await self._ticket.process(req2)
        upstream[STAGE_TICKET] = r2.result
        result.ticket_summary = _safe_result(r2)
        result.ticket_id = r2.result.get("ticket_id")
        _track(r2, STAGE_TICKET, completed, failed)

        # ── Stage 3: RCA Analysis ─────────────────────────────────────────────
        req3 = _make_agent_request(session_id, customer_id, message, upstream)
        r3 = await self._rca.process(req3)
        upstream[STAGE_RCA] = r3.result
        result.rca_summary = _safe_result(r3)
        _track(r3, STAGE_RCA, completed, failed)

        # ── Stage 4: Escalation + Parallel (concurrent) ───────────────────────
        req4 = _make_agent_request(session_id, customer_id, message, upstream)
        req5 = _make_agent_request(session_id, customer_id, message, upstream)
        r4, r5 = await asyncio.gather(
            self._escalation.process(req4),
            self._parallel.process(req5),
            return_exceptions=False,
        )
        upstream[STAGE_ESCALATION] = r4.result
        upstream[STAGE_PARALLEL]   = r5.result
        result.escalation_summary = _safe_result(r4)
        result.analysis_summary   = _safe_result(r5)
        _track(r4, STAGE_ESCALATION, completed, failed)
        _track(r5, STAGE_PARALLEL, completed, failed)

        # ── Stage 5: Response Generation ──────────────────────────────────────
        req6 = _make_agent_request(session_id, customer_id, message, upstream)
        r6 = await self._resolution.process(req6)
        upstream[STAGE_RESOLUTION] = r6.result
        result.resolution_summary = _safe_result(r6)
        _track(r6, STAGE_RESOLUTION, completed, failed)

        # ── Stage 6: Feedback ─────────────────────────────────────────────────
        req7 = _make_agent_request(session_id, customer_id, message, upstream)
        r7 = await self._feedback.process(req7)
        upstream[STAGE_FEEDBACK] = r7.result
        result.feedback_summary = _safe_result(r7)
        _track(r7, STAGE_FEEDBACK, completed, failed)

        result.total_execution_ms = round((time.monotonic() * 1000) - start_ms, 1)
        result.agents_completed   = completed
        result.agents_failed      = failed

        await AuditLogger.log_event(
            "orchestration_complete",
            {
                "session_id": session_id,
                "ticket_id": result.ticket_id,
                "agents_completed": len(completed),
                "agents_failed": len(failed),
                "total_ms": result.total_execution_ms,
            },
            session_id,
            "orchestrator",
        )

        logger.info(
            "Orchestration complete: session=%s ticket=%s completed=%d failed=%d ms=%.0f",
            session_id, result.ticket_id, len(completed), len(failed), result.total_execution_ms,
        )

        return result

    async def run_stream(
        self, request: OrchestrateRequest
    ) -> AsyncGenerator[str, None]:
        """
        Execute the pipeline and yield SSE events as each agent completes.

        Each event is a JSON string prefixed with 'data: ' per the SSE spec.
        The final event has stage='complete' and carries the full result.
        """
        start_ms = time.monotonic() * 1000
        session_id  = request.session_id
        customer_id = request.customer_id
        message     = request.message
        upstream: Dict[str, Any] = {}
        completed: List[str] = []
        failed: List[str] = []

        await AuditLogger.log_event(
            "orchestration_stream_start",
            {"session_id": session_id},
            session_id,
            "orchestrator",
        )

        result = OrchestrationResult(session_id=session_id)

        # Stage 1
        req = _make_agent_request(session_id, customer_id, message, upstream)
        r = await self._intent.process(req)
        upstream[STAGE_INTENT] = r.result
        result.intent_summary = _safe_result(r)
        _track(r, STAGE_INTENT, completed, failed)
        yield _sse_event(STAGE_INTENT, STAGE_INTENT, r.status.value,
                         r.metadata.confidence, _safe_result(r))

        # Stage 2
        req = _make_agent_request(session_id, customer_id, message, upstream)
        r = await self._ticket.process(req)
        upstream[STAGE_TICKET] = r.result
        result.ticket_summary = _safe_result(r)
        result.ticket_id = r.result.get("ticket_id")
        _track(r, STAGE_TICKET, completed, failed)
        yield _sse_event(STAGE_TICKET, STAGE_TICKET, r.status.value,
                         r.metadata.confidence, {"ticket_id": result.ticket_id,
                                                  "severity": r.result.get("severity")})

        # Stage 3
        req = _make_agent_request(session_id, customer_id, message, upstream)
        r = await self._rca.process(req)
        upstream[STAGE_RCA] = r.result
        result.rca_summary = _safe_result(r)
        _track(r, STAGE_RCA, completed, failed)
        yield _sse_event(STAGE_RCA, STAGE_RCA, r.status.value,
                         r.metadata.confidence,
                         {"root_cause": r.result.get("root_cause", "")[:120]})

        # Stage 4 — parallel
        req4 = _make_agent_request(session_id, customer_id, message, upstream)
        req5 = _make_agent_request(session_id, customer_id, message, upstream)
        r4, r5 = await asyncio.gather(
            self._escalation.process(req4),
            self._parallel.process(req5),
        )
        upstream[STAGE_ESCALATION] = r4.result
        upstream[STAGE_PARALLEL]   = r5.result
        result.escalation_summary = _safe_result(r4)
        result.analysis_summary   = _safe_result(r5)
        _track(r4, STAGE_ESCALATION, completed, failed)
        _track(r5, STAGE_PARALLEL, completed, failed)
        yield _sse_event(STAGE_ESCALATION, STAGE_ESCALATION, r4.status.value,
                         r4.metadata.confidence,
                         {"escalate": r4.result.get("escalate"),
                          "level": r4.result.get("escalation_level")})
        yield _sse_event(STAGE_PARALLEL, STAGE_PARALLEL, r5.status.value,
                         r5.metadata.confidence,
                         {"affected_customers": r5.result.get(
                             "customer_impact", {}).get("affected_customers", 0)})

        # Stage 5
        req = _make_agent_request(session_id, customer_id, message, upstream)
        r = await self._resolution.process(req)
        upstream[STAGE_RESOLUTION] = r.result
        result.resolution_summary = _safe_result(r)
        _track(r, STAGE_RESOLUTION, completed, failed)
        yield _sse_event(STAGE_RESOLUTION, STAGE_RESOLUTION, r.status.value,
                         r.metadata.confidence,
                         {"steps_count": len(r.result.get("resolution_steps", [])),
                          "automation_score": r.result.get("automation_score", 0)})

        # Stage 6
        req = _make_agent_request(session_id, customer_id, message, upstream)
        r = await self._feedback.process(req)
        upstream[STAGE_FEEDBACK] = r.result
        result.feedback_summary = _safe_result(r)
        _track(r, STAGE_FEEDBACK, completed, failed)
        yield _sse_event(STAGE_FEEDBACK, STAGE_FEEDBACK, r.status.value,
                         r.metadata.confidence,
                         {"sla_met": r.result.get("sla_met"),
                          "csat": r.result.get("customer_satisfaction")})

        result.total_execution_ms = round((time.monotonic() * 1000) - start_ms, 1)
        result.agents_completed   = completed
        result.agents_failed      = failed

        # Final complete event with full result
        final = {
            "stage": "complete",
            "agent": "orchestrator",
            "status": "success" if not failed else "partial",
            "total_execution_ms": result.total_execution_ms,
            "ticket_id": result.ticket_id,
            "agents_completed": completed,
            "agents_failed": failed,
        }
        yield f"data: {json.dumps(final)}\n\n"

        await AuditLogger.log_event(
            "orchestration_stream_complete",
            {"session_id": session_id, "total_ms": result.total_execution_ms},
            session_id,
            "orchestrator",
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _safe_result(response: AgentResponse) -> Dict[str, Any]:
    """Return result dict, or a minimal fallback if agent failed."""
    if response.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL):
        return response.result
    return {"status": response.status.value, "fallback": True}


def _track(
    response: AgentResponse,
    stage: str,
    completed: List[str],
    failed: List[str],
) -> None:
    """Update completed/failed lists based on agent response status."""
    if response.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL):
        completed.append(stage)
    else:
        failed.append(stage)
        logger.warning("Agent %s status=%s", stage, response.status.value)
