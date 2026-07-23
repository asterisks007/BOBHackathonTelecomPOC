# Architecture Decisions - Telecom Outage Resolution BOB POC
 
## Document Purpose
 
This document captures all major architecture decisions, design patterns, and technical choices made for the Telecom Outage Resolution BOB POC for IBM BOB Hackathon 2026.
 
---
 
## 1. System Architecture Overview
 
### High-Level Architecture
 
```
┌─────────────────────────────────────────────────────┐
│           React UI (Chat Interface)                  │
│      (Real-time messaging + Agent visualization)     │
└────────────────────┬────────────────────────────────┘
                     │ HTTP/WebSocket
                     ▼
┌─────────────────────────────────────────────────────┐
│        FastAPI Backend (Python 3.11+)               │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │   Master Orchestration Engine               │    │
│  │  ├─ Sequential Agent Coordination           │    │
│  │  ├─ Conditional Branching Logic            │    │
│  │  ├─ Error Recovery & Fallbacks             │    │
│  │  └─ Response Streaming (Server-Sent Events)│    │
│  └─────────────────────────────────────────────┘    │
│                     │                                 │
│  ┌──────┬──────┬───┴───┬──────┬───────┬──────┐      │
│  ▼      ▼      ▼       ▼      ▼       ▼      ▼      │
│ [IA]  [TA]   [RA]    [EA]   [PA]    [RGA]  [FA]    │
│  └──────┬──────┬───┬──────┬───────┬──────┘           │
│         │      │   │      │       │                   │
└─────────┼──────┼───┼──────┼───────┼──────────────────┘
          │      │   │      │       │
          │      │   │      │       │
    ┌─────┴──────┴───┴──┬───┴───────┴─────┐
    │                   │                  │
    ▼                   ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌─────────────┐
│ watsonx.ai   │  │  IBM NLU     │  │ Cloudant    │
│              │  │              │  │ (Tickets)   │
│ • Granite    │  │ • Entities   │  │             │
│   13B LLM    │  │ • Intent     │  │ • Incident  │
│              │  │ • Semantic   │  │   storage   │
│ • Embeddings │  │   sim.       │  │ • Audit     │
└──────────────┘  └──────────────┘  └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  ChromaDB   │
                   │  (Local RAG)│
                   └─────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │ Watson Orchestrate   │
              │ + IBM BOB Automation │
              └──────────────────────┘
```
 
### Key Decision: Modular Agentic Architecture
 
**Rationale**:
- **Separation of Concerns**: Each agent has a single responsibility
- **Testability**: Each agent can be tested independently with mocks
- **Scalability**: Easy to add more agents or modify existing ones
- **Reusability**: Agents can be composed in different orchestration flows
- **Observable**: Clear input/output at each stage for debugging
 
---
 
## 2. Agent Architecture
 
### 7 Specialized Agents
 
#### Agent 1: Intent Recognition Agent
**Purpose**: Classify customer issue and extract key attributes  
**Input**: Free-text customer complaint  
**Output**: Structured intent with confidence scores
 
```python
{
    "issue_type": "signal_degradation",      # Entity
    "service": "4G_Network",                 # Category
    "location": "New York",                  # Entity
    "priority": "high",                      # Derived
    "confidence": 0.92,                      # 0-1 score
    "entities": {                            # Detailed
        "locations": ["New York", "Brooklyn"],
        "services": ["4G", "LTE"],
        "keywords": ["signal", "degradation"]
    }
}
```
 
**Implementation**:
- Use IBM NLU for entity extraction
- Rule-based priority assignment
- Confidence scoring via NLU confidence metrics
 
**SLA**: <500ms per request
 
---
 
#### Agent 2: Ticket Classification Agent
**Purpose**: Route incident to appropriate team and categorize severity  
**Input**: Intent recognition output  
**Output**: Ticket metadata with queue assignment
 
```python
{
    "ticket_id": "INC-2024-001234",
    "queue": "Network_Operations",           # Routing
    "severity": "Critical",                  # P1, P2, P3, P4
    "category": "Infrastructure",            # Problem type
    "sub_category": "Wireless",              # Details
    "sla_minutes": 30,                       # Response SLA
    "assignment_group": "L2_Support"
}
```
 
**Implementation**:
- Lookup table: issue_type → queue
- Rule-based severity (location + service impact)
- SLA assignment based on severity
 
**SLA**: <200ms per request
 
---
 
#### Agent 3: RCA (Root Cause Analysis) Agent
**Purpose**: Perform root cause analysis using knowledge base + Granite LLM  
**Input**: Ticket + incident history  
**Output**: Likely root cause + confidence + recommended actions
 
