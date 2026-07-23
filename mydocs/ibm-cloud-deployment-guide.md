# IBM Cloud Deployment Guide — Telecom Outage Resolution BOB

**Project**: BOBHackathonTelecomPOC  
**Target Platform**: IBM Cloud (watsonx Orchestrate + IBM Cloud Code Engine + Cloudant + watsonx.ai + IBM NLU)  
**Version**: 1.0 | **Updated**: 2026-07-23  

---

## Executive Summary & Architecture Overview

This document provides a granular, production-ready guide for deploying the **Telecom Outage Resolution BOB** to **IBM Cloud**. 

The solution uses a **watsonx Orchestrate-Centric Multi-Agent Architecture**:
- **watsonx Orchestrate**: Functions as the central **Master Agent / Orchestrator Platform**, managing user conversations, goal decomposition, skill selection, state tracking, and execution flow.
- **FastAPI (Python 3.14)**: Deployed on **IBM Cloud Code Engine** as the **Intelligence & Skill Server**, hosting 7 specialized agent skills, security guardrails (PII masking & input validation), and the embedded **ChromaDB Vector DB** for RAG lookups.
- **React 19 + Vite 8 + TypeScript**: Deployed as a containerized static application on **IBM Cloud Code Engine** (or hosted via IBM Cloud Object Storage + CDN), embedding the watsonx Orchestrate Webchat widget.
- **IBM Managed Services**:
  - **watsonx.ai**: Powers Granite 13B LLM reasoning for RCA and response generation.
  - **IBM NLU**: Performs intent recognition and entity extraction.
  - **IBM Cloudant**: NoSQL storage for incident tickets and immutable audit logs.
  - **IBM BOB**: Workflow automation triggering ticket writes to Cloudant on skill completion.

---

## Multi-Agent System Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REACT 19 + VITE 8 FRONTEND                        │
│                   (Embeds watsonx Orchestrate Chat / API)                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        WATSONX ORCHESTRATE PLATFORM                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │             Master Agent: "Telecom Outage Resolver"                 │   │
│   │            (Granite LLM + Custom Agent Decision Planner)            │   │
│   └──────┬──────────┬──────────┬───────────┬───────────┬──────────┬─────┘   │
│          │          │          │           │           │          │         │
│     Intent Skill Ticket Skill RCA Skill Escalation Parallel Resolution Feedback │
└──────────┼──────────┼──────────┼───────────┼──────────┼──────────┼─────────┘
           │          │          │           │           │          │
           │  HTTPS REST over OpenAPI Spec (bobCode/openapi/skills_spec.json)
           ▼          ▼          ▼           ▼           ▼          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 FASTAPI BACKEND SERVICE (IBM Cloud Code Engine)             │
│                                                                             │
│   ┌───────────────────────────┐         ┌───────────────────────────────┐   │
│   │   Security Guardrails     │         │    ChromaDB Vector DB         │   │
│   │ (PII Masking & Input Check)│        │   (Local persistent RAG store)│   │
│   └───────────────────────────┘         └───────────────────────────────┘   │
│                                                                             │
│   REST Endpoints: /agents/intent | /agents/ticket | /agents/rca | ...      │
└──────────────┬──────────────────────────────────────────────┬───────────────┘
               │                                              │
               ▼                                              ▼
   ┌──────────────────────┐                       ┌──────────────────────┐
   │    IBM Cloudant DB   │                       │    watsonx.ai & NLU  │
   │  (Tickets & Audit)   │                       │  (Granite 13B / NLU) │
   └──────────────────────┘                       └──────────────────────┘
```

---

## Step 1: FastAPI (Python 3.14) & ChromaDB Vector DB Containerization

The backend service encapsulates the 7 specialized agents, PII security guardrails, and ChromaDB vector database.

### 1.1 `bobCode/Dockerfile`

Create `bobCode/Dockerfile` for Python 3.14 containerization:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install build tools & curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ingest RAG synthetic knowledge base into local ChromaDB storage
RUN python data/ingest.py || true

# Set environment variables
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Step 2: Deploy Backend to IBM Cloud Code Engine

### 2.1 Authenticate & Target Resource Group
```bash
# Login to IBM Cloud CLI
ibmcloud login --sso

