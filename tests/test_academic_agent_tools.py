"""Pruebas de invariantes expuestas por tools ReAct."""

from __future__ import annotations

from agents.support.nodes.academic_agent.tools import make_tools
from agents.support.state import AgentState


def _tool_by_name(tools: list, name: str):
    return next(tool for tool in tools if tool.name == name)


def test_add_academic_activity_rejects_work_context() -> None:
    state = AgentState()
    add_activity = _tool_by_name(make_tools(state), "add_academic_activity")

    result = add_activity.invoke(
        {
            "subject": "Trabajo",
            "activity_type": "entrega",
            "title": "Turno de oficina",
            "due_date": "2026-05-01",
            "is_priority": False,
            "difficulty": 3,
        }
    )

    assert "actividad laboral o extracurricular" in result
    assert "add_schedule_block" in result


def test_add_academic_activity_allows_known_academic_subject_with_work_title() -> None:
    state = AgentState(
        subjects=[
            {
                "nombre": "Gestion de Proyectos",
                "prioridad": "media",
                "dificultad": 3,
            }
        ]
    )
    add_activity = _tool_by_name(make_tools(state), "add_academic_activity")

    result = add_activity.invoke(
        {
            "subject": "Gestion de Proyectos",
            "activity_type": "entrega",
            "title": "Trabajo final",
            "due_date": "2026-05-01",
            "is_priority": False,
            "difficulty": 3,
        }
    )

    assert "registr" in result.lower()
