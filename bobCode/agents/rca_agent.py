"""
Agent 3 — Root Cause Analysis (RCA) Agent.

Queries the ChromaDB knowledge base for similar historical incidents,
then uses Granite LLM (mocked) to synthesise a root-cause hypothesis
with supporting evidence and resolution recommendation.

Input (upstream context):
    intent_recognition: issue_type, service, location, priority
    ticket_classification: ticket_id, severity

Output:
    root_cause          (str)  : primary cause statement
    confidence          (float): 0–1
    evidence            (list) : supporting evidence strings
    affected_services   (list) : impacted service names
    estimated_scope     (str)  : e.g. "3 cell sites, ~47k customers"
    recommendation      (str)  : immediate action to take
    estimated_resolution_minutes (int): ETA in minutes
    similar_incidents   (list) : IDs of similar past incidents
    cache_hit           (bool) : True if result served from RCA cache

SLA target: <2s (includes mock LLM + ChromaDB query)
"""

import hashlib
import logging
from typing import Any, Dict, List, Tuple

from api.models import AgentRequest
from core.base_agent import BaseAgent
from core.granite_client import GraniteClient
from core.vectorstore import VectorStore

logger = logging.getLogger(__name__)

# ── In-process RCA cache: (issue_type, location) → result ────────────────────
# Prevents duplicate LLM calls for identical incidents during demo
_RCA_CACHE: Dict[str, Dict[str, Any]] = {}

# ── Scope templates: issue_type → scope description ──────────────────────────
_SCOPE_TEMPLATES: Dict[str, str] = {
    "fiber_cut":            "Up to 3 cell sites, ~47k customers, backhaul affected",
    "signal_degradation":   "1 RAN sector, ~8k customers in coverage area",
    "core_network_failure": "All subscribers on affected core node, ~23k customers",
    "billing_system_outage":"All customer self-service, no data impact",
    "backhaul_degradation": "2–5 cell sites downstream, ~15k customers",
    "dns_failure":          "All subscribers relying on primary DNS, ~95k customers",
    "power_failure":        "Single cell site, ~5.5k customers",
    "capacity_exhaustion":  "All users in high-density zone, ~12k customers",
    "software_bug":         "All VoLTE subscribers, ~32k customers",
    "unknown_issue":        "Scope under investigation",
}

# ── Resolution ETA templates ──────────────────────────────────────────────────
_ETA_MAP: Dict[str, int] = {
    "fiber_cut": 120,
    "signal_degradation": 45,
    "core_network_failure": 60,
    "billing_system_outage": 40,
    "backhaul_degradation": 180,
    "dns_failure": 25,
    "power_failure": 240,
    "capacity_exhaustion": 90,
    "software_bug": 55,
    "unknown_issue": 120,
}


def _cache_key(issue_type: str, location: str) -> str:
    """Generate a deterministic cache key from issue type and location."""
    raw = f"{issue_type}:{location}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()


def _build_llm_prompt(issue_type: str, service: str, location: str,
                      similar_docs: List[Dict[str, Any]]) -> str:
    """
    Build a compact LLM prompt using top-3 similar incident context.
    Keeps token count minimal — uses at most 3 context documents.
    """
    context_lines = []
    for doc in similar_docs[:3]:
        snippet = doc["document"][:200].replace("\n", " ")
        context_lines.append(f"- {snippet}")
    context = "\n".join(context_lines) if context_lines else "No similar incidents found."

    return (
        f"Telecom incident analysis:\n"
        f"Issue: {issue_type} on {service} at {location}.\n"
        f"Similar past incidents:\n{context}\n"
        f"Provide a concise root cause and immediate recommendation."
    )


