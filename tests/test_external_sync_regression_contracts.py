"""Contratos pendientes para sincronizacion entrante desde Microsoft."""

from __future__ import annotations

from integrations.microsoft_graph._clients_impl import GraphMicrosoftTodoClient
from services.sync.outlook_calendar_sync_service import OutlookCalendarSyncService


def test_todo_client_exposes_task_listing_for_inbound_sync() -> None:
    assert hasattr(GraphMicrosoftTodoClient, "list_tasks")


def test_study_session_calendar_sync_exposes_reconciliation_entrypoint() -> None:
    assert hasattr(OutlookCalendarSyncService, "reconcile_student_calendar")
