# Option 1 Guide: Full IBM Cloud Code Engine Container Deployment

**Project**: BOBHackathonTelecomPOC  
**Target Platform**: IBM Cloud Code Engine (Serverless Containers) + IBM Container Registry (`us.icr.io`)  
**Status**: Container Images Built & Pushed to Registry ✅  

---

## Overview

This guide details **Option 1**: Containerizing both the **FastAPI Backend (Python 3.14 / 3.11)** and **React 19 Frontend**, building container images, pushing them to **IBM Cloud Container Registry (`us.icr.io`)**, and deploying them as serverless container apps on **IBM Cloud Code Engine**.

---

## How to Retrieve Your Account & Resource Group Details

Before targeting resources, retrieve your generic Account ID and Resource Group using the IBM Cloud CLI:

1. **List Your Available Accounts**:
   ```bash
   ibmcloud account list
   ```
   *Note down your target `<YOUR_ACCOUNT_ID>` or `<YOUR_ACCOUNT_NAME>`.*

2. **List Your Available Resource Groups**:
   ```bash
   ibmcloud resource groups
   ```
   *Note down your target `<YOUR_RESOURCE_GROUP>` (e.g. `Default`).*

3. **Target Your Account & Resource Group**:
   ```bash
   ibmcloud target -c <YOUR_ACCOUNT_ID> -g <YOUR_RESOURCE_GROUP>
   ```

---

## Summary of Steps Taken So Far

### 1. Backend Containerization & Fixes
- Created [bobCode/Dockerfile](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/bobCode/Dockerfile): Uses `python:3.11-slim` base image to guarantee pre-compiled wheels for `numpy`, `chromadb`, and `pydantic-core`.
- Optimized PyTorch installation: Added CPU-only PyTorch (`--index-url https://download.pytorch.org/whl/cpu`) to eliminate downloading 1.5GB CUDA GPU libraries and prevent network timeouts.
- Built & tagged backend container image:
  `docker build -t icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1 ./bobCode`

### 2. Frontend Containerization & Fixes
- Created [frontend/Dockerfile](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/frontend/Dockerfile) & [frontend/nginx.conf](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/frontend/nginx.conf): Multi-stage Node 22 build serving React 19 static bundle via NGINX.
- Created [frontend/.dockerignore](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/frontend/.dockerignore): Prevents local Windows `node_modules/` from overwriting Linux binaries inside the container.
- Configured build environment: Added `ENV NODE_ENV=development` and moved TypeScript `tsc` & Vite to main dependencies in `package.json` to resolve `sh: tsc: not found`.
- Built & tagged frontend container image:
  `docker build -t icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1 ./frontend`

### 3. IBM Cloud Container Registry Push (Completed ✅)
Both backend and frontend images were tagged for `us.icr.io` and pushed to IBM Cloud Container Registry:
- **Backend Image**: `us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1` ✅ (Pushed)
- **Frontend Image**: `us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1` ✅ (Pushed)

---

## Steps to Complete Option 1 Deployment

### 1. Target Account & Verify Project Permissions
```bash
# Target account & resource group
ibmcloud target -c <YOUR_ACCOUNT_ID> -g <YOUR_RESOURCE_GROUP>

# Create Code Engine project (requires IAM Administrator/Editor roles)
ibmcloud ce project create --name bob-telecom-project

# Select created or pre-existing project
ibmcloud ce project select --name bob-telecom-project
```

### 2. How to Update Credentials & Endpoints in Option 1
In Code Engine, you **never edit Python code or rebuild Docker images** to change credentials. Code Engine injects credentials directly into container memory via Environment Secrets:

**Via IBM Cloud CLI**:
```bash
# Create/Update secret with your live API keys & endpoints
ibmcloud ce secret create --name telecom-backend-secrets \
  --from-literal WATSONX_API_KEY="<YOUR_WATSONX_API_KEY>" \
  --from-literal WATSONX_PROJECT_ID="<YOUR_WATSONX_PROJECT_ID>" \
  --from-literal NLU_API_KEY="<YOUR_NLU_API_KEY>" \
  --from-literal NLU_URL="https://api.us-south.natural-language-understanding.watson.cloud.ibm.com" \
  --from-literal CLOUDANT_URL="https://<YOUR_CLOUDANT_INSTANCE>.cloudantnosqldb.appdomain.cloud" \
  --from-literal CLOUDANT_API_KEY="<YOUR_CLOUDANT_API_KEY>" \
  --from-literal BACKEND_API_KEY="<YOUR_BACKEND_API_KEY>" \
  --from-literal USE_MOCK="false"

# Bind updated secret to your running backend app (restarts container with new credentials)
ibmcloud ce app update --name bob-backend-api --env-from-secret telecom-backend-secrets
```

**Via IBM Cloud Console UI**:
- Go to **Code Engine** ➔ Projects ➔ `bob-telecom-project` ➔ Applications ➔ `bob-backend-api`.
- Click **Environment Variables** ➔ Add/Edit Key-Value pairs ➔ Click **Save and create new revision**.

### 3. Deploy Applications on Code Engine

**Deploy Backend Container**:
```bash
ibmcloud ce app create --name bob-backend-api \
  --image us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-backend:v1 \
  --port 8000 \
  --cpu 1 --memory 2G \
  --env-from-secret telecom-backend-secrets
```

**Deploy Frontend Container**:
```bash
ibmcloud ce app create --name bob-frontend-ui \
  --image us.icr.io/<YOUR_REGISTRY_NAMESPACE>/bob-frontend:v1 \
  --port 80
```

### 4. Connect to watsonx Orchestrate
Import `bobCode/openapi/skills_spec.json` into `ca-tor.watson-orchestrate.cloud.ibm.com` using the deployed Code Engine HTTPS URL (`https://bob-backend-api.<region>.codeengine.appdomain.cloud`).
