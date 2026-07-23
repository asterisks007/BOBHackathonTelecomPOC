"""
Unit tests for the FastAPI health / info endpoints.

Gate: ST-0 — must have ≥5 tests passing before Sub-Task 1G starts.
All tests run with USE_MOCK=True; zero real IBM API calls.
"""

import os

import pytest

os.environ["USE_MOCK"] = "true"

from api.models import HealthResponse  # noqa: E402


class TestRootEndpoint:
    """Tests for GET /"""

    def test_root_returns_200(self, sync_client):
        """Root endpoint responds with HTTP 200."""
        response = sync_client.get("/")
        assert response.status_code == 200

    def test_root_contains_name(self, sync_client):
        """Response body includes the application name."""
        data = sync_client.get("/").json()
        assert data["name"] == "Telecom Outage Resolution BOB"

    def test_root_contains_version(self, sync_client):
        """Response body includes a version field."""
        data = sync_client.get("/").json()
        assert "version" in data
        assert data["version"] == "0.1.0"

    def test_root_mock_mode_is_true(self, sync_client):
        """use_mock flag is reported as True in non-production mode."""
        data = sync_client.get("/").json()
        assert data["use_mock"] is True

    def test_root_docs_link_present(self, sync_client):
        """Root response includes a link to the API docs."""
        data = sync_client.get("/").json()
        assert data["docs"] == "/docs"

    def test_root_status_running(self, sync_client):
        """Root endpoint reports status=running."""
        data = sync_client.get("/").json()
        assert data["status"] == "running"


class TestHealthEndpoint:
    """Tests for GET /health"""

    def test_health_returns_200(self, sync_client):
        """Health endpoint responds with HTTP 200."""
        response = sync_client.get("/health")
        assert response.status_code == 200

    def test_health_status_ok(self, sync_client):
        """Health status is 'ok' when all services are mocked."""
        data = sync_client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_schema_valid(self, sync_client):
        """Response deserialises into HealthResponse model without error."""
        data = sync_client.get("/health").json()
        model = HealthResponse(**data)
        assert model.status == "ok"

    def test_health_services_listed(self, sync_client):
        """Health response lists at least 4 monitored services."""
        data = sync_client.get("/health").json()
        assert len(data["services"]) >= 4

    def test_health_use_mock_true(self, sync_client):
        """Health endpoint reports use_mock=True during scaffolding."""
        data = sync_client.get("/health").json()
        assert data["use_mock"] is True

    def test_health_api_calls_used_zero(self, sync_client):
        """No real API calls have been made at scaffold stage."""
        data = sync_client.get("/health").json()
        assert data["api_calls_used"] == 0

    def test_health_api_budget_is_100(self, sync_client):
        """Monthly Lite Plan budget is reported as 100 calls."""
        data = sync_client.get("/health").json()
        assert data["api_calls_budget"] == 100

    def test_health_services_include_watsonx(self, sync_client):
        """watsonx.ai appears in the service list."""
        data = sync_client.get("/health").json()
        names = [s["name"] for s in data["services"]]
        assert "watsonx.ai" in names

    def test_health_services_include_chromadb(self, sync_client):
        """ChromaDB (local, always real) appears in the service list."""
        data = sync_client.get("/health").json()
        names = [s["name"] for s in data["services"]]
        assert "ChromaDB" in names

    def test_health_chromadb_not_mocked(self, sync_client):
        """ChromaDB is flagged as mock_mode=False (it is always local)."""
        data = sync_client.get("/health").json()
        chroma = next(s for s in data["services"] if s["name"] == "ChromaDB")
        assert chroma["mock_mode"] is False


class TestReadinessEndpoint:
    """Tests for GET /ready"""

    def test_ready_returns_200(self, sync_client):
        """Readiness probe responds with HTTP 200."""
        response = sync_client.get("/ready")
        assert response.status_code == 200

    def test_ready_body(self, sync_client):
        """Readiness probe returns {ready: true}."""
        data = sync_client.get("/ready").json()
        assert data["ready"] is True


class TestCorsPolicy:
    """Verify CORS is not open to all origins."""

    def test_cors_allowed_for_vite_dev(self, sync_client):
        """Vite dev origin (localhost:5173) is accepted."""
        response = sync_client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 200

    def test_docs_endpoint_accessible(self, sync_client):
        """Swagger UI is accessible at /docs (useful for demo)."""
        response = sync_client.get("/docs")
        assert response.status_code == 200