# Set target region and resource group
ibmcloud target -g Default -r us-south
```

### 2.2 Build & Push Image to IBM Cloud Container Registry (ICR)
```bash
# Create namespace in ICR
ibmcloud cr namespace-add bob-telecom-poc

# Log Docker into ICR
ibmcloud cr login

# Build image from bobCode directory
docker build -t icr.io/bob-telecom-poc/bob-backend:v1 ./bobCode

# Push image to registry
docker push icr.io/bob-telecom-poc/bob-backend:v1
```

### 2.3 Create Code Engine Project & Deploy App
```bash
# Create Code Engine project
ibmcloud ce project create --name bob-telecom-project
ibmcloud ce project select --name bob-telecom-project

# Deploy Container Application
ibmcloud ce app create --name bob-backend-api \
  --image icr.io/bob-telecom-poc/bob-backend:v1 \
  --port 8000 \
  --min-scale 1 \
  --max-scale 3 \
  --cpu 1 --memory 2G \
  --env-from-secret telecom-backend-secrets
```

---

## Step 3: Granular Security & Credential Management

Security is Foundation #1. Credentials must never be committed to git or baked into image layers.

### 3.1 IBM Cloud Secrets Manager Setup
Store the following secrets in **IBM Cloud Secrets Manager**:

| Secret Name | Type | Description |
|---|---|---|
| `WATSONX_API_KEY` | IAM API Key | Key authorized for watsonx.ai runtime |
| `WATSONX_PROJECT_ID` | String | GUID of watsonx.ai project |
| `NLU_API_KEY` | Service API Key | Key for IBM Natural Language Understanding |
| `CLOUDANT_URL` | URL String | URL of Cloudant NoSQL instance |
| `CLOUDANT_API_KEY` | Service API Key | IAM key for Cloudant `tickets` & `audit_trail` DBs |
| `BACKEND_API_KEY` | String | Shared secret to authorize skill requests from Orchestrate |

### 3.2 Create Code Engine Secret Bindings
```bash
ibmcloud ce secret create --name telecom-backend-secrets \
  --from-literal WATSONX_API_KEY="sec_watsonx_key_..." \
  --from-literal WATSONX_PROJECT_ID="proj_guid_..." \
  --from-literal NLU_API_KEY="nlu_key_..." \
  --from-literal CLOUDANT_URL="https://xxx-bluemix.cloudantnosqldb.appdomain.cloud" \
  --from-literal CLOUDANT_API_KEY="cloudant_key_..." \
  --from-literal BACKEND_API_KEY="bob_hackathon_sec_key_2026" \
  --from-literal USE_MOCK="false"
```

### 3.3 Backend Secret Consumption & Header Validation

In `bobCode/core/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    watsonx_api_key: str
    watsonx_project_id: str
    nlu_api_key: str
    cloudant_url: str
    cloudant_api_key: str
    backend_api_key: str
    use_mock: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
```

In `bobCode/core/guardrails.py` (Header verification):
```python
from fastapi import Header, HTTPException

async def verify_orchestrate_key(x_api_key: str = Header(...)):
    if x_api_key != settings.backend_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized Skill Invocation")
```

---

## Step 4: Import OpenAPI Spec into watsonx Orchestrate

1. Log into **watsonx Orchestrate Console**.
2. Navigate to **Skill Studio** → **Add skill** → **From OpenAPI document**.
3. Upload `bobCode/openapi/skills_spec.json` (or point to `https://bob-backend-api.xxx.codeengine.appdomain.cloud/openapi.json`).
4. Verify the 7 agent skills are parsed:
   - `intent_agent` (`POST /agents/intent`)
   - `ticket_agent` (`POST /agents/ticket`)
   - `rca_agent` (`POST /agents/rca`)
   - `escalation_agent` (`POST /agents/escalation`)
   - `parallel_agent` (`POST /agents/parallel`)
   - `resolution_agent` (`POST /agents/resolution`)
   - `feedback_agent` (`POST /agents/feedback`)
   - `watson_orchestrate_webhook` (`POST /webhook/orchestrate`)
