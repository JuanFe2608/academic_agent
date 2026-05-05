"""Pruebas de rutas HTTP del callback OAuth Microsoft."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import app, habeas_data_policy
from services.reminders import RunDueRemindersResult


def test_microsoft_oauth_callback_supports_current_and_legacy_paths() -> None:
    paths = {
        route.path
        for route in app.routes
        if "GET" in getattr(route, "methods", set())
    }

    assert "/oauth/callback" in paths
    assert "/auth/microsoft/callback" in paths


def test_reminder_worker_route_is_registered() -> None:
    post_paths = {
        route.path
        for route in app.routes
        if "POST" in getattr(route, "methods", set())
    }

    assert "/tasks/reminders/run" in post_paths


def test_reminder_worker_rejects_missing_configured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_REMINDER_WORKER_TOKEN", raising=False)
    client = TestClient(app, raise_server_exceptions=True)

    response = client.post("/tasks/reminders/run")

    assert response.status_code == 503


def test_reminder_worker_rejects_query_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_REMINDER_WORKER_TOKEN", "expected-token")
    client = TestClient(app, raise_server_exceptions=True)

    response = client.post("/tasks/reminders/run?token=expected-token")

    assert response.status_code == 403


def test_reminder_worker_accepts_header_token_and_returns_safe_aggregates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.reminders as reminders_module

    class _FakeRunner:
        def run_due_dispatches(self, *, limit: int):
            assert limit == 3
            return RunDueRemindersResult(
                processed=True,
                leased_count=2,
                sent_count=1,
                failed_count=0,
                retryable_count=1,
                channel_counts={"whatsapp": 2},
                dispatch_type_counts={"activity_due_60m": 1, "followup_15m": 1},
            )

    monkeypatch.setenv("ACADEMIC_AGENT_REMINDER_WORKER_TOKEN", "expected-token")
    monkeypatch.setattr(
        reminders_module,
        "build_reminder_dispatch_runner",
        lambda: _FakeRunner(),
    )
    client = TestClient(app, raise_server_exceptions=True)

    response = client.post(
        "/tasks/reminders/run?limit=3",
        headers={"x-reminder-worker-token": "expected-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "leased_count": 2,
        "sent_count": 1,
        "failed_count": 0,
        "retryable_count": 1,
        "channels": {"whatsapp": 2},
        "dispatch_types": {"activity_due_60m": 1, "followup_15m": 1},
    }


def test_habeas_data_policy_route_is_registered() -> None:
    paths = {
        route.path
        for route in app.routes
        if "GET" in getattr(route, "methods", set())
    }

    assert "/legal/habeas-data" in paths


def test_habeas_data_policy_page_contains_core_sections() -> None:
    response = habeas_data_policy()
    body = response.body.decode("utf-8")

    assert "Autorizacion para el tratamiento de datos personales" in body
    assert "Universidad Catolica de Colombia" in body
    assert "jfjaramillo12@ucatolica.edu.co" in body
    assert "Version habeas-data-v1" in body
