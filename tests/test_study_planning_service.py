"""Pruebas del primer servicio determinista de planificación semanal."""

from __future__ import annotations

from types import SimpleNamespace

from agents.support.dependencies import (
    set_personalization_service,
    set_study_recommendation_service,
)
from agents.support.nodes.build_study_plan.node import build_study_plan
from agents.support.nodes.persist_study_profile.node import persist_study_profile
from agents.support.state import AgentState
from repositories.personalization.repository import InMemoryPersonalizationRepository
from schemas.planning import AcademicActivity, SubjectItem
from schemas.rag import StudyRecommendationResult
from services.personalization import (
    PersonalizationConfig,
    PersonalizationService,
    get_questions,
)
from services.planning import build_initial_study_plan
from services.scheduling import WeeklyScheduleBlock
from services.scheduling.constants import DAY_LABELS, DAY_ORDER
from services.scheduling.validation import validate_event


def _academic_block(
    day_of_week: str,
    start_time: str,
    end_time: str,
    title: str,
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        source_text=f"{title} {day_of_week} {start_time}-{end_time}",
    )


def _work_block(
    day_of_week: str,
    start_time: str = "09:00",
    end_time: str = "17:00",
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="work",
        title="Trabajo",
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        source_text=f"Trabajo {day_of_week} {start_time}-{end_time}",
    )


def _event_day_label(day_of_week: str) -> str:
    return DAY_LABELS[day_of_week].replace("é", "e").replace("á", "a")


def _to_minutes(value: str) -> int:
    hours, minutes = value.split(":", maxsplit=1)
    return int(hours) * 60 + int(minutes)


def _daily_minutes(events) -> dict[str, int]:
    minutes_by_day = {day: 0 for day in DAY_ORDER}
    spanish_to_english = {_event_day_label(day): day for day in DAY_ORDER}
    for event in events:
        day = spanish_to_english[event.dia]
        minutes_by_day[day] += _to_minutes(event.fin) - _to_minutes(event.inicio)
    return minutes_by_day


def _assert_no_overlap_with_fixed_blocks(plan_events, blocks) -> None:
    fixed_windows = {}
    for block in blocks:
        day_label = _event_day_label(block.day_of_week)
        fixed_windows.setdefault(day_label, []).append(
            (_to_minutes(block.start_time), _to_minutes(block.end_time))
        )

    for event in plan_events:
        event_start = _to_minutes(event.inicio)
        event_end = _to_minutes(event.fin)
        for block_start, block_end in fixed_windows.get(event.dia, []):
            assert event_end <= block_start or event_start >= block_end


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


class _StudyRecommendationServiceStub:
    def __init__(
        self,
        *,
        ready: bool = True,
        student_answer: str | None = None,
        session_answer: str | None = None,
        session_source_chunks: list[str] | None = None,
    ) -> None:
        self.status = SimpleNamespace(ready=ready)
        self.calls: list[dict[str, object]] = []
        self.student_answer = student_answer or (
            "Pomodoro puede ayudarte a empezar en bloques cortos y sostener la atencion "
            "cuando hay procrastinacion o distraccion."
        )
        self.session_answer = session_answer or (
            "Empieza la sesion con una meta concreta, trabaja en un bloque breve y cierra "
            "verificando que puedes recordar o aplicar lo estudiado."
        )
        self.session_source_chunks = session_source_chunks or ["technique.pomodoro::session"]

    def recommend_for_student(self, **kwargs):
        self.calls.append(dict(kwargs))
        return StudyRecommendationResult(
            answer=self.student_answer,
            recommended_techniques=["pomodoro"],
            source_chunks=["technique.pomodoro::answer"],
            confidence="media",
            groundedness_notes=["sources:cited"],
        )

    def recommend_for_session(self, **kwargs):
        self.calls.append({"method": "recommend_for_session", **dict(kwargs)})
        return StudyRecommendationResult(
            answer=self.session_answer,
            recommended_techniques=[str(kwargs.get("technique_id") or "pomodoro")],
            source_chunks=list(self.session_source_chunks),
            confidence="media",
            groundedness_notes=["sources:cited"],
        )

    def answer_query(self, query):
        self.calls.append({"method": "answer_query", "query": query})
        method_id = (
            "metodo_evaluacion_numerica_breve"
            if "evaluacion numerica" in query.query_text
            else "metodo_parcial_teorico"
        )
        return StudyRecommendationResult(
            answer=(
                "El metodo aplicado permite clasificar o listar el trabajo, "
                "responder sin mirar apuntes y corregir vacios."
            ),
            recommended_methods=[method_id],
            source_chunks=[f"study_method.{method_id}::steps"],
            confidence="media",
            groundedness_notes=["sources:cited"],
        )


