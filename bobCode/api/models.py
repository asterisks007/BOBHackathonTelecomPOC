"""
Pydantic request/response models shared across all agents and the API layer.

Every agent receives an AgentRequest and must return an AgentResponse.
The envelope schema ensures observability and consistent error handling.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class AgentStatus(str, Enum):
    """Possible terminal states for an agent execution."""

    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    FALLBACK = "fallback"


class IssuePriority(str, Enum):
    """Customer-facing incident priority levels."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class IncidentSeverity(str, Enum):
    """Internal ticket severity (maps to SLA minutes)."""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


# ── Request model ─────────────────────────────────────────────────────────────

class AgentContext(BaseModel):
    """Carries upstream results and session state between agents."""

    session_id: str = Field(..., description="Unique conversation session identifier")
    upstream_results: Dict[str, Any] = Field(
        default_factory=dict, description="Results from previously executed agents"
    )


class AgentRequest(BaseModel):
    """Standardised input envelope accepted by every agent endpoint."""

    request_id: str = Field(..., description="Unique request identifier (UUID recommended)")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the request",
    )
    customer_id: str = Field(..., description="Anonymised customer identifier")
    payload: Dict[str, Any] = Field(..., description="Agent-specific input fields")
    context: AgentContext = Field(..., description="Session and upstream context")

    @field_validator("payload")
    @classmethod
    def payload_must_not_be_empty(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure payload is not an empty dict."""
        if not v:
            raise ValueError("payload must contain at least one field")
        return v


# ── Response model ────────────────────────────────────────────────────────────

class AgentMetadata(BaseModel):
    """Execution metadata attached to every agent response."""

    execution_time_ms: float = Field(..., description="Wall-clock time in milliseconds")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Agent confidence score (0–1)"
    )
    cache_hit: bool = Field(default=False, description="True if result served from cache")
    mock_used: bool = Field(default=True, description="True if IBM service was mocked")
    model_used: Optional[str] = Field(default=None, description="LLM model identifier if used")


class AgentResponse(BaseModel):
    """Standardised output envelope returned by every agent endpoint."""

    request_id: str = Field(..., description="Echoed from AgentRequest")
    agent_name: str = Field(..., description="Name of the agent that produced this response")
    status: AgentStatus = Field(..., description="Execution outcome")
    result: Dict[str, Any] = Field(..., description="Agent-specific output fields")
    metadata: AgentMetadata = Field(..., description="Execution telemetry")
    error_message: Optional[str] = Field(
        default=None, description="Human-readable error details (never raw stack traces)"
    )


# ── Orchestration models ──────────────────────────────────────────────────────

class OrchestrateRequest(BaseModel):
    """Top-level request to the master orchestration endpoint."""

    session_id: str = Field(..., description="Session identifier for this conversation turn")
    customer_id: str = Field(..., description="Anonymised customer identifier")
    message: str = Field(
        ..., min_length=1, max_length=2000, description="Free-text customer complaint"
    )

    @field_validator("message")
    @classmethod
    def message_must_not_be_whitespace(cls, v: str) -> str:
        """Reject blank messages."""
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class OrchestrationResult(BaseModel):
    """Aggregated result returned after the full 7-agent pipeline completes."""

    session_id: str
    ticket_id: Optional[str] = None
    intent_summary: Optional[Dict[str, Any]] = None
    ticket_summary: Optional[Dict[str, Any]] = None
    rca_summary: Optional[Dict[str, Any]] = None
    escalation_summary: Optional[Dict[str, Any]] = None
    analysis_summary: Optional[Dict[str, Any]] = None
    resolution_summary: Optional[Dict[str, Any]] = None
    feedback_summary: Optional[Dict[str, Any]] = None
    total_execution_ms: float = 0.0
    agents_completed: List[str] = Field(default_factory=list)
    agents_failed: List[str] = Field(default_factory=list)


# ── Health models ─────────────────────────────────────────────────────────────

class ServiceStatus(BaseModel):
    """Health status of a single dependency."""

    name: str
    status: str  # "ok" | "degraded" | "unavailable"
    mock_mode: bool


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str  # "ok" | "degraded"
    version: str
    use_mock: bool
    services: List[ServiceStatus]
    api_calls_used: int = Field(default=0, description="Real IBM API calls consumed so far")
    api_calls_budget: int = Field(default=100, description="Monthly Lite Plan call budget")
