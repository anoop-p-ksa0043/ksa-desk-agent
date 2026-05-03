from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from desk_agent.main import app

_SECRET = "test-secret-value-32chars-longxxx"


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_webhook_rejects_missing_secret(client):
    resp = client.post(
        "/webhook/desk",
        json={"ticketId": "123", "departmentId": "dept_1"},
    )
    assert resp.status_code == 401


def test_webhook_rejects_wrong_secret(client):
    resp = client.post(
        "/webhook/desk",
        json={"ticketId": "123", "departmentId": "dept_1"},
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_webhook_accepts_correct_secret(client):
    with patch("desk_agent.webhook._process_ticket", new_callable=AsyncMock):
        resp = client.post(
            "/webhook/desk",
            json={"ticketId": "456", "departmentId": "dept_1"},
            headers={"X-Webhook-Secret": _SECRET},
        )
    assert resp.status_code == 202
    assert resp.json()["ticketId"] == "456"


def test_webhook_accepts_contact_email_in_payload(client):
    with patch("desk_agent.webhook._process_ticket", new_callable=AsyncMock):
        resp = client.post(
            "/webhook/desk",
            json={"ticketId": "789", "departmentId": "dept_1", "contactEmail": "alice@acme.com"},
            headers={"X-Webhook-Secret": _SECRET},
        )
    assert resp.status_code == 202


def test_webhook_accepts_missing_department_id(client):
    with patch("desk_agent.webhook._process_ticket", new_callable=AsyncMock):
        resp = client.post(
            "/webhook/desk",
            json={"ticketId": "000"},
            headers={"X-Webhook-Secret": _SECRET},
        )
    assert resp.status_code == 202
