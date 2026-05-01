"""Pruebas de rutas HTTP del callback OAuth Microsoft."""

from __future__ import annotations

from api.app import app


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
