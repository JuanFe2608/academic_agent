"""Tests de visibilidad de estado entre herramientas dentro del mismo ciclo ReAct.

Verifica que mutaciones de academic_activities producidas por una tool sean visibles
para las tools subsiguientes en el mismo turno, sin esperar al siguiente turno.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.support.nodes.academic_agent.tools import make_tools
from agents.support.state import AgentState
from schemas.planning import AcademicActivity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool(tools: list, name: str):
    return next(t for t in tools if t.name == name)


def _make_activity(**kwargs) -> AcademicActivity:
    defaults = {
        "activity_type": "parcial",
        "subject_name": "Matemáticas",
        "activity_title": "Parcial 1",
        "due_date": "2026-05-15",  # within 30 days of 2026-05-01 (today)
        "priority_level": "alta",
        "status": "pending",
    }
    return AcademicActivity(**(defaults | kwargs))


# ---------------------------------------------------------------------------
# Visibilidad del acumulador de ciclo
# ---------------------------------------------------------------------------

class TestCycleStateVisibility:
    """Comprueba que _cycle_updates propaga mutaciones entre tools del mismo ciclo."""

    def test_get_pending_activities_ve_actividad_recien_agregada(self) -> None:
        """get_pending_activities debe ver la actividad añadida por add_academic_activity
        en el mismo ciclo ReAct, aunque state.academic_activities esté vacío."""

        state = AgentState()  # sin actividades
        tools = make_tools(state)
        add_tool = _tool(tools, "add_academic_activity")
        pending_tool = _tool(tools, "get_pending_activities")

        new_act = _make_activity()

        # Mock de la capa de servicio que usa add_academic_activity internamente
        mock_result = MagicMock()
        mock_result.activities = [new_act]
        mock_result.message = "Parcial 1 registrada."
        mock_result.replan_required = False

        with (
            patch(
                "services.planning.academic_activity_service.build_activity_from_slots",
                return_value=new_act,
            ),
            patch(
                "services.planning.academic_activity_service.apply_confirmed_academic_activity_operation",
                return_value=mock_result,
            ),
        ):
            add_result = add_tool.invoke(
                {
                    "subject": "Matemáticas",
                    "activity_type": "parcial",
                    "title": "Parcial 1",
                    "due_date": "2026-05-15",
                    "is_priority": True,
                    "difficulty": 4,
                }
            )

        # add_academic_activity debe haber tenido éxito
        parsed = json.loads(add_result)
        assert "result" in parsed
        assert "_state_update" in parsed
        assert len(parsed["_state_update"]["academic_activities"]) == 1

        # get_pending_activities debe ver esa actividad SIN llamar a ningún servicio externo
        pending_result = pending_tool.invoke({"days_ahead": 30})
        assert "Parcial 1" in pending_result
        assert "Matemáticas" in pending_result

    def test_get_pending_activities_vacio_si_no_hay_mutacion_previa(self) -> None:
        """Sin mutación previa en el ciclo, get_pending_activities respeta state inicial."""
        state = AgentState()  # sin actividades en state
        tools = make_tools(state)
        pending_tool = _tool(tools, "get_pending_activities")

        result = pending_tool.invoke({"days_ahead": 7})
        assert "No tienes actividades" in result

    def test_sync_tasks_to_todo_ve_actividad_del_mismo_ciclo(self) -> None:
        """sync_tasks_to_todo debe usar la lista actualizada por add_academic_activity."""

        state = AgentState()
        tools = make_tools(state)
        add_tool = _tool(tools, "add_academic_activity")
        sync_tool = _tool(tools, "sync_tasks_to_todo")

        new_act = _make_activity(activity_id="act-sync-test")

        mock_add_result = MagicMock()
        mock_add_result.activities = [new_act]
        mock_add_result.message = "Registrada."
        mock_add_result.replan_required = False

        with (
            patch(
                "services.planning.academic_activity_service.build_activity_from_slots",
                return_value=new_act,
            ),
            patch(
                "services.planning.academic_activity_service.apply_confirmed_academic_activity_operation",
                return_value=mock_add_result,
            ),
        ):
            add_tool.invoke(
                {
                    "subject": "Matemáticas",
                    "activity_type": "parcial",
                    "title": "Parcial 1",
                    "due_date": "2026-05-15",
                    "is_priority": True,
                    "difficulty": 4,
                }
            )

        # Mock del servicio de sincronización con To Do
        captured_activities: list = []

        def _fake_sync(student_id, task_list_id, activities, **kwargs):
            del kwargs
            captured_activities.extend(activities)
            result = MagicMock()
            result.synced = False  # evita lógica de merge adicional
            result.detail = "test"
            result.error_code = None
            return result

        mock_todo_service = MagicMock()
        mock_todo_service.sync_academic_activities_to_todo.side_effect = _fake_sync

        with patch(
            "agents.support.dependencies.get_microsoft_todo_sync_service",
            return_value=mock_todo_service,
        ):
            sync_tool.invoke({})

        # El servicio debe haber recibido la actividad añadida en el mismo ciclo
        assert len(captured_activities) == 1
        assert captured_activities[0].activity_id == "act-sync-test"

    def test_ciclos_independientes_no_comparten_estado(self) -> None:
        """Cada llamada a make_tools crea un acumulador limpio — ciclos distintos son aislados."""

        state = AgentState()

        # Primer ciclo: agrega una actividad
        tools_cycle_1 = make_tools(state)
        add_tool_1 = _tool(tools_cycle_1, "add_academic_activity")
        pending_tool_1 = _tool(tools_cycle_1, "get_pending_activities")

        new_act = _make_activity()
        mock_result = MagicMock()
        mock_result.activities = [new_act]
        mock_result.message = "Registrada."
        mock_result.replan_required = False

        with (
            patch(
                "services.planning.academic_activity_service.build_activity_from_slots",
                return_value=new_act,
            ),
            patch(
                "services.planning.academic_activity_service.apply_confirmed_academic_activity_operation",
                return_value=mock_result,
            ),
        ):
            add_tool_1.invoke(
                {
                    "subject": "Matemáticas",
                    "activity_type": "parcial",
                    "title": "Parcial 1",
                    "due_date": "2026-05-15",
                    "is_priority": False,
                    "difficulty": 3,
                }
            )

        # get_pending dentro del mismo ciclo ve la actividad
        assert "Parcial 1" in pending_tool_1.invoke({"days_ahead": 30})

        # Segundo ciclo: distinto make_tools → acumulador limpio → no ve la actividad
        tools_cycle_2 = make_tools(state)
        pending_tool_2 = _tool(tools_cycle_2, "get_pending_activities")
        assert "No tienes actividades" in pending_tool_2.invoke({"days_ahead": 30})
