"""
Agent 1 — Intent Recognition Agent.

Classifies the customer's free-text complaint into a structured intent with
entities (issue type, service, location) and a priority level.

Input (payload):
    message (str): Free-text customer complaint

Output:
    issue_type    (str)   : e.g. "fiber_cut", "signal_degradation"
    service       (str)   : e.g. "4G_LTE", "5G_SA", "Fixed_Broadband"
    location      (str)   : extracted location reference
    priority      (str)   : Critical | High | Medium | Low
    confidence    (float) : 0–1
    entities      (dict)  : raw NLU entity list grouped by type
    keywords      (list)  : top keywords from NLU

SLA target: <500ms
"""

import logging
from typing import Any, Dict, List, Tuple

from api.models import AgentRequest
from core.base_agent import BaseAgent
from core.nlu_client import NLUClient

logger = logging.getLogger(__name__)

# ── Issue type mapping ────────────────────────────────────────────────────────
# Maps NLU keywords / entity text → canonical issue_type
_ISSUE_TYPE_MAP: Dict[str, str] = {
    "fiber": "fiber_cut",
    "cable": "fiber_cut",
    "cut": "fiber_cut",
    "signal": "signal_degradation",
    "degradation": "signal_degradation",
    "antenna": "signal_degradation",
    "5g": "core_network_failure",
    "amf": "core_network_failure",
    "core": "core_network_failure",
    "billing": "billing_system_outage",
    "payment": "billing_system_outage",
    "invoice": "billing_system_outage",
    "backhaul": "backhaul_degradation",
    "microwave": "backhaul_degradation",
    "dns": "dns_failure",
    "domain": "dns_failure",
    "power": "power_failure",
    "generator": "power_failure",
    "capacity": "capacity_exhaustion",
    "congestion": "capacity_exhaustion",
    "volte": "software_bug",
    "voip": "software_bug",
    "drop": "signal_degradation",
    "outage": "signal_degradation",  # generic fallback
}

# ── Service type mapping ──────────────────────────────────────────────────────
_SERVICE_MAP: Dict[str, str] = {
    "4g": "4G_LTE",
    "lte": "4G_LTE",
    "5g": "5G_SA",
    "nr": "5G_SA",
    "wifi": "WiFi",
    "broadband": "Fixed_Broadband",
    "fiber": "Fixed_Broadband",
    "billing": "Billing",
    "volte": "VoLTE",
    "voip": "VoLTE",
    "backhaul": "Backhaul",
    "dns": "DNS",
}

# ── Priority escalation rules ─────────────────────────────────────────────────
# Terms that trigger Critical or High priority
_CRITICAL_TERMS = {"critical", "emergency", "major", "total", "complete", "all", "entire", "city"}
_HIGH_TERMS = {"high", "severe", "significant", "widespread", "large", "50000", "100000"}
_MEDIUM_TERMS = {"medium", "moderate", "several", "multiple", "partial"}


def _extract_issue_type(text_lower: str) -> str:
    """Return the best-matching issue type for a lowercased text string."""
    for keyword, issue_type in _ISSUE_TYPE_MAP.items():
        if keyword in text_lower:
            return issue_type
    return "unknown_issue"


def _extract_service(text_lower: str, entities: List[Dict[str, Any]]) -> str:
    """Identify the affected service from text and NLU entities."""
    for keyword, service in _SERVICE_MAP.items():
        if keyword in text_lower:
            return service
    # Fallback: check entity types
    for entity in entities:
        entity_text = entity.get("text", "").lower()
        for keyword, service in _SERVICE_MAP.items():
            if keyword in entity_text:
                return service
    return "Network"


def _extract_location(text: str, entities: List[Dict[str, Any]]) -> str:
    """Extract location reference from text or NLU entities."""
    # Check NLU Location entities first (most reliable)
    for entity in entities:
        if entity.get("type") in ("Location", "GeographicFeature"):
            return entity.get("text", "Unknown")
    # Fallback: look for sector/site patterns in text
    import re
    sector_match = re.search(r"\b(sector|site|zone|area|region|district)\s+[\w\-]+", text, re.I)
    if sector_match:
        return sector_match.group(0)
    return "Unknown Location"


