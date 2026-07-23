# Agent Contract Docs � TelecoBOBot POC

Generated: 2026-07-22 | Status: ST-2 Complete

| Agent | Input (key fields) | Output (key fields) | SLA | Tests |
|---|---|---|---|---|
| intent_recognition | message (str) | issue_type, service, location, priority, confidence | <500ms | 45 |
| ticket_classification | issue_type, priority (from upstream) | ticket_id, queue, severity, sla_minutes | <200ms | 38 |
| rca_analysis | issue_type, service, location (upstream) | root_cause, evidence, recommendation, eta | <2000ms | 27 |
| escalation | severity, affected_count (upstream) | escalate, escalation_level, urgency, notify | <500ms | 20 |
| parallel_analysis | issue_type, severity (upstream) | customer_impact, network_impact, operational_impact | <1000ms | 22 |
| response_generation | rca+escalation+parallel (upstream) | resolution_steps, customer_message, automation_score | <1500ms | 26 |
| feedback | ticket+rca+escalation (upstream) | resolution_effective, csat, sla_met, learning_points | <500ms | 17 |

All agents:
- Inherit from BaseAgent (core/base_agent.py)
- Apply PII masking before processing
- Validate input and output via guardrails
- Write sanitised events to AuditLogger
- Return AgentResponse with status, result, metadata
- USE_MOCK=True default � zero real IBM calls

Full contract details are in each agent source file docstring.