def test_build_initial_study_plan_derives_subjects_from_schedule() -> None:
    blocks = [
        _academic_block("monday", "08:00", "10:00", "Calculo"),
        _academic_block("wednesday", "10:00", "12:00", "Programacion"),
        _work_block("friday", "14:00", "18:00"),
    ]

    plan = build_initial_study_plan(
        schedule_blocks=blocks,
        subjects=[],
        study_profile={"top_techniques": ["pomodoro", "feynman"]},
        constraints={},
        timezone="America/Bogota",
    )

    assert plan.rules["status"] == "generated"
    assert plan.rules["subjects_source"] == "derived_from_schedule"
    assert plan.rules["session_minutes"] == 25
    assert any("Calculo" in event.titulo for event in plan.plan_events)
    assert any("Programacion" in event.titulo for event in plan.plan_events)
    _assert_no_overlap_with_fixed_blocks(plan.plan_events, blocks)
    for event in plan.plan_events:
        validate_event(event)
        assert event.categoria == "estudio"
        assert event.tipo == "tentativo"


def test_build_initial_study_plan_respects_daily_maximum() -> None:
    blocks = [_work_block("monday")]
    subjects = [
        SubjectItem(nombre="Algebra", prioridad="alta", dificultad=4),
        SubjectItem(nombre="Fisica", prioridad="media", dificultad=3),
    ]

    plan = build_initial_study_plan(
        schedule_blocks=blocks,
        subjects=subjects,
        study_profile={"top_techniques": ["feynman"]},
        constraints={
            "study_session_min": 25,
            "study_session_max": 50,
            "max_study_per_day_min": 50,
        },
        timezone="America/Bogota",
    )

    assert plan.rules["subjects_source"] == "state.subjects"
    assert plan.rules["session_minutes"] == 50
    assert all(total <= 50 for total in _daily_minutes(plan.plan_events).values())
    assert any("Algebra" in event.titulo for event in plan.plan_events)
    assert any("Fisica" in event.titulo for event in plan.plan_events)


def test_build_initial_study_plan_spreads_sessions_for_spaced_repetition() -> None:
    blocks = [_academic_block("monday", "08:00", "10:00", "Calculo")]
    subjects = [SubjectItem(nombre="Calculo", prioridad="alta", dificultad=3)]

    plan = build_initial_study_plan(
        schedule_blocks=blocks,
        subjects=subjects,
        study_profile={"top_techniques": ["repeticion_espaciada"]},
        constraints={},
        timezone="America/Bogota",
    )

    calculo_days = [
        DAY_ORDER.index(day)
        for day in DAY_ORDER
        for event in plan.plan_events
        if event.titulo == "Estudio · Calculo" and event.dia == _event_day_label(day)
    ]

    assert len(calculo_days) >= 2
    assert calculo_days[1] - calculo_days[0] >= 2
    assert plan.rules["spacing_days"] == 2


def test_persist_study_profile_closes_without_generating_study_plan(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    set_personalization_service(personalization_service)
    try:
        study_profile = _completed_profile_payload()
        state = AgentState(
            phase="study_profile",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "08:00", "10:00", "Calculo")],
                "summary_text": "resumen",
                "conflicts": [],
            },
            study_profile=study_profile,
        )

        update = persist_study_profile(state)

        assert update["phase"] == "end"
        assert "subjects" not in update
        assert "priorities" not in update
        assert "study_plan" not in update
        assert "Listo, ya identifiqué cómo puedes estudiar de forma más efectiva" in update["messages"][0].content
    finally:
        set_personalization_service(None)


