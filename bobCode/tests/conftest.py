"""
Pytest shared fixtures for the Telecom BOB test suite.

All fixtures default to USE_MOCK=True. External IBM services are never
called during unit or integration tests.
"""

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Ensure mock mode is active before any import resolves settings
os.environ.setdefault("USE_MOCK", "true")

from api.main import app  # noqa: E402 — must come after env setup
from api.models import AgentContext, AgentRequest


# ── HTTP clients ──────────────────────────────────────────────────────────────


@pytest.fixture()
def sync_client() -> TestClient:
    """Synchronous HTTPX test client for simple endpoint tests."""
    with TestClient(app) as client:
        yield client


@pytest.fixture()
async def async_client() -> AsyncClient:
    """Async HTTPX client for async endpoint and streaming tests."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── Request factories ─────────────────────────────────────────────────────────


@pytest.fixture()
def make_agent_request():
    """Factory fixture: returns a callable that builds an AgentRequest."""

    def _build(payload: dict, session_id: str = "sess-test-001") -> AgentRequest:
        return AgentRequest(
            request_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            customer_id="CUST-0001",
            payload=payload,
            context=AgentContext(session_id=session_id, upstream_results={}),
        )

    return _build