```python
{
    "root_cause": "Fiber cut at junction Box_XY",
    "confidence": 0.88,
    "evidence": [
        "Similar incident on 2024-01-10",
        "Network topology shows single fiber path",
        "No BGP failover configured"
    ],
    "affected_services": ["4G", "LTE", "Backhaul"],
    "estimated_scope": "3 cell sites, ~50k customers",
    "recommendation": "Activate backup fiber route immediately",
    "estimated_time_to_resolve": 120                 # minutes
}
```
 
**Implementation**:
- RAG: Query ChromaDB for similar incidents
- LLM: Use Granite 13B for reasoning
- Evidence collection and ranking
- Confidence via LLM output scores
 
**SLA**: <2s per request (includes LLM call)
 
---
 
#### Agent 4: Escalation Agent
**Purpose**: Assess risk and decide on escalation  
**Input**: RCA output + incident severity  
**Output**: Escalation decision + notifications
 
```python
{
    "escalate": true,
    "escalation_level": "Executive",
    "reason": "High customer impact + network infrastructure",
    "notify": [
        "network-ops@company.com",
        "exec-on-call@company.com"
    ],
    "urgency": "Critical",
    "estimated_cost": "$50k+ revenue impact"
}
```
 
**Implementation**:
- Decision tree: severity + scope → escalation level
- Notification routing via incident type
- Cost estimation rules
 
**SLA**: <500ms per request
 
---
 
#### Agent 5: Parallel Analysis Agent
**Purpose**: Multi-dimensional analysis (customer impact, performance, scope)  
**Input**: Incident details  
**Output**: Impact metrics
 
```python
{
    "customer_impact": {
        "affected_customers": 47832,
        "affected_percentage": 0.12,                  # % of region
        "revenue_impact": "$23k/min"
    },
    "network_impact": {
        "affected_sites": 3,
        "traffic_loss": "45%",
        "latency_increase": 200                       # ms
    },
    "operational_impact": {
        "team_hours": 4,
        "tools_required": ["BGP config", "Fiber test"],
        "risk_level": "High"
    }
}
```
 
**Implementation**:
- Query Cloudant for incident history
- Calculate derived metrics (revenue/min, etc.)
- Aggregate from multiple data sources
- Parallel queries for speed
 
**SLA**: <1s per request
 
---
 
#### Agent 6: Response Generation Agent
**Purpose**: Generate automated resolution recommendations and communication  
**Input**: RCA + escalation decision + impact metrics  
**Output**: Resolution steps + customer communication template
 
```python
{
    "resolution_steps": [
        "1. Verify fiber cut location (BGP test)",
        "2. Activate backup route (10 min)",
        "3. Dispatch fiber repair crew",
        "4. Monitor traffic recovery"
    ],
    "automation_possible": true,
    "automation_score": 0.85,
    "customer_message": "We've detected a network issue...",
    "internal_notes": "Likely fiber cut, backup active, ETA 2hrs",
    "estimated_resolution_time": 120                  # minutes
}
```
 
**Implementation**:
- Template-based generation with variable substitution
- Granite LLM for personalized messages
- Automation scoring via rule engine
- Reference previous resolution patterns
 
**SLA**: <1.5s per request
 
---
 
#### Agent 7: Feedback Agent
**Purpose**: Post-resolution validation and feedback collection  
**Input**: Resolution actions + ticket closure  
**Output**: Feedback metrics for continuous improvement
 
```python
{
    "resolution_effective": true,
    "time_to_resolution": 127,                        # minutes
    "customer_satisfaction": 4.2,                     # 1-5 scale
    "preventive_action": "Install redundant fiber",
    "learning_points": [
        "Similar incident in 2023 - pattern recognized",
        "RCA accuracy: 92% match to actual cause"
    ],
    "recommended_changes": [
        "Add BGP failover to this site",
        "Increase monitoring alert sensitivity"
    ]
}
```
 
**Implementation**:
- Survey data collection
- MTTR (Mean Time To Resolution) calculation
- Pattern analysis for continuous improvement
- Recommend preventive actions
 
**SLA**: <500ms per request
 
---
 
## 3. Communication Patterns
 
### Agent-to-Agent Communication
 
**Sequential Orchestration** (Primary Pattern):
```
Customer Input
    ↓
[Intent Recognition Agent]
    ↓
[Ticket Classification Agent]
    ↓
[RCA Agent]
    ├─→ [Escalation Agent]
    ├─→ [Parallel Analysis Agent]
    ├─→ [Response Generation Agent]
    └─→ [Feedback Agent]
    ↓
Master Orchestration Engine
    ↓
Watson Orchestrate → IBM BOB → Ticket System
```
 
**Conditional Branching**:
- High priority → Escalation agent involved
- Known pattern → Skip RCA, use cached solution
- Critical → Parallel analysis mandatory
- Resolved → Feedback collection
 
