"""Integration smoke tests (require the Docker stack running)."""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.integration

BASE = "http://localhost:8000"


def test_health_ok():
    r = httpx.get(f"{BASE}/api/v1/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics_exposed():
    r = httpx.get(f"{BASE}/metrics", timeout=5)
    assert r.status_code == 200
    assert b"app_http_requests_total" in r.content


def test_auth_and_chat_flow():
    # Register (or log in if already present).
    email = "smoketest@example.com"
    reg = httpx.post(
        f"{BASE}/api/v1/auth/register",
        json={"email": email, "password": "smoke-password-123"},
        timeout=10,
    )
    if reg.status_code == 409:
        reg = httpx.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": email, "password": "smoke-password-123"},
            timeout=10,
        )
    token = reg.json()["access_token"]

    chat = httpx.post(
        f"{BASE}/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "How do I optimize my resume for an ATS?"},
        timeout=60,
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["answer"]
    assert body["route"] in {"knowledge", "job_search", "draft", "track"}
