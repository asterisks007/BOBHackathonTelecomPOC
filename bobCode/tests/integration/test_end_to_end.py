"""
Integration tests for Watson Orchestrate & IBM BOB webhook layer.

Gate: ST-4 — ≥5 integration tests, all mocked.
Tests cover: webhook endpoint, Cloudant ticket write, skill response schema,
             ticket retrieval, PII sanitisation in stored documents.
Zero real IBM API calls.
"""

import os
import uuid

import pytest

os.environ["USE_MOCK"] = "true"

from agents.rca_agent import RCAAgent
from core.cloudant_client import clear_mock_store, get_mock_store


class TestWatsonOrchestrateWebhook:
    """Tests for POST /webhook/orchestrate"""

    def setup_method(self):
        clear_mock_store()
        RCAAgent.clear_cache()

    def test_webhook_returns_200(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "fiber cut at junction box BX-42 affecting sector north",
                "source": "watson_orchestrate",
            },
        )
        assert response.status_code == 200

    def test_webhook_response_has_ticket_id(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "4G signal degradation across sector east",
            },
        )
        data = response.json()
        assert data.get("ticket_id") is not None
        assert data["ticket_id"].startswith("INC-")

    def test_webhook_response_has_severity(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "complete total fiber cut city-wide emergency",
            },
        )
        data = response.json()
        assert data.get("severity") in ("P1", "P2", "P3", "P4")

    def test_webhook_response_has_queue(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "billing system down, customers cannot pay",
            },
        )
        data = response.json()
        assert data.get("queue") is not None

    def test_webhook_response_has_resolution_steps_count(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "DNS failure affecting all subscribers",
            },
        )
        data = response.json()
        assert data.get("resolution_steps_count", 0) > 0

    def test_webhook_response_has_customer_message(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "signal degradation on 4G network",
            },
        )
        data = response.json()
        assert isinstance(data.get("customer_message"), str)
        assert len(data["customer_message"]) > 10

    def test_webhook_response_has_execution_ms(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "power failure at cell site TX-089",
            },
        )
        data = response.json()
        assert data.get("total_execution_ms", 0) > 0

    def test_webhook_rejects_empty_message(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "",
            },
        )
        assert response.status_code == 422

    def test_webhook_rejects_too_long_message(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "x" * 2001,
            },
        )
        assert response.status_code == 422

    def test_webhook_status_success_when_all_agents_complete(self, sync_client):
        response = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-WO-001",
                "message": "fiber cut affecting backhaul link",
            },
        )
        data = response.json()
        assert data.get("status") == "success"


class TestBOBCloudantTicketWrite:
    """Tests verifying the ticket document is written to Cloudant."""

    def setup_method(self):
        clear_mock_store()
        RCAAgent.clear_cache()

    def test_ticket_written_to_cloudant_tickets_db(self, sync_client):
        sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-BOB-001",
                "message": "fiber cut at junction box",
                "source": "ibm_bob",
            },
        )
        store = get_mock_store()
        assert "tickets" in store
        tickets = list(store["tickets"].values())
        assert len(tickets) >= 1

    def test_ticket_document_has_required_fields(self, sync_client):
        sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-BOB-001",
                "message": "signal degradation sector east",
            },
        )
        store = get_mock_store()
        ticket = list(store["tickets"].values())[0]
        for field in ("ticket_id", "severity", "queue", "issue_type",
                      "root_cause_summary", "resolution_steps", "status"):
            assert field in ticket, f"Missing field in Cloudant doc: {field}"

    def test_ticket_document_has_no_pii(self, sync_client):
        """PII in customer message must not reach the Cloudant ticket document."""
        sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-BOB-001",
                "message": "fiber cut, call 555-012-3456 for updates, user@example.com",
            },
        )
        store = get_mock_store()
        ticket = list(store.get("tickets", {}).values())[0]
        doc_str = str(ticket)
        assert "555-012-3456" not in doc_str
        assert "user@example.com" not in doc_str

    def test_ticket_document_status_is_open(self, sync_client):
        sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-BOB-001",
                "message": "billing system outage affecting all customers",
            },
        )
        store = get_mock_store()
        ticket = list(store["tickets"].values())[0]
        assert ticket.get("status") == "open"

    def test_ticket_document_has_created_at(self, sync_client):
        sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-BOB-001",
                "message": "dns failure all subscribers affected",
            },
        )
        store = get_mock_store()
        ticket = list(store["tickets"].values())[0]
        assert "created_at" in ticket or "_created_at" in ticket


class TestTicketRetrieval:
    """Tests for GET /webhook/tickets/{ticket_id}"""

    def setup_method(self):
        clear_mock_store()
        RCAAgent.clear_cache()

    def test_retrieve_existing_ticket(self, sync_client):
        # Create a ticket first
        post_resp = sync_client.post(
            "/webhook/orchestrate",
            json={
                "session_id": str(uuid.uuid4()),
                "customer_id": "CUST-RETR-001",
                "message": "4G capacity exhaustion at stadium district",
            },
        )
        ticket_id = post_resp.json().get("ticket_id")
        assert ticket_id is not None

        # Retrieve it
        get_resp = sync_client.get(f"/webhook/tickets/{ticket_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data.get("ticket_id") == ticket_id

    def test_retrieve_nonexistent_ticket_returns_404(self, sync_client):
        response = sync_client.get("/webhook/tickets/INC-9999-NONEXISTENT")
        assert response.status_code == 404


class TestWatsonHealth:
    """Tests for GET /webhook/health"""

    def test_webhook_health_returns_200(self, sync_client):
        response = sync_client.get("/webhook/health")
        assert response.status_code == 200

    def test_webhook_health_shows_mock_mode(self, sync_client):
        data = sync_client.get("/webhook/health").json()
        assert data.get("use_mock") is True

    def test_webhook_health_shows_integration_name(self, sync_client):
        data = sync_client.get("/webhook/health").json()
        assert data.get("integration") == "watson_orchestrate"