**Error Recovery**:
- Agent fails → Use fallback/mock response
- LLM timeout → Escalate to human
- NLU fails → Keyword-based fallback
 
### Request/Response Schema
 
**Standardized Input** (to all agents):
```python
{
    "request_id": "req_12345",
    "timestamp": "2024-01-15T14:30:00Z",
    "customer_id": "CUST_67890",
    "payload": {
        # Agent-specific fields
    },
    "context": {
        "upstream_results": {},  # Previous agent outputs
        "session_id": "sess_abc"
    }
}
```
 
**Standardized Output** (from all agents):
```python
{
    "request_id": "req_12345",
    "agent_name": "intent_recognition",
    "status": "success|error|partial",
    "result": {
        # Agent-specific output
    },
    "metadata": {
        "execution_time_ms": 234,
        "confidence": 0.92,
        "cache_hit": false
    }
}
```
 
---
 
## 4. Data Storage & Retrieval
 
### Cloudant (Document Database)
 
**Collections**:
 
```
incidents/
  ├─ incident_2024_001        # One per outage
  ├─ incident_2024_002
  └─ ...
 
tickets/
  ├─ INC-2024-001234          # Created by BOB
  ├─ INC-2024-001235
  └─ ...
 
knowledge_base/
  ├─ known_issues_001         # Pattern library
  ├─ resolution_templates
  └─ ...
 
audit_trail/
  ├─ audit_2024_01_15         # Action logs
  └─ ...
```
 
**Design**:
- One document per incident (not normalized)
- Audit trail for compliance
- TTL-based cleanup for demo data
 
---
 
### ChromaDB (Vector Store)
 
**Collections**:
 
```
telecom_knowledge_base/
  - Embedded incident descriptions
  - Resolution patterns
  - Troubleshooting guides
 
outage_patterns/
  - Known outage signatures
  - Similar incident clustering
 
customer_notes/
  - Historical customer communications
  - Feedback comments
```
 
**Indexing**:
- 500-1000 documents indexed
- Sentence-Transformers embeddings (384-dim)
- Top-K similarity search (k=3-5)
- Semantic matching for RAG
 
**Decision: Local ChromaDB, Not Managed**
- **Rationale**: POC scale, no persistence needed, faster setup
- **Tradeoff**: Single-instance only, no HA
 
---
 
## 5. Security & Guardrails
 
### PII Protection
 
```python
class PIIGuardrails:
    PATTERNS = {
        "phone": r"\+?1?\d{10}",
        "email": r"[a-z0-9.]+@[a-z]+\.[a-z]+",
        "ssn": r"\d{3}-\d{2}-\d{4}",
        "credit_card": r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"
    }
   
    def mask_input(text: str) -> str:
        # Replace PII with [REDACTED]
       
    def log_sanitized(data: dict) -> None:
        # Never log unmasked PII
```
 
**Application**:
- Input masking: Before any processing
- Output masking: Before returning to UI
- Log sanitization: For audit trail
- Vault integration: For stored credentials
 
---
 
### Input Validation
 
```python
class InputGuardrails:
    MAX_LENGTH = 2000       # Message length
    MAX_ENTITIES = 10       # Extracted entities
    RATE_LIMIT = 100       # Requests/minute per user
   
    def validate(message: str) -> bool:
        # Length check
        # SQL injection check
        # Prompt injection check (LLM-specific)
```
 
---
 
### Output Validation
 
```python
class OutputGuardrails:
    CONFIDENCE_MIN = 0.5    # Only use if confident
    TONE_CHECK = True       # Ensure professional tone
    FACTUALITY_CHECK = True # Verify against knowledge base
   
    def validate(response: dict) -> bool:
        # Schema validation (Pydantic)
        # Confidence threshold
        # Tone analysis
```
 
---
 
## 6. Error Handling & Recovery
 
### Error Categories
 
| Category | Handling |
|----------|----------|
| **Service Unavailable** | Use cached response / fallback |
| **Rate Limited** | Queue and retry with backoff |
| **Data Validation** | Return 400 Bad Request |
| **LLM Timeout** | Escalate to human |
| **Network Timeout** | Exponential backoff (5 retries) |
| **Schema Mismatch** | Log, escalate, use default |
 
### Fallback Strategy
 
```python
try:
    result = watsonx_client.generate(prompt)
except APIError:
    # Fallback 1: Cache hit from similar previous query
    result = cache.get(query_hash)
    if not result:
        # Fallback 2: Simple keyword matching
        result = keyword_match_fallback(prompt)
    if not result:
        # Fallback 3: Human escalation
        result = escalate_to_human()
```
 
---
 
## 7. Testing Strategy
 
### Unit Tests (Per Agent)
 
