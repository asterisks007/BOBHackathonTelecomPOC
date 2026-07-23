"""
Agent 6 — Response Generation Agent.

Generates structured resolution steps and a customer-facing communication
template from upstream RCA and impact analysis results.

Uses Granite LLM (mocked) for personalised message text.
Resolution steps are template-based with LLM polish.

Input (upstream context):
    rca_analysis:        root_cause, recommendation, estimated_resolution_minutes
    escalation:          escalate, escalation_level, urgency
    parallel_analysis:   customer_impact, network_impact, operational_impact
    ticket_classification: ticket_id, severity

Output:
    resolution_steps     (list) : ordered action steps
    automation_possible  (bool) : can steps be automated
    automation_score     (float): 0–1 confidence in automation
    customer_message     (str)  : sanitised customer-facing text
    internal_notes       (str)  : ops team summary
    estimated_resolution_time (int): minutes
    confidence           (float)

SLA target: <1.5s
"""

import logging
from typing import Any, Dict, List, Tuple

from api.models import AgentRequest
from core.base_agent import BaseAgent
from core.granite_client import GraniteClient

logger = logging.getLogger(__name__)

# ── Resolution step templates per issue type ──────────────────────────────────
_RESOLUTION_TEMPLATES: Dict[str, List[str]] = {
    "fiber_cut": [
        "1. Confirm fiber cut location via OTDR — correlate with alarm data",
        "2. Activate BGP failover to backup fiber route immediately",
        "3. Dispatch fiber repair crew with splice equipment to fault location",
        "4. Monitor traffic recovery on primary path — target: 80%+ within 15 min",
        "5. Update ticket with ETA and send customer notification",
        "6. Conduct post-incident review within 48 hours",
    ],
    "signal_degradation": [
        "1. Identify affected sector via RAN KPI dashboard",
        "2. Attempt remote antenna tilt/azimuth correction via REM system",
        "3. Compare current vs. baseline antenna parameters",
        "4. If remote correction fails, dispatch field crew for inspection",
        "5. Monitor RSRP/RSRQ and handover success rate",
    ],
    "core_network_failure": [
        "1. Identify failed core network element (AMF/MME/SMF)",
        "2. Check software version — if recently updated, initiate rollback",
        "3. Restart standby node and verify session continuity",
        "4. Monitor subscriber registration rate — target normal within 10 min",
        "5. Contact vendor if rollback unavailable",
    ],
    "billing_system_outage": [
        "1. Identify root cause: DB connection, application crash, or disk issue",
        "2. Terminate any runaway batch jobs or queries",
        "3. Restart billing application with increased connection pool",
        "4. Validate customer portal access and payment processing",
        "5. Schedule post-mortem to prevent recurrence",
    ],
    "dns_failure": [
        "1. Verify DNS server disk usage — clear logs if full",
        "2. Restart primary DNS service",
        "3. Confirm secondary DNS is handling load correctly",
        "4. Validate resolution time from multiple vantage points",
        "5. Apply log rotation policy to prevent recurrence",
    ],
    "power_failure": [
        "1. Confirm UPS status and remaining battery capacity",
        "2. Contact utility provider for grid restoration ETA",
        "3. Deploy mobile generator if UPS depletion is imminent",
        "4. Monitor cell site recovery via NMS after power restored",
        "5. Schedule UPS battery inspection and replacement",
    ],
    "backhaul_degradation": [
        "1. Identify affected backhaul link via transport NMS",
        "2. Reroute traffic to backup path immediately",
        "3. Analyse link degradation cause (rain fade, hardware fault)",
        "4. Request additional capacity from transport team if needed",
        "5. Monitor link performance and revert primary when stable",
    ],
    "capacity_exhaustion": [
        "1. Identify overloaded cells and confirm capacity saturation",
        "2. Deploy mobile cells (COW) to affected area",
        "3. Activate traffic prioritisation — voice over data",
        "4. Apply temporary video quality caps (720p max)",
        "5. Integrate event calendar into capacity planning process",
    ],
    "software_bug": [
        "1. Confirm software version causing the issue",
        "2. Execute emergency rollback to last known good version",
        "3. Verify service KPIs return to baseline after rollback",
        "4. File detailed bug report with vendor",
        "5. Schedule fix validation before re-deploying new version",
    ],
    "unknown_issue": [
        "1. Escalate to L2 network operations with full diagnostic logs",
        "2. Collect NMS alarms, KPI snapshots, and recent change log",
        "3. Engage RCA process — assign incident owner",
        "4. Communicate estimated investigation time to stakeholders",
    ],
}

