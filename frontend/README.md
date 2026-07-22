# React Frontend — Telecom Copilot

**Stack**: Vite 6 + React 19 + TypeScript  
**Purpose**: Real-time UI for the 7-agent Telecom Outage Resolution Copilot  
**Status**: ST-5 Complete

---

## Setup

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

## Environment

Copy `.env.example` to `.env` (already present):
```
VITE_API_URL=http://localhost:8000
```

The backend must be running first:
```bash
cd bobCode
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

## Build

```bash
npm run build      # outputs to dist/
npm run preview    # preview production build
```

## Components

| Component | File | Purpose |
|---|---|---|
| `ChatInput` | `components/ChatInput.tsx` | Free-text input form, load-demo button |
| `AgentPipeline` | `components/AgentPipeline.tsx` | 7-node SVG pipeline, SSE-driven state |
| `ResolutionPanel` | `components/ResolutionPanel.tsx` | Resolution steps, customer message, ticket |
| `IncidentTimeline` | `components/IncidentTimeline.tsx` | Chronological agent event log |

## Hook

`hooks/useOrchestration.ts` — connects to `POST /orchestrate/stream` (SSE) and
updates React state per-agent as each event arrives.

## Security Notes

- No customer data stored in `localStorage` or `sessionStorage`
- CORS allowed from `http://localhost:5173` only (configured in `bobCode/api/main.py`)
- All user input validated server-side by Pydantic before processing