def test_persist_study_profile_enriches_radar_summary_when_rag_service_is_ready(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    recommendation_service = _StudyRecommendationServiceStub(
        ready=True,
        student_answer=(
            'La técnica Feynman es ideal para trabajar el "explanation_gap". '
            'El Método Cornell ayuda con "note_organization" y la mnemotecnia '
            "sirve para recordar listas."
        ),
    )
    set_personalization_service(personalization_service)
    set_study_recommendation_service(recommendation_service)
    try:
        study_profile = _completed_profile_payload()
        state = AgentState(
            phase="study_profile",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "08:00", "10:00", "Calculo")],
                "summary_text": "resumen",
                "conflicts": [],
            },
            study_profile=study_profile,
        )

        update = persist_study_profile(state)

        final_message = update["messages"][0].content
        assert "Listo, ya identifiqué cómo puedes estudiar de forma más efectiva" in final_message
        assert "Para llevarlo a la práctica:" in final_message
        assert "fuentes internas" not in final_message
        assert "fragmento" not in final_message
        assert "Empieza cada sesión con un objetivo pequeño" in final_message
        assert "Feynman" not in final_message
        assert "Cornell" not in final_message
        assert "mnemotecnia" not in final_message
        assert "explanation_gap" not in final_message
        assert "note_organization" not in final_message
        assert recommendation_service.calls[0]["top_techniques"] == study_profile["top_techniques"]
        assert "procrastination" in recommendation_service.calls[0]["student_signals"]
    finally:
        set_personalization_service(None)
        set_study_recommendation_service(None)


def test_persist_study_profile_keeps_rag_guidance_complete_without_ellipsis(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    long_guidance = (
        "Pomodoro puede ayudarte a iniciar con una meta concreta. "
        + "Despues revisa una pregunta concreta para comprobar avance. " * 12
        + "Esta frase queda fuera del limite conversacional."
    )
    recommendation_service = _StudyRecommendationServiceStub(
        ready=True,
        student_answer=long_guidance,
    )
    set_personalization_service(personalization_service)
    set_study_recommendation_service(recommendation_service)
    try:
        state = AgentState(
            phase="study_profile",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "08:00", "10:00", "Calculo")],
                "summary_text": "resumen",
                "conflicts": [],
            },
            study_profile=_completed_profile_payload(),
        )

        update = persist_study_profile(state)

        final_message = update["messages"][0].content
        assert "Para llevarlo a la práctica:" in final_message
        assert "..." not in final_message
        assert final_message.endswith(".")
    finally:
        set_personalization_service(None)
        set_study_recommendation_service(None)


def test_persist_study_profile_keeps_base_summary_when_rag_service_is_not_ready(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    recommendation_service = _StudyRecommendationServiceStub(ready=False)
    set_personalization_service(personalization_service)
    set_study_recommendation_service(recommendation_service)
    try:
        state = AgentState(
            phase="study_profile",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "08:00", "10:00", "Calculo")],
                "summary_text": "resumen",
                "conflicts": [],
            },
            study_profile=_completed_profile_payload(),
        )

        update = persist_study_profile(state)

        final_message = update["messages"][0].content
        assert "Listo, ya identifiqué cómo puedes estudiar de forma más efectiva" in final_message
        assert "Para llevarlo a la práctica:" not in final_message
        assert recommendation_service.calls == []
    finally:
        set_personalization_service(None)
        set_study_recommendation_service(None)


def test_build_study_plan_adds_rag_session_guidance_when_service_is_ready() -> None:
    recommendation_service = _StudyRecommendationServiceStub(ready=True)
    set_study_recommendation_service(recommendation_service)
    try:
        state = AgentState(
            phase="running",
            study_profile={
                "top_techniques": ["pomodoro", "feynman"],
                "weakness_tags": ["procrastination", "distraction"],
            },
            schedule={
                "blocks": [_academic_block("monday", "08:00", "10:00", "Calculo")],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    is_priority_confirmed=True,
                )
            ],
        )

        update = build_study_plan(state)

        guidance = update["study_plan"]["rules"]["rag_session_guidance"]
        assert update["study_plan"]["rules"]["external_sync_status"] == "not_requested"
        assert update["study_plan"]["rules"]["external_sync_requires_confirmation"] is True
        assert guidance["primary_technique_id"] == "pomodoro"
        assert guidance["subject_name"] == "Calculo"
        assert guidance["source_chunks"] == ["technique.pomodoro::session"]
        assert "No he creado eventos en Outlook" in update["messages"][0].content
        assert "Guía sugerida para la primera sesión:" in update["messages"][0].content
        assert "Empieza la sesion" in update["messages"][0].content
        assert recommendation_service.calls[0]["method"] == "recommend_for_session"
        assert recommendation_service.calls[0]["student_signals"] == [
            "procrastination",
            "distraction",
        ]
    finally:
        set_study_recommendation_service(None)


