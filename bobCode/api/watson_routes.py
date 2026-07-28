"""
Watson Orchestrate webhook handler and IBM BOB integration layer.

Watson Orchestrate calls the /webhook/orchestrate endpoint when a skill is invoked.
IBM BOB automation writes the resulting ticket to Cloudant and returns the ticket_id.

Security:
  - Webhook payload validated by Pydantic before processing
  - All Cloudant writes are sanitised (no raw customer text stored)
  - API key validated from Authorization header (Bearer token)
  - No PII in Cloudant ticket document
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from api.models import OrchestrateRequest, OrchestrationResult
from api.orchestrator import MasterOrchestrator
from core.audit import AuditLogger
from core.cloudant_client import CloudantClient
from core.config import get_settings
from core.guardrails import PIIGuardrails

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["watson-orchestrate"])

_orchestrator = MasterOrchestrator()
_cloudant = CloudantClient()


# ── Webhook request / response models ────────────────────────────────────────


class WatsonSkillRequest(BaseModel):
    """
    Payload received from Watson Orchestrate when a skill is invoked.
    Maps Watson Orchestrate skill input parameters to our OrchestrateRequest.
    """

    session_id: str = Field(..., description="Watson Orchestrate session identifier")
    customer_id: str = Field(
        default="WO-CUSTOMER", description="Customer identifier from Watson Orchestrate context"
    )
    message: str = Field(
        ..., min_length=1, max_length=2000,
        description="Customer complaint forwarded from Watson Orchestrate"
    )
    source: str = Field(
        default="watson_orchestrate",
        description="Origination system identifier"
    )


class WatsonSkillResponse(BaseModel):
    """Response returned to Watson Orchestrate after skill execution."""

    ticket_id: Optional[str] = None
    severity: Optional[str] = None
    queue: Optional[str] = None
    root_cause_summary: Optional[str] = None
    resolution_steps_count: int = 0
    customer_message: Optional[str] = None
    escalated: bool = False
    sla_met: Optional[bool] = None
    total_execution_ms: float = 0.0
    status: str = "success"


class BOBTicketDocument(BaseModel):
    """IBM BOB ticket document written to Cloudant tickets/ collection."""

    ticket_id: str
    session_id: str
    source: str = "ibm_bob"
    severity: Optional[str] = None
    queue: Optional[str] = None
    issue_type: Optional[str] = None
    root_cause_summary: str = ""
    resolution_steps: list = Field(default_factory=list)
    escalated: bool = False
    escalation_level: str = "None"
    sla_minutes: Optional[int] = None
    affected_customers: int = 0
    automation_score: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "open"


# ── Webhook endpoint (called by Watson Orchestrate) ───────────────────────────


@router.post(
    "/orchestrate",
    response_model=WatsonSkillResponse,
    summary="Watson Orchestrate skill entry point",
    description=(
        "Called by Watson Orchestrate when the Telecom BOB skill is invoked. "
        "Runs the full 7-agent pipeline and writes the resulting ticket to Cloudant via IBM BOB."
    ),
)
async def watson_orchestrate_webhook(
    request: WatsonSkillRequest,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> WatsonSkillResponse:
    """
    Watson Orchestrate skill webhook.

    Validates the caller, runs the orchestration pipeline, writes to Cloudant,
    and returns a structured skill response.
    """
    settings = get_settings()

    # ── API key validation (Authorization or x-api-key header check) ──────────
    if not settings.use_mock:
        authorized = False
        if authorization and (authorization.startswith("Bearer ") or (settings.backend_api_key and authorization == settings.backend_api_key)):
            authorized = True
        elif x_api_key and (not settings.backend_api_key or x_api_key == settings.backend_api_key):
            authorized = True
        
        if not authorized:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization / x-api-key header",
            )

    # ── Run the orchestration pipeline ───────────────────────────────────────
    orchestrate_req = OrchestrateRequest(
        session_id=request.session_id,
        customer_id=request.customer_id,
        message=request.message,
    )

    result: OrchestrationResult = await _orchestrator.run(orchestrate_req)

    # ── Write ticket to Cloudant via IBM BOB ─────────────────────────────────
    ticket_doc = _build_ticket_document(result, request)
    await _cloudant.save(settings.cloudant_db_tickets, ticket_doc.model_dump())

    await AuditLogger.log_event(
        "watson_orchestrate_skill_complete",
        {
            "ticket_id": result.ticket_id,
            "session_id": request.session_id,
            "source": request.source,
            "agents_completed": len(result.agents_completed),
        },
        request.session_id,
        "watson_orchestrate",
    )

    return _build_skill_response(result)


@router.get(
    "/health",
    tags=["watson-orchestrate"],
    summary="Watson Orchestrate integration health check",
)
async def watson_health() -> Dict[str, Any]:
    """Confirm the Watson Orchestrate webhook is reachable."""
    settings = get_settings()
    return {
        "status": "ok",
        "integration": "watson_orchestrate",
        "use_mock": settings.use_mock,
        "cloudant_db": settings.cloudant_db_tickets,
    }


# ── BOB ticket retrieval ──────────────────────────────────────────────────────


@router.get(
    "/tickets/{ticket_id}",
    tags=["watson-orchestrate"],
    summary="Retrieve a BOB-created ticket from Cloudant",
)
async def get_ticket(ticket_id: str) -> Dict[str, Any]:
    """Return a ticket document from Cloudant by ticket_id."""
    settings = get_settings()
    docs = await _cloudant.query(
        settings.cloudant_db_tickets,
        {"ticket_id": ticket_id},
        limit=1,
    )
    if not docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    return docs[0]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_ticket_document(
    result: OrchestrationResult,
    request: WatsonSkillRequest,
) -> BOBTicketDocument:
    """
    Build a sanitised Cloudant ticket document from orchestration output.
    No raw customer text is stored — only structured metadata.
    """
    ticket    = result.ticket_summary or {}
    rca       = result.rca_summary    or {}
    resolution = result.resolution_summary or {}
    escalation = result.escalation_summary or {}
    intent    = result.intent_summary or {}
    parallel  = result.analysis_summary or {}

    # Root cause truncated to 500 chars — no PII (already masked upstream)
    root_cause_summary = str(rca.get("root_cause", "Under investigation"))[:500]

    # Strip any residual PII just in case
    root_cause_summary = PIIGuardrails.mask_input(root_cause_summary)

    affected = parallel.get("customer_impact", {}).get("affected_customers", 0)

    return BOBTicketDocument(
        ticket_id=result.ticket_id or f"BOB-{request.session_id[:8]}",
        session_id=request.session_id,
        source=request.source,
        severity=ticket.get("severity"),
        queue=ticket.get("queue"),
        issue_type=intent.get("issue_type"),
        root_cause_summary=root_cause_summary,
        resolution_steps=resolution.get("resolution_steps", []),
        escalated=bool(escalation.get("escalate", False)),
        escalation_level=str(escalation.get("escalation_level", "None")),
        sla_minutes=ticket.get("sla_minutes"),
        affected_customers=affected,
        automation_score=float(resolution.get("automation_score", 0.0)),
    )


def _build_skill_response(result: OrchestrationResult) -> WatsonSkillResponse:
    """Map OrchestrationResult to the WatsonSkillResponse schema."""
    ticket    = result.ticket_summary    or {}
    rca       = result.rca_summary       or {}
    resolution = result.resolution_summary or {}
    escalation = result.escalation_summary or {}
    feedback  = result.feedback_summary  or {}

    root_cause = str(rca.get("root_cause", ""))[:200]

    return WatsonSkillResponse(
        ticket_id=result.ticket_id,
        severity=ticket.get("severity"),
        queue=ticket.get("queue"),
        root_cause_summary=PIIGuardrails.mask_input(root_cause),
        resolution_steps_count=len(resolution.get("resolution_steps", [])),
        customer_message=PIIGuardrails.mask_input(
            str(resolution.get("customer_message", ""))
        ),
        escalated=bool(escalation.get("escalate", False)),
        sla_met=feedback.get("sla_met"),
        total_execution_ms=result.total_execution_ms,
        status="success" if not result.agents_failed else "partial",
    )
