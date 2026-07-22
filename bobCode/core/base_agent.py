"""
Abstract base class for all 7 Telecom Copilot agents.

Every agent inherits from BaseAgent and implements _process_internal().
The base class handles the full security lifecycle automatically:
  1. Input validation (InputGuardrails)
  2. PII masking (PIIGuardrails)
  3. Timing measurement
  4. Output validation (OutputGuardrails)
  5. Audit logging (AuditLogger)
  6. Error recovery with typed fallback responses

Agents never bypass this lifecycle — security and observability are enforced at the base.
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from api.models import AgentMetadata, AgentRequest, AgentResponse, AgentStatus
from core.audit import AuditLogger
from core.config import get_settings
from core.guardrails import InputGuardrails, OutputGuardrails, PIIGuardrails

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class providing the standard agent execution lifecycle.

    Subclasses must implement:
      - agent_name (str): unique snake_case identifier
      - required_output_fields (list[str]): fields that must appear in result
      - _process_internal(safe_text, context) -> (result, confidence)
    """

    agent_name: str = "base_agent"
    required_output_fields: List[str] = []

    def __init__(self) -> None:
        self._settings = get_settings()

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Execute the full agent lifecycle for a given request.

        Lifecycle:
          validate input → mask PII → _process_internal → validate output → audit log

        Args:
            request: Standardised AgentRequest envelope.

        Returns:
            AgentResponse with result, metadata, and status.
        """
        start_ms = time.monotonic() * 1000

        # ── 1. Input validation ───────────────────────────────────────────────
        raw_message = str(request.payload.get("message", ""))
        valid, reason = InputGuardrails.validate(raw_message) if raw_message else (True, "")
        if raw_message and not valid:
            return self._error_response(
                request.request_id,
                f"Input validation failed: {reason}",
                start_ms,
            )

        # ── 2. PII masking — never process raw user text ──────────────────────
        safe_text = PIIGuardrails.mask_input(raw_message) if raw_message else ""
        safe_payload = PIIGuardrails.log_sanitised(request.payload)

        # ── 3. Core processing (agent-specific logic) ─────────────────────────
        try:
            result, confidence = await self._process_internal(safe_text, request)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Agent %s failed: %s | request_id=%s",
                self.agent_name,
                type(exc).__name__,
                request.request_id,
            )
            await AuditLogger.log_event(
                "agent_error",
                {"agent": self.agent_name, "error_type": type(exc).__name__},
                request.request_id,
                self.agent_name,
                status="error",
            )
            return self._fallback_response(request.request_id, str(exc), start_ms)

        # ── 4. Output validation ──────────────────────────────────────────────
        ok, out_reason = OutputGuardrails.validate(
            result, confidence, self.required_output_fields
        )
        if not ok:
            logger.warning(
                "Agent %s output validation failed: %s | request_id=%s",
                self.agent_name,
                out_reason,
                request.request_id,
            )
            # Sanitise the result and lower confidence rather than hard-fail
            # (graceful degradation: return partial rather than nothing)
            result = PIIGuardrails.log_sanitised(result)
            confidence = max(0.0, confidence - 0.1)
            status = AgentStatus.PARTIAL
        else:
            status = AgentStatus.SUCCESS

        elapsed_ms = (time.monotonic() * 1000) - start_ms

        # ── 5. Audit log ──────────────────────────────────────────────────────
        await AuditLogger.log_event(
            "agent_completed",
            {
                "agent": self.agent_name,
                "status": status.value,
                "confidence": confidence,
                "execution_ms": round(elapsed_ms, 1),
            },
            request.request_id,
            self.agent_name,
            status=status.value,
        )

        return AgentResponse(
            request_id=request.request_id,
            agent_name=self.agent_name,
            status=status,
            result=result,
            metadata=AgentMetadata(
                execution_time_ms=round(elapsed_ms, 1),
                confidence=confidence,
                cache_hit=False,
                mock_used=self._settings.use_mock,
            ),
        )

    @abstractmethod
    async def _process_internal(
        self,
        safe_text: str,
        request: AgentRequest,
    ) -> tuple[Dict[str, Any], float]:
        """
        Agent-specific processing logic.

        Receives PII-masked text and the full request context.
        Must return (result_dict, confidence_float).

        Args:
            safe_text: PII-masked version of request.payload["message"].
            request:   Full AgentRequest (use request.context.upstream_results for prior results).

        Returns:
            Tuple of (result dict, confidence 0.0–1.0).
        """

    def _error_response(
        self, request_id: str, message: str, start_ms: float
    ) -> AgentResponse:
        """Build a typed error response — never exposes internal details."""
        elapsed = (time.monotonic() * 1000) - start_ms
        return AgentResponse(
            request_id=request_id,
            agent_name=self.agent_name,
            status=AgentStatus.ERROR,
            result={},
            metadata=AgentMetadata(
                execution_time_ms=round(elapsed, 1),
                confidence=0.0,
                mock_used=self._settings.use_mock,
            ),
            error_message=message,
        )

    def _fallback_response(
        self, request_id: str, exc_summary: str, start_ms: float
    ) -> AgentResponse:
        """Build a fallback response when _process_internal raises an exception."""
        elapsed = (time.monotonic() * 1000) - start_ms
        return AgentResponse(
            request_id=request_id,
            agent_name=self.agent_name,
            status=AgentStatus.FALLBACK,
            result={"fallback": True, "message": "Service temporarily unavailable"},
            metadata=AgentMetadata(
                execution_time_ms=round(elapsed, 1),
                confidence=0.0,
                mock_used=self._settings.use_mock,
            ),
            error_message="Agent processing failed — fallback applied",
        )
