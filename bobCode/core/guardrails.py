"""
Security guardrails — the first line of defence for all data flowing through the system.

Three classes enforce different protection layers:
  - PIIGuardrails:   Detects and redacts Personally Identifiable Information
  - InputGuardrails: Validates and rejects malicious or malformed inputs
  - OutputGuardrails: Validates agent outputs before returning to the client

Design principle: FAIL CLOSED — if validation is uncertain, reject/redact rather than allow.
These classes are imported and called by every agent before any processing or logging.
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Redaction sentinel ────────────────────────────────────────────────────────

REDACTED = "[REDACTED]"

# ── PII Guardrails ────────────────────────────────────────────────────────────

# Compiled patterns — ordered from most-specific to least-specific to avoid
# partial matches corrupting subsequent patterns.
_PII_PATTERNS: Dict[str, re.Pattern] = {
    # Credit card: 4×4 digits with optional space/dash separator
    "credit_card": re.compile(
        r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"
    ),
    # US Social Security Number: NNN-NN-NNNN
    "ssn": re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
    ),
    # E.164 international phone or US 10-digit (with optional country code)
    "phone": re.compile(
        r"(?<!\d)(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})(?!\d)"
    ),
    # Email address (basic RFC-5321 subset sufficient for PII detection)
    "email": re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    ),
}

# Patterns in output that suggest injected PII even after LLM processing
_LOOSE_PII_SCAN: Dict[str, re.Pattern] = {
    k: v for k, v in _PII_PATTERNS.items()
}


class PIIGuardrails:
    """
    Detect and redact Personally Identifiable Information.

    All methods are static — no instance state required.
    Call mask_input() on every user-provided string BEFORE any processing.
    Call log_sanitised() when writing events to logs or audit trail.
    """

    @staticmethod
    def mask_input(text: str) -> str:
        """
        Replace PII patterns in *text* with [REDACTED].

        Patterns applied (in order): credit card, SSN, phone, email.
        Non-PII text is returned unchanged.

        Args:
            text: Raw input string that may contain PII.

        Returns:
            String with all detected PII replaced by [REDACTED].
        """
        if not text:
            return text

        masked = text
        for name, pattern in _PII_PATTERNS.items():
            before = masked
            masked = pattern.sub(REDACTED, masked)
            if masked != before:
                logger.debug("PIIGuardrails: masked pattern=%s", name)

        return masked

    @staticmethod
    def contains_pii(text: str) -> bool:
        """
        Return True if *text* contains any detectable PII pattern.

        Args:
            text: String to inspect.

        Returns:
            True if PII is found, False otherwise.
        """
        for pattern in _PII_PATTERNS.values():
            if pattern.search(text):
                return True
        return False

    @staticmethod
    def log_sanitised(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively mask PII in a dict before it is written to any log or audit trail.

        Operates on string values only; non-string values are left unchanged.

        Args:
            data: Dictionary that may contain PII in its string values.

        Returns:
            New dictionary with PII replaced; original dict is not mutated.
        """
        sanitised: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitised[key] = PIIGuardrails.mask_input(value)
            elif isinstance(value, dict):
                sanitised[key] = PIIGuardrails.log_sanitised(value)
            elif isinstance(value, list):
                sanitised[key] = [
                    PIIGuardrails.mask_input(v) if isinstance(v, str) else v for v in value
                ]
            else:
                sanitised[key] = value
        return sanitised


# ── Input Guardrails ──────────────────────────────────────────────────────────

_MAX_MESSAGE_LENGTH = 2000
_MAX_ENTITY_COUNT = 10

