"""Clasificador semantico de intencion basado en LLM para el router de Lara."""

from __future__ import annotations

import json
from dataclasses import dataclass

_INTENTS: dict[str, tuple[str, str]] = {
    # intent: (domain, route_name)
    "smalltalk_greeting":                    ("smalltalk_contextual",       "answer_scope_boundary"),
    "manage_fixed_schedule":                 ("schedule_management",         "manage_fixed_schedule"),
    "view_weekly_agenda":                    ("schedule_management",         "view_weekly_agenda"),
    "request_study_method_recommendation":   ("study_method_recommendation", "answer_study_recommendation"),
    "request_guided_academic_help":          ("guided_academic_support",     "guided_academic_support"),
    "enter_socratic_mode":                   ("guided_academic_support",     "guided_academic_support"),
    "track_study_session":                   ("session_tracking",            "handle_academic_update"),
    "request_replan":                        ("replanning",                  "request_replan"),
    "sync_study_calendar":                   ("calendar_action",             "sync_study_calendar"),
    "sync_study_todo":                       ("todo_action",                 "sync_study_todo"),
    "register_academic_activity":            ("activity_management",         "handle_academic_update"),
    "view_tasks":                            ("activity_management",         "view_tasks"),
    "request_weekly_prioritization":         ("prioritization",              "collect_priorities"),
    "followup_in_context":                   ("guided_academic_support",     "guided_academic_support"),
    "out_of_scope":                          ("out_of_scope",                "answer_scope_boundary"),
}

_INTENT_DESCRIPTIONS = (
    '"smalltalk_greeting": saludo simple sin pregunta academica (hola, buenos dias, como estas)\n'
    '"manage_fixed_schedule": modificar, consultar o gestionar el horario fijo semanal\n'
    '"view_weekly_agenda": ver o consultar la agenda de la semana, que tengo hoy/manana/esta semana\n'
    '"request_study_method_recommendation": pedir tecnica, metodo o estrategia de estudio\n'
    '"request_guided_academic_help": pedir ayuda para entender o preparar una actividad SIN que Lara la resuelva\n'
    '"enter_socratic_mode": pedir guia con preguntas o modo socratico explicito\n'
    '"track_study_session": reportar sesion de estudio completada, no completada o perdida\n'
    '"request_replan": reorganizar o ajustar el plan de estudio\n'
    '"sync_study_calendar": sincronizar el plan de estudio con Outlook Calendar\n'
    '"sync_study_todo": sincronizar pendientes academicos con Microsoft To Do\n'
    '"register_academic_activity": registrar nueva actividad academica (parcial, tarea, quiz, entrega, proyecto)\n'
    '"view_tasks": ver, listar o consultar tareas y actividades academicas pendientes\n'
    '"request_weekly_prioritization": pedir priorizacion o radar de la semana\n'
    '"followup_in_context": pregunta de seguimiento o continuacion del tema anterior\n'
    '"out_of_scope": pregunta completamente ajena al ambito academico'
)

_SYSTEM_PROMPT = (
    "Eres el clasificador de intencion de Lara, asistente academica universitaria.\n"
    "Dado un mensaje del estudiante, determina su intencion principal.\n\n"
    "Intenciones disponibles:\n"
    + _INTENT_DESCRIPTIONS
    + "\n\nResponde SOLO con JSON valido sin texto adicional: "
    '{"intent": "<nombre_exacto>", "confidence": <0.0-1.0>}'
)


@dataclass(frozen=True)
class IntentClassificationResult:
    intent: str
    domain: str
    route_name: str
    confidence: float
    source: str = "llm"


def classify_intent_with_llm(
    text: str,
    *,
    recent_messages: list[str] | None = None,
    active_domain: str | None = None,
    active_intent: str | None = None,
) -> IntentClassificationResult:
    """Clasifica la intencion del mensaje con LLM. Fallback deterministico si falla."""

    from integrations.ai._llm_impl import maybe_get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    if not text or not text.strip():
        return _fallback("empty_text")

    llm = maybe_get_llm(temperature=0.0)
    if not llm:
        return _fallback("no_llm")

    context_parts: list[str] = []
    if recent_messages:
        history = "\n".join(f"  - {msg[:120]}" for msg in recent_messages[-2:])
        context_parts.append(f"Historial reciente:\n{history}")
    if active_domain and active_domain not in {"out_of_scope", ""}:
        context_parts.append(f"Dominio activo: {active_domain}")
    if active_intent:
        context_parts.append(f"Intencion activa: {active_intent}")

    context_block = "\n".join(context_parts)
    user_prompt = (
        f"{context_block}\n\nMensaje actual del estudiante:\n{text.strip()}"
        if context_block
        else f"Mensaje del estudiante:\n{text.strip()}"
    )

    try:
        response = llm.bind(max_tokens=60).invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        raw = getattr(response, "content", "") or ""
        data = json.loads(raw.strip())
        intent = str(data.get("intent", "")).strip()
        confidence = float(data.get("confidence", 0.5))
        if intent not in _INTENTS:
            return _fallback("unknown_intent")
        domain, route_name = _INTENTS[intent]
        return IntentClassificationResult(
            intent=intent,
            domain=domain,
            route_name=route_name,
            confidence=max(0.0, min(1.0, confidence)),
        )
    except Exception:
        return _fallback("llm_error")


def _fallback(reason: str) -> IntentClassificationResult:
    return IntentClassificationResult(
        intent="out_of_scope",
        domain="out_of_scope",
        route_name="answer_scope_boundary",
        confidence=0.4,
        source=f"fallback:{reason}",
    )


__all__ = ["IntentClassificationResult", "classify_intent_with_llm"]
