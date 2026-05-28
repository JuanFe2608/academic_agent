"""Factory de herramientas del agente académico.

Todas las tools son closures creados por make_tools(state) que capturan el
AgentState del turno actual, dándoles acceso a los datos del estudiante sin
exponer state como parámetro visible para el LLM.

Patrón de retorno para tools que modifican estado:
    json.dumps({"result": "<texto para el LLM>", "_state_update": {...}})

extract_tool_state_updates() recoge estas actualizaciones después del ciclo
ReAct y las fusiona en el dict de retorno del nodo academic_agent.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfoNotFoundError
from typing import Any

from langchain_core.tools import tool

from agents.support.nodes.academic_agent.context import (
    current_datetime,
    format_current_datetime_for_student,
)
from agents.support.state import AgentState
from services.scheduling.constants import SPANISH_TO_ENGLISH
from services.scheduling.validation import (
    normalize_day,
    normalize_day_typos_in_text,
    normalize_time as normalize_schedule_time,
    sort_events,
    validate_event,
)

_DAYS_ES: dict[str, str] = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

_DAYS_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_EVENT_DAY_BY_WEEKDAY: dict[str, str] = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miercoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sabado",
    "sunday": "Domingo",
}
_WEEKDAY_BY_EVENT_DAY = {value: key for key, value in _EVENT_DAY_BY_WEEKDAY.items()}
_WEEKDAY_LABELS_FOR_PARSER: dict[str, str] = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miercoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sabado",
    "sunday": "Domingo",
}
_SCHEDULE_BLOCK_TYPE_ALIASES: dict[str, str] = {
    "academic": "academic",
    "academico": "academic",
    "academica": "academic",
    "clase": "academic",
    "materia": "academic",
    "asignatura": "academic",
    "curso": "academic",
    "work": "work",
    "laboral": "work",
    "trabajo": "work",
    "empleo": "work",
    "turno": "work",
    "extracurricular": "extracurricular",
    "extra": "extracurricular",
    "hobby": "extracurricular",
    "deporte": "extracurricular",
    "personal": "extracurricular",
}

_VALID_PRIORIDAD: frozenset[str] = frozenset({"alta", "media", "baja"})


def _format_manual_todo_change_prompt(result: object) -> str:
    changes = list(getattr(result, "inbound_changes", []) or [])
    lines = [
        "Detecté cambios manuales en Microsoft To Do antes de sincronizar.",
        "",
        "No los voy a sobrescribir sin confirmación.",
    ]
    for index, change in enumerate(changes[:5], start=1):
        title = str(change.get("activity_title") or change.get("assistant_title") or "actividad")
        changed_fields = set(str(field) for field in change.get("changed_fields") or [])
        details: list[str] = []
        if "title" in changed_fields:
            details.append(f"título en To Do: {change.get('todo_title')}")
        if "due_date" in changed_fields:
            details.append(f"fecha en To Do: {change.get('todo_due_date') or 'sin fecha'}")
        lines.append(f"{index}. {title} — {', '.join(details)}")
    if len(changes) > 5:
        lines.append(f"... y {len(changes) - 5} cambio(s) más.")
    imported_count = getattr(result, "imported_completed_count", 0)
    if imported_count:
        lines.append("")
        lines.append(
            f"Además, marqué {imported_count} actividad(es) como completada(s) porque ya estaban completas en To Do."
        )
    lines.extend(
        [
            "",
            "¿Qué quieres hacer?",
            "1. Importar esos cambios al asistente",
            "2. Restaurar Microsoft To Do con la información del asistente",
            "3. Cancelar",
        ]
    )
    return "\n".join(lines)


def _local_today(timezone_name: str = "America/Bogota") -> date:
    try:
        return current_datetime(str(timezone_name or "America/Bogota")).date()
    except ZoneInfoNotFoundError:
        return current_datetime("America/Bogota").date()


def _compute_urgency_from_due_date(
    due_date: str | None,
    *,
    reference_date: date | None = None,
) -> str:
    """Calcula prioridad interna desde la fecha límite. No exponer al LLM."""
    if not due_date:
        return "baja"
    try:
        today = reference_date or _local_today()
        delta = (date.fromisoformat(due_date) - today).days
        if delta <= 2:
            return "alta"
        if delta <= 7:
            return "media"
        return "baja"
    except ValueError:
        return "baja"


def make_tools(state: AgentState) -> list:
    """Crea las herramientas del agente con el estado actual capturado en closure."""
    student_id = _get_student_id(state)
    timezone_name = str(state.timezone or "America/Bogota")

    def _today() -> date:
        return _local_today(timezone_name)

    # Accumulator: tracks in-cycle mutations to academic_activities so that tools
    # called later in the same ReAct turn see the result of earlier tools.
    # Example: add_academic_activity → sync_tasks_to_todo must see the new activity.
    _cycle_updates: dict[str, Any] = {}

    def _current_activities() -> list:
        raw = _cycle_updates.get("academic_activities")
        if raw is not None:
            return list(raw)
        local = list(state.academic_activities)
        if local:
            return local
        if not student_id:
            return local
        try:
            from agents.support.dependencies import get_academic_activity_persistence_service

            result = get_academic_activity_persistence_service().list_activities(
                student_id=int(student_id),
                include_deleted=False,
            )
            if result.loaded:
                return list(result.activities)
        except Exception:
            pass
        return local

    # ------------------------------------------------------------------ RAG --

    @tool
    def get_current_datetime() -> str:
        """Devuelve la fecha y hora actual oficial del agente en Bogotá/Colombia.
        Úsala cuando el estudiante pregunte qué día es hoy, la fecha actual,
        la hora actual, o cuando necesites resolver fechas relativas antes de agendar."""

        now = current_datetime(timezone_name)
        return (
            f"Hoy en Bogotá/Colombia es {format_current_datetime_for_student(now)}. "
            f"Fecha ISO: {now.date().isoformat()}. Zona horaria: {timezone_name}."
        )

    @tool
    def search_study_methods(
        query: str,
        technique_id: str | None = None,
        subject: str | None = None,
        activity_type: str | None = None,
    ) -> str:
        """Busca métodos y estrategias de estudio en la base de conocimiento.
        Úsala cuando el estudiante pregunte cómo estudiar para una materia,
        cómo prepararse para un tipo de evaluación, o qué técnica aplicar.
        technique_id: slug de la técnica (p.ej. pomodoro, feynman, cornell).
        subject: nombre de la materia. activity_type: parcial, tarea, quiz, etc."""
        import dataclasses

        from agents.support.dependencies import get_study_recommendation_service
        from schemas.rag import StudyRecommendationQuery
        from services.study_recommendations import (
            AppliedStudyMethodService,
            build_applied_method_request_from_text,
            format_applied_study_method_for_user,
            is_applied_study_method_message,
        )

        service = get_study_recommendation_service()
        try:
            # Path 1: explica una técnica específica por slug
            if technique_id:
                result = service.explain_technique(
                    technique_id,
                    query_text=query or subject or activity_type,
                )
                return result.answer or "No encontré guía para esa técnica."

            # Path 2: método aplicado paso a paso para una actividad concreta
            if is_applied_study_method_message(query) or activity_type:
                profile_dict = {
                    "weakness_tags": list(state.study_profile.weakness_tags or []),
                    "top_techniques": list(state.study_profile.top_techniques or []),
                }
                request = build_applied_method_request_from_text(query, study_profile=profile_dict)
                if subject or activity_type:
                    request = dataclasses.replace(
                        request,
                        subject_name=subject or request.subject_name,
                        activity_type=activity_type or request.activity_type,
                    )
                applied_result = AppliedStudyMethodService(service).apply_to_activity(request)
                if applied_result.applied:
                    return format_applied_study_method_for_user(applied_result)

            # Path 3: búsqueda general con perfil del estudiante
            rag_result = service.answer_query(
                StudyRecommendationQuery(
                    query_text=query,
                    intent="recommend_technique",
                    top_techniques=list(state.study_profile.top_techniques or []),
                    student_signals=list(state.study_profile.weakness_tags or []),
                    subject_name=subject,
                    activity_type=activity_type,
                )
            )
            if rag_result.confidence != "baja":
                return rag_result.answer

            # Path 4: fallback LLM cuando RAG no tiene fuentes suficientes
            return _llm_study_fallback(query) or rag_result.answer or "No encontré información relevante sobre ese método de estudio."
        except Exception as exc:
            return f"No pude buscar métodos de estudio: {exc}"

    @tool
    def get_technique_guide(
        technique_id: str,
        activity_type: str | None = None,
        available_minutes: int | None = None,
    ) -> str:
        """Obtiene una guía paso a paso de cómo aplicar una técnica de estudio
        específica. Úsala cuando el estudiante ya sabe qué técnica usar y necesita
        instrucciones de ejecución.
        technique_id: slug de la técnica (pomodoro, feynman, cornell, spaced_repetition, etc.).
        activity_type: tipo de evaluación a preparar. available_minutes: tiempo disponible."""
        from agents.support.dependencies import get_study_recommendation_service

        service = get_study_recommendation_service()
        try:
            parts = [p for p in [activity_type, f"{available_minutes}min" if available_minutes else ""] if p]
            query_text = " ".join(parts) or None
            result = service.explain_technique(technique_id, query_text=query_text)
            return result.answer or "No encontré guía para esa técnica."
        except Exception as exc:
            return f"No pude obtener la guía: {exc}"

    # -------------------------------------------------------- Actividades ----

    @tool
    def add_academic_activity(
        subject: str,
        activity_type: str,
        title: str,
        due_date: str,
        is_priority: bool = False,
        difficulty: int = 3,
    ) -> str:
        """Registra una actividad académica nueva del estudiante.
        activity_type: parcial | quiz | tarea | taller | entrega | exposicion | proyecto.
        due_date: fecha límite en formato YYYY-MM-DD.
        is_priority: True si el estudiante quiere marcarla como prioritaria (⭐ en To Do), False por defecto.
          Pregunta al estudiante UNA sola vez "¿Quieres marcarla como prioritaria?" antes de llamar esta tool.
        difficulty: escala 1 (fácil) a 5 (muy difícil).
        Úsala cuando el estudiante mencione cualquier evaluación, entrega o compromiso académico."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            build_activity_from_slots,
            coerce_academic_activities,
        )

        guard = _validate_academic_activity_tool_input(
            state,
            subject=subject,
            activity_type=activity_type,
            title=title,
        )
        if guard:
            return guard

        # Urgencia interna: si el estudiante la marcó como prioritaria → alta;
        # si no, se calcula automáticamente por cercanía de la fecha.
        today = _today()
        priority_level = (
            "alta"
            if is_priority
            else _compute_urgency_from_due_date(due_date, reference_date=today)
        )

        activities = coerce_academic_activities(_current_activities())

        # Guard contra duplicados semánticos: subject + activity_type + due_date ya registrados.
        # Evita crear una segunda fila en DB cuando el LLM vuelve a llamar esta tool
        # para una actividad que el estudiante ya registró en el mismo turno o en turnos anteriores.
        _norm_subject = _normalize_text_key(subject)
        _norm_type = _normalize_text_key(activity_type)
        for _existing in activities:
            if (
                _existing.status != "deleted"
                and _normalize_text_key(str(_existing.subject_name or "")) == _norm_subject
                and _normalize_text_key(str(_existing.activity_type or "")) == _norm_type
                and str(_existing.due_date or "") == str(due_date or "")
            ):
                return json.dumps({
                    "result": (
                        f"La actividad '{_existing.activity_title}' de {_existing.subject_name} "
                        f"para el {_existing.due_date} ya está registrada. "
                        "Si quieres modificarla usa edit_academic_activity."
                    ),
                    "_state_update": {},
                })

        try:
            new_act = build_activity_from_slots(
                {
                    "activity_type": activity_type,
                    "subject_name": subject,
                    "activity_title": title,
                    "due_date": due_date,
                    "priority_level": priority_level,
                    "difficulty_level": difficulty,
                },
                source_text=f"{subject} {activity_type} {title}",
                timezone=state.timezone,
            )
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "create", "activity": new_act.model_dump()},
                timezone=state.timezone,
                reference_date=today,
            )
            star_note = " ⭐ Marcada como prioritaria." if is_priority else ""
            msg = (result.message or f"Actividad '{title}' registrada para el {due_date}.") + star_note
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
            return json.dumps({"result": msg, "_state_update": state_update})
        except Exception as exc:
            return f"No pude registrar la actividad: {exc}"

    @tool
    def edit_academic_activity(
        activity_reference: str,
        subject: str | None = None,
        activity_type: str | None = None,
        title: str | None = None,
        due_date: str | None = None,
        is_priority: bool | None = None,
        difficulty: int | None = None,
    ) -> str:
        """Edita una actividad académica ya registrada del estudiante.
        activity_reference: descripción para identificar la actividad (materia, tipo o título).
        subject: nuevo nombre de materia (opcional).
        activity_type: nuevo tipo — parcial | quiz | tarea | taller | entrega | exposicion | proyecto (opcional).
        title: nuevo título de la actividad (opcional).
        due_date: nueva fecha límite YYYY-MM-DD (opcional).
        is_priority: True para marcarla como prioritaria ⭐, False para quitarle la prioridad (opcional).
        difficulty: nueva dificultad 1-5 (opcional).
        Úsala cuando el estudiante quiera corregir datos de una actividad ya registrada."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            coerce_academic_activities,
            match_academic_activities,
        )

        activities = coerce_academic_activities(_current_activities())
        matches = match_academic_activities(activities, text=activity_reference)
        if not matches:
            return f"No encontré ninguna actividad que coincida con '{activity_reference}'."
        if len(matches) > 1:
            lines = [f"Encontré {len(matches)} actividades que podrían ser esa. Especifica cuál:"]
            for a in matches:
                due_str = f" — vence {a.due_date}" if a.due_date else ""
                lines.append(f"  • [{a.activity_type}] {a.subject_name}: {a.activity_title}{due_str}")
            return "\n".join(lines)
        target = matches[0]
        changes: dict[str, Any] = {}
        if subject is not None:
            changes["subject_name"] = subject
        if activity_type is not None:
            changes["activity_type"] = activity_type
        if title is not None:
            changes["activity_title"] = title
        if due_date is not None:
            changes["due_date"] = due_date
        if is_priority is not None:
            # Recompute priority_level: starred → alta; unstarred → recalculate from due_date
            effective_due = due_date or getattr(target, "due_date", None)
            changes["priority_level"] = (
                "alta"
                if is_priority
                else _compute_urgency_from_due_date(
                    effective_due,
                    reference_date=_today(),
                )
            )
        if difficulty is not None:
            changes["difficulty_level"] = difficulty
        if not changes:
            return "No indicaste ningún campo a actualizar."
        try:
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "update", "activity_id": target.activity_id, "changes": changes},
                timezone=state.timezone,
                reference_date=_today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
            return json.dumps({"result": result.message or "Actividad actualizada.", "_state_update": state_update})
        except Exception as exc:
            return f"No pude actualizar la actividad: {exc}"

    @tool
    def delete_academic_activity(activity_reference: str) -> str:
        """Elimina una actividad académica del estudiante.
        activity_reference: descripción para identificar la actividad (materia, tipo o título).
        Úsala cuando el estudiante diga que canceló una actividad, que fue un registro incorrecto,
        o que ya no necesita hacer seguimiento de esa actividad."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            coerce_academic_activities,
            match_academic_activities,
        )

        activities = coerce_academic_activities(_current_activities())
        matches = match_academic_activities(activities, text=activity_reference)
        if not matches:
            return f"No encontré ninguna actividad que coincida con '{activity_reference}'."
        if len(matches) > 1:
            lines = [f"Encontré {len(matches)} actividades. Especifica cuál eliminar:"]
            for a in matches:
                due_str = f" — vence {a.due_date}" if a.due_date else ""
                lines.append(f"  • [{a.activity_type}] {a.subject_name}: {a.activity_title}{due_str}")
            return "\n".join(lines)
        target = matches[0]
        try:
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "delete", "activity_id": target.activity_id},
                timezone=state.timezone,
                reference_date=_today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
            return json.dumps({"result": result.message or "Actividad eliminada.", "_state_update": state_update})
        except Exception as exc:
            return f"No pude eliminar la actividad: {exc}"

    @tool
    def get_pending_activities(days_ahead: int = 7) -> str:
        """Lista actividades académicas pendientes del estudiante.
        Úsala cuando el estudiante pregunte qué tiene pendiente, cuáles son sus próximas
        entregas o quiera saber para qué prepararse. Siempre muestra también pendientes
        más lejanos; days_ahead solo separa próximos vs. más adelante."""
        from services.planning.academic_activity_service import active_academic_activities

        activities = active_academic_activities(_current_activities())
        pending = [a for a in activities if a.status == "pending"]
        if not pending:
            return "No tienes actividades académicas pendientes registradas."
        today = _today()
        cutoff = today + timedelta(days=max(0, int(days_ahead or 7)))

        def _due_date(activity) -> date | None:
            if not activity.due_date:
                return None
            try:
                return date.fromisoformat(activity.due_date)
            except ValueError:
                return None

        dated = [(a, _due_date(a)) for a in pending]
        upcoming = [(a, d) for a, d in dated if d is None or d <= cutoff]
        later = [(a, d) for a, d in dated if d is not None and d > cutoff]
        lines = [f"Tienes {len(pending)} actividad(es) académica(s) pendiente(s):"]
        if upcoming:
            lines.append(f"\nPróximos {days_ahead} días:")
            for a, d in sorted(upcoming, key=lambda item: item[1] or date.max):
                lines.append(_format_pending_activity_line(a, today=today, due=d))
        if later:
            lines.append("\nMás adelante:")
            for a, d in sorted(later, key=lambda item: item[1] or date.max):
                lines.append(_format_pending_activity_line(a, today=today, due=d))
        return "\n".join(lines)

    @tool
    def mark_activity_done(activity_reference: str) -> str:
        """Marca una actividad académica como completada.
        activity_reference: descripción para identificar la actividad (materia, tipo o título).
        Úsala cuando el estudiante diga que ya entregó, presentó o completó una actividad."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            coerce_academic_activities,
            match_academic_activities,
        )

        activities = coerce_academic_activities(_current_activities())
        matches = match_academic_activities(activities, text=activity_reference)
        if not matches:
            return f"No encontré ninguna actividad que coincida con '{activity_reference}'."
        if len(matches) > 1:
            lines = [f"Encontré {len(matches)} actividades. Especifica cuál completar:"]
            for a in matches:
                due_str = f" — vence {a.due_date}" if a.due_date else ""
                lines.append(f"  • [{a.activity_type}] {a.subject_name}: {a.activity_title}{due_str}")
            return "\n".join(lines)
        target = matches[0]
        try:
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "update", "activity_id": target.activity_id, "changes": {"status": "completed"}},
                timezone=state.timezone,
                reference_date=_today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
            act_title = target.activity_title or target.activity_type
            return json.dumps({
                "result": result.message or f"✅ '{act_title}' marcada como completada.",
                "_state_update": state_update,
            })
        except Exception as exc:
            return f"No pude marcar la actividad como completada: {exc}"

    # -------------------------------------------------------- Plan de estudio -

    @tool
    def get_weekly_plan(week_offset: int = 0) -> str:
        """Obtiene el plan de estudio semanal del estudiante.
        week_offset=0 para la semana actual.
        Úsala cuando el estudiante pida ver su plan, su agenda de estudio o
        cómo tiene distribuida la semana."""
        events = list(state.study_plan.plan_events or [])
        if not events:
            return (
                "No tienes plan de estudio generado aún. "
                "Puedo generarlo si me indicas tus prioridades y horario disponible."
            )
        by_day: dict[str, list[str]] = {}
        for ev in events:
            day_key = getattr(ev, "dia", "monday")
            day_label = _DAYS_ES.get(day_key, day_key)
            by_day.setdefault(day_label, []).append(f"  • {ev.inicio}–{ev.fin}: {ev.titulo}")
        lines = ["Tu plan de estudio esta semana:"]
        for day_key in _DAYS_ORDER:
            day_label = _DAYS_ES[day_key]
            if day_label in by_day:
                lines.append(f"\n{day_label}:")
                lines.extend(by_day[day_label])
        return "\n".join(lines)

    @tool
    def update_study_plan(reason: str) -> str:
        """Propone un plan semanal de sesiones de estudio. El resultado es una PROPUESTA —
        las sesiones NO se guardan en Outlook hasta que el estudiante las confirme explícitamente.
        Después de obtener la propuesta, SIEMPRE preséntala al estudiante y pregunta:
        '¿Confirmas estas sesiones para guardarlas en tu Outlook? ¿O quieres ajustar algo?'
        Solo llama sync_plan_to_calendar cuando el estudiante diga que sí confirma.
        Úsala cuando el estudiante registre una actividad nueva, pida reorganizar su semana,
        o cuando cambie el horario fijo.
        reason: motivo del cambio (ej: 'parcial de Filosofía el viernes')."""
        from agents.support.dependencies import get_study_replanning_service

        service = get_study_replanning_service()
        try:
            result = service.propose_replan(
                student_id=student_id,
                current_study_plan=state.study_plan,
                schedule_blocks=list(state.schedule.blocks),
                subjects=list(state.subjects),
                academic_activities=_current_activities(),
                study_profile=state.study_profile,
                constraints=state.constraints,
                timezone=state.timezone,
                replan_state=state.replan,
                explicit_request_text=reason,
            )
            if result.proposed:
                proposal = result.proposal_payload or {}
                study_plan_update = dict(proposal.get("study_plan") or {})
                new_plan_events = list(study_plan_update.get("plan_events") or [])
                new_subjects = list(proposal.get("subjects") or [])

                # Formatear plan para que el LLM lo presente de forma natural
                by_day: dict[str, list[str]] = {}
                for ev in new_plan_events[:20]:
                    if isinstance(ev, dict):
                        day_key = ev.get("dia", "")
                        titulo = ev.get("titulo", "Sesión")
                        inicio = ev.get("inicio", "—")
                        fin = ev.get("fin", "—")
                    else:
                        day_key = getattr(ev, "dia", "")
                        titulo = getattr(ev, "titulo", "Sesión")
                        inicio = getattr(ev, "inicio", "—")
                        fin = getattr(ev, "fin", "—")
                    day_label = _DAYS_ES.get(day_key, day_key)
                    by_day.setdefault(day_label, []).append(f"  • {inicio}–{fin}: {titulo}")

                summary = result.summary_text or f"{len(new_plan_events)} sesión(es) planificadas"
                plan_lines = [f"Plan de estudio generado — {summary}:"]
                for day_key in _DAYS_ORDER:
                    day_label = _DAYS_ES[day_key]
                    if day_label in by_day:
                        plan_lines.append(f"\n{day_label}:")
                        plan_lines.extend(by_day[day_label])
                extra = len(new_plan_events) - 20
                if extra > 0:
                    plan_lines.append(f"\n  ... y {extra} sesión(es) más")

                state_update: dict[str, object] = {
                    "study_plan": study_plan_update,
                    "replan": {"status": "applied", "trigger": "user_request"},
                }
                if new_subjects:
                    state_update["subjects"] = new_subjects

                return json.dumps({
                    "result": "\n".join(plan_lines),
                    "_state_update": state_update,
                })

            # Sin cambios: el plan actual ya es óptimo — formatearlo para que el LLM lo presente
            current_events = list(state.study_plan.plan_events or [])
            if result.no_changes and current_events:
                by_day_curr: dict[str, list[str]] = {}
                for ev in current_events[:20]:
                    day_key = getattr(ev, "dia", "")
                    day_label = _DAYS_ES.get(day_key, day_key)
                    titulo = getattr(ev, "titulo", "Sesión")
                    inicio = getattr(ev, "inicio", "—")
                    fin = getattr(ev, "fin", "—")
                    by_day_curr.setdefault(day_label, []).append(f"  • {inicio}–{fin}: {titulo}")
                plan_lines_curr = ["Plan de estudio actual (ya incorpora todas tus actividades):"]
                for day_key in _DAYS_ORDER:
                    day_label = _DAYS_ES[day_key]
                    if day_label in by_day_curr:
                        plan_lines_curr.append(f"\n{day_label}:")
                        plan_lines_curr.extend(by_day_curr[day_label])
                return "\n".join(plan_lines_curr)
            return result.prompt_text or result.summary_text or "No fue necesario cambiar el plan."
        except Exception as exc:
            return f"No pude generar la propuesta de replanificación: {exc}"

    @tool
    def move_study_session(
        session_reference: str,
        target_day: str | None = None,
        target_start_time: str | None = None,
        target_end_time: str | None = None,
        source_day: str | None = None,
        after_event_reference: str | None = None,
        target_date: str | None = None,
    ) -> str:
        """Mueve una sesión del plan de estudio, validando disponibilidad antes de aplicar.
        session_reference: materia, título, id o número de la sesión a mover. Ej: "Física", "sesión 2".
        target_day: nuevo día deseado. Ej: "martes".
        target_start_time: nueva hora de inicio en HH:MM o con am/pm. Ej: "17:00".
        target_end_time: nueva hora de fin opcional; si se omite, conserva la duración actual.
        source_day: día actual de la sesión si el estudiante lo menciona. Ej: "martes".
        after_event_reference: bloque fijo después del cual ubicarla. Ej: "clase de Física".
        target_date: fecha concreta de la instancia a mover (YYYY-MM-DD o texto como 'esta semana',
        'el martes que viene'). Si se provee, el cambio aplica SOLO a esa semana y no modifica
        la plantilla. Si se omite, el cambio aplica a todas las semanas.
        Úsala para frases como "mueve la sesión de Física del martes a las 5",
        "esa sesión no me sirve" o "ponla después de clase"."""
        plan_events = list(state.study_plan.plan_events or [])
        if not plan_events:
            return "No tienes sesiones de estudio generadas para mover."

        matches = _match_study_sessions(
            plan_events,
            session_reference=session_reference,
            source_day=source_day,
        )
        if not matches:
            return f"No encontré una sesión de estudio que coincida con '{session_reference}'."
        if len(matches) > 1:
            return _format_ambiguous_study_sessions(matches)

        target = matches[0]
        duration = _event_duration_minutes(target)
        if duration <= 0:
            return "No pude calcular la duración de esa sesión para moverla."

        resolved_day = _normalize_event_day(target_day) if target_day else None
        resolved_start = _normalize_move_time(target_start_time) if target_start_time else None
        resolved_end = _normalize_move_time(target_end_time) if target_end_time else None

        if after_event_reference and not resolved_start:
            after_slot = _resolve_after_event_slot(
                state,
                target,
                after_event_reference=after_event_reference,
                target_day=resolved_day,
            )
            if after_slot is None:
                alternatives = _suggest_study_session_slots(
                    state,
                    target,
                    preferred_day=resolved_day,
                    limit=4,
                )
                return (
                    "No encontré una clase o bloque fijo claro para ubicar esa sesión después.\n"
                    + _format_alternatives(alternatives)
                ).strip()
            resolved_day, resolved_start = after_slot

        if resolved_day is None and resolved_start is None:
            alternatives = _suggest_study_session_slots(state, target, limit=5)
            return (
                "Puedo mover esa sesión, pero necesito un nuevo día y hora.\n"
                + _format_alternatives(alternatives)
            ).strip()
        if resolved_day is None:
            resolved_day = target.dia
        if resolved_start is None:
            alternatives = _suggest_study_session_slots(
                state,
                target,
                preferred_day=resolved_day,
                limit=5,
            )
            return (
                f"Necesito la hora de inicio para moverla a **{resolved_day}**.\n"
                + _format_alternatives(alternatives)
            ).strip()
        if resolved_end is None:
            resolved_end = _minutes_to_hhmm(_time_to_minutes(resolved_start) + duration)

        try:
            start_min = _time_to_minutes(resolved_start)
            end_min = _time_to_minutes(resolved_end)
        except ValueError:
            return "No pude interpretar la hora solicitada. Usa formato HH:MM o am/pm."
        if start_min >= end_min:
            return "La hora de inicio debe ser anterior a la hora de fin."

        availability = _study_session_slot_availability(
            state,
            target,
            day=resolved_day,
            start_time=resolved_start,
            end_time=resolved_end,
        )
        if not availability[0]:
            alternatives = _suggest_study_session_slots(
                state,
                target,
                preferred_day=resolved_day,
                limit=4,
            )
            return (
                f"No puedo mover **{target.titulo}** a {resolved_day} "
                f"{resolved_start}–{resolved_end}: {availability[1]}.\n"
                + _format_alternatives(alternatives)
            ).strip()

        # ── Instancia única (target_date presente) ────────────────────────────
        if target_date:
            timezone_name = str(state.get("timezone") or "America/Bogota")
            resolved_date = _resolve_target_date_from_text(
                target_date, str(target.dia or ""), timezone_name
            )
            if resolved_date is None:
                return (
                    f"No pude interpretar la fecha '{target_date}'. "
                    "Usa formato YYYY-MM-DD o expresiones como 'esta semana', 'el martes que viene'."
                )

            # Calcular la fecha real del evento movido (puede ser diferente si cambia de día)
            orig_wd = _day_str_to_weekday(str(target.dia or ""))
            new_wd = _day_str_to_weekday(str(resolved_day or ""))
            if orig_wd is not None and new_wd is not None and orig_wd != new_wd:
                new_date = resolved_date + timedelta(days=new_wd - orig_wd)
            else:
                new_date = resolved_date

            from agents.support.dependencies import get_study_plan_materialization_service
            mat_svc = get_study_plan_materialization_service()
            profile_id = state.study_plan.persisted_profile_id
            student_id_raw = dict(state.get("student_profile", {})).get("persisted_student_id")
            try:
                student_id_int = int(student_id_raw)
            except (TypeError, ValueError):
                return "No pude identificar tu perfil de estudiante para mover la sesión."

            if not profile_id:
                return "El plan de estudio no tiene un perfil persistido; no puedo mover instancias individuales."

            instance = mat_svc.find_instance_for_session_and_date(
                student_id=student_id_int,
                study_plan_profile_id=int(profile_id),
                source_event_id=str(target.id),
                target_date=resolved_date,
            )
            if instance is None:
                return (
                    f"No encontré una instancia de **{target.titulo}** "
                    f"para la semana del {resolved_date.isoformat()}. "
                    "Es posible que ya haya pasado o que aún no esté materializada."
                )

            start_min = _time_to_minutes(resolved_start)
            new_starts_at = datetime.combine(
                new_date, time(hour=start_min // 60, minute=start_min % 60)
            )
            end_min = _time_to_minutes(resolved_end)
            new_ends_at = datetime.combine(
                new_date, time(hour=end_min // 60, minute=end_min % 60)
            )

            updated = mat_svc.update_instance_schedule_manually(
                source_instance_key=str(instance["source_instance_key"]),
                student_id=student_id_int,
                new_starts_at=new_starts_at,
                new_ends_at=new_ends_at,
            )
            if not updated:
                return (
                    f"No pude actualizar la instancia de **{target.titulo}** "
                    f"del {resolved_date.isoformat()}."
                )

            # Parchar en Outlook si el plan está sincronizado (no bloqueante)
            if profile_id:
                try:
                    from agents.support.dependencies import get_outlook_calendar_sync_service
                    get_outlook_calendar_sync_service().patch_single_study_session(
                        student_id=student_id_int,
                        source_instance_key=str(instance["source_instance_key"]),
                        subject=str(target.titulo or "Sesión de estudio"),
                        new_starts_at=new_starts_at,
                        new_ends_at=new_ends_at,
                        timezone=timezone_name,
                    )
                except Exception:
                    pass

            return json.dumps(
                {
                    "result": (
                        f"✅ Moví **{target.titulo}** al {resolved_day} "
                        f"{resolved_start}–{resolved_end} solo para la semana del "
                        f"{resolved_date.isoformat()}. Las demás semanas no cambian."
                    )
                }
            )

        # ── Plantilla semanal (target_date ausente) ───────────────────────────
        moved = target.model_copy(
            update={
                "dia": resolved_day,
                "inicio": resolved_start,
                "fin": resolved_end,
            }
        )
        try:
            validate_event(moved)
        except ValueError as exc:
            return f"No pude aplicar el cambio porque la sesión quedaría inválida: {exc}"

        updated_events = [
            moved if getattr(event, "id", None) == getattr(target, "id", None) else event
            for event in plan_events
        ]
        updated_plan = state.study_plan.model_copy(
            update={
                "plan_events": sort_events(updated_events),
                "rules": {
                    **dict(state.study_plan.rules or {}),
                    "last_manual_session_move": {
                        "session_id": target.id,
                        "from": {
                            "day": target.dia,
                            "start_time": target.inicio,
                            "end_time": target.fin,
                        },
                        "to": {
                            "day": moved.dia,
                            "start_time": moved.inicio,
                            "end_time": moved.fin,
                        },
                    },
                },
            }
        )
        return json.dumps(
            {
                "result": (
                    f"✅ Moví **{target.titulo}** de {target.dia} "
                    f"{target.inicio}–{target.fin} a {moved.dia} {moved.inicio}–{moved.fin}. "
                    "El cambio aplica a todas las semanas."
                ),
                "_state_update": {"study_plan": updated_plan.model_dump(mode="python")},
            }
        )

    # ------------------------------------------------- Restricciones --------

    @tool
    def update_constraints(
        study_session_min: int | None = None,
        study_session_max: int | None = None,
        max_study_per_day_min: int | None = None,
        preferred_study_start: str | None = None,
        preferred_study_end: str | None = None,
        sleep_start: str | None = None,
        sleep_end: str | None = None,
        unavailable_windows: list[dict[str, Any]] | None = None,
    ) -> str:
        """Actualiza las restricciones de planificación del estudiante.
        study_session_min: duración mínima de sesión en minutos (ej: 25).
        study_session_max: duración máxima de sesión en minutos (ej: 90).
        max_study_per_day_min: máximo total de minutos de estudio por día (ej: 180).
        preferred_study_start: hora de inicio preferida para estudiar, formato HH:MM (ej: '08:00').
        preferred_study_end: hora de fin preferida para estudiar, formato HH:MM (ej: '14:00').
        sleep_start: hora a la que se acuesta, formato HH:MM (ej: '23:00').
        sleep_end: hora a la que se levanta, formato HH:MM (ej: '06:00').
        unavailable_windows: franjas donde NO puede estudiar; lista de objetos con day o days,
        start_time, end_time y reason. Ej: [{"days":["monday","tuesday"],"start_time":"06:00",
        "end_time":"07:00","reason":"transporte"}].
        Úsala cuando el estudiante mencione: cuánto puede concentrarse seguido, cuándo prefiere estudiar,
        cuánto puede estudiar al día, su hora de dormir/levantarse, o restricciones de horario.
        Ejemplos: 'solo puedo estudiar de 8am a 2pm', 'máximo 45 minutos seguidos',
        'duermo a las 11pm', 'estoy en transporte de lunes a viernes de 6 a 7',
        'no puedo estudiar en esos espacios', 'bloquea esa hora'."""
        from schemas.planning import Constraints

        current = state.constraints
        changes: dict[str, Any] = {}

        if study_session_min is not None:
            if not (10 <= study_session_min <= 120):
                return f"Sesión mínima inválida: {study_session_min}. Debe estar entre 10 y 120 minutos."
            changes["study_session_min"] = study_session_min
        if study_session_max is not None:
            if not (15 <= study_session_max <= 240):
                return f"Sesión máxima inválida: {study_session_max}. Debe estar entre 15 y 240 minutos."
            changes["study_session_max"] = study_session_max
        if max_study_per_day_min is not None:
            if not (30 <= max_study_per_day_min <= 720):
                return f"Máximo diario inválido: {max_study_per_day_min}. Debe estar entre 30 y 720 minutos."
            changes["max_study_per_day_min"] = max_study_per_day_min
        if preferred_study_start is not None:
            try:
                changes["preferred_study_start"] = _normalize_time(preferred_study_start)
            except Exception:
                return f"Hora de inicio inválida: '{preferred_study_start}'. Usa formato HH:MM."
        if preferred_study_end is not None:
            try:
                changes["preferred_study_end"] = _normalize_time(preferred_study_end)
            except Exception:
                return f"Hora de fin inválida: '{preferred_study_end}'. Usa formato HH:MM."
        if sleep_start is not None:
            try:
                changes["sleep_start"] = _normalize_time(sleep_start)
            except Exception:
                return f"Hora de sueño inválida: '{sleep_start}'. Usa formato HH:MM."
        if sleep_end is not None:
            try:
                changes["sleep_end"] = _normalize_time(sleep_end)
            except Exception:
                return f"Hora de despertar inválida: '{sleep_end}'. Usa formato HH:MM."
        if unavailable_windows is not None:
            normalized_windows = _normalize_unavailable_windows(unavailable_windows)
            if not normalized_windows:
                return "No pude identificar una franja no disponible válida. Indica día, hora de inicio y hora de fin."
            existing_windows = [
                _window_to_dict(window)
                for window in list(current.unavailable_windows or [])
            ]
            changes["unavailable_windows"] = _dedupe_unavailable_windows(
                existing_windows + normalized_windows
            )

        if not changes:
            return "No indicaste ningún límite a actualizar."

        new_min = changes.get("study_session_min", current.study_session_min)
        new_max = changes.get("study_session_max", current.study_session_max)
        if new_min > new_max:
            return f"La sesión mínima ({new_min} min) no puede ser mayor que la máxima ({new_max} min)."

        pref_s = changes.get("preferred_study_start", current.preferred_study_start)
        pref_e = changes.get("preferred_study_end", current.preferred_study_end)
        if pref_s and pref_e:
            try:
                ps_min = int(pref_s.split(":")[0]) * 60 + int(pref_s.split(":")[1])
                pe_min = int(pref_e.split(":")[0]) * 60 + int(pref_e.split(":")[1])
                if ps_min >= pe_min:
                    return f"El horario preferido de inicio ({pref_s}) debe ser anterior al de fin ({pref_e})."
            except Exception:
                pass

        updated = Constraints(**(current.model_dump(mode="python") | changes))
        msg_parts: list[str] = []
        if "study_session_min" in changes or "study_session_max" in changes:
            msg_parts.append(f"sesiones de {updated.study_session_min}–{updated.study_session_max} min")
        if "max_study_per_day_min" in changes:
            msg_parts.append(f"máximo {updated.max_study_per_day_min} min/día")
        if "preferred_study_start" in changes or "preferred_study_end" in changes:
            msg_parts.append(
                f"horario preferido {updated.preferred_study_start or '—'}–{updated.preferred_study_end or '—'}"
            )
        if "sleep_start" in changes or "sleep_end" in changes:
            msg_parts.append(f"sueño {updated.sleep_end}–{updated.sleep_start}")
        if "unavailable_windows" in changes:
            added = len(changes["unavailable_windows"]) - len(current.unavailable_windows or [])
            msg_parts.append(f"{max(added, 0)} franja(s) no disponible(s)")

        msg = "✅ Restricciones de planificación actualizadas: " + ", ".join(msg_parts) + "."
        state_update: dict[str, Any] = {"constraints": updated.model_dump()}
        if state.study_plan.plan_events:
            trigger = "availability_change" if "unavailable_windows" in changes else "user_request"
            state_update["replan"] = {"trigger": trigger}

        return json.dumps({"result": msg, "_state_update": state_update})

    # --------------------------------------------------------- Prioridades ---

    @tool
    def update_priorities(subjects_with_priorities: list[dict]) -> str:
        """Actualiza las prioridades de materias para esta semana.
        subjects_with_priorities: lista de objetos con campos:
          nombre (str), prioridad (alta|media|baja), urgencia (opcional: alta|media|baja).
        Úsala cuando el estudiante quiera ajustar qué materias son más importantes
        o urgentes esta semana."""
        subjects = list(state.subjects)
        if not subjects:
            return "No tienes materias configuradas aún."
        updated = []
        changed = 0
        for s in subjects:
            nombre = getattr(s, "nombre", "")
            match_data = next(
                (x for x in subjects_with_priorities if x.get("nombre", "").lower() == nombre.lower()),
                None,
            )
            if match_data:
                patch: dict[str, Any] = {}
                if "prioridad" in match_data:
                    val = match_data["prioridad"]
                    if val not in _VALID_PRIORIDAD:
                        return f"Prioridad inválida: '{val}'. Valores aceptados: alta, media, baja."
                    patch["prioridad"] = val
                if "urgencia" in match_data:
                    val = match_data["urgencia"]
                    if val is not None and val not in _VALID_PRIORIDAD:
                        return f"Urgencia inválida: '{val}'. Valores aceptados: alta, media, baja."
                    patch["urgencia"] = val
                updated.append(s.model_copy(update=patch) if patch else s)
                changed += 1
            else:
                updated.append(s)
        if not changed:
            return "No encontré las materias especificadas en tu perfil. Verifica los nombres."
        return json.dumps({
            "result": f"Prioridades actualizadas para {changed} materia(s).",
            "_state_update": {"subjects": [s.model_dump() for s in updated]},
        })

    # --------------------------------------------------------- Horario -------

    @tool
    def get_schedule(filter_type: str | None = None) -> str:
        """Obtiene el horario fijo del estudiante: clases, trabajo y actividades extracurriculares.
        filter_type: filtra por tipo — 'academic' (clases/materias), 'work' (trabajo/laboral),
        'extracurricular' (deportes, actividades personales). Si es None, muestra todo.
        Úsala cuando el estudiante pregunte por su horario, sus clases, su trabajo, sus actividades,
        cuándo tiene tiempo libre, o qué días tiene compromisos fijos."""
        _TYPE_LABELS = {
            "academic": "Académico 📚",
            "work": "Laboral 💼",
            "extracurricular": "Extracurricular 🏃",
        }
        blocks = _load_current_schedule_blocks(state)
        if not blocks:
            return "No tienes horario fijo registrado."
        active = [b for b in blocks if getattr(b, "is_active", True)]
        if not active:
            return "No tienes bloques activos en tu horario."

        # Aplicar filtro de tipo si se especificó
        type_norm = (filter_type or "").strip().lower()
        if type_norm in {"academic", "work", "extracurricular"}:
            active = [b for b in active if getattr(b, "block_type", "") == type_norm]
            if not active:
                label = _TYPE_LABELS.get(type_norm, type_norm)
                return f"No tienes bloques de tipo {label} en tu horario."

        # Agrupar por tipo y luego por día
        by_type: dict[str, dict[str, list[str]]] = {}
        for b in active:
            btype = getattr(b, "block_type", "academic")
            day_key = getattr(b, "day_of_week", "monday")
            by_type.setdefault(btype, {}).setdefault(day_key, []).append(
                f"    • {b.start_time}–{b.end_time}: {b.title}"
            )

        # Orden de tipos para mostrar: academic → work → extracurricular
        type_order = ["academic", "work", "extracurricular"]
        lines = ["**Tu horario fijo:**"]
        for btype in type_order:
            if btype not in by_type:
                continue
            lines.append(f"\n**{_TYPE_LABELS[btype]}**")
            day_map = by_type[btype]
            for day_key in _DAYS_ORDER:
                if day_key in day_map:
                    lines.append(f"  {_DAYS_ES[day_key]}:")
                    lines.extend(day_map[day_key])
        return "\n".join(lines)

    @tool
    def add_schedule_block(
        title: str,
        day: str,
        start_time: str,
        end_time: str,
        block_type: str = "academic",
    ) -> str:
        """Agrega un bloque al horario fijo del estudiante y sincroniza con Outlook.
        title: nombre de la clase/materia/actividad.
        day: día en español o inglés; acepta rangos o varios días (ej: "martes y viernes").
        start_time: hora de inicio en HH:MM o con am/pm (ej: '09:00', '4 pm').
        end_time: hora de fin en HH:MM o con am/pm (ej: '11:00', '7 pm').
        block_type: academic/academico | work/laboral | extracurricular.
        Úsala cuando el estudiante quiera agregar una clase, trabajo o actividad al horario semanal.
        Extrae día y horas del mensaje del usuario — NO pidas datos que ya mencionó."""
        try:
            repair_guard = _fixed_schedule_outlook_repair_guard(state)
            if repair_guard:
                return repair_guard

            from services.scheduling.fixed_schedule_management import (
                build_fixed_schedule_add_preview,
            )

            type_norm = _normalize_schedule_block_type(block_type)
            raw_text = _build_schedule_add_parser_text(
                title=title,
                day=day,
                start_time=start_time,
                end_time=end_time,
                block_type=type_norm,
            )
            preview = build_fixed_schedule_add_preview(
                raw_text,
                type_norm,
                timezone=timezone_name,
            )
            if preview.prompt:
                return preview.prompt
            if not preview.replacement_blocks:
                return "No pude interpretar el nuevo bloque. Indica nombre, día, hora de inicio y hora de fin."

            title_norm = _normalize_schedule_tool_title(title, type_norm)
            if not title_norm:
                return "Indica el nombre del nuevo bloque."

            new_blocks = [
                _prepare_schedule_tool_block(
                    block,
                    title=title_norm,
                    block_type=type_norm,
                    timezone=timezone_name,
                )
                for block in preview.replacement_blocks
            ]
            blocks = _load_current_schedule_blocks(state)
            updated_blocks = blocks + new_blocks
            msg, state_update = _apply_and_persist_schedule(state, updated_blocks, "actualizado")
            block_count = len(new_blocks)
            block_label = "Bloque" if block_count == 1 else "Bloques"
            added_label = f"'{title_norm}'" if block_count == 1 else f"'{title_norm}' ({block_count})"
            return json.dumps(
                {"result": f"✅ {block_label} {added_label} agregado(s) al horario. {msg}", "_state_update": state_update},
                default=_json_default,
            )
        except ValueError as exc:
            return str(exc)
        except Exception as exc:
            return f"Error inesperado al agregar el bloque '{title}': {exc}"

    @tool
    def update_schedule_block(
        block_reference: str,
        title: str | None = None,
        day: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        block_type: str | None = None,
    ) -> str:
        """Modifica un bloque existente del horario fijo y sincroniza con Outlook.
        block_reference: descripción para identificar el bloque (nombre, día, o combinación).
        Pasa solo los campos que cambian: day puede venir en español o inglés; horas en HH:MM o am/pm.
        Úsala cuando el estudiante quiera cambiar horario, día o nombre de una clase ya registrada."""
        from services.scheduling.fixed_schedule_management import (
            build_fixed_schedule_update_preview,
            match_fixed_schedule_blocks,
        )

        try:
            repair_guard = _fixed_schedule_outlook_repair_guard(state)
            if repair_guard:
                return repair_guard

            blocks = _load_current_schedule_blocks(state)
            if not blocks:
                return "No tienes bloques registrados en el horario fijo."
            result = match_fixed_schedule_blocks(blocks, block_reference)
            if not result.matches:
                lines = ["No encontré bloque con esa descripción. Bloques actuales:"]
                for b in blocks:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title} [{b.block_type}]")
                return "\n".join(lines)
            if len(result.matches) > 1:
                lines = [f"Encontré {len(result.matches)} bloques similares. Especifica cuál:"]
                for b in result.matches:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title}")
                return "\n".join(lines)

            target = result.matches[0]
            updates: dict[str, Any] = {}
            type_norm = _normalize_schedule_block_type(block_type) if block_type is not None else None
            if title is not None:
                normalized_title = _normalize_schedule_tool_title(title, type_norm or target.block_type)
                if not normalized_title:
                    return "Indica el nuevo nombre del bloque."
                updates["title"] = normalized_title
            if type_norm is not None:
                updates["block_type"] = type_norm
            if not updates:
                schedule_updates = _build_schedule_update_replacements_from_tool_args(
                    target,
                    day=day,
                    start_time=start_time,
                    end_time=end_time,
                    timezone=timezone_name,
                    build_preview=build_fixed_schedule_update_preview,
                )
                if isinstance(schedule_updates, str):
                    return schedule_updates
                if schedule_updates:
                    updated_blocks = [
                        b for b in blocks if b.block_id != target.block_id
                    ] + schedule_updates
                    msg, state_update = _apply_and_persist_schedule(state, updated_blocks, "actualizado")
                    return json.dumps(
                        {"result": f"✅ Bloque '{target.title}' modificado. {msg}", "_state_update": state_update},
                        default=_json_default,
                    )
                return "No indicaste ningún campo a cambiar."

            schedule_updates = _build_schedule_update_replacements_from_tool_args(
                target.model_copy(update=updates),
                day=day,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone_name,
                build_preview=build_fixed_schedule_update_preview,
            )
            if isinstance(schedule_updates, str):
                return schedule_updates
            if schedule_updates:
                updated_replacements = [
                    _prepare_schedule_tool_block(
                        block,
                        title=updates.get("title"),
                        block_type=updates.get("block_type"),
                        timezone=timezone_name,
                    )
                    for block in schedule_updates
                ]
                updated_blocks = [
                    b for b in blocks if b.block_id != target.block_id
                ] + updated_replacements
            else:
                updated_target = _prepare_schedule_tool_block(
                    target.model_copy(update=updates),
                    timezone=timezone_name,
                )
                updated_blocks = [updated_target if b.block_id == target.block_id else b for b in blocks]
            msg, state_update = _apply_and_persist_schedule(state, updated_blocks, "actualizado")
            return json.dumps(
                {"result": f"✅ Bloque '{target.title}' modificado. {msg}", "_state_update": state_update},
                default=_json_default,
            )
        except ValueError as exc:
            return str(exc)
        except Exception as exc:
            return f"Error inesperado al modificar el bloque '{block_reference}': {exc}"

    @tool
    def delete_schedule_block(block_reference: str) -> str:
        """Elimina un bloque del horario fijo y sincroniza con Outlook.
        block_reference: descripción del bloque a eliminar (nombre, día, o combinación).
        Úsala cuando el estudiante quiera quitar una clase, trabajo o actividad del horario semanal."""
        from services.scheduling.fixed_schedule_management import match_fixed_schedule_blocks

        try:
            repair_guard = _fixed_schedule_outlook_repair_guard(state)
            if repair_guard:
                return repair_guard

            blocks = _load_current_schedule_blocks(state)
            if not blocks:
                return "No tienes bloques registrados en el horario fijo."
            result = match_fixed_schedule_blocks(blocks, block_reference)
            if not result.matches:
                lines = ["No encontré bloque con esa descripción. Bloques actuales:"]
                for b in blocks:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title} [{b.block_type}]")
                return "\n".join(lines)
            if len(result.matches) > 1:
                lines = [f"Encontré {len(result.matches)} bloques similares. Especifica cuál eliminar:"]
                for b in result.matches:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title}")
                return "\n".join(lines)

            target = result.matches[0]
            updated_blocks = [b for b in blocks if b.block_id != target.block_id]
            msg, state_update = _apply_and_persist_schedule(state, updated_blocks, "actualizado")
            return json.dumps(
                {"result": f"✅ Bloque '{target.title}' eliminado del horario. {msg}", "_state_update": state_update},
                default=_json_default,
            )
        except Exception as exc:
            return f"Error inesperado al eliminar el bloque '{block_reference}': {exc}"

    # ------------------------------------------------- Integración externa ---

    @tool
    def add_one_time_event(
        title: str,
        date: str,
        start_time: str,
        end_time: str,
        event_type: str = "extracurricular",
    ) -> str:
        """Agrega un evento puntual a Outlook Calendar para una fecha específica.
        NO modifica el horario fijo semanal — el evento existe solo para ese día.
        title: nombre del evento (ej: 'Partido U. La Sabana vs Católica').
        date: fecha en formato YYYY-MM-DD (ej: '2026-05-24').
        start_time: hora de inicio en HH:MM (ej: '15:00').
        end_time: hora de fin en HH:MM (ej: '17:00').
        event_type: extracurricular | academic | work.
        Úsala cuando el estudiante quiera agendar algo para un día concreto
        sin que se repita cada semana en su horario fijo."""
        from datetime import date as _date, time as _time
        from agents.support.dependencies import get_outlook_one_time_event_service

        valid_types = {"extracurricular", "academic", "work"}
        type_norm = event_type.strip().lower()
        if type_norm not in valid_types:
            return f"Tipo inválido: '{event_type}'. Acepta: extracurricular, academic, work."

        try:
            event_date = _date.fromisoformat(date.strip())
        except ValueError:
            return f"Fecha inválida: '{date}'. Usa formato YYYY-MM-DD (ej: '2026-05-24')."

        try:
            _start = _normalize_time(start_time)
            _end = _normalize_time(end_time)
            event_start = _time.fromisoformat(_start)
            event_end = _time.fromisoformat(_end)
        except Exception:
            return f"Horario inválido: '{start_time}' o '{end_time}'. Usa formato HH:MM."

        try:
            result = get_outlook_one_time_event_service().create_event(
                student_id=student_id,
                calendar_state=state.calendar,
                title=title.strip(),
                event_date=event_date,
                start_time=event_start,
                end_time=event_end,
                timezone=timezone_name,
                event_type=type_norm,
                calendar_id=state.calendar.calendar_id,
            )
            if result.created:
                return (
                    f"✅ Evento '{title}' agendado en Outlook para el "
                    f"{event_date.strftime('%d/%m/%Y')} de {_start} a {_end}. "
                    f"Solo aparece ese día — no afecta tu horario fijo."
                )
            err = result.detail or result.error_code or "error desconocido"
            return (
                f"No pude agendar '{title}' en Outlook: {err}. "
                f"El evento no fue guardado."
            )
        except Exception as exc:
            return f"Error inesperado al agendar el evento '{title}': {exc}"

    @tool
    def sync_plan_to_calendar(
        restore_manual_outlook_changes: bool = False,
        keep_manual_outlook_changes: bool = False,
    ) -> str:
        """Guarda en Outlook Calendar las sesiones de estudio propuestas por update_study_plan.
        SOLO úsala después de que el estudiante confirme explícitamente las sesiones propuestas.
        NO usar para clases, materias ni bloques del horario fijo (work, academic, extracurricular):
        esos se sincronizan automáticamente al usar add_schedule_block o update_schedule_block.
        restore_manual_outlook_changes: True solo si el estudiante eligió restaurar el plan del asistente
        tras detectar cambios manuales en Outlook.
        keep_manual_outlook_changes: True solo si el estudiante eligió conservar cambios manuales de Outlook."""
        from agents.support.dependencies import (
            get_outlook_calendar_sync_service,
            get_study_plan_materialization_service,
        )

        service = get_outlook_calendar_sync_service()
        calendar_id = state.calendar.calendar_id
        try:
            plan = state.study_plan
            if plan.plan_events and plan.persisted_profile_id:
                materialized = get_study_plan_materialization_service().materialize_plan_instances(
                    student_id=student_id,
                    study_plan_profile_id=plan.persisted_profile_id,
                    study_plan=plan,
                    timezone=str(state.timezone or "America/Bogota"),
                )
                if not materialized.materialized:
                    return "No pude preparar las sesiones para Outlook. Intenta de nuevo más tarde."
                manual_guard = _study_calendar_outlook_manual_change_guard(
                    state,
                    restore_manual_outlook_changes=restore_manual_outlook_changes,
                    keep_manual_outlook_changes=keep_manual_outlook_changes,
                )
                if manual_guard:
                    return manual_guard
            result = service.sync_student_calendar(
                student_id=student_id,
                calendar_state=state.calendar,
                calendar_id=calendar_id,
                study_plan_profile_id=state.study_plan.persisted_profile_id,
            )
            if result.synced:
                if result.upserted_count == 0 and result.deleted_count == 0:
                    return (
                        "No había sesiones del plan de estudio pendientes de sincronizar con Outlook. "
                        "Si esperabas eventos nuevos, verifica que el plan tenga sesiones generadas y guardadas."
                    )
                return (
                    f"✅ Sincronización completada: {result.upserted_count} sesión(es) "
                    f"creadas/actualizadas, {result.deleted_count} eliminadas en Outlook."
                )
            return "No se pudo sincronizar con Outlook Calendar. Intenta de nuevo más tarde."
        except Exception:
            return "No se pudo sincronizar con Outlook Calendar. Intenta de nuevo más tarde."

    @tool
    def sync_tasks_to_todo(
        import_manual_todo_changes: bool = False,
        restore_assistant_tasks: bool = False,
    ) -> str:
        """Sincroniza actividades académicas con Microsoft To Do.
        Las actividades con prioridad alta aparecen con ⭐ en To Do.
        Actividades completadas se marcan como completadas y eliminadas se retiran de To Do.
        Si To Do tiene cambios manuales de título o fecha, pregunta antes de importarlos.
        Usa import_manual_todo_changes=True si el estudiante quiere conservar lo editado en To Do.
        Usa restore_assistant_tasks=True si el estudiante quiere restaurar To Do con los datos del asistente.
        Úsala solo cuando el estudiante pida explícitamente ver o sincronizar sus tareas en Microsoft To Do."""
        from agents.support.dependencies import get_microsoft_todo_sync_service
        from services.planning.academic_activity_service import (
            coerce_academic_activities,
        )

        service = get_microsoft_todo_sync_service()
        task_list_id = state.calendar.todo_task_list_id
        activities = coerce_academic_activities(_current_activities())
        try:
            result = service.sync_academic_activities_to_todo(
                student_id=student_id,
                task_list_id=task_list_id,
                activities=activities,
                import_manual_todo_changes=import_manual_todo_changes,
                restore_manual_todo_changes=restore_assistant_tasks,
            )
            if getattr(result, "requires_confirmation", False):
                msg = _format_manual_todo_change_prompt(result)
                state_update: dict[str, object] = {}
                if result.synced_activities:
                    updated_all = {a.activity_id: a for a in result.synced_activities}
                    merged = [
                        updated_all.get(a.activity_id, a).model_dump()
                        for a in activities
                    ]
                    _cycle_updates["academic_activities"] = merged
                    state_update["academic_activities"] = merged
                return json.dumps({"result": msg, "_state_update": state_update})
            if result.synced:
                msg = f"✅ {result.upserted_count} actividad(es) sincronizada(s) en Microsoft To Do."
                if getattr(result, "deleted_count", 0):
                    msg += f" {result.deleted_count} tarea(s) eliminada(s)."
                imported_count = getattr(result, "imported_completed_count", 0)
                if imported_count:
                    msg += f" {imported_count} actividad(es) marcada(s) como completada(s) desde To Do."
                if import_manual_todo_changes and getattr(result, "inbound_change_count", 0):
                    msg += " Importé los cambios manuales de To Do al asistente."
                if restore_assistant_tasks and getattr(result, "inbound_change_count", 0):
                    msg += " Restauré To Do con la información del asistente."
                if result.synced_activities:
                    updated_all = {a.activity_id: a for a in result.synced_activities}
                    merged = [
                        updated_all.get(a.activity_id, a).model_dump()
                        for a in activities
                    ]
                    _cycle_updates["academic_activities"] = merged
                    return json.dumps({"result": msg, "_state_update": {"academic_activities": merged}})
                return msg
            return "No se pudo sincronizar con Microsoft To Do. Intenta de nuevo más tarde."
        except Exception:
            return "No se pudo sincronizar con Microsoft To Do. Intenta de nuevo más tarde."

    @tool
    def apply_outlook_reconciliation(
        accept: bool,
        reconciliation_id: str | None = None,
    ) -> str:
        """Aplica o rechaza un cambio detectado en Outlook Calendar.
        Úsala cuando el estudiante responda sí/no a una notificación de cambio detectado.
        accept: True si confirma el cambio, False si lo rechaza.
        reconciliation_id: ID del cambio pendiente (opcional; si se omite, aplica al más reciente)."""
        from agents.support.dependencies import get_reconciliation_repository

        if not student_id:
            return "No pude identificar tu perfil para procesar el cambio."

        repo = get_reconciliation_repository()
        try:
            pending = repo.list_pending_for_student(str(student_id))
        except Exception as exc:
            return f"No pude consultar los cambios pendientes: {exc}"

        unresolved = [p for p in pending if p.get("resolved_at") is None]
        if not unresolved:
            return "No hay cambios de Outlook pendientes de confirmar."

        if reconciliation_id:
            target = next((p for p in unresolved if str(p.get("id") or "") == reconciliation_id), None)
            if target is None:
                return f"No encontré el cambio pendiente con ID '{reconciliation_id}'."
        else:
            target = unresolved[0]

        rec_id = str(target["id"])
        drift_kind = str(target.get("drift_kind") or "")
        instance_id = str(target.get("instance_id") or "")
        session_title = str(target.get("session_title") or "la sesión").strip() or "la sesión"

        if not accept:
            try:
                repo.resolve(rec_id, "rejected")
            except Exception:
                pass

            if drift_kind == "moved":
                try:
                    orig_start = _parse_reconciliation_datetime(target.get("original_start"))
                    orig_end = _parse_reconciliation_datetime(target.get("original_end"))
                    if orig_start and orig_end and student_id:
                        from agents.support.dependencies import get_outlook_calendar_sync_service
                        get_outlook_calendar_sync_service().patch_single_study_session(
                            student_id=int(student_id),
                            source_instance_key=instance_id,
                            subject=session_title,
                            new_starts_at=orig_start,
                            new_ends_at=orig_end,
                            timezone=timezone_name,
                        )
                except Exception:
                    pass

            return (
                f"De acuerdo. Mantendré tu plan original para *{session_title}* "
                "sin aplicar el cambio de Outlook."
            )

        # accept=True
        if drift_kind == "moved":
            new_start = _parse_reconciliation_datetime(target.get("new_start"))
            new_end = _parse_reconciliation_datetime(target.get("new_end"))
            if not new_start or not new_end:
                return f"No tengo las nuevas fechas para *{session_title}*. No pude aplicar el cambio."
            try:
                from agents.support.dependencies import get_study_plan_materialization_service
                updated = get_study_plan_materialization_service().update_instance_schedule_manually(
                    source_instance_key=instance_id,
                    student_id=int(student_id),
                    new_starts_at=new_start,
                    new_ends_at=new_end,
                )
                repo.resolve(rec_id, "accepted")
                if updated:
                    return f"✅ Actualicé *{session_title}* en tu plan con la nueva hora de Outlook."
                return f"No pude actualizar *{session_title}* en el plan (puede que ya no exista la instancia)."
            except Exception as exc:
                return f"Error al aplicar el cambio en el plan: {exc}"

        if drift_kind == "deleted":
            try:
                from agents.support.dependencies import get_study_plan_materialization_service
                cancelled = get_study_plan_materialization_service().cancel_instance(
                    source_instance_key=instance_id,
                    student_id=int(student_id),
                )
                repo.resolve(rec_id, "accepted")
                if cancelled:
                    return f"✅ Eliminé *{session_title}* de tu plan de estudio."
                return f"La sesión *{session_title}* ya no estaba activa en el plan."
            except Exception as exc:
                return f"Error al eliminar la sesión del plan: {exc}"

        return f"No pude procesar el cambio para *{session_title}*."

    return [
        get_current_datetime,
        search_study_methods,
        get_technique_guide,
        add_academic_activity,
        edit_academic_activity,
        delete_academic_activity,
        mark_activity_done,
        get_pending_activities,
        get_weekly_plan,
        update_study_plan,
        move_study_session,
        update_constraints,
        get_schedule,
        add_schedule_block,
        update_schedule_block,
        delete_schedule_block,
        add_one_time_event,
        sync_plan_to_calendar,
        sync_tasks_to_todo,
        apply_outlook_reconciliation,
    ]


def _load_current_schedule_blocks(state: AgentState) -> list:
    """Carga bloques del horario fijo desde el estado o la DB como fallback."""
    from services.scheduling.models import ensure_weekly_block

    blocks = list(state.schedule.blocks or [])
    if blocks:
        return [ensure_weekly_block(b) for b in blocks]
    student_id = _get_student_id(state)
    if not student_id:
        return []
    try:
        from agents.support.dependencies import get_schedule_service
        result = get_schedule_service().list_current_schedule_blocks(student_id=student_id)
        if result.found and result.blocks:
            return [_block_from_persisted_record(r) for r in result.blocks]
    except Exception:
        pass
    return []


_RECONCILIATION_THROTTLE_SECONDS = 60


def _was_recently_reconciled(student_id: int, *, throttle_seconds: int = _RECONCILIATION_THROTTLE_SECONDS) -> bool:
    """Retorna True si algún bloque fue reconciliado con Outlook hace menos de throttle_seconds."""
    try:
        from datetime import datetime, timezone as dt_timezone

        from agents.support.dependencies import get_schedule_service

        result = get_schedule_service().list_current_schedule_blocks(student_id=student_id)
        if not result.found or not result.blocks:
            return False
        now = datetime.now(dt_timezone.utc)
        for block in result.blocks:
            raw = str(block.external_sync_metadata.get("reconciled_at") or "").strip()
            if not raw:
                continue
            try:
                reconciled_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if (now - reconciled_at).total_seconds() < throttle_seconds:
                    return True
            except ValueError:
                continue
    except Exception:
        pass
    return False


def _fixed_schedule_outlook_repair_guard(state: AgentState) -> str | None:
    """Reconciliación previa para no sobrescribir cambios manuales de Outlook."""
    student_id = _get_student_id(state)
    if not student_id:
        return None
    schedule_profile_id = getattr(state.schedule, "persisted_profile_id", None)
    if not schedule_profile_id:
        return None
    if _was_recently_reconciled(student_id):
        return None
    calendar = state.calendar
    calendar_id = getattr(calendar, "calendar_id", None)
    try:
        from agents.support.dependencies import get_outlook_fixed_schedule_reconciliation_service
        from agents.support.scheduling.state_helpers import update_schedule_flow_state

        result = get_outlook_fixed_schedule_reconciliation_service().reconcile_schedule_profile(
            student_id=student_id,
            schedule_profile_id=schedule_profile_id,
            calendar_id=calendar_id,
        )
    except Exception:
        return None

    if not result.reconciled:
        return None
    if result.drifted_count <= 0 and result.missing_count <= 0:
        return None

    schedule_update = update_schedule_flow_state(
        state.schedule,
        repair_stage="awaiting_decision",
        persisted_profile_id=result.schedule_profile_id or schedule_profile_id,
    )
    prompt = _fixed_schedule_manual_change_prompt(
        drifted_count=result.drifted_count,
        missing_count=result.missing_count,
    )
    return json.dumps(
        {
            "result": prompt,
            "_state_update": {
                "schedule": schedule_update,
                "phase": "schedule_repair",
                "awaiting_user_input": True,
            },
        },
        default=_json_default,
    )


def _fixed_schedule_manual_change_prompt(*, drifted_count: int, missing_count: int) -> str:
    return (
        "🛠️ Detecté cambios manuales en tu horario fijo de Outlook.\n"
        f"Eventos editados: {drifted_count}. Eventos eliminados: {missing_count}.\n\n"
        "Tu horario oficial sigue guardado en el asistente. Antes de mostrarlo o modificarlo, "
        "necesito que decidas qué hacer:\n"
        "(Escribe el número de la opción que quieres elegir)\n"
        "1. Restaurar Outlook con el horario oficial del asistente\n"
        "2. Conservar el cambio de Outlook y organizar un horario fijo nuevo\n"
        "3. Revisarlo después"
    )


def _study_calendar_outlook_manual_change_guard(
    state: AgentState,
    *,
    restore_manual_outlook_changes: bool,
    keep_manual_outlook_changes: bool,
) -> str | None:
    student_id = _get_student_id(state)
    study_plan_profile_id = getattr(state.study_plan, "persisted_profile_id", None)
    if not student_id or not study_plan_profile_id:
        return None
    try:
        from agents.support.dependencies import get_outlook_study_calendar_reconciliation_service

        service = get_outlook_study_calendar_reconciliation_service()
        result = service.reconcile_student_calendar(
            student_id=student_id,
            calendar_id=getattr(state.calendar, "calendar_id", None),
            study_plan_profile_id=study_plan_profile_id,
        )
    except Exception:
        return None

    if not result.reconciled:
        return None
    manual_findings = [
        finding for finding in result.findings if finding.status in {"drifted", "missing"}
    ]
    if not manual_findings:
        return None

    if restore_manual_outlook_changes:
        missing_keys = [
            finding.source_instance_key
            for finding in manual_findings
            if finding.status == "missing"
        ]
        if missing_keys:
            try:
                service.mark_missing_links_deleted(
                    student_id=student_id,
                    source_instance_keys=missing_keys,
                )
            except Exception:
                pass
        return None

    if keep_manual_outlook_changes:
        state_update = _study_plan_external_sync_update(
            state,
            status="manual_outlook_change_kept",
            result={
                "decision": "keep",
                "manual_change_count": len(manual_findings),
            },
        )
        return json.dumps(
            {
                "result": (
                    "De acuerdo. Conservaré el cambio manual en Outlook y no lo sobrescribiré ahora. "
                    "Tu plan oficial del asistente queda igual."
                ),
                "_state_update": state_update,
            },
            default=_json_default,
        )

    state_update = _study_plan_external_sync_update(
        state,
        status="awaiting_manual_outlook_decision",
        preview={
            "drifted_count": result.drifted_count,
            "missing_count": result.missing_count,
        },
    )
    return json.dumps(
        {
            "result": _study_calendar_manual_change_prompt(
                drifted_count=result.drifted_count,
                missing_count=result.missing_count,
                findings=manual_findings,
            ),
            "_state_update": state_update,
        },
        default=_json_default,
    )


def _study_calendar_manual_change_prompt(
    *,
    drifted_count: int,
    missing_count: int,
    findings: list[Any],
) -> str:
    first = findings[0] if findings else None
    title = str(getattr(first, "title", "") or "esta sesión").strip()
    noun = "esta sesión" if drifted_count + missing_count == 1 else "estas sesiones"
    return (
        f"Detecté que editaste {noun} en Outlook: {title}.\n"
        f"Sesiones editadas: {drifted_count}. Sesiones eliminadas: {missing_count}.\n\n"
        "¿Quieres conservar ese cambio o restaurar el plan del asistente?\n"
        "(Escribe el número de la opción que quieres elegir)\n"
        "1. Conservar el cambio de Outlook\n"
        "2. Restaurar el plan del asistente en Outlook\n"
        "3. Cancelar"
    )


def _study_plan_external_sync_update(
    state: AgentState,
    *,
    status: str,
    preview: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
) -> dict[str, object]:
    from services.planning import ensure_study_plan_state, update_study_plan_state

    normalized = ensure_study_plan_state(state.study_plan)
    rules = dict(normalized.rules or {})
    payload = dict(rules.get("external_sync") or {})
    payload.update(
        {
            "provider": "outlook",
            "target": "study_sessions",
            "status": status,
            "requires_confirmation": status == "awaiting_manual_outlook_decision",
            "last_error": None,
        }
    )
    if preview is not None:
        payload["preview"] = dict(preview)
    if result is not None:
        payload["result"] = dict(result)
    rules["external_sync"] = payload
    rules["external_sync_status"] = status
    rules["external_sync_requires_confirmation"] = status == "awaiting_manual_outlook_decision"
    return {"study_plan": update_study_plan_state(normalized.model_copy(update={"rules": rules}))}


def _block_from_persisted_record(record: object):
    from services.scheduling.models import WeeklyScheduleBlock
    return WeeklyScheduleBlock(
        block_id=str(getattr(record, "source_block_id", "")),
        block_type=str(getattr(record, "block_type", "academic")),
        title=str(getattr(record, "title", "")),
        day_of_week=str(getattr(record, "day_of_week", "monday")),
        start_time=str(getattr(record, "start_time", "00:00")),
        end_time=str(getattr(record, "end_time", "00:00")),
        frequency=str(getattr(record, "frequency", "weekly")),
        timezone=str(getattr(record, "timezone", "America/Bogota")),
        source_text=str(getattr(record, "source_text", "")),
        is_active=bool(getattr(record, "is_active", True)),
        user_confirmed=bool(getattr(record, "confirmed_by_user", True)),
        has_conflict=bool(getattr(record, "has_conflict", False)),
        conflict_accepted=bool(getattr(record, "conflict_accepted", False)),
        metadata={"persisted_block_id": getattr(record, "id", None)},
    )


def _apply_and_persist_schedule(
    state: AgentState,
    updated_blocks: list,
    success_label: str,
) -> tuple[str, dict]:
    """Persiste cambios al horario fijo y sincroniza con Outlook. Retorna (msg, state_update).

    Siempre retorna un state_update con los bloques actualizados en memoria, incluso si la
    persistencia en DB o la sincronización con Outlook fallan (fallo parcial = advertencia).
    Nunca lanza excepciones — todos los errores se capturan y se incluyen en el mensaje.
    """
    from agents.support.dependencies import (
        get_outlook_fixed_schedule_sync_service,
        get_schedule_service,
    )
    from agents.support.scheduling.conflicts import detect_schedule_conflicts
    from agents.support.scheduling.formatter import build_schedule_summary
    from agents.support.scheduling.state_helpers import (
        ensure_schedule_flow_state,
        update_schedule_flow_state,
    )
    from services.scheduling.block_operations import current_section_blocks
    from services.scheduling.extracurricular_state import build_extracurricular_items_from_blocks
    from services.scheduling.models import ensure_weekly_block
    from services.scheduling.raw_input_sync import sync_schedule_blocks_to_raw_inputs

    # --- 1. Normalizar bloques y detectar conflictos ---
    try:
        schedule_state = ensure_schedule_flow_state(state.schedule)
        normalized = [
            ensure_weekly_block(b).model_copy(update={"user_confirmed": True})
            for b in updated_blocks
        ]
        normalized, conflicts = detect_schedule_conflicts(normalized)
        summary_text = build_schedule_summary(normalized)
    except Exception as exc:
        return f"Error preparando los bloques del horario: {exc}", {}

    student_id = _get_student_id(state)
    profile = state.student_profile
    occupation = str(getattr(profile, "occupation", None) or "")
    tz = str(state.timezone or "America/Bogota")

    sched_end = None
    if schedule_state.schedule_end_date:
        try:
            from datetime import date as _date
            sched_end = _date.fromisoformat(schedule_state.schedule_end_date)
        except ValueError:
            pass

    # --- 2. Persistir en DB (fallo → advertencia, no bloqueo) ---
    persist_note = ""
    schedule_profile_id = getattr(schedule_state, "persisted_profile_id", None)
    new_sched_end_iso = schedule_state.schedule_end_date

    try:
        persist_result = get_schedule_service().persist_schedule(
            student_id=student_id,
            occupation=occupation,
            timezone=tz,
            summary_text=summary_text,
            blocks=normalized,
            conflicts=conflicts,
            conflicts_accepted=bool(schedule_state.conflicts_accepted),
            schedule_end_date=sched_end,
        )
        if persist_result.persisted:
            schedule_profile_id = persist_result.schedule_profile_id
            if getattr(persist_result, "schedule_end_date", None):
                new_sched_end_iso = persist_result.schedule_end_date.isoformat()
        else:
            detail = persist_result.detail or persist_result.error_code or "desconocido"
            persist_note = f" ⚠️ No se guardó en BD: {detail}."
    except Exception as exc:
        persist_note = f" ⚠️ Error al guardar en BD: {exc}."

    # --- 3. Construir schedule_update con los bloques en memoria ---
    try:
        schedule_update = update_schedule_flow_state(
            schedule_state,
            blocks=normalized,
            conflicts=conflicts,
            summary_text=summary_text,
            review_stage="idle",
            persisted_profile_id=schedule_profile_id,
            persistence_error=persist_note.strip() if persist_note else None,
            schedule_end_date=new_sched_end_iso,
        )
        if "blocks" in schedule_update:
            schedule_update["blocks"] = [
                b.model_dump(mode="python") if hasattr(b, "model_dump") else dict(b)
                for b in schedule_update["blocks"]
            ]
        if "conflicts" in schedule_update:
            schedule_update["conflicts"] = [
                c.model_dump(mode="python") if hasattr(c, "model_dump") else dict(c)
                for c in schedule_update["conflicts"]
            ]
    except Exception as exc:
        return f"Error construyendo el estado del horario: {exc}", {}

    # --- 4. Sincronizar con Outlook (fallo → advertencia, no bloqueo) ---
    cal = state.calendar
    base_cal = cal.model_dump(mode="python") if hasattr(cal, "model_dump") else dict(cal)
    cal_dict = dict(base_cal)
    sync_note = ""

    if schedule_profile_id:
        try:
            sync_result = get_outlook_fixed_schedule_sync_service().sync_schedule_profile(
                student_id=student_id,
                schedule_profile_id=schedule_profile_id,
                calendar_state=base_cal,
                calendar_id=base_cal.get("calendar_id"),
            )
            if getattr(sync_result, "synced", False):
                sync_note = " Outlook sincronizado ✅"
                cal_dict = {
                    **base_cal,
                    "provider": "outlook",
                    "authorized": True,
                    "synced_event_map": dict(getattr(sync_result, "synced_event_map", {})),
                }
            else:
                err = getattr(sync_result, "detail", None) or getattr(sync_result, "error_code", None) or "desconocido"
                sync_note = f" ⚠️ Outlook no sincronizado: {err}."
                cal_dict = {**base_cal, "synced_event_map": dict(getattr(sync_result, "synced_event_map", {}))}
        except Exception as exc:
            sync_note = f" ⚠️ Error Outlook: {exc}."
    else:
        sync_note = " ⚠️ Outlook no sincronizado (horario no persistido en BD)."

    # --- 5. Efectos secundarios: raw_inputs y extracurriculares ---
    try:
        raw_inputs = sync_schedule_blocks_to_raw_inputs(
            state.raw_inputs, "academic", current_section_blocks(normalized, "academic")
        )
        raw_inputs = sync_schedule_blocks_to_raw_inputs(
            raw_inputs, "work", current_section_blocks(normalized, "work")
        )
        extracurricular = build_extracurricular_items_from_blocks(
            current_section_blocks(normalized, "extracurricular")
        )
        raw_inputs_dict = raw_inputs.model_dump(mode="python") if hasattr(raw_inputs, "model_dump") else dict(raw_inputs)
        extracurricular_list = [
            e.model_dump(mode="python") if hasattr(e, "model_dump") else dict(e)
            for e in extracurricular
        ]
    except Exception:
        raw_inputs_src = state.raw_inputs
        raw_inputs_dict = raw_inputs_src.model_dump(mode="python") if hasattr(raw_inputs_src, "model_dump") else {}
        extracurricular_list = [
            e.model_dump(mode="python") if hasattr(e, "model_dump") else dict(e)
            for e in list(state.extracurricular or [])
        ]

    state_update: dict[str, Any] = {
        "schedule": schedule_update,
        "calendar": cal_dict,
        "raw_inputs": raw_inputs_dict,
        "extracurricular": extracurricular_list,
    }

    # --- 6. Activar replan si hay plan de estudio vigente ---
    plan_events = list(state.study_plan.plan_events or [])
    if plan_events and schedule_profile_id:
        state_update["replan"] = {
            "trigger": "fixed_schedule_change",
            "status": "pending",
            "change_request": {
                "trigger": "fixed_schedule_change",
                "source": "schedule_tools",
                "operation": "schedule_change",
                "schedule_profile_id": schedule_profile_id,
                "reason": f"Horario {success_label}",
            },
        }

    return f"Horario {success_label}.{persist_note}{sync_note}", state_update


def _normalize_time(t: str) -> str:
    """Normaliza hora a HH:MM. Acepta '9', '9:00', '09:00', '9.00', '9h'."""
    raw = str(t or "").strip().replace(".", ":").replace(" ", "").rstrip("h")
    if ":" not in raw:
        try:
            return f"{int(raw):02d}:00"
        except ValueError:
            return raw
    parts = raw.split(":")
    try:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except (ValueError, IndexError):
        return raw


def _normalize_schedule_block_type(block_type: str | None) -> str:
    from services.scheduling.activity_matching import normalize_text

    key = normalize_text(str(block_type or "academic"))
    key = re.sub(r"[^a-z]+", " ", key).strip()
    key = re.sub(r"\s+", " ", key)
    normalized = _SCHEDULE_BLOCK_TYPE_ALIASES.get(key)
    if normalized:
        return normalized
    raise ValueError(
        f"Tipo inválido: '{block_type}'. Acepta: academic/academico, work/laboral o extracurricular."
    )


def _normalize_schedule_tool_title(title: str | None, block_type: str) -> str:
    if block_type == "work":
        return "Trabajo"
    return re.sub(r"\s+", " ", str(title or "")).strip()


def _build_schedule_add_parser_text(
    *,
    title: str | None,
    day: str | None,
    start_time: str | None,
    end_time: str | None,
    block_type: str,
) -> str:
    title_text = _normalize_schedule_tool_title(title, block_type)
    return " ".join(
        part
        for part in (
            title_text,
            _coerce_day_text_for_schedule_parser(day),
            _build_schedule_time_range_text(start_time, end_time),
        )
        if part
    ).strip()


def _build_schedule_time_range_text(
    start_time: str | None,
    end_time: str | None,
) -> str:
    start = str(start_time or "").strip()
    end = str(end_time or "").strip()
    if start and end:
        return f"{start} a {end}"
    return start or end


def _coerce_day_text_for_schedule_parser(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\bto\b", "a", text, flags=re.IGNORECASE)
    text = re.sub(r"\band\b", "y", text, flags=re.IGNORECASE)
    for english_day, spanish_day in _WEEKDAY_LABELS_FOR_PARSER.items():
        text = re.sub(
            rf"\b{re.escape(english_day)}\b",
            spanish_day,
            text,
            flags=re.IGNORECASE,
        )
    return normalize_day_typos_in_text(text)


def _build_schedule_update_replacements_from_tool_args(
    target: Any,
    *,
    day: str | None,
    start_time: str | None,
    end_time: str | None,
    timezone: str,
    build_preview: Any,
) -> list[Any] | str:
    has_day = bool(str(day or "").strip())
    has_start = bool(str(start_time or "").strip())
    has_end = bool(str(end_time or "").strip())
    if not has_day and not has_start and not has_end:
        return []

    if has_day and has_start != has_end:
        missing = "hora de fin" if has_start else "hora de inicio"
        return f"Indica también la {missing} para cambiar el día y horario del bloque."

    day_text = _coerce_day_text_for_schedule_parser(day)
    if has_day and (has_start and has_end or _contains_schedule_time_range(day_text)):
        schedule_text = " ".join(
            part
            for part in (
                day_text,
                _build_schedule_time_range_text(start_time, end_time),
            )
            if part
        ).strip()
        preview = build_preview(target, schedule_text, timezone=timezone)
        if preview.prompt:
            return preview.prompt
        if not preview.replacement_blocks:
            return "No pude interpretar el nuevo horario del bloque."
        return [
            _prepare_schedule_tool_block(block, timezone=timezone)
            for block in preview.replacement_blocks
        ]

    if has_day:
        weekdays = _extract_weekdays_for_schedule_tool(day_text)
        if not weekdays:
            return "Indica el día exacto del nuevo horario."
        from services.scheduling.models import new_block_id

        return [
            _prepare_schedule_tool_block(
                target.model_copy(
                    update={
                        "block_id": target.block_id if index == 0 else new_block_id(),
                        "day_of_week": weekday,
                        "timezone": timezone,
                    }
                ),
                timezone=timezone,
            )
            for index, weekday in enumerate(weekdays)
        ]

    updates: dict[str, str] = {}
    if has_start:
        updates["start_time"] = _normalize_schedule_tool_time(start_time)
    if has_end:
        updates["end_time"] = _normalize_schedule_tool_time(end_time)
    return [
        _prepare_schedule_tool_block(
            target.model_copy(update=updates),
            timezone=timezone,
        )
    ]


def _contains_schedule_time_range(text: str | None) -> bool:
    return bool(
        re.search(
            r"\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?"
            r"\s*(?:-|a|hasta)\s*"
            r"\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
            str(text or ""),
            re.IGNORECASE,
        )
    )


def _extract_weekdays_for_schedule_tool(day_text: str) -> list[str]:
    from services.scheduling.text_parser import extract_natural_schedule_components

    try:
        parsed = extract_natural_schedule_components(f"{day_text} 00:00-01:00")
    except ValueError:
        return []
    weekdays: list[str] = []
    for spanish_day in list(parsed.get("days") or []):
        weekday = SPANISH_TO_ENGLISH.get(str(spanish_day))
        if weekday and weekday not in weekdays:
            weekdays.append(weekday)
    return weekdays


def _prepare_schedule_tool_block(
    block: Any,
    *,
    title: str | None = None,
    block_type: str | None = None,
    timezone: str,
) -> Any:
    from services.scheduling.models import ensure_weekly_block

    base = ensure_weekly_block(block)
    normalized_type = _normalize_schedule_block_type(block_type or base.block_type)
    normalized_title = _normalize_schedule_tool_title(title or base.title, normalized_type)
    if not normalized_title:
        raise ValueError("Indica el nombre del bloque.")

    weekday = _normalize_schedule_weekday(base.day_of_week)
    start = _normalize_schedule_tool_time(base.start_time)
    end = _normalize_schedule_tool_time(base.end_time)
    if _time_to_minutes(start) >= _time_to_minutes(end):
        raise ValueError(
            "La hora de inicio debe ser anterior a la hora de fin. "
            "Si el bloque cruza medianoche, divídelo en dos bloques."
        )

    return base.model_copy(
        update={
            "block_type": normalized_type,
            "title": normalized_title,
            "day_of_week": weekday,
            "start_time": start,
            "end_time": end,
            "timezone": timezone or base.timezone,
            "source_text": _build_schedule_block_source_text(
                normalized_type,
                title=normalized_title,
                day_of_week=weekday,
                start_time=start,
                end_time=end,
            ),
            "user_confirmed": True,
            "has_conflict": False,
            "conflict_accepted": False,
        }
    )


def _normalize_schedule_weekday(day: str | None) -> str:
    raw = str(day or "").strip()
    if not raw:
        raise ValueError("Indica el día exacto del nuevo horario.")
    lowered = raw.lower()
    if lowered in _DAYS_ORDER:
        return lowered
    spanish_day = normalize_day(normalize_day_typos_in_text(raw))
    weekday = SPANISH_TO_ENGLISH.get(spanish_day)
    if not weekday:
        raise ValueError(f"Día inválido: '{day}'.")
    return weekday


def _normalize_schedule_tool_time(value: str | None) -> str:
    from services.scheduling.text_parser._common import normalize_parser_text, strip_seconds

    raw = normalize_parser_text(str(value or "")).strip().lower()
    raw = re.sub(r"\s+", "", raw).rstrip("h")
    if "." in raw and not re.search(r"[ap]\.?m\.?$", raw):
        raw = raw.replace(".", ":")
    raw = strip_seconds(raw)
    return normalize_schedule_time(raw)


def _build_schedule_block_source_text(
    block_type: str,
    *,
    title: str,
    day_of_week: str,
    start_time: str,
    end_time: str,
) -> str:
    day_label = _DAYS_ES.get(day_of_week, day_of_week)
    if block_type == "work":
        return f"{day_label} {start_time}-{end_time}"
    return f"{day_label} {start_time}-{end_time} {title}".strip()


def _normalize_unavailable_windows(windows: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    normalized: list[dict[str, str | None]] = []
    for raw_window in list(windows or []):
        if not isinstance(raw_window, dict):
            continue
        raw_days = raw_window.get("days", raw_window.get("day", raw_window.get("day_of_week")))
        days = _normalize_unavailable_days(raw_days)
        if not days:
            continue
        try:
            start_time = _normalize_time(str(raw_window.get("start_time") or raw_window.get("start") or ""))
            end_time = _normalize_time(str(raw_window.get("end_time") or raw_window.get("end") or ""))
            _validate_time_range(start_time, end_time)
        except ValueError:
            continue
        reason = str(raw_window.get("reason") or "no disponible").strip() or "no disponible"
        for day in days:
            normalized.append(
                {
                    "day": day,
                    "start_time": start_time,
                    "end_time": end_time,
                    "reason": reason,
                }
            )
    return normalized


def _normalize_unavailable_days(value: Any) -> list[str]:
    if isinstance(value, str):
        range_days = _expand_spanish_day_range(value)
        raw_values = range_days if range_days else [value]
    elif isinstance(value, list):
        raw_values = list(value)
    else:
        raw_values = []

    days: list[str] = []
    for raw_day in raw_values:
        day = _normalize_unavailable_day(raw_day)
        if day and day not in days:
            days.append(day)
    return days


def _normalize_unavailable_day(value: Any) -> str | None:
    raw = str(value or "").strip()
    if raw in _DAYS_ORDER:
        return raw
    try:
        spanish = normalize_day(raw)
    except ValueError:
        return None
    return SPANISH_TO_ENGLISH.get(spanish)


def _expand_spanish_day_range(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    separators = (" a ", " hasta ", "-")
    for separator in separators:
        if separator not in raw.lower():
            continue
        parts = raw.lower().split(separator, maxsplit=1)
        if len(parts) != 2:
            continue
        start = _normalize_unavailable_day(parts[0])
        end = _normalize_unavailable_day(parts[1])
        if start not in _DAYS_ORDER or end not in _DAYS_ORDER:
            continue
        start_index = _DAYS_ORDER.index(start)
        end_index = _DAYS_ORDER.index(end)
        if start_index <= end_index:
            return _DAYS_ORDER[start_index:end_index + 1]
        return _DAYS_ORDER[start_index:] + _DAYS_ORDER[:end_index + 1]
    return []


def _validate_time_range(start_time: str, end_time: str) -> None:
    start = _time_to_minutes(start_time)
    end = _time_to_minutes(end_time)
    if start == end:
        raise ValueError("empty unavailable window")


def _time_to_minutes(value: str) -> int:
    hour, minute = str(value or "").split(":", maxsplit=1)
    hour_int = int(hour)
    minute_int = int(minute)
    if not (0 <= hour_int <= 23 and 0 <= minute_int <= 59):
        raise ValueError(f"invalid time: {value!r}")
    return hour_int * 60 + minute_int


def _window_to_dict(window: Any) -> dict[str, str | None]:
    if isinstance(window, dict):
        return {
            "day": str(window.get("day") or ""),
            "start_time": str(window.get("start_time") or ""),
            "end_time": str(window.get("end_time") or ""),
            "reason": str(window.get("reason") or "") or None,
        }
    return {
        "day": str(getattr(window, "day", "") or ""),
        "start_time": str(getattr(window, "start_time", "") or ""),
        "end_time": str(getattr(window, "end_time", "") or ""),
        "reason": str(getattr(window, "reason", "") or "") or None,
    }


def _dedupe_unavailable_windows(windows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    deduped: list[dict[str, str | None]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for window in windows:
        key = (
            str(window.get("day") or ""),
            str(window.get("start_time") or ""),
            str(window.get("end_time") or ""),
            str(window.get("reason") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(window)
    return deduped


def _match_study_sessions(
    plan_events: list,
    *,
    session_reference: str,
    source_day: str | None = None,
) -> list:
    study_events = [
        event
        for event in list(plan_events or [])
        if getattr(event, "categoria", None) == "estudio"
    ]
    if not study_events:
        return []

    reference = str(session_reference or "").strip()
    source_day_label = (
        _normalize_event_day(source_day)
        if source_day
        else _infer_event_day_from_reference(reference)
    )
    if source_day_label:
        study_events = [event for event in study_events if getattr(event, "dia", "") == source_day_label]

    reference_key = _normalize_text_key(reference)
    if not reference_key or reference_key in {"esa", "estasesion", "esasesion", "sesion", "lasesion"}:
        return study_events if len(study_events) == 1 else []

    if reference_key.isdigit():
        index = int(reference_key) - 1
        return [study_events[index]] if 0 <= index < len(study_events) else []

    matches = []
    for event in study_events:
        title_key = _normalize_text_key(getattr(event, "titulo", ""))
        event_id_key = _normalize_text_key(getattr(event, "id", ""))
        subject_key = _normalize_text_key(_session_subject(event))
        if (
            reference_key == event_id_key
            or reference_key in title_key
            or title_key in reference_key
            or (subject_key and (reference_key in subject_key or subject_key in reference_key))
        ):
            matches.append(event)
    return matches


def _format_ambiguous_study_sessions(events: list) -> str:
    lines = ["Encontré varias sesiones de estudio. Indícame cuál quieres mover:"]
    for index, event in enumerate(events, start=1):
        lines.append(
            f"{index}. {event.titulo} — {event.dia} de {event.inicio} a {event.fin}"
        )
    return "\n".join(lines)


def _normalize_event_day(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("day value is required")
    if raw in _WEEKDAY_BY_EVENT_DAY:
        return raw
    if raw.lower() in _EVENT_DAY_BY_WEEKDAY:
        return _EVENT_DAY_BY_WEEKDAY[raw.lower()]
    return normalize_day(raw)


def _infer_event_day_from_reference(value: str) -> str | None:
    key = _normalize_text_key(value)
    aliases = {
        "lunes": "Lunes",
        "monday": "Lunes",
        "martes": "Martes",
        "tuesday": "Martes",
        "miercoles": "Miercoles",
        "wednesday": "Miercoles",
        "jueves": "Jueves",
        "thursday": "Jueves",
        "viernes": "Viernes",
        "friday": "Viernes",
        "sabado": "Sabado",
        "saturday": "Sabado",
        "domingo": "Domingo",
        "sunday": "Domingo",
    }
    for alias, day in aliases.items():
        if alias in key:
            return day
    return None


def _normalize_move_time(value: str | None) -> str:
    return normalize_schedule_time(str(value or ""))


def _event_duration_minutes(event) -> int:
    return _time_to_minutes(event.fin) - _time_to_minutes(event.inicio)


def _resolve_after_event_slot(
    state: AgentState,
    target_event,
    *,
    after_event_reference: str,
    target_day: str | None,
) -> tuple[str, str] | None:
    candidates = _matching_fixed_blocks_after_reference(
        state,
        target_event,
        after_event_reference=after_event_reference,
        target_day=target_day,
    )
    if not candidates:
        return None
    block = candidates[0]
    day = _EVENT_DAY_BY_WEEKDAY.get(getattr(block, "day_of_week", ""), "")
    if not day:
        return None
    return day, str(getattr(block, "end_time", ""))


def _matching_fixed_blocks_after_reference(
    state: AgentState,
    target_event,
    *,
    after_event_reference: str,
    target_day: str | None,
) -> list:
    reference_key = _normalize_text_key(after_event_reference)
    subject_key = _normalize_text_key(_session_subject(target_event))
    generic_reference = reference_key in {
        "",
        "clase",
        "clases",
        "despuesdeclase",
        "despuesdemiclase",
        "despuesdelaclase",
    }
    blocks = []
    for raw_block in list(state.schedule.blocks or []):
        if not getattr(raw_block, "is_active", True):
            continue
        if target_day and _EVENT_DAY_BY_WEEKDAY.get(getattr(raw_block, "day_of_week", "")) != target_day:
            continue
        block_type = str(getattr(raw_block, "block_type", "") or "")
        title_key = _normalize_text_key(getattr(raw_block, "title", ""))
        if generic_reference:
            if block_type == "academic" and subject_key and subject_key in title_key:
                blocks.append(raw_block)
            continue
        if block_type == "academic" and subject_key and subject_key in reference_key and subject_key in title_key:
            blocks.append(raw_block)
            continue
        if reference_key in title_key or title_key in reference_key:
            blocks.append(raw_block)
    if not blocks and generic_reference:
        blocks = [
            block
            for block in list(state.schedule.blocks or [])
            if getattr(block, "is_active", True)
            and str(getattr(block, "block_type", "") or "") == "academic"
            and (not target_day or _EVENT_DAY_BY_WEEKDAY.get(getattr(block, "day_of_week", "")) == target_day)
        ]
    return sorted(
        blocks,
        key=lambda block: (
            _DAYS_ORDER.index(getattr(block, "day_of_week", "monday"))
            if getattr(block, "day_of_week", "") in _DAYS_ORDER
            else len(_DAYS_ORDER),
            str(getattr(block, "end_time", "")),
        ),
    )


def _study_session_slot_availability(
    state: AgentState,
    target_event,
    *,
    day: str,
    start_time: str,
    end_time: str,
) -> tuple[bool, str]:
    start = _time_to_minutes(start_time)
    end = _time_to_minutes(end_time)
    if start >= end:
        return False, "la hora de inicio debe ser anterior a la hora de fin"

    allowed_windows = _allowed_study_windows_for_day(state.constraints, day)
    if not any(start >= window_start and end <= window_end for window_start, window_end in allowed_windows):
        return False, "queda fuera de tus límites de estudio o descanso"

    busy = _busy_intervals_for_move(state, exclude_event_id=getattr(target_event, "id", None)).get(day, [])
    for busy_start, busy_end, label in busy:
        if start < busy_end and end > busy_start:
            return False, f"se cruza con {label}"
    return True, ""


def _suggest_study_session_slots(
    state: AgentState,
    target_event,
    *,
    preferred_day: str | None = None,
    limit: int = 4,
) -> list[tuple[str, str, str]]:
    duration = _event_duration_minutes(target_event)
    if duration <= 0:
        return []
    day_order = list(_WEEKDAY_BY_EVENT_DAY.keys())
    if preferred_day in day_order:
        day_order = [preferred_day] + [day for day in day_order if day != preferred_day]
    busy_by_day = _busy_intervals_for_move(state, exclude_event_id=getattr(target_event, "id", None))
    alternatives: list[tuple[str, str, str]] = []
    for day in day_order:
        free_windows = list(_allowed_study_windows_for_day(state.constraints, day))
        for busy_start, busy_end, _label in busy_by_day.get(day, []):
            free_windows = _subtract_move_interval_list(free_windows, (busy_start, busy_end))
        for window_start, window_end in free_windows:
            cursor = _round_up_to_step(window_start, 15)
            while cursor + duration <= window_end:
                start = _minutes_to_hhmm(cursor)
                end = _minutes_to_hhmm(cursor + duration)
                if not (day == getattr(target_event, "dia", "") and start == target_event.inicio):
                    alternatives.append((day, start, end))
                    if len(alternatives) >= limit:
                        return alternatives
                cursor += 15
    return alternatives


def _format_alternatives(alternatives: list[tuple[str, str, str]]) -> str:
    if not alternatives:
        return "No encontré alternativas con la disponibilidad actual."
    lines = ["Alternativas disponibles:"]
    for index, (day, start, end) in enumerate(alternatives, start=1):
        lines.append(f"{index}. {day} de {start} a {end}")
    return "\n".join(lines)


def _busy_intervals_for_move(
    state: AgentState,
    *,
    exclude_event_id: str | None,
) -> dict[str, list[tuple[int, int, str]]]:
    busy: dict[str, list[tuple[int, int, str]]] = {day: [] for day in _WEEKDAY_BY_EVENT_DAY}
    for block in list(state.schedule.blocks or []):
        if not getattr(block, "is_active", True):
            continue
        day = _EVENT_DAY_BY_WEEKDAY.get(getattr(block, "day_of_week", ""))
        if not day:
            continue
        busy[day].append(
            (
                _time_to_minutes(str(getattr(block, "start_time", ""))),
                _time_to_minutes(str(getattr(block, "end_time", ""))),
                f"{getattr(block, 'title', 'bloque fijo')} [{getattr(block, 'block_type', 'horario')}]",
            )
        )

    for event in list(state.study_plan.plan_events or []):
        if getattr(event, "id", None) == exclude_event_id:
            continue
        if getattr(event, "categoria", None) != "estudio":
            continue
        day = _normalize_event_day(getattr(event, "dia", ""))
        busy.setdefault(day, []).append(
            (
                _time_to_minutes(event.inicio),
                _time_to_minutes(event.fin),
                getattr(event, "titulo", "otra sesión de estudio"),
            )
        )

    for event in list(state.events or []):
        if getattr(event, "categoria", None) == "estudio":
            continue
        try:
            day = _normalize_event_day(getattr(event, "dia", ""))
            busy.setdefault(day, []).append(
                (
                    _time_to_minutes(event.inicio),
                    _time_to_minutes(event.fin),
                    getattr(event, "titulo", "evento del horario"),
                )
            )
        except Exception:
            continue

    for day, start, end, reason in _constraint_unavailable_intervals(state.constraints):
        busy.setdefault(day, []).append((start, end, reason or "franja no disponible"))

    return {
        day: sorted(intervals, key=lambda item: (item[0], item[1], item[2]))
        for day, intervals in busy.items()
    }


def _allowed_study_windows_for_day(constraints, day: str) -> list[tuple[int, int]]:
    try:
        windows = _awake_move_windows(
            sleep_start=str(constraints.sleep_start),
            sleep_end=str(constraints.sleep_end),
        )
    except Exception:
        windows = [(0, 24 * 60)]

    pref_start = getattr(constraints, "preferred_study_start", None)
    pref_end = getattr(constraints, "preferred_study_end", None)
    if pref_start and pref_end:
        try:
            pref = (_time_to_minutes(pref_start), _time_to_minutes(pref_end))
        except ValueError:
            pref = None
        if pref and pref[0] < pref[1]:
            preferred = _intersect_move_intervals(windows, [pref])
            if preferred:
                windows = preferred
    return windows


def _awake_move_windows(*, sleep_start: str, sleep_end: str) -> list[tuple[int, int]]:
    start = _time_to_minutes(sleep_start)
    end = _time_to_minutes(sleep_end)
    if start == end:
        return [(0, 24 * 60)]
    if start < end:
        return _merge_move_intervals([(0, start), (end, 24 * 60)])
    return [(end, start)]


def _constraint_unavailable_intervals(constraints) -> list[tuple[str, int, int, str]]:
    intervals: list[tuple[str, int, int, str]] = []
    windows = list(getattr(constraints, "unavailable_windows", []) or [])
    for raw_window in windows:
        window = _window_to_dict(raw_window)
        day_key = _normalize_unavailable_day(window.get("day"))
        if not day_key:
            continue
        day = _EVENT_DAY_BY_WEEKDAY[day_key]
        try:
            start = _time_to_minutes(str(window.get("start_time") or ""))
            end = _time_to_minutes(str(window.get("end_time") or ""))
        except ValueError:
            continue
        reason = str(window.get("reason") or "franja no disponible")
        if start == end:
            continue
        if start < end:
            intervals.append((day, start, end, reason))
            continue
        intervals.append((day, start, 24 * 60, reason))
        next_day_key = _DAYS_ORDER[(_DAYS_ORDER.index(day_key) + 1) % len(_DAYS_ORDER)]
        intervals.append((_EVENT_DAY_BY_WEEKDAY[next_day_key], 0, end, reason))
    return intervals


def _session_subject(event) -> str:
    title = str(getattr(event, "titulo", "") or "")
    if "·" in title:
        return title.split("·", maxsplit=1)[1].strip()
    lowered = title.lower()
    for prefix in ("sesión de estudio", "sesion de estudio", "estudio", "repaso", "bloque"):
        if lowered.startswith(prefix):
            return title[len(prefix):].strip(" :-")
    return title


def _subtract_move_interval_list(
    windows: list[tuple[int, int]],
    busy_interval: tuple[int, int],
) -> list[tuple[int, int]]:
    busy_start, busy_end = busy_interval
    remaining: list[tuple[int, int]] = []
    for window_start, window_end in windows:
        if busy_end <= window_start or busy_start >= window_end:
            remaining.append((window_start, window_end))
            continue
        if busy_start > window_start:
            remaining.append((window_start, busy_start))
        if busy_end < window_end:
            remaining.append((busy_end, window_end))
    return _merge_move_intervals(remaining)


def _intersect_move_intervals(
    a: list[tuple[int, int]],
    b: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for a_start, a_end in a:
        for b_start, b_end in b:
            start = max(a_start, b_start)
            end = min(a_end, b_end)
            if start < end:
                result.append((start, end))
    return _merge_move_intervals(result)


def _merge_move_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    clean = sorted(
        [(start, end) for start, end in intervals if end > start],
        key=lambda item: (item[0], item[1]),
    )
    if not clean:
        return []
    merged = [clean[0]]
    for start, end in clean[1:]:
        current_start, current_end = merged[-1]
        if start <= current_end:
            merged[-1] = (current_start, max(current_end, end))
            continue
        merged.append((start, end))
    return merged


def _round_up_to_step(value: int, step: int) -> int:
    remainder = value % step
    return value if remainder == 0 else value + (step - remainder)


def _day_str_to_weekday(day_str: str) -> int | None:
    """Convierte nombre de día (español title-case o inglés) a weekday number (lunes=0)."""
    _MAP = {
        "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
        "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    return _MAP.get(str(day_str or "").strip().lower())


def _resolve_target_date_from_text(text: str, session_day: str, timezone_name: str) -> date | None:
    """Resuelve texto de fecha (ISO, día, 'esta semana', etc.) a una fecha concreta.

    session_day: día del evento en español title-case o inglés (ej. 'Martes', 'tuesday').
    Retorna None si no se puede resolver.
    """
    from zoneinfo import ZoneInfo

    text_norm = str(text or "").strip()
    if not text_norm:
        return None

    # 1. ISO date YYYY-MM-DD
    try:
        return date.fromisoformat(text_norm.replace(" ", ""))
    except ValueError:
        pass

    # 2. Today en timezone del estudiante
    try:
        zone = ZoneInfo(str(timezone_name or "America/Bogota"))
    except Exception:
        zone = ZoneInfo("America/Bogota")
    today = datetime.now(zone).date()

    key = text_norm.lower()

    # 3. Detectar semana siguiente
    next_week = any(kw in key for kw in ("próxima", "proxima", "que viene", "siguiente", "next week"))

    # 4. Detectar día mencionado en el texto, fallback al día de la sesión
    _ALIASES: dict[str, int] = {
        "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
        "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    detected_wd: int | None = None
    for alias, wd in _ALIASES.items():
        if alias in key:
            detected_wd = wd
            break
    if detected_wd is None:
        detected_wd = _day_str_to_weekday(session_day)
    if detected_wd is None:
        return None

    # 5. Calcular la fecha correspondiente dentro de la semana actual (o siguiente)
    current_monday = today - timedelta(days=today.weekday())
    candidate = current_monday + timedelta(days=detected_wd)
    if next_week:
        candidate += timedelta(days=7)
    return candidate


def _minutes_to_hhmm(value: int) -> str:
    hour = value // 60
    minute = value % 60
    return f"{hour:02d}:{minute:02d}"


def _format_pending_activity_line(activity: Any, *, today: date, due: date | None) -> str:
    due_str = ""
    if due is not None:
        delta = (due - today).days
        if delta < 0:
            due_str = f" — venció hace {abs(delta)} día(s), el {due.isoformat()}"
        elif delta == 0:
            due_str = f" — vence hoy, {due.isoformat()}"
        elif delta == 1:
            due_str = f" — vence mañana, {due.isoformat()}"
        else:
            due_str = f" — vence {due.isoformat()} (faltan {delta} días)"
    elif getattr(activity, "due_date", None):
        due_str = f" — vence {activity.due_date}"
    pri_str = f" [{activity.priority_level}]" if getattr(activity, "priority_level", None) else ""
    title = getattr(activity, "activity_title", None) or getattr(activity, "activity_type", "actividad")
    return f"  • [{activity.activity_type}] {activity.subject_name}: {title}{due_str}{pri_str}"


def _validate_academic_activity_tool_input(
    state: AgentState,
    *,
    subject: str,
    activity_type: str,
    title: str,
) -> str | None:
    valid_types = {
        "parcial",
        "quiz",
        "tarea",
        "taller",
        "entrega",
        "exposicion",
        "proyecto",
        "estudio_pendiente",
    }
    normalized_type = _normalize_text_key(activity_type)
    if normalized_type not in valid_types:
        return (
            f"Tipo de actividad inválido: '{activity_type}'. "
            "Usa parcial, quiz, tarea, taller, entrega, exposicion o proyecto."
        )

    if _looks_like_non_academic_activity(state, subject=subject, title=title):
        return (
            "Esto parece una actividad laboral o extracurricular, no una actividad académica puntual. "
            "Para trabajo, hobbies o extracurriculares usa add_schedule_block con block_type='work' "
            "o block_type='extracurricular'. No la sincronices con Microsoft To Do ni generes sesiones de estudio."
        )
    return None


def _looks_like_non_academic_activity(
    state: AgentState,
    *,
    subject: str,
    title: str,
) -> bool:
    subject_key = _normalize_text_key(subject)
    if subject_key and subject_key in _known_academic_subject_keys(state):
        return False

    combined = _normalize_text_key(f"{subject} {title}")
    if not combined:
        return False

    work_markers = {
        "trabajo",
        "laboral",
        "turno",
        "oficina",
        "empleo",
        "empresa",
        "jornada",
        "practica laboral",
    }
    extracurricular_markers = {
        "extracurricular",
        "gimnasio",
        "gym",
        "deporte",
        "entrenamiento",
        "futbol",
        "crochet",
        "hobby",
        "musica",
    }
    academic_markers = {
        "parcial",
        "quiz",
        "tarea",
        "taller",
        "entrega",
        "exposicion",
        "proyecto",
        "materia",
        "clase",
        "curso",
        "universidad",
    }

    has_non_academic_marker = any(marker in combined for marker in work_markers | extracurricular_markers)
    has_explicit_academic_marker = any(marker in combined for marker in academic_markers)
    return bool(has_non_academic_marker and not has_explicit_academic_marker)


def _known_academic_subject_keys(state: AgentState) -> set[str]:
    keys = {
        _normalize_text_key(getattr(subject, "nombre", ""))
        for subject in list(state.subjects or [])
        if _normalize_text_key(getattr(subject, "nombre", ""))
    }
    for block in list(state.schedule.blocks or []):
        block_type = getattr(block, "block_type", "")
        title = getattr(block, "title", "")
        if block_type == "academic" and str(title or "").strip():
            keys.add(_normalize_text_key(title))
    return keys


def _normalize_text_key(value: object) -> str:
    import unicodedata

    text = str(value or "").strip().lower()
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(text.split())


def _json_default(obj: Any) -> Any:
    """Serializador JSON fallback para objetos Pydantic, date/datetime, etc."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def extract_tool_state_updates(result: dict) -> dict:
    """Extrae y fusiona los _state_update de todos los ToolMessages del ciclo ReAct.

    Las tools que modifican estado retornan JSON con la clave _state_update.
    Esta función recorre los mensajes del agente, parsea los ToolMessages y
    fusiona los updates (last-write-wins por clave).
    """
    from langchain_core.messages import ToolMessage

    merged: dict = {}
    for msg in result.get("messages", []):
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(data, dict) or "_state_update" not in data:
            continue
        update = data["_state_update"]
        if isinstance(update, dict):
            merged.update(update)
    return merged


def _llm_study_fallback(query: str) -> str | None:
    """Responde con LLM cuando el RAG no tiene fuentes suficientes para la consulta."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from services.ai_runtime import maybe_get_llm

    llm = maybe_get_llm(temperature=0.3)
    if not llm:
        return None
    try:
        response = llm.bind(max_tokens=400).invoke([
            SystemMessage(content=(
                "Eres Lara, asistente académica universitaria. "
                "Explica técnicas y métodos de estudio de forma clara y concisa. "
                "No resuelvas ejercicios ni tareas directamente. "
                "Si la pregunta pide resolver algo concreto, indica al estudiante que consulte a su docente."
            )),
            HumanMessage(content=str(query).strip()),
        ])
        content = getattr(response, "content", "") or ""
        return str(content).strip() or None
    except Exception:
        return None


def _get_student_id(state: AgentState) -> int | None:
    profile = state.student_profile
    if hasattr(profile, "persisted_student_id"):
        return profile.persisted_student_id
    d = profile.model_dump() if hasattr(profile, "model_dump") else {}
    return d.get("persisted_student_id")


def _parse_reconciliation_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        raw = str(value).strip()
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


__all__ = ["extract_tool_state_updates", "make_tools"]
