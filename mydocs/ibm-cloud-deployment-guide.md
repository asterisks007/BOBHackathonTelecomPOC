# IBM Cloud Deployment Guide — Telecom Outage Resolution BOB

**Project**: BOBHackathonTelecomPOC  
**Target Platform**: IBM Cloud (watsonx Orchestrate + IBM Cloud Code Engine + Cloudant + watsonx.ai + IBM NLU)  
**Version**: 1.0 | **Updated**: 2026-07-24  

---

## Executive Summary & Architecture Overview

This document provides a granular, production-ready guide for deploying the **Telecom Outage Resolution BOB** to **IBM Cloud**. 

The solution uses a **watsonx Orchestrate-Centric Multi-Agent Architecture**:
- **watsonx Orchestrate**: Functions as the central **Master Agent / Orchestrator Platform**, managing user conversations, goal decomposition, skill selection, state tracking, and execution flow.
- **FastAPI (Python 3.14 / 3.11)**: Deployed on **IBM Cloud Code Engine** as the **Intelligence & Skill Server**, hosting 7 specialized agent skills, security guardrails (PII masking & input validation), and the embedded **ChromaDB Vector DB** for RAG lookups.
- **React 19 + Vite 8 + TypeScript**: Deployed as a containerized static application on **IBM Cloud Code Engine** (or hosted via IBM Cloud Object Storage + CDN), embedding the watsonx Orchestrate Webchat widget.
- **IBM Managed Services**:
  - **watsonx.ai**: Powers Granite 13B LLM reasoning for RCA and response generation.
  - **IBM NLU**: Performs intent recognition and entity extraction.
  - **IBM Cloudant**: NoSQL storage for incident tickets and immutable audit logs.
  - **IBM BOB**: Workflow automation triggering ticket writes to Cloudant on skill completion.

---

## How to Retrieve Your Account & Resource Group Details

Before executing deployment commands, retrieve your account ID and resource group:

1. **List Accounts**:
   ```bash
   ibmcloud account list
   ```
2. **List Resource Groups**:
   ```bash
   ibmcloud resource groups
   ```
3. **Target Account & Resource Group**:
   ```bash
   ibmcloud target -c <YOUR_ACCOUNT_ID> -g <YOUR_RESOURCE_GROUP>
   ```

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

## Step 1: FastAPI & ChromaDB Vector DB Containerization

The backend service encapsulates the 7 specialized agents, PII security guardrails, and ChromaDB vector database.

### 1.1 `bobCode/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install build tools & curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU PyTorch to prevent memory exhaustion & timeouts
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy dependency specifications
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

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

# Target account, region, and resource group
ibmcloud target -c <YOUR_ACCOUNT_ID> -r us-south -g <YOUR_RESOURCE_GROUP>
```

### 2.2 Build & Push Image to IBM Cloud Container Registry (ICR)
```bash
# Create namespace in ICR
ibmcloud cr namespace-add <YOUR_REGISTRY_NAMESPACE>

# Log Docker into ICR
ibmcloud cr login

# Build image from bobCode directory
docker build -t icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1 ./bobCode

# Tag for regional registry if applicable
docker tag icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1 us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1

# Push image to registry
docker push us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1
```

### 2.3 Create Code Engine Project & Deploy App
```bash
# Create Code Engine project
ibmcloud ce project create --name bob-telecom-project
ibmcloud ce project select --name bob-telecom-project

# Deploy Container Application
ibmcloud ce app create --name bob-backend-api \
  --image us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1 \
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
  --from-literal WATSONX_API_KEY="<YOUR_WATSONX_API_KEY>" \
  --from-literal WATSONX_PROJECT_ID="<YOUR_WATSONX_PROJECT_ID>" \
  --from-literal NLU_API_KEY="<YOUR_NLU_API_KEY>" \
  --from-literal CLOUDANT_URL="https://<YOUR_CLOUDANT_INSTANCE>.cloudantnosqldb.appdomain.cloud" \
  --from-literal CLOUDANT_API_KEY="<YOUR_CLOUDANT_API_KEY>" \
  --from-literal BACKEND_API_KEY="<YOUR_BACKEND_API_KEY>" \
  --from-literal USE_MOCK="false"
```

---

## Step 4: Import OpenAPI Spec into watsonx Orchestrate

1. Log into **watsonx Orchestrate Console** (`ca-tor.watson-orchestrate.cloud.ibm.com`).
2. Navigate to **Skill Studio** → **Add skill** → **From OpenAPI document**.
3. Upload `bobCode/openapi/skills_spec.json`.
4. Verify the 7 agent skills are parsed.
5. Under **Connection Manager**, configure:
   - Base URL: `https://bob-backend-api.<region>.codeengine.appdomain.cloud`
   - Header Key: `x-api-key`
   - Header Value: `<YOUR_BACKEND_API_KEY>`

---

## Step 5: Create & Configure Agent in watsonx Orchestrate

1. Navigate to **Agents** → **Create Agent**.
2. **Agent Name**: `Telecom Outage Resolution BOB`
3. **Attach Skills**: Select all 7 imported skills.
4. Publish Agent.

---

## Step 6: React 19 + Vite 8 + TypeScript Frontend Deployment

### 6.1 Deploy Frontend to Code Engine
```bash
docker build -t icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1 ./frontend
docker tag icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1 us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1
docker push us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1

ibmcloud ce app create --name bob-frontend-ui \
  --image us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1 \
  --port 80
```
