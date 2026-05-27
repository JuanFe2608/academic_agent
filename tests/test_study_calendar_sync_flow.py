"""Pruebas del flujo confirmable de sync de sesiones con Outlook."""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from agents.support.flows.sync.study_calendar_sync import sync_study_calendar_turn
from agents.support.state import AgentState
from schemas.scheduling import Event


def _study_plan_state() -> dict:
    return {
        "persisted_profile_id": 77,
        "plan_events": [
            Event(
                id="study-1",
                dia="Lunes",
                inicio="08:00",
                fin="09:00",
                titulo="Estudiar Bases de Datos",
                tipo="confirmado",
                categoria="estudio",
                origen="study_plan",
                timezone="America/Bogota",
            )
        ],
    }


def test_study_calendar_sync_prompts_when_outlook_has_manual_drift(monkeypatch) -> None:
    materialization_service = MagicMock()
    materialization_service.materialize_plan_instances.return_value = MagicMock(
        materialized=True,
        materialized_instance_count=1,
        superseded_instance_count=0,
        horizon_days=14,
        materialized_through_date="2026-01-18",
    )
    reconciliation_service = MagicMock()
    reconciliation_service.reconcile_student_calendar.return_value = MagicMock(
        reconciled=True,
        drifted_count=1,
        missing_count=0,
        findings=[
            MagicMock(
                status="drifted",
                title="Estudiar Bases de Datos",
                source_instance_key="study-plan:77:1",
                external_event_id="outlook:study-1",
                drift_fields=("start",),
                detail="Se detectaron diferencias manuales en Outlook.",
                web_link=None,
            )
        ],
    )
    calendar_service = MagicMock()
    monkeypatch.setattr(
        "agents.support.flows.sync.study_calendar_sync.get_study_plan_materialization_service",
        lambda: materialization_service,
    )
    monkeypatch.setattr(
        "agents.support.flows.sync.study_calendar_sync.get_outlook_study_calendar_reconciliation_service",
        lambda: reconciliation_service,
    )
    monkeypatch.setattr(
        "agents.support.flows.sync.study_calendar_sync.get_outlook_calendar_sync_service",
        lambda: calendar_service,
    )
    state = AgentState(
        phase="running",
        messages=[HumanMessage(content="sincroniza mis sesiones con Outlook")],
        student_profile={"persisted_student_id": 15},
        calendar={"provider": "outlook", "authorized": True, "calendar_id": "cal-1"},
        study_plan=_study_plan_state(),
    )

    update = sync_study_calendar_turn(state)

    assert update["awaiting_user_input"] is True
    assert "Detecté que editaste" in update["messages"][0].content
    assert update["interaction"]["confirmation_pending"] is True
    assert update["interaction"]["last_confirmation_payload"]["operation"] == "resolve_study_calendar_manual_changes"
    assert update["study_plan"]["rules"]["external_sync_status"] == "awaiting_manual_outlook_decision"
    calendar_service.preview_student_calendar_sync.assert_not_called()


def test_study_calendar_sync_restores_assistant_plan_after_manual_drift_decision(monkeypatch) -> None:
    calendar_service = MagicMock()
    calendar_service.sync_student_calendar.return_value = MagicMock(
        synced=True,
        upserted_count=1,
        deleted_count=0,
        synced_event_map={"study-plan:77:1": "outlook:study-1"},
    )
    reconciliation_service = MagicMock()
    monkeypatch.setattr(
        "agents.support.flows.sync.study_calendar_sync.get_outlook_calendar_sync_service",
        lambda: calendar_service,
    )
    monkeypatch.setattr(
        "agents.support.flows.sync.study_calendar_sync.get_outlook_study_calendar_reconciliation_service",
        lambda: reconciliation_service,
    )
    state = AgentState(
        phase="running",
        awaiting_user_input=True,
        messages=[HumanMessage(content="2")],
        student_profile={"persisted_student_id": 15},
        calendar={"provider": "outlook", "authorized": True, "calendar_id": "cal-1"},
        study_plan=_study_plan_state(),
        interaction={
            "confirmation_pending": True,
            "last_confirmation_payload": {
                "domain": "calendar_sync",
                "operation": "resolve_study_calendar_manual_changes",
                "study_plan_profile_id": 77,
                "findings": [
                    {
                        "status": "drifted",
                        "source_instance_key": "study-plan:77:1",
                        "title": "Estudiar Bases de Datos",
                    }
                ],
            },
        },
    )

    update = sync_study_calendar_turn(state)

    assert update["awaiting_user_input"] is False
    assert "Restauré Outlook" in update["messages"][0].content
    assert update["study_plan"]["rules"]["external_sync"]["result"]["decision"] == "restore"
    calendar_service.sync_student_calendar.assert_called_once()
