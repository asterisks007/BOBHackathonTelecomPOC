"""
Agent 2 — Ticket Classification Agent.

Routes an incident to the correct operations queue, assigns severity (P1–P4),
and sets SLA response windows. Pure rule-based — no external IBM calls.

Input (payload fields from upstream context):
    issue_type (str): from IntentAgent output
    service    (str): from IntentAgent output
    priority   (str): from IntentAgent output (Critical|High|Medium|Low)
    location   (str): from IntentAgent output

Output:
    ticket_id        (str)  : INC-{YYYY}-{NNNNNN}
    queue            (str)  : target operations team
    severity         (str)  : P1 | P2 | P3 | P4
    category         (str)  : Infrastructure | Software | Operations | Billing
    sub_category     (str)  : detailed problem type
    sla_minutes      (int)  : resolution SLA in minutes
    assignment_group (str)  : specific team name
    confidence       (float): routing confidence

SLA target: <200ms (pure lookup, no I/O)
"""

import logging
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from api.models import AgentRequest
from core.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ── Routing table: issue_type → (queue, category, sub_category, assignment_group) ──
_ROUTING_TABLE: Dict[str, Dict[str, str]] = {
    "fiber_cut": {
        "queue": "Network_Operations",
        "category": "Infrastructure",
        "sub_category": "Fiber_Physical",
        "assignment_group": "Field_Operations_L2",
    },
    "signal_degradation": {
        "queue": "RAN_Operations",
        "category": "Infrastructure",
        "sub_category": "Radio_Access_Network",
        "assignment_group": "RAN_Engineering_L2",
    },
    "core_network_failure": {
        "queue": "Core_Network_Operations",
        "category": "Infrastructure",
        "sub_category": "Core_Network",
        "assignment_group": "Core_Engineering_L3",
    },
    "billing_system_outage": {
        "queue": "IT_Operations",
        "category": "Software",
        "sub_category": "Billing_Platform",
        "assignment_group": "BSS_Support_L2",
    },
    "backhaul_degradation": {
        "queue": "Transport_Operations",
        "category": "Infrastructure",
        "sub_category": "Transport_Backhaul",
        "assignment_group": "Transport_Engineering_L2",
    },
    "dns_failure": {
        "queue": "IT_Operations",
        "category": "Infrastructure",
        "sub_category": "DNS_Services",
        "assignment_group": "Network_Services_L2",
    },
    "power_failure": {
        "queue": "Field_Operations",
        "category": "Infrastructure",
        "sub_category": "Power_Systems",
        "assignment_group": "Field_Operations_L1",
    },
    "capacity_exhaustion": {
        "queue": "Network_Operations",
        "category": "Operations",
        "sub_category": "Capacity_Management",
        "assignment_group": "Capacity_Planning_L2",
    },
    "software_bug": {
        "queue": "Core_Network_Operations",
        "category": "Software",
        "sub_category": "Software_Defect",
        "assignment_group": "Core_Engineering_L3",
    },
    "unknown_issue": {
        "queue": "Network_Operations",
        "category": "Operations",
        "sub_category": "General_Inquiry",
        "assignment_group": "NOC_L1",
    },
}

# ── Priority → Severity + SLA minutes ────────────────────────────────────────
_SEVERITY_MAP: Dict[str, Dict[str, Any]] = {
    "Critical": {"severity": "P1", "sla_minutes": 240},   # 4 hours
    "High":     {"severity": "P2", "sla_minutes": 480},   # 8 hours
    "Medium":   {"severity": "P3", "sla_minutes": 1440},  # 24 hours
    "Low":      {"severity": "P4", "sla_minutes": 4320},  # 72 hours
}

# ── Routing confidence by category ───────────────────────────────────────────
_ROUTING_CONFIDENCE: Dict[str, float] = {
    "Infrastructure": 0.93,
    "Software": 0.89,
    "Operations": 0.85,
    "Billing": 0.91,
}


def _generate_ticket_id() -> str:
    """Generate a unique ticket ID in INC-{YYYY}-{NNNNNN} format."""
    year = datetime.now(timezone.utc).year
    suffix = "".join(random.choices(string.digits, k=6))
    return f"INC-{year}-{suffix}"


class TicketAgent(BaseAgent):
    """
    Routes incidents to operations queues and assigns ticket metadata.

    Pure rule-based logic — uses the intent output from upstream context.
    No external service calls required.
    """

    agent_name = "ticket_classification"
    required_output_fields = ["ticket_id", "queue", "severity", "sla_minutes"]

    async def _process_internal(
        self, safe_text: str, request: AgentRequest
    ) -> Tuple[Dict[str, Any], float]:
        """
        Derive ticket metadata from intent output in upstream context.

        Reads intent_recognition results from context.upstream_results if present,
        falls back to payload fields otherwise.
        """
        upstream = request.context.upstream_results
        intent = upstream.get("intent_recognition", {})

        # Pull intent fields — prefer upstream results, fall back to payload
        issue_type = intent.get("issue_type") or request.payload.get("issue_type", "unknown_issue")
        priority   = intent.get("priority")   or request.payload.get("priority", "Medium")
        service    = intent.get("service")    or request.payload.get("service", "Network")
        location   = intent.get("location")   or request.payload.get("location", "Unknown")

        # Routing lookup
        routing = _ROUTING_TABLE.get(issue_type, _ROUTING_TABLE["unknown_issue"])
        severity_info = _SEVERITY_MAP.get(priority, _SEVERITY_MAP["Medium"])

        ticket_id = _generate_ticket_id()
        category = routing["category"]
        confidence = _ROUTING_CONFIDENCE.get(category, 0.80)

        result: Dict[str, Any] = {
            "ticket_id": ticket_id,
            "queue": routing["queue"],
            "severity": severity_info["severity"],
            "category": category,
            "sub_category": routing["sub_category"],
            "sla_minutes": severity_info["sla_minutes"],
            "assignment_group": routing["assignment_group"],
            "issue_type": issue_type,
            "service": service,
            "location": location,
            "confidence": round(confidence, 3),
        }

        logger.info(
            "TicketAgent: ticket_id=%s queue=%s severity=%s sla=%dmin",
            ticket_id, routing["queue"], severity_info["severity"], severity_info["sla_minutes"],
        )

        return result, round(confidence, 3)
