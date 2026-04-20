"""Pruebas de persistencia de materias, prioridades y plan semanal."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime as real_datetime

from langchain_core.messages import HumanMessage

import services.planning.materialization_service as materialization_module
import services.reminders.service as reminders_module
import agents.support.flows.planning.persistence_support as persistence_support
from agents.support.dependencies import (
    set_personalization_service,
    set_reminders_service,
    set_study_plan_materialization_service,
    set_study_planning_persistence_service,
)
from bootstrap.errors import RepositoryConfigurationError
from agents.support.nodes.build_study_plan.node import build_study_plan
from agents.support.nodes.collect_priorities.node import collect_priorities
from agents.support.nodes.persist_study_profile.node import persist_study_profile
from repositories.personalization.repository import InMemoryPersonalizationRepository
from repositories.planning.repository import (
    InMemoryStudyPlanningRepository,
    PostgresStudyPlanningRepository,
)
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.reminders.repository import InMemoryRemindersRepository
from schemas.planning import SubjectItem
from schemas.scheduling import Event
from services.personalization import (
    PersonalizationConfig,
    PersonalizationService,
    get_questions,
)
from agents.support.state import AgentState
from services.planning import StudyPlanningPersistenceService
from services.planning import StudyPlanMaterializationService
from services.reminders import StudyPlanRemindersService
from services.scheduling import WeeklyScheduleBlock


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


def _academic_block(day_of_week: str, title: str) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day_of_week,
        start_time="08:00",
        end_time="10:00",
        source_text=f"{title} {day_of_week} 08:00-10:00",
    )



def _study_event(title: str) -> Event:
    return Event(
        id=f"evt-{title.lower()}",
        dia="Lunes",
        inicio="18:00",
        fin="18:25",
        titulo=title,
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner_v1",
        prioridad="alta",
        dificultad=4,
        timezone="America/Bogota",
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



def test_in_memory_study_planning_repository_versions_priority_and_plan_profiles() -> None:
    repository = InMemoryStudyPlanningRepository()

    first = repository.replace_student_planning_snapshot(
        student_id=7,
        schedule_profile_id=11,
        personalization_profile_id=21,
        priorities_state={"status": "collecting", "source": "derived_from_schedule"},
        subjects=[
            SubjectItem(
                nombre="Calculo",
                prioridad="alta",
                dificultad=4,
                urgencia=None,
                carga_semanal_min=240,
                origen="derived_from_schedule",
            )
        ],
        study_plan={
            "plan_events": [_study_event("Estudio Calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )
    second = repository.replace_student_planning_snapshot(
        student_id=7,
        schedule_profile_id=12,
        personalization_profile_id=22,
        priorities_state={"status": "completed", "source": "manual"},
        subjects=[
            SubjectItem(
                nombre="Programacion",
                prioridad="media",
                dificultad=3,
                urgencia="alta",
                carga_semanal_min=180,
                origen="manual",
            )
        ],
        study_plan={
            "plan_events": [_study_event("Estudio Programacion")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )

    assert first.priority_profile_id == 1
    assert first.study_plan_profile_id == 1
    assert second.priority_profile_id == 2
    assert second.study_plan_profile_id == 2
    assert repository._priority_history[7][0]["status"] == "superseded"
    assert repository._study_plan_history[7][0]["status"] == "superseded"
    assert repository._priority_profiles[7]["status"] == "completed"
    assert repository._study_plan_profiles[7]["is_current"] is True
    assert repository._priority_profiles[7]["result_payload"]["persisted_profile_id"] == 2
    assert repository._priority_profiles[7]["result_payload"]["version_number"] == 2
    assert repository._study_plan_profiles[7]["result_payload"]["persisted_profile_id"] == 2
    assert repository._study_plan_profiles[7]["result_payload"]["version_number"] == 2


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.commit_called = False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if "FROM study_priority_profiles" in query and "SELECT COALESCE(MAX(version_number)" in query:
            return _FakeResult({"current_version": 0})
        if "FROM study_plan_profiles" in query and "SELECT COALESCE(MAX(version_number)" in query:
            return _FakeResult({"current_version": 0})
        if "INSERT INTO study_priority_profiles" in query:
            return _FakeResult({"id": 31, "version_number": 1})
        if "INSERT INTO study_plan_profiles" in query:
            return _FakeResult({"id": 41, "version_number": 1})
        return _FakeResult(None)

    def commit(self) -> None:
        self.commit_called = True


@contextmanager
def _fake_connect(connection: _FakeConnection):
    yield connection



def test_postgres_study_planning_repository_persists_profiles_subjects_and_events() -> None:
    connection = _FakeConnection()
    repository = PostgresStudyPlanningRepository("postgresql://ignored")
    repository._connect = lambda: _fake_connect(connection)

    record = repository.replace_student_planning_snapshot(
        student_id=9,
        schedule_profile_id=11,
        personalization_profile_id=19,
        priorities_state={"status": "completed", "source": "manual", "prompt_version": "v1"},
        subjects=[
            SubjectItem(
                nombre="Calculo",
                prioridad="alta",
                dificultad=4,
                urgencia="alta",
                carga_semanal_min=240,
                origen="manual",
                importance_rank_selected_by_student=1,
                perceived_difficulty=4,
                urgency_type="parcial",
                urgency_due_at="2026-04-17T23:59:00-05:00",
                computed_priority_score=0.82,
                priority_source="weekly_flow",
                is_priority_confirmed=True,
                updated_from_flow_at="2026-04-13T08:00:00-05:00",
            ),
            SubjectItem(
                nombre="Programacion",
                prioridad="media",
                dificultad=3,
                urgencia="media",
                carga_semanal_min=180,
                origen="manual",
            ),
        ],
        study_plan={
            "plan_events": [_study_event("Estudio Calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )

    assert record.priority_profile_id == 31
    assert record.study_plan_profile_id == 41
    assert connection.commit_called is True

    priority_subject_params = [
        params
        for query, params in connection.executed
        if "INSERT INTO study_priority_subjects" in query
    ]
    plan_event_params = [
        params
        for query, params in connection.executed
        if "INSERT INTO study_plan_events" in query
    ]
    plan_profile_params = [
        params
        for query, params in connection.executed
        if "INSERT INTO study_plan_profiles" in query
    ]
    priority_payload_update_params = [
        params
        for query, params in connection.executed
        if "UPDATE study_priority_profiles" in query and "SET result_payload = %s::jsonb" in query
    ]
    plan_payload_update_params = [
        params
        for query, params in connection.executed
        if "UPDATE study_plan_profiles" in query and "SET result_payload = %s::jsonb" in query
    ]

    assert len(priority_subject_params) == 2
    assert priority_subject_params[0][8] == 1
    assert priority_subject_params[0][10] == "parcial"
    assert priority_subject_params[0][12] == 0.82
    assert priority_subject_params[0][14] is True
    assert len(plan_event_params) == 1
    assert plan_profile_params[0][3] == 31
    assert len(priority_payload_update_params) == 1
    assert len(plan_payload_update_params) == 1
    assert priority_payload_update_params[0][1] == 31
    assert plan_payload_update_params[0][1] == 41
    assert json.loads(priority_payload_update_params[0][0])["persisted_profile_id"] == 31
    assert json.loads(priority_payload_update_params[0][0])["version_number"] == 1
    assert json.loads(plan_payload_update_params[0][0])["persisted_profile_id"] == 41
    assert json.loads(plan_payload_update_params[0][0])["version_number"] == 1



def test_persist_study_profile_does_not_persist_initial_priorities_or_plan(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", "1")
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    set_personalization_service(personalization_service)
    set_study_planning_persistence_service(planning_service)
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

        assert update["phase"] == "end"
        assert "priorities" not in update
        assert "study_plan" not in update
        assert planning_repository._priority_profiles == {}
        assert planning_repository._study_plan_profiles == {}
    finally:
        set_personalization_service(None)
        set_study_planning_persistence_service(None)



def test_collect_priorities_skip_persists_skipped_snapshot() -> None:
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    set_study_planning_persistence_service(planning_service)
    try:
        state = AgentState(
            phase="priorities",
            awaiting_user_input=True,
            user_message_count=0,
            student_profile={"persisted_student_id": 15},
            study_profile={"persisted_profile_id": 7, "top_techniques": ["pomodoro"]},
            priorities={"status": "collecting", "source": "derived_from_schedule"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "Calculo")],
            },
            study_plan={
                "plan_events": [_study_event("Estudio Calculo")],
                "rules": {"planner_version": "study_planner_v1", "status": "generated"},
            },
            messages=[HumanMessage(content="omitir")],
        )

        update = collect_priorities(state)

        assert update["phase"] == "end"
        assert update["priorities"]["status"] == "skipped"
        assert update["priorities"]["persisted_profile_id"] == 1
        assert update["study_plan"]["persisted_profile_id"] == 1
        assert planning_repository._priority_profiles[15]["status"] == "skipped"
    finally:
        set_study_planning_persistence_service(None)



def test_build_study_plan_persists_recalculated_snapshot() -> None:
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    set_study_planning_persistence_service(planning_service)
    try:
        state = AgentState(
            phase="study_plan",
            student_profile={"persisted_student_id": 15},
            study_profile={"persisted_profile_id": 7, "top_techniques": ["pomodoro"]},
            priorities={"status": "completed", "source": "manual"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [
                    _academic_block("monday", "Calculo"),
                    _academic_block("wednesday", "Programacion"),
                ],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=5,
                    urgencia="alta",
                    carga_semanal_min=240,
                    origen="manual",
                ),
                SubjectItem(
                    nombre="Programacion",
                    prioridad="media",
                    dificultad=3,
                    urgencia="media",
                    carga_semanal_min=180,
                    origen="manual",
                ),
            ],
        )

        update = build_study_plan(state)

        assert update["phase"] == "end"
        assert update["priorities"]["persisted_profile_id"] == 1
        assert update["study_plan"]["persisted_profile_id"] == 1
        assert update["study_plan"]["version_number"] == 1
        assert len(planning_repository._study_plan_profiles[15]["plan_events"]) >= 2
    finally:
        set_study_planning_persistence_service(None)


def test_phase_11_persists_only_generated_plan_after_priorities_completion(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW", "1")
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    set_study_planning_persistence_service(planning_service)
    try:
        state = AgentState(
            phase="priorities",
            awaiting_user_input=True,
            user_message_count=0,
            student_profile={"persisted_student_id": 15},
            study_profile={"persisted_profile_id": 7, "top_techniques": ["pomodoro"]},
            priorities={"status": "collecting", "source": "derived_from_schedule"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [
                    _academic_block("monday", "Calculo"),
                    _academic_block("wednesday", "Programacion"),
                ],
            },
            messages=[HumanMessage(content="usar horario")],
        )

        priorities_update = collect_priorities(state)

        assert priorities_update["phase"] == "study_plan"
        assert planning_repository._priority_profiles == {}
        assert planning_repository._study_plan_profiles == {}

        next_state = AgentState(**{**state.model_dump(), **priorities_update})
        plan_update = build_study_plan(next_state)

        assert plan_update["phase"] == "end"
        assert plan_update["priorities"]["persisted_profile_id"] == 1
        assert plan_update["study_plan"]["persisted_profile_id"] == 1
        assert len(planning_repository._priority_profiles) == 1
        assert len(planning_repository._study_plan_profiles) == 1
        assert len(planning_repository._study_plan_profiles[15]["plan_events"]) >= 2
    finally:
        set_study_planning_persistence_service(None)


def test_phase_11_does_not_materialize_plan_without_phase_12_flag(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION", raising=False)
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=14,
    )
    set_study_planning_persistence_service(planning_service)
    set_study_plan_materialization_service(materialization_service)
    try:
        state = AgentState(
            phase="study_plan",
            student_profile={"persisted_student_id": 15},
            study_profile={"persisted_profile_id": 7, "top_techniques": ["pomodoro"]},
            priorities={"status": "completed", "source": "manual"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "Calculo")],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    origen="manual",
                )
            ],
        )

        update = build_study_plan(state)

        assert update["study_plan"]["persisted_profile_id"] == 1
        assert update["study_plan"]["materialized_instance_count"] is None
        assert instances_repository._instances_by_key == {}
    finally:
        set_study_planning_persistence_service(None)
        set_study_plan_materialization_service(None)


def test_phase_12_materializes_and_syncs_reminders_from_generated_plan(
    monkeypatch,
) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(reminders_module, "datetime", _FrozenDateTime)
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION", "1")
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS", raising=False)
    monkeypatch.delenv("ACADEMIC_AGENT_REMINDER_CHANNELS", raising=False)
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    reminders_repository = InMemoryRemindersRepository(
        instances_repository=instances_repository,
    )
    reminders_service = StudyPlanRemindersService(repository=reminders_repository)
    set_study_planning_persistence_service(planning_service)
    set_study_plan_materialization_service(materialization_service)
    set_reminders_service(reminders_service)
    try:
        state = AgentState(
            phase="study_plan",
            student_profile={"persisted_student_id": 15},
            study_profile={"persisted_profile_id": 7, "top_techniques": ["pomodoro"]},
            priorities={"status": "completed", "source": "manual"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [
                    _academic_block("monday", "Calculo"),
                    _academic_block("wednesday", "Programacion"),
                ],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    origen="manual",
                )
            ],
        )

        update = build_study_plan(state)

        instance_count = int(update["study_plan"]["materialized_instance_count"] or 0)
        assert update["phase"] == "end"
        assert update["study_plan"]["persisted_profile_id"] == 1
        assert instance_count >= 1
        assert update["study_plan"]["materialized_through_date"] == "2026-01-11"
        assert update["study_plan"]["rules"]["external_sync_requires_confirmation"] is True
        assert update["reminders"]["policy"] == {"channels": ["in_app"]}
        assert update["reminders"]["policy_count"] == 4
        assert update["reminders"]["schedulable_instance_count"] == instance_count
        assert update["reminders"]["created_dispatch_count"] == instance_count * 4
        assert update["reminders"]["last_dispatch_error"] is None
        assert len(instances_repository._instances_by_key) == instance_count
        assert len(reminders_repository._dispatches_by_id) == instance_count * 4
        assert {row["status"] for row in reminders_repository._dispatches_by_id.values()} == {
            "pending"
        }
        assistant_message = update["messages"][-1].content
        assert "Plan guardado en tu perfil académico." in assistant_message
        assert "Sesiones materializadas:" in assistant_message
        assert "Recordatorios activados por canal interno" in assistant_message
        assert "No he creado eventos en Outlook ni tareas en Microsoft To Do" in assistant_message
    finally:
        set_study_planning_persistence_service(None)
        set_study_plan_materialization_service(None)
        set_reminders_service(None)


def test_phase_12_repository_failures_do_not_break_conversation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION", "1")
    monkeypatch.setattr(
        persistence_support,
        "get_study_plan_materialization_service",
        lambda: (_ for _ in ()).throw(RepositoryConfigurationError("missing db")),
    )
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    set_study_planning_persistence_service(planning_service)
    try:
        state = AgentState(
            phase="study_plan",
            student_profile={"persisted_student_id": 15},
            study_profile={"persisted_profile_id": 7, "top_techniques": ["pomodoro"]},
            priorities={"status": "completed", "source": "manual"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "Calculo")],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    origen="manual",
                )
            ],
        )

        update = build_study_plan(state)

        assert update["phase"] == "end"
        assert update["study_plan"]["persisted_profile_id"] == 1
        assert (
            update["study_plan"]["materialization_error"]
            == "study_plan_materialization_service_unavailable"
        )
        assert update["messages"][-1].content
        assert "No pude dejar listas las sesiones fechadas todavía" in update["messages"][-1].content
    finally:
        set_study_planning_persistence_service(None)


def test_phase_12_reminder_failure_keeps_materialized_plan(
    monkeypatch,
) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION", "1")
    monkeypatch.setattr(
        persistence_support,
        "get_reminders_service",
        lambda: (_ for _ in ()).throw(RepositoryConfigurationError("missing reminders")),
    )
    planning_repository = InMemoryStudyPlanningRepository()
    planning_service = StudyPlanningPersistenceService(repository=planning_repository)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    set_study_planning_persistence_service(planning_service)
    set_study_plan_materialization_service(materialization_service)
    try:
        state = AgentState(
            phase="study_plan",
            student_profile={"persisted_student_id": 15},
            study_profile={"persisted_profile_id": 7, "top_techniques": ["pomodoro"]},
            priorities={"status": "completed", "source": "manual"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "Calculo")],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    origen="manual",
                )
            ],
        )

        update = build_study_plan(state)

        assert update["phase"] == "end"
        assert update["study_plan"]["materialized_instance_count"] >= 1
        assert (
            update["reminders"]["last_dispatch_error"]
            == "study_plan_reminders_service_unavailable"
        )
        assert "No pude activar recordatorios todavía" in update["messages"][-1].content
    finally:
        set_study_planning_persistence_service(None)
        set_study_plan_materialization_service(None)