def _extract_evidence(similar_docs: List[Dict[str, Any]], issue_type: str) -> List[str]:
    """Build an evidence list from similar incident metadata."""
    evidence = []
    for doc in similar_docs[:3]:
        meta = doc.get("metadata", {})
        incident_type = meta.get("type", "")
        if incident_type == issue_type:
            evidence.append(
                f"Similar incident ({meta.get('type', 'N/A')}): "
                f"MTTR {meta.get('mttr_minutes', '?')} min, "
                f"severity {meta.get('severity', '?')}"
            )
    if not evidence:
        evidence = ["Historical pattern match from knowledge base"]
    return evidence


class RCAAgent(BaseAgent):
    """
    Performs Root Cause Analysis using RAG + Granite LLM.

    Process:
      1. Check RCA cache for identical (issue_type, location) pairs
      2. Query ChromaDB for top-5 similar incidents
      3. Build minimal LLM prompt with top-3 context chunks
      4. Parse LLM output into structured result
    """

    agent_name = "rca_analysis"
    required_output_fields = ["root_cause", "recommendation", "confidence"]

    def __init__(self) -> None:
        super().__init__()
        self._granite = GraniteClient()
        self._vectorstore = VectorStore()

    async def _process_internal(
        self, safe_text: str, request: AgentRequest
    ) -> Tuple[Dict[str, Any], float]:
        upstream = request.context.upstream_results
        intent   = upstream.get("intent_recognition", {})
        ticket   = upstream.get("ticket_classification", {})

        issue_type = intent.get("issue_type", request.payload.get("issue_type", "unknown_issue"))
        service    = intent.get("service",    request.payload.get("service", "Network"))
        location   = intent.get("location",   request.payload.get("location", "Unknown"))
        severity   = ticket.get("severity",   "P2")

        # ── 1. Cache check ────────────────────────────────────────────────────
        cache_key = _cache_key(issue_type, location)
        if cache_key in _RCA_CACHE:
            cached = dict(_RCA_CACHE[cache_key])
            cached["cache_hit"] = True
            logger.info("RCAAgent: cache hit key=%s", cache_key)
            return cached, cached.get("confidence", 0.85)

        # ── 2. ChromaDB similarity search ─────────────────────────────────────
        query_text = f"{issue_type} {service} {location}"
        try:
            similar_docs = self._vectorstore.query(query_text, k=5)
        except Exception as exc:
            logger.warning("RCAAgent: vectorstore query failed: %s", exc)
            similar_docs = []

        # ── 3. LLM generation ─────────────────────────────────────────────────
        prompt = _build_llm_prompt(issue_type, service, location, similar_docs)
        llm_output = await self._granite.generate(prompt, max_new_tokens=256)

        # ── 4. Assemble result ────────────────────────────────────────────────
        evidence = _extract_evidence(similar_docs, issue_type)
        similar_ids = [d["id"] for d in similar_docs[:3]]
        scope = _SCOPE_TEMPLATES.get(issue_type, _SCOPE_TEMPLATES["unknown_issue"])
        eta = _ETA_MAP.get(issue_type, 120)

        # Confidence: higher for known issue types with strong evidence
        confidence = 0.88 if similar_docs and issue_type != "unknown_issue" else 0.65
        if severity == "P1":
            confidence = min(1.0, confidence + 0.05)

        result: Dict[str, Any] = {
            "root_cause": llm_output,
            "confidence": round(confidence, 3),
            "evidence": evidence,
            "affected_services": [service],
            "estimated_scope": scope,
            "recommendation": llm_output.split(". ")[-1] if "." in llm_output else llm_output,
            "estimated_resolution_minutes": eta,
            "similar_incidents": similar_ids,
            "cache_hit": False,
        }

        # Store in cache for subsequent identical requests
        _RCA_CACHE[cache_key] = result

        logger.info(
            "RCAAgent: issue_type=%s confidence=%.2f eta=%dmin similar=%d",
            issue_type, confidence, eta, len(similar_ids),
        )

        return result, round(confidence, 3)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the RCA result cache (test use only)."""
        _RCA_CACHE.clear()
