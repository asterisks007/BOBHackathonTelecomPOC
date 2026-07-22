"""
Agent 4 — Escalation Agent.

Applies a decision tree to determine whether and how to escalate an incident.
Pure rule-based — no external service calls.

Input (upstream context):
    intent_recognition:    priority, issue_type, affected_count_estimate
    ticket_classification: severity, queue
    rca_analysis:          confidence, estimated_scope

Output:
    escalate          (bool)  : whether escalation is required
    escalation_level  (str)   : None | Operational | Management | Executive
    reason            (str)   : human-readable justification
    notify            (list)  : email group aliases to alert
    urgency           (str)   : Standard | High | Critical
    estimated_cost    (str)   : rough revenue-impact estimate
    confidence        (float) : decision confidence

SLA target: <500ms (decision tree, no I/O)
"""

import logging
from typing import Any, Dict, List, Tuple

from api.models import AgentRequest
from core.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ── Escalation rules: severity + scope → level ───────────────────────────────
# Rules are evaluated in order; first match wins.
_ESCALATION_RULES: List[Dict[str, Any]] = [
    {
        "condition": lambda sev, scope, count: sev == "P1" and count > 50000,
        "level": "Executive",
        "urgency": "Critical",
        "notify": ["network-ops@telecomco.internal", "exec-oncall@telecomco.internal",
                   "pr-team@telecomco.internal"],
        "cost": "$100k+ revenue impact per hour",
        "reason": "P1 incident affecting >50k customers — executive notification required",
    },
    {
        "condition": lambda sev, scope, count: sev == "P1",
        "level": "Management",
        "urgency": "Critical",
        "notify": ["network-ops@telecomco.internal", "mgmt-oncall@telecomco.internal"],
        "cost": "$50k+ revenue impact",
        "reason": "P1 severity — management escalation required per SLA policy",
    },
    {
        "condition": lambda sev, scope, count: sev == "P2" and count > 10000,
        "level": "Operational",
        "urgency": "High",
        "notify": ["network-ops@telecomco.internal", "noc-lead@telecomco.internal"],
        "cost": "$10k–$50k estimated impact",
        "reason": "P2 incident with significant customer impact",
    },
    {
        "condition": lambda sev, scope, count: sev == "P2",
        "level": "Operational",
        "urgency": "High",
        "notify": ["network-ops@telecomco.internal"],
        "cost": "Moderate customer impact",
        "reason": "P2 severity — operational escalation required",
    },
]

_NO_ESCALATION = {
    "escalate": False,
    "escalation_level": "None",
    "urgency": "Standard",
    "notify": [],
    "estimated_cost": "Minimal impact",
    "reason": "Severity P3/P4 — standard handling, no escalation required",
    "confidence": 0.92,
}


def _extract_affected_count(estimated_scope: str) -> int:
    """Parse rough customer count from an estimated_scope string."""
    import re
    match = re.search(r"~?([\d,]+)\s*k?\s*customers?", estimated_scope, re.I)
    if match:
        num = int(match.group(1).replace(",", ""))
        if "k" in estimated_scope[match.start():match.end() + 2].lower():
            num *= 1000
        return num
    return 0


class EscalationAgent(BaseAgent):
    """
    Evaluates incident risk and decides escalation level.

    Uses a priority-ordered decision tree combining severity,
    affected customer count, and issue type.
    """

    agent_name = "escalation"
    required_output_fields = ["escalate", "escalation_level", "urgency"]

    async def _process_internal(
        self, safe_text: str, request: AgentRequest
    ) -> Tuple[Dict[str, Any], float]:
        upstream = request.context.upstream_results
        intent = upstream.get("intent_recognition", {})
        ticket = upstream.get("ticket_classification", {})
        rca    = upstream.get("rca_analysis", {})

        severity      = ticket.get("severity", request.payload.get("severity", "P3"))
        issue_type    = intent.get("issue_type", request.payload.get("issue_type", "unknown_issue"))
        estimated_scope = rca.get("estimated_scope", "")
        raw_count = intent.get("affected_count_estimate", 0)
        scope_count = _extract_affected_count(estimated_scope)
        affected_count = max(raw_count, scope_count)

        # Evaluate rules in priority order
        for rule in _ESCALATION_RULES:
            if rule["condition"](severity, estimated_scope, affected_count):
                result: Dict[str, Any] = {
                    "escalate": True,
                    "escalation_level": rule["level"],
                    "urgency": rule["urgency"],
                    "notify": list(rule["notify"]),
                    "estimated_cost": rule["cost"],
                    "reason": rule["reason"],
                    "issue_type": issue_type,
                    "severity": severity,
                    "affected_count": affected_count,
                    "confidence": 0.92,
                }
                logger.info(
                    "EscalationAgent: ESCALATE level=%s urgency=%s count=%d",
                    rule["level"], rule["urgency"], affected_count,
                )
                return result, 0.92

        # No escalation
        result = dict(_NO_ESCALATION)
        result.update({"issue_type": issue_type, "severity": severity, "affected_count": affected_count})
        logger.info("EscalationAgent: no escalation severity=%s count=%d", severity, affected_count)
        return result, result["confidence"]