```python
# Structure per agent:
tests/unit/test_<agent_name>.py
├── test_valid_input               # Happy path
├── test_invalid_input             # Input validation
├── test_schema_validation         # Output schema
├── test_error_handling            # Error recovery
├── test_performance               # SLA compliance
└── test_mocking                   # Mocked dependencies
```
 
**Coverage Target**: 70%+  
**Total Tests**: 280+ (40 per agent)
 
### Integration Tests
 
```python
tests/integration/
├── test_orchestration_flow.py     # Sequential agents
├── test_error_recovery.py         # Fallback paths
├── test_rag_pipeline.py           # ChromaDB queries
├── test_cloudant_storage.py       # Document ops
└── test_end_to_end.py             # Full flow
```
 
**Coverage Target**: Critical paths  
**Total Tests**: 20+
 
### Mock Strategy
 
- **All external services mocked** during development
- Use `pytest-mock` with `@patch` decorator
- Create realistic fixture data
- Test with synthetic outages
- **Zero real API calls** in Phase 0-2
 
---
 
## 8. Performance & Scalability
 
### Latency Targets
 
| Agent | Target | Notes |
|-------|--------|-------|
| Intent Recognition | <500ms | NLU entity extraction |
| Ticket Classification | <200ms | Rule-based lookup |
| RCA | <2s | Includes LLM call |
| Escalation | <500ms | Decision tree |
| Parallel Analysis | <1s | Multiple queries |
| Response Generation | <1.5s | Template + LLM |
| Feedback | <500ms | Async after resolution |
| **End-to-End** | <8s | Total orchestration |
 
### Optimization Strategies
 
1. **Caching**:
   - Cache similar incidents in RCA agent
   - Cache embedding vectors
   - Cache resolution templates
 
2. **Parallelization**:
   - Run Escalation + Parallel Analysis in parallel
   - Async I/O for Cloudant queries
 
3. **Fallbacks**:
   - Use simple keyword match if LLM slow
   - Skip parallel analysis for simple cases
 
---
 
## 9. Deployment & Operations
 
### Environment Configuration
 
- **Development**: Local ChromaDB, mocked IBM services
- **Staging**: Real services, mocked LLM
- **Production**: All real services (for demo)
 
### Credential Management
 
- Store in `.env` (development only)
- Use environment variables
- Never commit credentials
- Rotate keys regularly
 
### Monitoring & Observability
 
```python
logger.info(f"Agent: {agent_name}, Duration: {execution_time}ms, Status: {status}")
# Log all requests/responses
# Track confidence scores
# Monitor API quota usage
```
 
---
 
## 10. Lite Plan Budget Management
 
### Strategy: Mock-First Development
 
**Phase 0-2**: 100% mocked services  
**Phase 3-4**: 5 real calls for testing  
**Phase 5**: 5 real calls for demo  
 
**Total Budget Used**: ~10 calls  
**Monthly Limit**: 100 calls  
**Safety Margin**: 900%+
 
---
 
## 11. Decision Log
 
| Decision | Rationale | Alternatives Considered |
|----------|-----------|--------------------------|
| **FastAPI** | Modern, async-first, excellent testing | Django, Flask |
| **Pydantic** | Type-safe, built-in validation | dataclasses, attrs |
| **ChromaDB** | Local, simple, fast setup | Pinecone, Weaviate |
| **pytest** | Industry standard, excellent mocking | unittest, nose |
| **Mock-first** | Preserve API budget, faster testing | Real API early |
| **Sequential agents** | Simple orchestration, easy debugging | Parallel agents |
| **Watson Orchestrate** | Native IBM tool, easy integration | Custom orchestration |
 
---
 
## 12. Known Limitations & Future Work
 
### Current Limitations
 
- Single-instance deployment (no HA)
- No distributed caching
- Synchronous orchestration only
- No multi-language support
- No advanced NLU training
 
### Future Enhancements
 
1. **Phase 6**: Add advanced RCA with causal graphs
2. **Phase 7**: Implement predictive escalation
3. **Phase 8**: Add multi-channel support (Slack, Teams)
4. **Phase 9**: Real-time incident simulation
5. **Phase 10**: ML-based SLA optimization
 
---
 
## References
 
