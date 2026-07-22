"""
API routes — orchestration endpoint, per-agent endpoints, SSE streaming.

Security: All routes validate input via Pydantic before any processing.
CORS is configured in main.py (restricted origins only).
"""

import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from api.models import (
    AgentRequest,
    AgentResponse,
    AgentStatus,
    AgentContext,
    OrchestrateRequest,
    OrchestrationResult,
)
from api.orchestrator import MasterOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# Singleton orchestrator — agents are stateless so this is safe
_orchestrator = MasterOrchestrator()


# ── Master orchestration ──────────────────────────────────────────────────────


@router.post(
    "/orchestrate",
    response_model=OrchestrationResult,
    tags=["orchestration"],
    summary="Run full 7-agent pipeline",
    description=(
        "Accepts a free-text customer complaint and runs it through the full "
        "7-agent pipeline: Intent → Ticket → RCA → Escalation+Parallel → "
        "Resolution → Feedback. Returns aggregated result."
    ),
)
async def orchestrate(request: OrchestrateRequest) -> OrchestrationResult:
    """Execute the full orchestration pipeline (non-streaming)."""
    try:
        return await _orchestrator.run(request)
    except Exception as exc:
        logger.error("Orchestration failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestration failed — please try again",
        )


@router.post(
    "/orchestrate/stream",
    tags=["orchestration"],
    summary="Run pipeline with SSE streaming",
    description=(
        "Same as POST /orchestrate but streams per-agent progress events "
        "as Server-Sent Events. Each event: {stage, agent, status, confidence, partial_result}."
    ),
)
async def orchestrate_stream(request: OrchestrateRequest) -> StreamingResponse:
    """Execute the pipeline and stream SSE events as each agent completes."""

    async def event_generator():
        try:
            async for event in _orchestrator.run_stream(request):
                yield event
        except Exception as exc:
            logger.error("SSE stream failed: %s", exc)
            import json
            yield f"data: {json.dumps({'stage': 'error', 'message': 'Stream failed'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Individual agent endpoints ────────────────────────────────────────────────


def _agent_route(agent_instance, route_name: str, summary: str):
    """Register a POST endpoint for a single agent."""

    @router.post(
        f"/agents/{route_name}",
        response_model=AgentResponse,
        tags=["agents"],
        summary=summary,
    )
    async def _handler(request: AgentRequest) -> AgentResponse:
        try:
            return await agent_instance.process(request)
        except Exception as exc:
            logger.error("Agent %s error: %s", route_name, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent {route_name} failed",
            )

    _handler.__name__ = f"agent_{route_name}"
    return _handler


# Register all 7 agents
from agents.intent_agent import IntentAgent
from agents.ticket_agent import TicketAgent
from agents.rca_agent import RCAAgent
from agents.escalation_agent import EscalationAgent
from agents.parallel_agent import ParallelAgent
from agents.resolution_agent import ResolutionAgent
from agents.feedback_agent import FeedbackAgent

_agent_route(IntentAgent(),     "intent",     "Intent Recognition Agent")
_agent_route(TicketAgent(),     "ticket",     "Ticket Classification Agent")
_agent_route(RCAAgent(),        "rca",        "Root Cause Analysis Agent")
_agent_route(EscalationAgent(), "escalation", "Escalation Agent")
_agent_route(ParallelAgent(),   "parallel",   "Parallel Analysis Agent")
_agent_route(ResolutionAgent(), "resolution", "Response Generation Agent")
_agent_route(FeedbackAgent(),   "feedback",   "Feedback Agent")
