# Option 2 Guide: Laptop Execution + Public Tunnel + watsonx Orchestrate

**Project**: BOBHackathonTelecomPOC  
**Target Platform**: Laptop / Workstation Execution + `npx localtunnel` (or `ngrok`) + `ca-tor.watson-orchestrate.cloud.ibm.com`  
**Status**: Recommended Hackathon Strategy — 100% Ready & Verified ✅  

---

## Clarification: What Does "Local" Mean?

> **"Local" means running directly on your laptop / personal workstation** (the physical computer where your `BOBHackathonTelecomPOC` codebase is located).

You do **NOT** need to create or pay for container hosting on IBM Cloud Code Engine. Your laptop runs the Python backend and React UI, while **`ca-tor.watson-orchestrate.cloud.ibm.com`** (IBM Cloud Toronto) acts as the central cloud Master Agent calling your laptop over a secure HTTPS tunnel.

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
                                       │ Secure HTTPS Tunnel (localtunnel/ngrok)
                                       │ https://<YOUR_SUBDOMAIN>.loca.lt
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

## Step-by-Step Instructions to Run & Present (Option 2)

### Step 1: Configure Credentials on Your Laptop
Copy `bobCode/.env.example` to `bobCode/.env` on your laptop and set your pre-provisioned IBM service credentials:

```ini
# bobCode/.env

# ── Runtime mode ─────────────────────────────────────────────
USE_MOCK=false

# ── API Server ───────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
ALLOWED_ORIGINS=http://localhost:5173

# ── IBM NLU Instance Credentials (Dallas us-south) ───────────
NLU_API_KEY=<YOUR_NLU_API_KEY>
NLU_URL=https://api.us-south.natural-language-understanding.watson.cloud.ibm.com/instances/<YOUR_NLU_INSTANCE_ID>

# ── IBM Cloudant DB Credentials (Dallas us-south) ────────────
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

### Step 2: Start the Python Backend & Vector DB on Your Laptop
Open Terminal #1 on your laptop:

```powershell
cd bobCode

# Install dependencies (uses flexible version bounds for Windows compatibility)
python -m pip install -r requirements.txt

# Start FastAPI backend & Vector DB
python -m uvicorn api.main:app --reload --port 8000
```
*FastAPI backend and local ChromaDB Vector DB are now running on your laptop at `http://localhost:8000`.*

---

### Step 3: Create Secure HTTPS Tunnel via `npx localtunnel` or `ngrok`
Open Terminal #2 on your laptop to expose your local FastAPI server to IBM Cloud:

```powershell
npx localtunnel --port 8000
```
*(Or if using ngrok: `ngrok http 8000`)*

**Output**:
Copy the generated HTTPS URL, for example:  
👉 `https://<YOUR_SUBDOMAIN>.loca.lt`

---

### Step 4: Link Your Tunnel URL in `skills_spec.json` & Import into Watson Orchestrate

1. Open `bobCode/openapi/skills_spec.json` in VS Code and set your active tunnel URL on line 10:
   ```json
     "servers": [
       {
         "url": "https://<YOUR_SUBDOMAIN>.loca.lt",
         "description": "FastAPI Agent Backend Server"
       }
     ]
   ```

2. Log into **`ca-tor.watson-orchestrate.cloud.ibm.com`** in your browser.
3. Go to **Manage Agents** ➔ Select your agent **`BobTelecomOrchestrate`** (or click **Create new agent**).
4. Under **Toolset**, click **Add Tool** ➔ Select **OpenAPI**.
5. Upload `bobCode/openapi/skills_spec.json`.
6. Under Connection Header, set:
   - **Key**: `x-api-key`
   - **Value**: `<YOUR_BACKEND_SECRET_KEY>`
7. Click **Deploy 🚀** at the top-right corner to publish the agent.

---

### Step 5: Start React 19 Frontend on Your Laptop & Demo
Open Terminal #3 on your laptop:

```powershell
cd frontend
npm install
npm run dev
```

1. Open `http://localhost:5173` in your browser.
2. Enter a sample complaint:
   ```text
   Fibercut at Purbalok Kalibari
   ```
3. Show the judges the live **7-Agent Pipeline** animation, real-time SSE progress events, location-aware RCA analysis, and live Cloudant ticket logs!

---

## Security & Exclusion Files (.gitignore & .bobignore)

Sensitive credentials and environment files are protected from git commits and push operations:
- **`.gitignore`**: Excludes `.env`, `.env.*`, `.venv/`, `chroma_data/`, `node_modules/`, `*.key`, `*.pem`.
- **`.bobignore`**: Prevents IBM BOB tooling from scanning or pushing credential files or build output.
