"""Clasificador semantico de intencion basado en LLM para el router de Lara."""

from __future__ import annotations

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
    "answer_academic_concept_question":       ("guided_academic_support",     "answer_study_recommendation"),
    "followup_in_context":                   ("guided_academic_support",     "guided_academic_support"),
    "out_of_scope":                          ("out_of_scope",                "answer_scope_boundary"),
}

_INTENT_DESCRIPTIONS = (
    '"smalltalk_greeting": saludo simple sin pregunta academica — ej: hola, buenos dias, como estas\n'
    '"manage_fixed_schedule": modificar, consultar o gestionar el horario fijo semanal — ej: cambiar bloque del lunes, agregar clase\n'
    '"view_weekly_agenda": ver la agenda de la semana — ej: que tengo hoy, que hay esta semana, mostrar agenda\n'
    '"request_study_method_recommendation": pedir tecnica, metodo o estrategia de estudio — ej: que tecnica uso para memorizar, como combino pomodoro con cornell\n'
    '"request_guided_academic_help": pedir ayuda para abordar una actividad concreta SIN que se resuelva — ej: ayudame a preparar mi parcial, guiame con mi taller (NO: que es X, NO: explicame X)\n'
    '"enter_socratic_mode": pedir guia con preguntas orientadoras — ej: hazme preguntas para preparar el examen, modo socratico\n'
    '"track_study_session": reportar sesion de estudio — ej: estudie 2 horas, complete la sesion de calculo, no pude estudiar\n'
    '"request_replan": reorganizar o ajustar el plan de estudio — ej: replanifica mi semana, no pude hacer lo de ayer\n'
    '"sync_study_calendar": sincronizar el plan de estudio con Outlook Calendar\n'
    '"sync_study_todo": sincronizar pendientes academicos con Microsoft To Do\n'
    '"register_academic_activity": registrar nueva actividad academica — ej: tengo un parcial el viernes, me pusieron un quiz, hay entrega el lunes\n'
    '"view_tasks": ver tareas y actividades pendientes — ej: cuales son mis tareas, que me falta, mis pendientes\n'
    '"request_weekly_prioritization": pedir priorizacion o radar de la semana — ej: priorizame la semana, que materia es mas urgente\n'
    '"answer_academic_concept_question": preguntar que es un concepto, termino o metodologia — ej: que es una ecuacion diferencial, explicame spaced repetition, para que sirve Python, como funciona un compilador (NO: ayudame a resolver, NO: haceme la tarea)\n'
    '"followup_in_context": continuacion del tema anterior sin nueva intencion — ej: y eso como se aplica, que pasa si no lo hago\n'
    '"out_of_scope": pregunta completamente ajena al ambito academico — ej: quien gano el partido, recomiendame una pelicula, chistes\n'
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
        response = llm.bind(max_tokens=120).invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        raw = getattr(response, "content", "") or ""
        from integrations.ai._llm_impl import _safe_json_value
        data = _safe_json_value(raw.strip())
        if not isinstance(data, dict):
            return _fallback("invalid_json")
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