def _assign_priority(text_lower: str, affected_count: int = 0) -> str:
    """Assign priority based on keywords and customer impact estimate."""
    if any(term in text_lower for term in _CRITICAL_TERMS) or affected_count > 50000:
        return "Critical"
    if any(term in text_lower for term in _HIGH_TERMS) or affected_count > 10000:
        return "High"
    if any(term in text_lower for term in _MEDIUM_TERMS) or affected_count > 1000:
        return "Medium"
    return "Low"


def _estimate_affected_count(text_lower: str) -> int:
    """Rough customer-count extraction from text (for priority scoring)."""
    import re
    # Look for patterns like "50k", "50,000", "50000 customers"
    match = re.search(r"(\d[\d,]*)\s*k?\s*(customers?|users?|subscribers?)?", text_lower)
    if match:
        num_str = match.group(1).replace(",", "")
        multiplier = 1000 if "k" in text_lower[match.start():match.end() + 2] else 1
        try:
            return int(num_str) * multiplier
        except ValueError:
            pass
    return 0


class IntentAgent(BaseAgent):
    """
    Classifies customer complaints into structured intents.

    Uses IBM NLU for entity extraction and rule-based logic for priority
    assignment. Input text is PII-masked before NLU analysis.
    """

    agent_name = "intent_recognition"
    required_output_fields = ["issue_type", "service", "priority", "confidence"]

    def __init__(self) -> None:
        super().__init__()
        self._nlu = NLUClient()

    async def _process_internal(
        self, safe_text: str, request: AgentRequest
    ) -> Tuple[Dict[str, Any], float]:
        """
        Run NLU analysis and derive structured intent from results.

        Args:
            safe_text: PII-masked customer complaint text.
            request:   Full agent request (context unused at this stage).

        Returns:
            (result dict, confidence float)
        """
        nlu_result = await self._nlu.analyze(safe_text)

        entities: List[Dict[str, Any]] = nlu_result.get("entities", [])
        keywords: List[Dict[str, Any]] = nlu_result.get("keywords", [])
        sentiment: Dict[str, Any] = nlu_result.get("sentiment", {})

        text_lower = safe_text.lower()
        issue_type = _extract_issue_type(text_lower)
        service = _extract_service(text_lower, entities)
        location = _extract_location(safe_text, entities)
        affected_count = _estimate_affected_count(text_lower)
        priority = _assign_priority(text_lower, affected_count)

        # Aggregate entity confidence (average of top-3 by confidence)
        entity_confidences = sorted(
            [e.get("confidence", 0.7) for e in entities], reverse=True
        )[:3]
        base_confidence = (
            sum(entity_confidences) / len(entity_confidences)
            if entity_confidences
            else 0.65
        )
        # Boost confidence if issue_type was specifically matched
        if issue_type != "unknown_issue":
            base_confidence = min(1.0, base_confidence + 0.05)

        # Group entities by type for richer output
        entity_groups: Dict[str, List[str]] = {}
        for entity in entities:
            etype = entity.get("type", "Other")
            entity_groups.setdefault(etype, []).append(entity.get("text", ""))

        result: Dict[str, Any] = {
            "issue_type": issue_type,
            "service": service,
            "location": location,
            "priority": priority,
            "confidence": round(base_confidence, 3),
            "sentiment": sentiment.get("label", "neutral"),
            "entities": entity_groups,
            "keywords": [kw.get("text", "") for kw in keywords[:5]],
            "affected_count_estimate": affected_count,
        }

        logger.info(
            "IntentAgent: issue_type=%s service=%s priority=%s confidence=%.2f",
            issue_type, service, priority, base_confidence,
        )

        return result, round(base_confidence, 3)
