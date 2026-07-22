"""
Audit logger — immutable, sanitised event trail for every orchestration action.

Design principles:
  - Never log raw user input — always pass through PIIGuardrails.log_sanitised() first
  - In mock mode: events are appended to an in-memory list (inspectable in tests)
  - In live mode: events are written asynchronously to Cloudant audit_trail collection
  - Each event is append-only; no update/delete operations on the audit trail
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.guardrails import PIIGuardrails

logger = logging.getLogger(__name__)

# In-memory audit log (used when USE_MOCK=True — accessible in tests)
_MOCK_AUDIT_LOG: List[Dict[str, Any]] = []


def get_mock_audit_log() -> List[Dict[str, Any]]:
    """Return the in-memory audit log (test inspection only)."""
    return _MOCK_AUDIT_LOG


def clear_mock_audit_log() -> None:
    """Clear the in-memory audit log between tests."""
    _MOCK_AUDIT_LOG.clear()


class AuditLogger:
    """
    Write sanitised audit events to the audit trail.

    Usage:
        await AuditLogger.log_event("agent_completed", {"agent": "intent", "status": "ok"}, "req-123")
    """

    @staticmethod
    async def log_event(
        event_type: str,
        sanitised_payload: Dict[str, Any],
        request_id: str,
        agent_name: Optional[str] = None,
        status: str = "ok",
    ) -> str:
        """
        Record an audit event.

        Payload is passed through PIIGuardrails.log_sanitised() as a final safety net
        even if the caller already masked data.

        Args:
            event_type:        Category of event (e.g. "orchestration_start", "agent_completed")
            sanitised_payload: Event data dict — must NOT contain raw user input.
            request_id:        The originating request's ID for correlation.
            agent_name:        Name of the agent involved (optional).
            status:            "ok" | "error" | "fallback"

        Returns:
            audit_id: Unique identifier of this audit record.
        """
        settings = get_settings()

        # Final PII safety net — redundant but never harmful
        clean_payload = PIIGuardrails.log_sanitised(sanitised_payload)

        audit_id = str(uuid.uuid4())
        event = {
            "_id": audit_id,
            "event_type": event_type,
            "request_id": request_id,
            "agent_name": agent_name or "orchestrator",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": clean_payload,
        }

        if settings.use_mock:
            _MOCK_AUDIT_LOG.append(event)
            logger.debug("AuditLogger [MOCK]: event_type=%s request_id=%s", event_type, request_id)
        else:
            # Live mode: write to Cloudant audit_trail collection
            # Cloudant client is injected in ST-1 to avoid circular imports here
            logger.info(
                "AuditLogger [LIVE]: event_type=%s request_id=%s audit_id=%s",
                event_type,
                request_id,
                audit_id,
            )
            # TODO(ST-4): inject CloudantClient and call .save(settings.cloudant_db_audit, event)

        return audit_id