# ── Automation scoring rules ──────────────────────────────────────────────────
_AUTOMATION_SCORES: Dict[str, float] = {
    "dns_failure": 0.90,
    "billing_system_outage": 0.75,
    "signal_degradation": 0.70,
    "software_bug": 0.65,
    "core_network_failure": 0.60,
    "capacity_exhaustion": 0.55,
    "backhaul_degradation": 0.50,
    "fiber_cut": 0.30,       # Requires physical crew — hard to automate
    "power_failure": 0.25,
    "unknown_issue": 0.20,
}

_CUSTOMER_MESSAGE_TEMPLATE = (
    "We are aware of a service issue affecting your {service} connection in your area. "
    "Our engineering team has identified the root cause and is working to restore service. "
    "Estimated restoration time: {eta} minutes. "
    "Ticket reference: {ticket_id}. We apologise for the inconvenience."
)


class ResolutionAgent(BaseAgent):
    """
    Generates resolution steps and customer communication from upstream context.

    Uses template-based steps for reliability and Granite LLM (mocked)
    for personalised customer-facing message text.
    """

    agent_name = "response_generation"
    required_output_fields = ["resolution_steps", "customer_message", "automation_score"]

    def __init__(self) -> None:
        super().__init__()
        self._granite = GraniteClient()

    async def _process_internal(
        self, safe_text: str, request: AgentRequest
    ) -> Tuple[Dict[str, Any], float]:
        upstream = request.context.upstream_results
        rca      = upstream.get("rca_analysis", {})
        ticket   = upstream.get("ticket_classification", {})
        escalation = upstream.get("escalation", {})
        parallel = upstream.get("parallel_analysis", {})
        intent   = upstream.get("intent_recognition", {})

        issue_type = intent.get("issue_type", request.payload.get("issue_type", "unknown_issue"))
        service    = intent.get("service",    request.payload.get("service", "Network"))
        ticket_id  = ticket.get("ticket_id",  request.payload.get("ticket_id", "INC-PENDING"))
        eta        = rca.get("estimated_resolution_minutes", 120)
        severity   = ticket.get("severity", "P2")

        # ── 1. Resolution steps from template ─────────────────────────────────
        steps = list(_RESOLUTION_TEMPLATES.get(issue_type, _RESOLUTION_TEMPLATES["unknown_issue"]))

        # ── 2. Automation score ───────────────────────────────────────────────
        automation_score = _AUTOMATION_SCORES.get(issue_type, 0.40)
        automation_possible = automation_score >= 0.60

        # ── 3. Customer message (LLM for personalisation) ─────────────────────
        prompt = (
            f"Write a brief, professional customer notification for a {issue_type} "
            f"affecting {service} service. ETA: {eta} minutes. Ticket: {ticket_id}. "
            f"Be empathetic and avoid technical jargon."
        )
        llm_message = await self._granite.generate(prompt, max_new_tokens=128)

        # Use template as fallback if LLM output is too short
        customer_message = (
            llm_message if len(llm_message) > 30
            else _CUSTOMER_MESSAGE_TEMPLATE.format(
                service=service, eta=eta, ticket_id=ticket_id
            )
        )

        # ── 4. Internal ops notes ─────────────────────────────────────────────
        root_cause = rca.get("root_cause", "Under investigation")[:200]
        escalated  = escalation.get("escalate", False)
        affected   = parallel.get("customer_impact", {}).get("affected_customers", 0)
        internal_notes = (
            f"Issue: {issue_type} | Severity: {severity} | "
            f"Escalated: {escalated} | Affected: {affected} customers | "
            f"RCA: {root_cause}"
        )

        confidence = 0.88 if issue_type != "unknown_issue" else 0.70

        result: Dict[str, Any] = {
            "resolution_steps": steps,
            "automation_possible": automation_possible,
            "automation_score": round(automation_score, 3),
            "customer_message": customer_message,
            "internal_notes": internal_notes,
            "estimated_resolution_time": eta,
            "ticket_id": ticket_id,
            "issue_type": issue_type,
            "confidence": round(confidence, 3),
        }

        logger.info(
            "ResolutionAgent: issue=%s steps=%d automation=%.2f eta=%dmin",
            issue_type, len(steps), automation_score, eta,
        )

        return result, round(confidence, 3)
