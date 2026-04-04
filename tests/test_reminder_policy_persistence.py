"""Pruebas de integración ligera entre persistencia del plan y reminders."""

from __future__ import annotations

from datetime import datetime as real_datetime

import services.planning.materialization_service as materialization_module
import services.reminders.service as reminders_module
from agents.support.dependencies import (
    set_personalization_service,
    set_reminders_service,
    set_study_plan_materialization_service,
    set_study_planning_persistence_service,
)
from agents.support.nodes.persist_study_profile.node import persist_study_profile
from agents.support.state import AgentState
from repositories.personalization.repository import InMemoryPersonalizationRepository
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.planning.repository import InMemoryStudyPlanningRepository
from repositories.reminders.repository import InMemoryRemindersRepository
from services.personalization import (
    PersonalizationConfig,
    PersonalizationService,
    get_questions,
)
from services.planning import (
    StudyPlanMaterializationService,
    StudyPlanningPersistenceService,
)
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


def test_persist_study_profile_syncs_reminders_without_breaking_flow(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(reminders_module, "datetime", _FrozenDateTime)
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    planning_service = StudyPlanningPersistenceService(
        repository=InMemoryStudyPlanningRepository()
    )
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=14,
    )
    reminders_service = StudyPlanRemindersService(
        repository=InMemoryRemindersRepository(instances_repository=instances_repository)
    )
    set_personalization_service(personalization_service)
    set_study_planning_persistence_service(planning_service)
    set_study_plan_materialization_service(materialization_service)
    set_reminders_service(reminders_service)
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
        assert update["reminders"]["last_dispatch_error"] is None
        assert len(update["reminders"]["persisted_policy_ids"]) == 4
        assert update["reminders"]["last_sync_at"] is not None
    finally:
        set_personalization_service(None)
        set_study_planning_persistence_service(None)
        set_study_plan_materialization_service(None)
        set_reminders_service(None)