5. Under **Connection Manager**, configure:
   - Base URL: `https://bob-backend-api.xxx.codeengine.appdomain.cloud`
   - Header Key: `x-api-key`
   - Header Value: `bob_hackathon_sec_key_2026`

---

## Step 5: Create & Configure Agent in watsonx Orchestrate

1. Navigate to **Agents** → **Create Agent**.
2. **Agent Name**: `Telecom Outage Resolution BOB`
3. **Agent Description**: `Autonomous 7-agent pipeline for resolving telecom network outages.`
4. **System Instructions / Prompt**:
   > *"You are an expert Telecom Outage Resolution Master Agent. Upon receiving a customer outage report, execute the incident resolution workflow by orchestrating the Intent Recognition, Ticket Classification, Root Cause Analysis (Vector DB RAG), Escalation Assessment, Parallel Impact Analysis, Resolution Generation, and Feedback skills."*
5. **Attach Skills**: Select all 7 imported skills.
6. Publish Agent.

---

## Step 6: IBM BOB Automation Workflow Setup

Configure IBM BOB to record ticket creations automatically upon skill execution:

1. Open **IBM BOB** workspace.
2. Create workflow: `Telecom Outage Ticket Write`.
3. Set trigger: **watsonx Orchestrate skill completion** (`watson_orchestrate_webhook`).
4. Action: **Cloudant Document Write**:
   - Database: `tickets`
   - Document Schema: Maps skill output to `BOBTicketDocument`.
   - URL & API Key: Configured via `CLOUDANT_URL` and `CLOUDANT_API_KEY`.

---

## Step 7: React 19 + Vite 8 + TypeScript Frontend Deployment

### 7.1 Multi-Stage `frontend/Dockerfile`
```dockerfile
# Stage 1: Build React 19 App
FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
ENV VITE_API_URL=https://bob-backend-api.xxx.codeengine.appdomain.cloud
RUN npm run build

# Stage 2: Serve via NGINX
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 7.2 `frontend/nginx.conf`
```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

### 7.3 Deploy Frontend to Code Engine
```bash
docker build -t icr.io/bob-telecom-poc/bob-frontend:v1 ./frontend
docker push icr.io/bob-telecom-poc/bob-frontend:v1

ibmcloud ce app create --name bob-frontend-ui \
  --image icr.io/bob-telecom-poc/bob-frontend:v1 \
  --port 80 \
  --min-scale 1 \
  --max-scale 2
```

---

## Step 8: Multi-Agent Deployment & Verification Checklist

| Phase | Verification Command / Step | Expected Result |
|---|---|---|
| **Backend Health** | `curl -f https://bob-backend-api.xxx.codeengine.appdomain.cloud/health` | `{"status": "healthy"}` (200 OK) |
| **OpenAPI Spec** | `curl https://bob-backend-api.xxx.codeengine.appdomain.cloud/openapi.json` | Valid OpenAPI 3.0 JSON with 7 agent paths |
| **Header Security** | `curl -X POST https://bob-backend-api.../agents/intent` (no key) | `401 Unauthorized` |
| **Skill Authorization**| `curl -H "x-api-key: bob_hackathon_sec_key_2026" -X POST .../agents/intent` | `200 OK` with intent JSON |
| **Vector DB RAG** | Invoke `rca_agent` skill via Orchestrate test console | Root cause returned with confidence score from ChromaDB |
| **Cloudant Audit** | Query Cloudant `audit_trail` database | Sanitised audit record present (no raw PII) |
| **Frontend UI** | Open `https://bob-frontend-ui.xxx.codeengine.appdomain.cloud` | React 19 UI loads, connects to backend & webchat |

---

**Guide Document Created**: 2026-07-23  
**Location**: `mydocs/ibm-cloud-deployment-guide.md`
