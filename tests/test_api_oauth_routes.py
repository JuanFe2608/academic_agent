"""Pruebas de rutas HTTP del callback OAuth Microsoft."""

from __future__ import annotations

from api.app import app, habeas_data_policy


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
