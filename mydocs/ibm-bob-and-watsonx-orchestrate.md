# IBM Bob & watsonx Orchestrate Integration Guide

## Overview

The **Telecom Outage Resolution BOB** platform uses a **watsonx Orchestrate-Centric Multi-Agent Architecture**. Rather than relying on a traditional monolithic chatbot, **IBM watsonx Orchestrate** serves as the cloud Master Agent that orchestrates conversational skills, delegates outage reports to **IBM BOB**'s 7-agent microservices pipeline, and coordinates automated ticket management, root cause analysis (RCA), and resolution actions.

---

## High-Level Architecture & Interaction Flow

```
                               ┌──────────────────────────────────────────┐
                               │     Customer / NOC Engineer / Admin      │
                               └────────────────────┬─────────────────────┘
                                                    │
                                                    ▼
                               ┌──────────────────────────────────────────┐
                               │        IBM watsonx Orchestrate           │
                               │        (Cloud Master Agent Skills)       │
                               └────────────────────┬─────────────────────┘
                                                    │
                             OpenAPI Webhook        │  (POST /webhook/orchestrate)
                             (HTTPS / ngrok / CE)   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    IBM BOB 7-Agent Backend                                       │
│                                                                                                 │
│  ┌────────────────┐    ┌────────────────┐    ┌─────────────────┐    ┌────────────────────────┐  │
│  │ 1. Intent Agent│───►│ 2. Ticket Agent│───►│  3. RCA Agent   │───►│  4. Escalation Agent   │  │
│  │  (Watson NLU)  │    │ (Cloudant DB)  │    │ (ChromaDB RAG)  │    │     (SLA Rules)        │  │
│  └────────────────┘    └────────────────┘    └─────────────────┘    └────────────────────────┘  │
│                                                                                  │              │
│  ┌────────────────┐    ┌────────────────┐    ┌─────────────────┐                 │              │
│  │7.Feedback Agent│◄───│6.Resolutn Agent│◄───│5. Parallel Agent│◄────────────────┘              │
│  │ (Audit Trail)  │    │  (Granite LLM) │    │(Impact Analysis)│                                 │
│  └────────────────┘    └────────────────┘    └─────────────────┘                                 │
└───────────────────────────┬─────────────────────────────────────────────────────┘
                                            │ Writes Ticket
                                            ▼
                               ┌──────────────────────────────────────────┐
                               │           IBM Cloudant DB                │
                               │           (Tickets Store)                │
                               └──────────────────────────────────────────┘
```

---

## 1. Role of IBM watsonx Orchestrate

**watsonx Orchestrate** acts as the intelligent front-end conversational orchestrator and skill router:

* **Natural Language Intent Triggering**: When a user submits an outage complaint (e.g., *"Fibercut at Purbalok Kalibari"*), watsonx Orchestrate matches the intent and invokes the relevant skill.
* **OpenAPI Skill Specs**: All endpoints of the backend Python FastAPI service are described in `bobCode/openapi/skills_spec.json`. Importing this OpenAPI spec into watsonx Orchestrate exposes the following skills:
  * `watson_orchestrate_webhook` (`POST /webhook/orchestrate`): Main end-to-end skill triggering the 7-agent execution.
  * `intent_agent`, `ticket_agent`, `rca_agent`, `escalation_agent`, `parallel_agent`, `resolution_agent`, `feedback_agent`: Micro-skills for granular stage execution.
* **Session & Context Management**: Orchestrate passes `session_id`, `customer_id`, and `message` payloads to the backend webhooks while enforcing Bearer token authentication.

---

## 2. Role of IBM BOB (Back-Office Operations Automation)

**IBM BOB** is the backend execution engine that executes the multi-agent AI pipeline and integrates with IBM Cloud services:

### A. The 7-Agent Microservices Pipeline
1. **Intent Agent**: Uses **IBM Watson NLU** (or mock mode) to extract entities, sentiment, and outage categories.
2. **Ticket Agent**: Formats structured incident metadata and writes ticket records directly to **IBM Cloudant NoSQL DB**.
3. **RCA Agent**: Runs semantic RAG search over local **ChromaDB** vector embeddings to identify historical fiber cut / antenna failure patterns.
4. **Escalation Agent**: Evaluates SLA thresholds (P1/P2) and flags management escalation requirements.
5. **Parallel Analysis Agent**: Computes customer impact, affected cell towers, and estimated financial risk concurrently.
6. **Resolution Agent**: Queries **IBM watsonx.ai (Granite 13B LLM)** to generate step-by-step technical dispatch instructions and customer notification text.
7. **Feedback Agent**: Writes audit trails and self-learning feedback scores.

### B. Security & PII Protection
Before writing any ticket payload to Cloudant DB, IBM BOB executes **PII Guardrails** to sanitize customer names, phone numbers, and sensitive addresses, ensuring GDPR/telecom privacy compliance.

---

## 3. How to Run & Connect Locally

### Step 1: Start the Backend with `uvicorn`
Navigate to `bobCode` and run the FastAPI server inside your virtual environment (`.venv`):

```powershell
# Navigate to bobCode directory
cd bobCode

# Activate virtual environment (PowerShell)
..\.venv\Scripts\Activate.ps1

# Run Uvicorn server
uvicorn api.main:app --reload --port 8000
```

### Step 2: Expose via `ngrok` for watsonx Orchestrate Webhooks
Since watsonx Orchestrate runs in the IBM Cloud, expose your local port `8000`:

```bash
ngrok http 8000
```

### Step 3: Import Skill into watsonx Orchestrate
1. Open the **Watson Orchestrate Console**.
2. Go to **Skills** → **Add skill** → **From OpenAPI file**.
3. Upload `bobCode/openapi/skills_spec.json` (updating the `servers.url` to your active `ngrok` HTTPS address).
4. Save and test the `watson_orchestrate_webhook` skill.

---

## Reference Documentation Files

* 📄 **OpenAPI Specification & Guide**: [bobCode/openapi/README.md](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/bobCode/openapi/README.md)
* 📄 **Laptop & ngrok Setup Guide**: [mydocs/option-2-local-laptop-ngrok-watsonx-orchestrate-guide.md](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/mydocs/option-2-local-laptop-ngrok-watsonx-orchestrate-guide.md)
* 📄 **IBM Cloud Deployment Guide**: [mydocs/ibm-cloud-deployment-guide.md](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/mydocs/ibm-cloud-deployment-guide.md)