def test_build_study_plan_adds_applied_method_guidance_for_pending_activity() -> None:
    recommendation_service = _StudyRecommendationServiceStub(ready=True)
    set_study_recommendation_service(recommendation_service)
    try:
        state = AgentState(
            phase="running",
            study_profile={
                "top_techniques": ["pomodoro"],
                "weakness_tags": ["procrastination"],
            },
            schedule={
                "blocks": [_academic_block("monday", "08:00", "10:00", "Calculo")],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    is_priority_confirmed=True,
                )
            ],
            academic_activities=[
                AcademicActivity(
                    activity_type="parcial",
                    subject_name="Calculo",
                    due_date="2026-04-24",
                    estimated_effort_minutes=90,
                    priority_level="alta",
                    difficulty_level=4,
                )
            ],
        )

        update = build_study_plan(state)

        guidance = update["study_plan"]["rules"]["applied_method_guidance"]
        item = guidance["items"][0]
        assert guidance["status"] == "generated"
        assert guidance["activity_count"] == 1
        assert item["selected_method_id"] == "metodo_evaluacion_numerica_breve"
        assert item["subject_name"] == "Calculo"
        assert item["session_event_ids"]
        assert "Clasifica los ejercicios" in item["steps"][1]
        assert "Método aplicado para una actividad prioritaria:" in update["messages"][0].content
        assert any(call["method"] == "answer_query" for call in recommendation_service.calls)
    finally:
        set_study_recommendation_service(None)


def test_build_study_plan_skips_rag_session_guidance_when_sources_do_not_match_primary_technique() -> None:
    recommendation_service = _StudyRecommendationServiceStub(
        ready=True,
        session_source_chunks=["technique.active_recall::session"],
    )
    set_study_recommendation_service(recommendation_service)
    try:
        state = AgentState(
            phase="running",
            study_profile={
                "top_techniques": ["feynman", "active_recall"],
                "weakness_tags": ["explanation_gap", "passive_review_dependence"],
            },
            schedule={
                "blocks": [_academic_block("monday", "08:00", "10:00", "Fisica")],
            },
            subjects=[
                SubjectItem(
                    nombre="Fisica",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    is_priority_confirmed=True,
                )
            ],
        )

        update = build_study_plan(state)

        assert update["study_plan"]["rules"]["primary_technique_id"] == "feynman"
        assert "rag_session_guidance" not in update["study_plan"]["rules"]
        assert "Guía sugerida para la primera sesión:" not in update["messages"][0].content
        assert recommendation_service.calls[0]["method"] == "recommend_for_session"
    finally:
        set_study_recommendation_service(None)


def test_build_study_plan_keeps_full_rag_session_guidance_without_extra_truncation() -> None:
    long_guidance = " ".join(
        [
            "Paso 1: elige un concepto concreto.",
            "Paso 2: explicalo con tus palabras.",
            "Paso 3: marca dudas reales.",
            "Paso 4: corrige solo los vacios.",
            "Paso 5: vuelve a explicarlo de forma simple.",
            "Paso 6: comprueba si puedes sostener la explicacion.",
            "Paso 7: conecta el concepto con un ejemplo.",
            "Paso 8: cierra con una pregunta de verificacion final completa.",
        ]
        * 4
    )
    recommendation_service = _StudyRecommendationServiceStub(
        ready=True,
        session_answer=long_guidance,
        session_source_chunks=["technique.pomodoro::session"],
    )
    set_study_recommendation_service(recommendation_service)
    try:
        state = AgentState(
            phase="running",
            study_profile={
                "top_techniques": ["pomodoro"],
                "weakness_tags": ["procrastination"],
            },
            schedule={
                "blocks": [_academic_block("monday", "08:00", "10:00", "Calculo")],
            },
            subjects=[
                SubjectItem(
                    nombre="Calculo",
                    prioridad="alta",
                    dificultad=4,
                    urgencia="alta",
                    carga_semanal_min=180,
                    is_priority_confirmed=True,
                )
            ],
        )

        update = build_study_plan(state)

        guidance = update["study_plan"]["rules"]["rag_session_guidance"]["answer"]
        assert "verificacion final completa" in guidance
        assert not guidance.endswith("...")
    finally:
        set_study_recommendation_service(None)
