"""
Agent 7 — Feedback Agent.

Post-resolution validation: computes MTTR, customer satisfaction estimate,
preventive action recommendations, and learning points for continuous improvement.
Writes the closed-loop feedback record to Cloudant.

Input (upstream context):
    ticket_classification: ticket_id, severity, sla_minutes
    rca_analysis:         root_cause, estimated_resolution_minutes, confidence
    parallel_analysis:    customer_impact
    escalation:           escalation_level

Output:
    resolution_effective     (bool)
    time_to_resolution       (int)   : actual/estimated minutes
    customer_satisfaction    (float) : 1–5 scale (estimated)
    preventive_action        (str)   : recommended follow-up
    learning_points          (list)  : key takeaways
    recommended_changes      (list)  : systemic improvements
    sla_met                  (bool)  : was SLA achieved
    confidence               (float)

SLA target: <500ms (async write, no LLM)
"""

import logging
from typing import Any, Dict, List, Tuple

from api.models import AgentRequest
from core.audit import AuditLogger
from core.base_agent import BaseAgent
from core.cloudant_client import CloudantClient

logger = logging.getLogger(__name__)

# ── Preventive action lookup ──────────────────────────────────────────────────
_PREVENTIVE_ACTIONS: Dict[str, str] = {
    "fiber_cut": "Install conduit markers; notify construction companies; add redundant fiber paths",
    "signal_degradation": "Add wind-speed monitoring on exposed towers; enable SON auto-correction",
    "core_network_failure": "Implement staged rollout with automated rollback triggers for core SW",
    "billing_system_outage": "Schedule batch jobs in maintenance windows; increase connection pool",
    "backhaul_degradation": "Configure automatic traffic re-routing at 80% utilisation threshold",
    "dns_failure": "Implement disk-usage alerting at 80%; enforce log rotation on all services",
    "power_failure": "Upgrade UPS capacity; add generator auto-start; increase fuel check frequency",
    "capacity_exhaustion": "Integrate event calendar into capacity planning; pre-position COWs",
    "software_bug": "Add KPI-based rollback triggers; enforce staged rollout; improve test coverage",
    "unknown_issue": "Conduct full RCA; update runbook with findings",
}

# ── CSAT estimation: severity + escalation → satisfaction score ───────────────
_CSAT_TABLE: Dict[str, float] = {
    "P1_Executive": 2.8,
    "P1_Management": 3.2,
    "P1_Operational": 3.5,
    "P1_None": 3.7,
    "P2_Operational": 3.9,
    "P2_None": 4.0,
    "P3_None": 4.2,
    "P4_None": 4.4,
}


def _estimate_csat(severity: str, escalation_level: str) -> float:
    """Estimate customer satisfaction based on severity and escalation."""
    key = f"{severity}_{escalation_level}"
    return _CSAT_TABLE.get(key, 3.8)


def _build_learning_points(
    issue_type: str, rca_confidence: float, csat: float, sla_met: bool
) -> List[str]:
    """Generate learning points based on incident outcome metrics."""
    points = []
    if rca_confidence >= 0.85:
        points.append(f"RCA confidence {rca_confidence:.0%} — pattern well-understood")
    else:
        points.append("RCA confidence below 85% — knowledge base should be enriched")
    if not sla_met:
        points.append("SLA missed — review escalation thresholds and runbook steps")
    if csat < 3.5:
        points.append("Low CSAT score — improve customer communication frequency")
    points.append(f"Issue type '{issue_type}' logged for trend analysis")
    return points


def _build_recommended_changes(issue_type: str, escalation_level: str) -> List[str]:
    """Suggest systemic improvements based on incident characteristics."""
    changes = []
    preventive = _PREVENTIVE_ACTIONS.get(issue_type, "")
    if preventive:
        changes.append(preventive)
    if escalation_level in ("Executive", "Management"):
        changes.append("Review escalation matrix — executive escalation indicates gap in earlier detection")
    changes.append("Update runbook with latest resolution steps and timings")
    return changes


class FeedbackAgent(BaseAgent):
    """
    Collects post-resolution metrics and writes a feedback record to Cloudant.

    Estimates CSAT, checks SLA compliance, and generates learning points
    for continuous improvement.
    """

    agent_name = "feedback"
    required_output_fields = ["resolution_effective", "customer_satisfaction", "sla_met"]

    def __init__(self) -> None:
        super().__init__()
        self._cloudant = CloudantClient()

    async def _process_internal(
        self, safe_text: str, request: AgentRequest
    ) -> Tuple[Dict[str, Any], float]:
        upstream = request.context.upstream_results
        ticket    = upstream.get("ticket_classification", {})
        rca       = upstream.get("rca_analysis", {})
        escalation = upstream.get("escalation", {})
        parallel  = upstream.get("parallel_analysis", {})
        intent    = upstream.get("intent_recognition", {})

        ticket_id      = ticket.get("ticket_id", request.payload.get("ticket_id", "INC-UNKNOWN"))
        severity       = ticket.get("severity", "P3")
        sla_minutes    = ticket.get("sla_minutes", 480)
        issue_type     = intent.get("issue_type", "unknown_issue")
        rca_confidence = rca.get("confidence", 0.70)
        eta            = rca.get("estimated_resolution_minutes", 120)
        escalation_level = escalation.get("escalation_level", "None")

        # ── Compute metrics ───────────────────────────────────────────────────
        time_to_resolution = eta  # In live mode: actual ticket close time
        sla_met = time_to_resolution <= sla_minutes
        csat = _estimate_csat(severity, escalation_level)
        resolution_effective = rca_confidence >= 0.70

        learning_points = _build_learning_points(issue_type, rca_confidence, csat, sla_met)
        recommended_changes = _build_recommended_changes(issue_type, escalation_level)

        confidence = 0.88

        result: Dict[str, Any] = {
            "resolution_effective": resolution_effective,
            "time_to_resolution": time_to_resolution,
            "customer_satisfaction": round(csat, 1),
            "preventive_action": _PREVENTIVE_ACTIONS.get(issue_type, "Review and update runbook"),
            "learning_points": learning_points,
            "recommended_changes": recommended_changes,
            "sla_met": sla_met,
            "ticket_id": ticket_id,
            "issue_type": issue_type,
            "confidence": round(confidence, 3),
        }

        # ── Write feedback record to Cloudant ─────────────────────────────────
        feedback_doc = {
            "type": "feedback_record",
            "ticket_id": ticket_id,
            "issue_type": issue_type,
            "severity": severity,
            "sla_met": sla_met,
            "csat": csat,
            "rca_confidence": rca_confidence,
            "time_to_resolution": time_to_resolution,
        }
        await self._cloudant.save("audit_trail", feedback_doc)

        # Extra audit log entry for the closed loop
        await AuditLogger.log_event(
            "incident_closed",
            {"ticket_id": ticket_id, "sla_met": sla_met, "csat": csat},
            request.request_id,
            self.agent_name,
        )

        logger.info(
            "FeedbackAgent: ticket=%s sla_met=%s csat=%.1f learning=%d",
            ticket_id, sla_met, csat, len(learning_points),
        )

        return result, round(confidence, 3)
