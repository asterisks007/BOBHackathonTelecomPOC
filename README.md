# Telecom Outage Resolution BOB — Option 2 Quickstart & Execution Guide

**Project**: BOBHackathonTelecomPOC  
**Target Platform**: Laptop Execution + `npx localtunnel` (or `ngrok`) + `ca-tor.watson-orchestrate.cloud.ibm.com`  
**Version**: 1.0 | **Updated**: 2026-07-28  

---

## Executive Summary

This is the primary **README.md** guide for starting and demonstrating the complete **7-Agent Telecom Outage Resolution BOB** system using **Option 2** (Laptop Execution + Cloud Master Agent Orchestration).

In Option 2:
- Your laptop runs the **FastAPI Backend (Python 3.14/3.11)**, **ChromaDB Vector DB**, and **React 19 Frontend**.
- Your Python backend connects directly to your live IBM Cloud services:
  - **`watsonx-Hackathon NLU`** (Dallas `us-south`)
  - **`watsonx-Hackathon Cloudant DB`** (Dallas `us-south`)
- **`ca-tor.watson-orchestrate.cloud.ibm.com`** (Toronto) acts as the cloud Master Agent calling your 7 backend skills over a secure HTTPS tunnel.

---

## Quickstart: How to Start the Solution (Step-by-Step)

### Step 1: Configure Credentials in `bobCode/.env`

Copy `bobCode/.env.example` to `bobCode/.env` on your laptop and set your live IBM Cloud credentials:

```ini
# bobCode/.env

# ── Runtime mode ─────────────────────────────────────────────
USE_MOCK=false

# ── API Server ───────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
ALLOWED_ORIGINS=http://localhost:5173

# ── IBM NLU (Dallas us-south) ────────────────────────────────
NLU_API_KEY=<YOUR_NLU_API_KEY>
NLU_URL=https://api.us-south.natural-language-understanding.watson.cloud.ibm.com/instances/<YOUR_NLU_INSTANCE_ID>

# ── IBM Cloudant DB (Dallas us-south) ────────────────────────
CLOUDANT_URL=https://<YOUR_CLOUDANT_INSTANCE_ID>-bluemix.cloudantnosqldb.appdomain.cloud
CLOUDANT_API_KEY=<YOUR_CLOUDANT_API_KEY>
CLOUDANT_DB_INCIDENTS=incidents
CLOUDANT_DB_TICKETS=tickets
CLOUDANT_DB_AUDIT=audit_trail
CLOUDANT_DB_KNOWLEDGE=knowledge_base

# ── Security Header Key for Webhook Protection ───────────────
BACKEND_API_KEY=<YOUR_BACKEND_SECRET_KEY>
```

---

### Step 2: Start the Python Backend & ChromaDB Vector DB

Open **Terminal #1** on your laptop:

```powershell
cd bobCode

# 1. Install dependencies (uses flexible version bounds for Windows compatibility)
python -m pip install -r requirements.txt

# 2. Start FastAPI Server & Vector DB
python -m uvicorn api.main:app --reload --port 8000
```

*Your backend and ChromaDB Vector DB are now running locally at `http://localhost:8000`.*

---

### Step 3: Create Secure HTTPS Tunnel (`npx localtunnel` or `ngrok`)

Open **Terminal #2** on your laptop to expose your local FastAPI server to IBM Cloud:

```powershell
npx localtunnel --port 8000
```
*(Or if using ngrok: `ngrok http 8000`)*

**Output**:
Copy the generated HTTPS URL, for example:
👉 `https://<YOUR_SUBDOMAIN>.loca.lt`

---

### Step 4: Link Your Tunnel URL in `skills_spec.json` & Upload to watsonx Orchestrate

1. Open `bobCode/openapi/skills_spec.json` in VS Code and set your active tunnel URL on line 10:
   ```json
     "servers": [
       {
         "url": "https://<YOUR_SUBDOMAIN>.loca.lt",
         "description": "FastAPI Agent Backend Server"
       }
     ]
   ```

2. Log into **`ca-tor.watson-orchestrate.cloud.ibm.com`**.
3. Go to **Manage Agents** ➔ Select your agent **`BobTelecomOrchestrate`** (or click **Create new agent**).
4. Under **Toolset**, click **Add Tool** ➔ Select **OpenAPI**.
5. Upload `bobCode/openapi/skills_spec.json`.
6. Under Connection Header, set:
   - **Key**: `x-api-key`
   - **Value**: `<YOUR_BACKEND_SECRET_KEY>`
7. Click **Deploy 🚀** at the top-right corner to publish the agent.

---

### Step 5: Start the React 19 Frontend & Run Demo

Open **Terminal #3** on your laptop:

```powershell
cd frontend
npm install
npm run dev
```

1. Open **`http://localhost:5173`** in your browser.
2. Type a customer complaint, for example:
   ```text
   Fibercut at Purbalok Kalibari
   ```
3. Watch the live **7-Agent Pipeline** execute real-time intent recognition, automated ticket generation in **IBM Cloudant DB**, RAG similarity search in **ChromaDB**, dynamic root cause analysis, and customer response generation!

---

## Security & Exclusion Files (.gitignore & .bobignore)

Sensitive API credentials, `.env` files, virtual environments, and database storage are strictly excluded from git commits and IBM BOB tooling via:
- `.gitignore` (excludes `.env`, `.venv/`, `chroma_data/`, `node_modules/`, `*.key`, `*.pem`)
- `.bobignore` (prevents BOB CLI/tooling from uploading environment secrets or build artifacts)

---