# SQL injection fragments — common UNION/DROP/INSERT/SELECT attack patterns
_SQL_INJECTION_PATTERNS = re.compile(
    r"""
    (union\s+select)
    |(drop\s+table)
    |(insert\s+into)
    |(delete\s+from)
    |(select\s+\*\s+from)
    |(exec\s*\()
    |(-{2,}\s*$)        # SQL line comment at end
    |(/\*.*\*/)         # SQL block comment
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Prompt injection heuristics — attempts to override system instructions
_PROMPT_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior|above)\s+instructions?)"
    r"|(you\s+are\s+now\s+a)"
    r"|(system\s*:\s*you)"
    r"|(forget\s+everything)"
    r"|(\[INST\])"
    r"|(<\|im_start\|>)"
    r"|(###\s*human:)"
    r"|(act\s+as\s+(?:if\s+you\s+are|a\s+))",
    re.IGNORECASE,
)


class InputGuardrails:
    """
    Validate and gate all external input before it reaches business logic.

    Blocks: over-length messages, SQL injection, prompt injection attempts.
    Returns a (valid: bool, reason: str) tuple so callers can build safe error messages.
    """

    MAX_LENGTH: int = _MAX_MESSAGE_LENGTH

    @staticmethod
    def validate(message: str) -> Tuple[bool, str]:
        """
        Validate *message* against all input rules.

        Args:
            message: Raw user input string.

        Returns:
            (True, "") if valid.
            (False, reason) if the input should be rejected.
        """
        if not message or not message.strip():
            return False, "Input must not be empty"

        if len(message) > _MAX_MESSAGE_LENGTH:
            return (
                False,
                f"Input exceeds maximum length of {_MAX_MESSAGE_LENGTH} characters",
            )

        if _SQL_INJECTION_PATTERNS.search(message):
            logger.warning("InputGuardrails: SQL injection pattern detected")
            return False, "Input contains disallowed content"

        if _PROMPT_INJECTION_PATTERNS.search(message):
            logger.warning("InputGuardrails: Prompt injection pattern detected")
            return False, "Input contains disallowed content"

        return True, ""

    @staticmethod
    def is_valid(message: str) -> bool:
        """Convenience wrapper — returns bool only (discards reason)."""
        valid, _ = InputGuardrails.validate(message)
        return valid


# ── Output Guardrails ─────────────────────────────────────────────────────────

_CONFIDENCE_MINIMUM = 0.5


class OutputGuardrails:
    """
    Validate agent outputs before they leave the system boundary.

    Checks: confidence threshold, schema presence, PII leak scan.
    """

    CONFIDENCE_MIN: float = _CONFIDENCE_MINIMUM

    @staticmethod
    def validate_confidence(confidence: float) -> Tuple[bool, str]:
        """
        Reject outputs where the agent confidence is below the minimum threshold.

        Args:
            confidence: Float in [0.0, 1.0] from agent metadata.

        Returns:
            (True, "") if acceptable. (False, reason) if below threshold.
        """
        if confidence < _CONFIDENCE_MINIMUM:
            return (
                False,
                f"Confidence {confidence:.2f} is below minimum threshold {_CONFIDENCE_MINIMUM}",
            )
        return True, ""

    @staticmethod
    def scan_for_pii(result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Scan agent result dict for any PII that may have leaked through.

        Args:
            result: Agent result dictionary.

        Returns:
            (True, "") if clean. (False, field_name) if PII found.
        """
        for key, value in result.items():
            check_value = str(value) if not isinstance(value, str) else value
            if PIIGuardrails.contains_pii(check_value):
                logger.warning("OutputGuardrails: PII detected in output field=%s", key)
                return False, f"PII detected in output field: {key}"
        return True, ""

    @staticmethod
    def validate(
        result: Dict[str, Any],
        confidence: float,
        required_fields: Optional[list] = None,
    ) -> Tuple[bool, str]:
        """
        Run all output validation checks.

        Args:
            result:          Agent result dictionary.
            confidence:      Agent confidence score.
            required_fields: Optional list of keys that must be present in result.

        Returns:
            (True, "") if all checks pass. (False, reason) if any check fails.
        """
        # 1. Confidence threshold
        ok, reason = OutputGuardrails.validate_confidence(confidence)
        if not ok:
            return False, reason

        # 2. Required fields
        if required_fields:
            for field in required_fields:
                if field not in result:
                    return False, f"Required output field missing: {field}"

        # 3. PII scan on string values
        ok, reason = OutputGuardrails.scan_for_pii(result)
        if not ok:
            return False, reason

        return True, ""