- [FastAPI Best Practices](https://fastapi.tiangolo.com/)
- [IBM Watson Documentation](https://cloud.ibm.com/docs/watson)
- [Pydantic Validation](https://docs.pydantic.dev/)
- [ChromaDB Embeddings](Introduction - Chroma Docs)
- [Microservices Patterns](https://microservices.io/)
 
---
 
**Document Version**: 1.0  
**Last Updated**: 2026-07-22  
**Status**: APPROVED ✅
 
FastAPI - FastAPI
FastAPI framework, high performance, easy to learn, fast to code, ready for production
 
# Plan: Telecom Outage Resolution BOB POC
 
## Event & Context
 
- **Event**: IBM BOB Hackathon 2026
- **Duration**: 2-day POC (July 22-23, 2026)
- **Architecture**: 7 specialized agents coordinated by Watson Orchestrate + IBM BOB
- **Backend**: Python + FastAPI
- **Frontend**: React UI
- **LLM**: IBM Granite via watsonx.ai
- **Data Store**: Cloudant (incidents), ChromaDB (embeddings/RAG)
- **Services**: watsonx.ai, NLU, Watson Orchestrate, Cloudant, STT/TTS
 
---
 
## Project Structure
 
```
bobCode/
├── agents/               # 7 FastAPI agent modules
│   ├── intent_agent.py           # Intent recognition (NLU)
│   ├── ticket_agent.py           # Ticket classification
│   ├── rca_agent.py              # Root cause analysis
│   ├── escalation_agent.py       # Risk assessment & escalation
│   ├── parallel_agent.py         # Multi-dimensional analysis
│   ├── resolution_agent.py       # Automated response generation
│   └── feedback_agent.py         # Post-resolution validation
│
├── core/                 # Shared infrastructure
│   ├── granite_client.py         # watsonx.ai Granite wrapper
│   ├── nlu_client.py             # IBM NLU service wrapper
│   ├── vectorstore.py            # ChromaDB RAG management
│   ├── cloudant_client.py        # Cloudant document storage
│   ├── guardrails.py             # Security & PII protection
│   └── config.py                 # Environment settings
│
├── data/                 # Data management
│   ├── seed_data/                # Synthetic telecom datasets
│   │   ├── outages.json
│   │   ├── incidents.json
│   │   └── knowledge_base.txt
│   └── ingest.py                 # Vector DB ingestion script
│
├── api/
│   ├── main.py                   # FastAPI entrypoint
│   ├── models.py                 # Pydantic schemas
│   └── routes.py                 # Additional routes
│
├── openapi/              # API specifications
│   └── skills_spec.json          # Exported for Watson Orchestrate
│
├── frontend/             # React UI (Phase 4)
│   ├── components/
│   ├── pages/
│   └── App.tsx
│
├── tests/                # Testing infrastructure
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── conftest.py
│
└── scripts/              # Utility scripts
    ├── demo.md                   # Demo flow documentation
    ├── test_credentials.py       # Credential verification
    └── setup.sh                  # Environment setup
```
 
---
 
## Implementation Phases
 
### Phase 0: Setup & Scaffolding (Complete ✅)
**Duration**: ~2 hours  
**Status**: DONE
 
- ✅ Python venv setup
- ✅ FastAPI + dependencies installation
- ✅ IBM service credentials → .env
- ✅ ChromaDB local instance initialization
- ✅ Health check endpoints
- ✅ 5 unit tests passing (100%)
- ✅ Zero real API calls made
 
**Deliverables**:
- Complete project structure
- All dependencies installed
- Tests passing
- Documentation ready
 
---
 
### Phase 1: Core Infrastructure & Data Preparation
**Duration**: ~3-4 hours  
**Status**: NEXT
 
**Tasks**:
1. **Agent Base Class** (30 min)
   - Define abstract agent interface
   - Implement request validation
   - Implement response formatting
   - Error handling patterns
 
2. **Synthetic Data Generation** (45 min)
   - 50+ telecom outage scenarios
   - Location data (major cities)
   - Service types (4G, 5G, WiFi, fiber)
   - Incident patterns
 
3. **RAG Setup** (45 min)
   - Ingest knowledge base into ChromaDB
   - Create vector embeddings
   - Implement similarity search
   - Test retrieval quality
 
4. **NLU Integration** (45 min)
   - Entity extraction patterns
   - Intent classification setup
   - Training data preparation
   - Mock NLU responses
 
5. **Agent Tests** (60 min)
   - 40+ unit tests per agent
   - Fixture-based mocking
   - Input validation tests
   - Output schema tests
 
**Deliverables**:
- 7 agent endpoints (all mocked)
- 280+ passing unit tests
- RAG pipeline working locally
- Synthetic dataset ready
 
---
 
### Phase 2: Agent Implementation & Orchestration
**Duration**: ~3-4 hours  
**Status**: AFTER PHASE 1
 
**Tasks**:
1. **Intent Recognition Agent** (45 min)
   - Classify issue types
   - Extract location, service, priority
   - Compute confidence scores
 
2. **Ticket Classification Agent** (45 min)
   - Route to appropriate queue
   - Categorize by severity
   - Add metadata
 
3. **RCA Agent** (60 min)
   - Query RAG for similar incidents
   - Use Granite LLM for analysis
   - Generate root cause hypothesis
 
4. **Escalation Agent** (30 min)
   - Risk assessment
   - Escalation decision logic
   - Notify team
 
5. **Parallel Analysis Agent** (45 min)
   - Multi-dimensional analysis
   - Performance impact
   - Customer affected count
 
6. **Response Generation Agent** (45 min)
   - Generate resolution steps
   - Create customer communication
   - Draft ticket response
 
7. **Feedback Agent** (30 min)
   - Post-resolution surveys
   - Quality metrics
   - Learning collection
 
8. **Master Orchestration** (60 min)
   - `/orchestrate` endpoint logic
   - Sequential agent coordination
   - Conditional branching
   - Error recovery
 
**Deliverables**:
- 7 fully functional agents
- Orchestration flow working
- Integration tests passing
- API spec exported for Watson Orchestrate
 
---
 
### Phase 3: Watson Orchestrate & BOB Integration
**Duration**: ~2 hours  
**Status**: AFTER PHASE 2
 
**Tasks**:
1. **Export API Specification** (20 min)
   - Generate OpenAPI spec
   - Register all agent endpoints
   - Document skill parameters
 
2. **Watson Orchestrate Setup** (40 min)
   - Create orchestration skills
   - Define skill parameters
   - Build orchestration flow
 
3. **IBM BOB Integration** (40 min)
   - Create incident workflow
   - Integrate with ticket system
   - Automate ticket creation
 
4. **End-to-End Testing** (20 min)
   - Test full orchestration flow
   - Verify BOB ticket creation
   - Test error scenarios
 
**Deliverables**:
- Watson Orchestrate skills defined
- BOB workflow automated
- E2E tests passing
 
---
 
### Phase 4: React Frontend
**Duration**: ~2 hours  
**Status**: AFTER PHASE 3
 
**Tasks**:
1. **Chat Interface** (45 min)
   - Customer input form
   - Real-time message streaming
   - Response formatting
 
2. **Agent Visualization** (45 min)
   - Show active agents
   - Display data flow
   - Show confidence metrics
 
3. **Incident Timeline** (20 min)
   - Display agent actions
   - Show timestamps
   - Link to tickets
 
4. **Error Handling UI** (10 min)
   - Error messages
   - Retry buttons
 
**Deliverables**:
- Working React UI
- Real-time chat functional
- Agent visualization working
 
---
 
### Phase 5: Demo & Polish
**Duration**: ~1 hour  
**Status**: AFTER PHASE 4
 
**Tasks**:
1. **Real API Integration** (20 min)
   - Activate watsonx.ai calls
   - Enable NLU entity extraction
   - Real Cloudant storage
 
2. **Demo Scenarios** (20 min)
   - Prepare 3-5 demo flows
   - Load sample incidents
   - Test end-to-end
 
3. **Performance Tuning** (15 min)
   - Measure end-to-end latency
   - Optimize slow paths
   - Cache optimization
 
4. **Final Testing** (5 min)
   - Smoke tests
   - Quick verification
 
**Deliverables**:
- Live demo ready
- All systems working
- Performance acceptable
- Budget under Lite Plan limits (~10 API calls)
 
---
 
## IBM Service Integration
 
### watsonx.ai (Granite LLM)
**Purpose**: LLM inference for RCA, resolution generation  
**Model**: `ibm/granite-13b-instruct-v2`  
**Usage**: 5-10 API calls for POC (mocked in Phase 0-2, real in Phase 5)  
**Lite Plan**: 100 free calls/month ✅
 
### IBM NLU
**Purpose**: Entity extraction, intent detection  
**Entities**: Location, service type, priority  
**Usage**: Mocked in Phase 0-2, real in Phase 3+  
**Lite Plan**: 30,000 free calls/month ✅
 
### Cloudant (NoSQL Database)
**Purpose**: Store incidents, tickets, audit trail  
**Collections**: incidents, tickets, knowledge_base  
**Usage**: All testing uses mocks, optional real storage  
**Lite Plan**: Unlimited free tier ✅
 
### ChromaDB (Vector Store)
**Purpose**: Local RAG database for knowledge base  
**Index**: Telecom incident patterns + resolution steps  
**Usage**: Local instance, no API calls  
**Cost**: Zero ✅
 
### Watson Orchestrate
**Purpose**: Skill orchestration and coordination  
**Skills**: 7 agent endpoints + fallback logic  
**Usage**: Phase 3+  
**Cost**: Depends on BOB plan
 
### STT/TTS (Optional)
**Purpose**: Speech demo (if time permits)  
**Models**: Speech-to-Text, Text-to-Speech  
**Usage**: Optional, Phase 5 demo only  
**Lite Plan**: Limited free tier ⚠️
 
---
 
## Testing Strategy
 
### Unit Tests (Per Agent)
- **Count**: 40+ per agent (280+ total)
- **Scope**: Mocked all external services
- **Coverage Target**: 70%+
- **Duration**: Phase 1
 
### Integration Tests
- **Count**: 20+
- **Scope**: Real ChromaDB, mocked IBM services
- **Coverage**: Agent sequences, error paths
- **Duration**: Phase 2
 
### E2E Tests
- **Count**: 5+
- **Scope**: Full orchestration, real services (Phase 5 only)
- **Coverage**: Demo scenarios
- **Duration**: Phase 5
 
### Test Recording
All tests recorded with:
- Test name
- Input parameters
- Expected output
- Actual output
- Pass/Fail status
- Duration
 
---
 
## Lite Plan Budget Management
 
**Critical Strategy**: Mock-first development
 
| Phase | Real API Calls | Mock Calls |
|-------|---|---|
| Phase 0 | 0 | 100+ |
| Phase 1 | 0 | 200+ |
| Phase 2 | 0 | 250+ |
| Phase 3 | 5 | 100+ |
| Phase 4 | 0 | 50+ |
| Phase 5 | 5 | 20+ |
| **TOTAL** | **~10** | **700+** |
 
**Budget Remaining**: 90+ calls (900% safety margin)
 
---
 
## Milestones & Timeline
 
| Milestone | Time | Status |
|-----------|------|--------|
| Phase 0 Complete | 2:00 PM | ✅ DONE |
| Phase 1 Complete | 5:00 PM | 🔜 NEXT |
| Phase 2 Complete | 9:00 PM | 📋 DAY 1 |
| **Day 1 Checkpoint** | 9:00 PM | 📋 |
| Phase 3 Complete | 11:00 AM (Day 2) | 📋 DAY 2 |
| Phase 4 Complete | 2:00 PM (Day 2) | 📋 DAY 2 |
| Phase 5 Complete | 4:00 PM (Day 2) | 📋 DEMO |
| **Demo Ready** | 4:30 PM (Day 2) | 📋 GO-LIVE |
 
---
 
## Risk Mitigation
 
| Risk | Mitigation |
|------|-----------|
| API rate limit exceeded | Use mocks 100% during dev/test |
| Granite LLM latency | Cache responses, use embedding similarity first |
| NLU service unavailable | Fallback to keyword matching |
| Cloudant connection issues | Local SQLite backup for demo |
| Frontend build issues | Skip UI if time short, use Swagger API |
| End-to-end latency | Profile and optimize critical paths |
 
---
 
## Success Criteria
 
✅ **Phase 0**: All tests passing, zero real API calls  
✅ **Phase 1**: 280+ unit tests passing, RAG working  
✅ **Phase 2**: 7 agents implemented, orchestration working  
✅ **Phase 3**: Watson Orchestrate skills registered  
✅ **Phase 4**: React UI functional  
✅ **Phase 5**: Live demo with end-to-end flow  
 
**Final Demo**: Show customer reporting outage → system recommending resolution in <5 seconds with human approval workflow.
 
---
 
## Team Responsibilities
 
- **Infrastructure**: Ensure all services connected, API budget managed
- **Backend**: Agent implementations, orchestration logic
- **Frontend**: React UI, real-time updates
- **QA**: Test recording, coverage validation
- **Demo**: End-to-end flow verification, slides
 
---
 
## References
 
- [IBM Watsonx.ai Docs](IBM Cloud Pak for Data)
- [Watson NLU Docs](https://cloud.ibm.com/docs/natural-language-understanding)
- [IBM Watson Orchestrate](https://www.ibm.com/products/cloud-orchestrate)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [ChromaDB Docs](Introduction - Chroma Docs)
 
---
 
**Plan Last Updated**: 2026-07-22  
**Status**: ACTIVE ✅
 
IBM Cloud Pak for Data
Log in to explore IBM Cloud Pak for Data services on one platform, fully managed on the IBM Cloud, and see how you can accelerate your journey to AI today.
 
# Telecom BOB POC - IBM BOB Hackathon
 
**Event**: IBM BOB Hackathon 2026  
**Date**: July 22, 2026  
**Project**: 7-Agent Orchestration for Telecom Outage Resolution  
**Status**: Phase 0 - Project Scaffolding ✅
 
## Overview
 
A FastAPI-based conversational AI system that coordinates 7 specialized agents to resolve telecom outages through intelligent orchestration:
 
1. **Intent Recognition Agent** - Classify customer issues
2. **Ticket Classification Agent** - Categorize and route tickets
3. **RCA Agent** - Root cause analysis
4. **Escalation Agent** - Risk assessment
5. **Parallel Analysis Agent** - Multi-dimensional analysis
6. **Response Generation Agent** - Prepare automated responses
7. **Feedback Agent** - Post-resolution validation
 
Coordinated by **Watson Orchestrate** with IBM Watson NLU, Cloudant, and watsonx.ai (Granite 13B LLM).
 
## Quick Start
 
### Prerequisites
- Python 3.11+
- Windows PowerShell (or bash)
- IBM Lite Plan account with watsonx.ai, NLU, and Cloudant
 
### Setup
 
```powershell
# 1. Clone repository
cd c:\coding\IBMBobHackathon\bobCode
 
# 2. Create virtual environment
python -m venv venv
 
# 3. Activate venv
venv\Scripts\activate
 
# 4. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-test.txt
 
# 5. Create .env file from template
copy .env.example .env
# Edit .env with your IBM credentials
 
# 6. Run tests
pytest tests/ -v
 
# 7. Start API
uvicorn api.main:app --reload --port 8000
# Access Swagger: http://localhost:8000/docs
```
 
## Project Structure
 
```
bobCode/
├── agents/              # 7 specialized agent implementations
├── core/
│   ├── config.py        # Environment & settings
│   └── __init__.py
├── api/
│   ├── main.py          # FastAPI app & orchestration
│   ├── models.py        # Pydantic schemas
│   └── __init__.py
├── data/
│   └── seed_data/       # Sample outage scenarios
├── tests/
│   ├── unit/            # Unit tests (mocked services)
│   ├── integration/      # Integration tests
│   ├── fixtures/        # Shared test data
│   ├── conftest.py      # Pytest fixtures
│   └── __init__.py
├── scripts/             # Utility scripts
├── requirements.txt     # Core dependencies
├── requirements-dev.txt # Dev tools
├── requirements-test.txt # Test dependencies
├── pytest.ini           # Test configuration
├── pyproject.toml       # Project metadata
└── .env.example         # Credential template
```
 
## Testing Strategy
 
**Phase 0**: Unit tests with 100% mocked services (0 real API calls)
- 5 health check tests for API endpoints
- All tests use pytest with fixtures
 
```bash
# Run tests
pytest tests/ -v
 
# Generate coverage report
pytest tests/ -v --cov=api --cov=core --cov-report=html
```
 
## IBM Credentials
 
See [WATSONX_CREDENTIALS_GUIDE.md](../mydocs/WATSONX_CREDENTIALS_GUIDE.md) for detailed instructions on retrieving:
- **watsonx.ai**: API Key + Project ID
- **IBM NLU**: API Key + URL
- **IBM Cloudant**: API Key + URL
 
## API Endpoints
 
### Health & Info
- `GET /` - Application info
- `GET /health` - Health check
 
### Orchestration (Phase 2)
- `POST /orchestrate` - Master orchestration (placeholder)
 
Access Swagger at: `http://localhost:8000/docs`
 
## Development Commands
 
```bash
# Format code
black . --line-length 100
 
# Lint code
flake8 . --max-line-length 100
 
# Check imports
isort .
 
# Type checking
mypy agents/ core/ api/
 
# Run all checks
black . && flake8 . && isort . && mypy . && pytest
```
 
## Phases
 
- **Phase 0** ✅ Project scaffolding, health checks
- **Phase 1** 🔜 Core agent implementations with mocked IBM services
- **Phase 2** 🔜 Master orchestration & sequential agent coordination
- **Phase 3** 🔜 Real IBM service integration & credential validation
- **Phase 4** 🔜 Full integration testing & demo scenarios
 
## IBM Services Used
 
| Service | API Calls/Month | Phase 0 | Phase 1+ |
|---------|-----------------|---------|----------|
| watsonx.ai (Granite 13B) | 100 (Lite) | Mocked | Real |
| NLU | 30,000 (Lite) | Mocked | Real |
| Cloudant | Unlimited | Mocked | Real |
| STT/TTS | Limited (Lite) | Mocked | Optional |
 
**Budget**: ~10 real API calls total for POC (well under Lite Plan limits)
 
## Troubleshooting
 
### "ModuleNotFoundError: No module named 'fastapi'"
```bash
pip install -r requirements.txt
```
 
### ".env not found"
```bash
copy .env.example .env
# Add your IBM credentials to .env
```
 
### Tests fail
```bash
# Verify all dependencies installed
pip install -r requirements-test.txt
 
# Run with verbose output
pytest tests/ -vv
```
 
## Team
 
IBM BOB Hackathon 2026 - Telecom BOB Team

## Deployment Documentation

For comprehensive technical steps on deploying the solution to **IBM Cloud** (including IBM Cloud Code Engine containerization, watsonx Orchestrate agent skill integration, ChromaDB Vector DB setup, and IBM Cloud Secrets Manager credential management), refer to:
- [IBM Cloud Deployment Guide](file:///c:/tridibs/mylearning/BOBHackathonTelecomPOC/mydocs/ibm-cloud-deployment-guide.md)
 
## License
 
Internal Use Only
 
 