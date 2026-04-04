"""Pruebas de materialización persistente de instancias del plan semanal."""

from __future__ import annotations

from datetime import datetime as real_datetime

import services.planning.materialization_service as materialization_module
from agents.support.dependencies import (
    set_personalization_service,
    set_study_plan_materialization_service,
    set_study_planning_persistence_service,
)
from agents.support.nodes.persist_study_profile.node import persist_study_profile
from repositories.personalization.repository import InMemoryPersonalizationRepository
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.planning.repository import InMemoryStudyPlanningRepository
from schemas.planning import SubjectItem
from schemas.scheduling import Event
from services.personalization import (
    PersonalizationConfig,
    PersonalizationService,
    get_questions,
)
from agents.support.state import AgentState
from services.planning import (
    StudyPlanMaterializationService,
    StudyPlanningPersistenceService,
)
from services.scheduling import WeeklyScheduleBlock


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


def _study_event(day: str, title: str, source_id: str) -> Event:
    return Event(
        id=source_id,
        dia=day,
        inicio="18:00",
        fin="18:25",
        titulo=title,
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner",
        prioridad="alta",
        dificultad=4,
        timezone="America/Bogota",
    )


def _academic_block(day_of_week: str, title: str) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day_of_week,
        start_time="08:00",
        end_time="10:00",
        source_text=f"{title} {day_of_week} 08:00-10:00",
    )


def _completed_profile_payload() -> dict[str, object]:
    repository = InMemoryPersonalizationRepository()
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=repository,
    )
    answers = {
        question.question_id: answer
        for question, answer in zip(
            get_questions(),
            [3, 3, 2, 2, 1, 1, 0, 3, 1, 1],
            strict=True,
        )
    }
    payload = service.evaluate_answers(answers).model_dump(mode="python")
    payload["completed_at"] = "2026-01-01T08:00:00-05:00"
    return payload


def test_materialization_service_creates_instances_for_horizon(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    repository = InMemoryStudyPlanInstancesRepository()
    service = StudyPlanMaterializationService(repository=repository, horizon_days=14)

    result = service.materialize_plan_instances(
        student_id=7,
        study_plan_profile_id=31,
        study_plan={
            "plan_events": [
                _study_event("Lunes", "Estudio Lunes", "evt-mon"),
                _study_event("Martes", "Estudio Martes", "evt-tue"),
                _study_event("Miercoles", "Estudio Miercoles", "evt-wed"),
                _study_event("Jueves", "Estudio Jueves", "evt-thu"),
                _study_event("Viernes", "Estudio Viernes", "evt-fri"),
                _study_event("Sabado", "Estudio Sabado", "evt-sat"),
                _study_event("Domingo", "Estudio Domingo", "evt-sun"),
            ],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )

    assert result.materialized is True
    assert result.materialized_instance_count == 14
    assert result.superseded_instance_count == 0
    assert result.materialized_through_date == "2026-01-18"
    assert len(repository._instances_by_key) == 14


def test_materialization_service_supersedes_future_instances_from_previous_plan(
    monkeypatch,
) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    repository = InMemoryStudyPlanInstancesRepository()
    service = StudyPlanMaterializationService(repository=repository, horizon_days=7)

    first = service.materialize_plan_instances(
        student_id=9,
        study_plan_profile_id=101,
        study_plan={
            "plan_events": [_study_event("Lunes", "Estudio Calculo", "evt-calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )
    second = service.materialize_plan_instances(
        student_id=9,
        study_plan_profile_id=102,
        study_plan={
            "plan_events": [_study_event("Miercoles", "Estudio Programacion", "evt-progra")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )

    assert first.materialized_instance_count == 1
    assert second.materialized_instance_count == 1
    assert second.superseded_instance_count == 1
    previous_plan_statuses = {
        payload["status"]
        for payload in repository._instances_by_key.values()
        if payload["study_plan_profile_id"] == 101
    }
    assert previous_plan_statuses == {"superseded"}


def test_persist_study_profile_materializes_instances_without_breaking_flow(
    monkeypatch,
) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=14,
    )
    set_personalization_service(personalization_service)
    set_study_planning_persistence_service(planning_service)
    set_study_plan_materialization_service(materialization_service)
    try:
        state = AgentState(
            phase="study_profile_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "Calculo")],
                "summary_text": "resumen",
                "conflicts": [],
            },
            study_profile=_completed_profile_payload(),
        )

        update = persist_study_profile(state)

        assert update["study_plan"]["persisted_profile_id"] == 1
        assert update["study_plan"]["materialization_error"] is None
        assert (update["study_plan"]["materialized_instance_count"] or 0) >= 1
        assert update["study_plan"]["materialized_horizon_days"] == 14
        assert len(instances_repository._instances_by_key) >= 1
    finally:
        set_personalization_service(None)
        set_study_planning_persistence_service(None)
        set_study_plan_materialization_service(None)
