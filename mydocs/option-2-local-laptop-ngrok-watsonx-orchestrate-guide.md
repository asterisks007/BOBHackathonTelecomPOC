# Option 2 Guide: Laptop Execution + ngrok Tunnel + watsonx Orchestrate

**Project**: BOBHackathonTelecomPOC  
**Target Platform**: Laptop / Workstation Execution + `ngrok` HTTPS Tunnel + `ca-tor.watson-orchestrate.cloud.ibm.com`  
**Status**: Recommended Hackathon Strategy — 100% Sufficient & Ready ✅  

---

## Clarification: What Does "Local" Mean?

> **"Local" means running directly on your laptop / personal workstation** (the physical computer where your `BOBHackathonTelecomPOC` codebase is located).

You do **NOT** need to create or pay for container hosting on IBM Cloud Code Engine. Your laptop runs the Python backend and React UI, while **`ca-tor.watson-orchestrate.cloud.ibm.com`** (IBM Cloud Toronto) acts as the central cloud Master Agent.

---

## Summary of Architecture & Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 IBM CLOUD PLATFORM (Toronto ca-tor & Dallas us-south)       │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │      watsonx-Hackathon Orchestrate (ca-tor.watson-orchestrate)      │   │
│   │           Master Agent / Skill Studio / Webchat Console             │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│                 Calls OpenAPI Skills │ Direct Service APIs                  │
│                 over HTTPS Tunnel    │ (NLU & Cloudant DB)                  │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   watsonx-Hackathon NLU  |  watsonx-Hackathon Cloudant DB           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       │ Secure HTTPS Tunnel (ngrok)
                                       │ https://<YOUR_SUBDOMAIN>.ngrok-free.app
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           YOUR LAPTOP / WORKSTATION                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                 React 19 + Vite 8 UI (frontend/)                    │   │
│   │              Runs locally at http://localhost:5173                  │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │             FastAPI Backend (bobCode/ - Python 3.14)                │   │
│   │  • Hosts 7 Agent Skills & PII Guardrails                            │   │
│   │  • Local ChromaDB Vector DB (RAG Knowledge Base)                    │   │
│   │  • Connects to watsonx-Hackathon NLU & Cloudant DB                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## How to Retrieve Your IBM Service Credentials

To connect your local Python backend to your pre-provisioned IBM Cloud services:

1. **Get IBM NLU Credentials**:
   - Log into [IBM Cloud Resource List](https://cloud.ibm.com/resources).
   - Expand **AI / Machine Learning** ➔ Select your NLU instance (e.g. `watsonx-Hackathon NLU`).
   - Copy **API Key** and **URL**.

2. **Get IBM Cloudant Credentials**:
   - In Resource List ➔ Expand **Databases** ➔ Select your Cloudant instance (e.g. `watsonx-Hackathon Cloudant`).
   - Copy **Service URL** and **API Key**.

---

## Step-by-Step Instructions to Run & Present (Option 2)

### Step 1: Configure Credentials on Your Laptop
Open `bobCode/.env` on your laptop and set your pre-provisioned IBM service credentials:

```ini
# bobCode/.env
USE_MOCK=false

# 1. IBM NLU Instance Credentials
NLU_API_KEY=<YOUR_NLU_API_KEY>
NLU_URL=https://api.us-south.natural-language-understanding.watson.cloud.ibm.com

# 2. IBM Cloudant DB Credentials
CLOUDANT_URL=https://<YOUR_CLOUDANT_INSTANCE>.cloudantnosqldb.appdomain.cloud
CLOUDANT_API_KEY=<YOUR_CLOUDANT_API_KEY>

# 3. Security Header Key for Orchestrate Webhook
BACKEND_API_KEY=<YOUR_BACKEND_SECRET_KEY>
```

---

### Step 2: Start the Python Backend & Vector DB on Your Laptop
Open Terminal #1 on your laptop:

```bash
cd bobCode

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Start FastAPI backend
uvicorn api.main:app --reload --port 8000
```
*FastAPI backend and local ChromaDB Vector DB are now running on your laptop at `http://localhost:8000`.*

---

### Step 3: Create Secure HTTPS Tunnel via `ngrok`
Open Terminal #2 on your laptop to expose your local FastAPI server to IBM Cloud:

```bash
ngrok http 8000
```
*ngrok will generate a public HTTPS URL, for example:*  
`https://<YOUR_SUBDOMAIN>.ngrok-free.app`

---

### Step 4: Import OpenAPI Specification into Watson Orchestrate

1. Log into **`ca-tor.watson-orchestrate.cloud.ibm.com`** in your browser.
2. Go to **Skill Studio** ➔ **Add skill** ➔ **From OpenAPI document**.
3. Upload `bobCode/openapi/skills_spec.json`.
4. Under **Server Connection Settings**:
   - Set **Server Base URL**: `https://<YOUR_SUBDOMAIN>.ngrok-free.app` *(your ngrok HTTPS URL)*.
   - Set **Header**: `x-api-key` = `<YOUR_BACKEND_SECRET_KEY>`.
5. Save & Publish the 7 agent skills.

---

### Step 5: Build Master Agent in Watson Orchestrate

1. In `ca-tor.watson-orchestrate.cloud.ibm.com`, go to **Agents** ➔ **Create Agent**.
2. Name: `Telecom Outage Resolution BOB`
3. Prompt: *"You are an autonomous Telecom Outage Resolution Master Agent. When a customer reports a network issue, execute the resolution flow by invoking the Intent Skill, Ticket Skill, RCA Skill (queries Vector DB), Escalation Skill, Parallel Impact Skill, Resolution Skill, and Feedback Skill."*
4. Attach Skills: Select all 7 imported skills.
5. Publish Agent.

---

### Step 6: Start React 19 Frontend on Your Laptop & Demo
Open Terminal #3 on your laptop:

```bash
cd frontend
npm run dev
```
1. Open `http://localhost:5173` in your browser.
2. Enter a sample complaint: *"Fiber cut near Manhattan junction box XY, 4G network is down"*.
3. Show the judges the live 7-agent pipeline animation, real-time SSE progress events, confidence meters, and Cloudant ticket logs!
