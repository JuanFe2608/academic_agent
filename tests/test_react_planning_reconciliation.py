"""Regresiones para reconciliacion post-tool del agente ReAct."""

from __future__ import annotations

from agents.support.state import AgentState
from schemas.planning import SubjectItem
from schemas.scheduling import Event
from services.planning import reconcile_react_tool_updates
from services.scheduling import WeeklyScheduleBlock


def _block(
    title: str,
    *,
    block_type: str = "academic",
    day: str = "monday",
    start: str = "08:00",
    end: str = "10:00",
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type=block_type,
        title=title,
        day_of_week=day,
        start_time=start,
        end_time=end,
        source_text=f"{title} {day} {start}-{end}",
        is_active=True,
    )


def _study_event(title: str) -> Event:
    return Event(
        id=f"evt-{title.lower().replace(' ', '-')}",
        dia="Lunes",
        inicio="18:00",
        fin="18:45",
        titulo=f"Estudio · {title}",
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner",
        prioridad="media",
        dificultad=3,
        timezone="America/Bogota",
    )


def _event_titles(study_plan_update: dict[str, object]) -> list[str]:
    return [
        getattr(event, "titulo", str(event))
        for event in list(study_plan_update.get("plan_events") or [])
    ]


def test_reconciliation_removes_deleted_schedule_subject_from_plan() -> None:
    calculo = _block("Calculo")
    bases = _block("Bases de datos", day="tuesday")
    state = AgentState(
        schedule={"blocks": [calculo, bases]},
        subjects=[
            SubjectItem(nombre="Calculo", prioridad="media", dificultad=3),
            SubjectItem(nombre="Bases de datos", prioridad="alta", dificultad=4),
        ],
        study_plan={
            "plan_events": [_study_event("Calculo"), _study_event("Bases de datos")],
            "rules": {"status": "generated"},
        },
        study_profile={"top_techniques": ["pomodoro"]},
    )

    updates = {
        "schedule": {
            "blocks": [calculo.model_dump(mode="python")],
            "summary_text": "solo Calculo",
            "conflicts": [],
        }
    }

    reconciled = reconcile_react_tool_updates(state, updates)

    subject_names = [subject.nombre for subject in reconciled["subjects"]]
    titles = _event_titles(reconciled["study_plan"])
    assert "Bases de datos" not in subject_names
    assert all("Bases de datos" not in title for title in titles)
    assert "Calculo" in subject_names


def test_reconciliation_does_not_create_subjects_for_work_or_extracurricular() -> None:
    calculo = _block("Calculo")
    work = _block("Trabajo", block_type="work", day="monday", start="07:00", end="17:00")
    crochet = _block("Crochet", block_type="extracurricular", day="saturday", start="16:00", end="18:00")
    state = AgentState(
        schedule={"blocks": [calculo]},
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        study_plan={
            "plan_events": [_study_event("Calculo")],
            "rules": {"status": "generated"},
        },
        study_profile={"top_techniques": ["pomodoro"]},
    )

    updates = {
        "schedule": {
            "blocks": [
                calculo.model_dump(mode="python"),
                work.model_dump(mode="python"),
                crochet.model_dump(mode="python"),
            ],
            "summary_text": "con trabajo y crochet",
            "conflicts": [],
        }
    }

    reconciled = reconcile_react_tool_updates(state, updates)

    subject_names = [subject.nombre for subject in reconciled["subjects"]]
    titles = _event_titles(reconciled["study_plan"])
    assert subject_names == ["Calculo"]
    assert all("Trabajo" not in title for title in titles)
    assert all("Crochet" not in title for title in titles)


def test_reconciliation_clears_plan_when_only_non_academic_sources_remain() -> None:
    work = _block("Trabajo", block_type="work", day="monday", start="07:00", end="17:00")
    state = AgentState(
        schedule={"blocks": [work]},
        subjects=[SubjectItem(nombre="Bases de datos", prioridad="alta", dificultad=4)],
        study_plan={
            "plan_events": [_study_event("Bases de datos")],
            "rules": {"status": "generated"},
        },
    )

    updates = {
        "schedule": {
            "blocks": [work.model_dump(mode="python")],
            "summary_text": "solo trabajo",
            "conflicts": [],
        }
    }

    reconciled = reconcile_react_tool_updates(state, updates)

    assert reconciled["subjects"] == []
    assert reconciled["study_plan"]["plan_events"] == []
    assert reconciled["study_plan"]["rules"]["status"] == "skipped"
