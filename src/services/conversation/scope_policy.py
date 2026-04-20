"""Politica deterministica de alcance para Lara."""

from __future__ import annotations

from schemas.conversation import InputClassification, ScopeDecision

from .guided_academic_support import (
    is_guided_academic_support_message,
    is_socratic_mode_message,
)
from .input_classifier import classify_input
from .text_normalization import contains_any

_EVALUATION_TERMS = {
    "quiz",
    "quices",
    "parcial",
    "parciales",
    "taller",
    "talleres",
    "tarea",
    "tareas",
    "ejercicio",
    "ejercicios",
    "exposicion",
    "exposiciones",
    "entrega",
    "entregas",
    "trabajo",
    "trabajos",
    "proyecto",
    "proyectos",
    "laboratorio",
    "laboratorios",
    "practica",
    "practicas",
    "presentacion",
    "presentaciones",
    "resumen",
    "resumenes",
    "sintesis",
    "informe",
    "informes",
    "ensayo",
    "ensayos",
}
_FORBIDDEN_SOLUTION_TERMS = {
    "resuelveme",
    "resuelve",
    "resolverme",
    "soluciona",
    "solucionalo",
    "hazme",
    "hacerme",
    "haz el",
    "haz la",
    "redacta",
    "redactame",
    "escribe",
    "escribeme",
    "dame la respuesta",
    "respuesta exacta",
    "respuesta final",
    "para copiar",
    "copiar y pegar",
    "solucion completa",
    "solucionalo",
    "contesta por mi",
    "pasame la respuesta",
    "hagame",
}
_GUIDED_EVALUATION_TERMS = {
    "organizar",
    "planea",
    "planear",
    "planificar",
    "como estudio",
    "como estudiar",
    "ayudame a estudiar",
    "guia",
    "guiame",
    "paso a paso",
    "abordar",
    "descomponer",
    "sin resolver",
}
_ACADEMIC_SCOPE_TERMS = {
    "materia",
    "materias",
    "entrega",
    "entregas",
    "parcial",
    "quiz",
    "quices",
    "horario",
    "clase",
    "clases",
    "actividad",
    "actividades",
    "tarea",
    "tareas",
    "prioridad",
    "priorizar",
    "tecnica",
    "tecnicas",
    "metodo",
    "metodos",
    "estudio",
    "estudiar",
    "repasar",
    "calendario",
    "agenda",
    "outlook",
    "recordatorio",
    "todo",
    "to do",
    "pendientes",
    "semana",
    "cronograma",
}
_PARTIAL_SCOPE_TERMS = {
    "memorizar",
    "formulas",
    "me distraigo",
    "no entiendo",
    "como estudio",
    "como estudiar",
    "metodo",
    "tecnica",
    "tecnicas",
    "exposicion",
}
_REDIRECTABLE_TERMS = {
    "estoy perdido",
    "estoy perdida",
    "perdido",
    "perdida",
    "no se que hacer",
    "tengo demasiadas cosas",
    "tengo muchas cosas",
    "voy muy mal",
    "me fue mal",
    "estoy atrasado",
    "estoy atrasada",
    "no se por donde empezar",
}
_HUMAN_SUPPORT_TERMS = {
    "no quiero vivir",
    "me quiero morir",
    "hacerme dano",
    "hacerme daño",
    "autolesion",
    "suicid",
    "crisis emocional",
    "ataque de panico",
    "salud mental",
    "necesito un psicologo",
    "necesito una psicologa",
    "no se con quien hablar",
}
_GREETING_TOKENS = {
    "hola",
    "buenas",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
    "como estas",
    "como estan",
    "que tal",
    "saludos",
    "hey",
}
_GENERAL_OUT_OF_SCOPE_TERMS = {
    "messi",
    "partido",
    "politica",
    "presidente",
    "noticia",
    "noticias",
    "entretenimiento",
    "chiste",
    "poema",
    "amoroso",
    "amorosa",
    "novia",
    "novio",
    "fitness",
    "rutina de gym",
    "medico",
    "legal",
}

_GREETING_RESPONSE = (
    "¡Hola! Soy Lara, tu asistente academica. "
    "¿En que te puedo ayudar hoy con tus materias, pendientes o plan de estudio?"
)
_REDIRECT_RESPONSE = (
    "Puedo ayudarte a organizar esa carga academica, priorizar tus pendientes "
    "y proponerte una forma de estudio para avanzar paso a paso. Cuentame que "
    "materias, entregas o evaluaciones tienes y lo organizamos."
)
_LIMITED_RESPONSE = (
    "Para ese caso si puedo orientarte. Puedo sugerirte una tecnica de estudio "
    "y ayudarte a aplicarla segun tu tiempo, tu materia y lo que tengas "
    "pendiente esta semana."
)
_EVALUATION_REJECTION_RESPONSE = (
    "No puedo resolver evaluaciones, quices, parciales o tareas por ti. "
    "Si puedo ayudarte a organizarlos, explicarte como estudiarlos paso a paso "
    "o guiarte con preguntas para que tu construyas la respuesta."
)
_GENERAL_REJECTION_RESPONSE = (
    "Eso esta fuera de lo que puedo ayudarte. Soy tu asistente academica. "
    "¿Hay algo de tu semana o tus materias en lo que te pueda apoyar?"
)
_HUMAN_SUPPORT_RESPONSE = (
    "Lo que describes parece requerir apoyo humano directo. Te recomiendo buscar "
    "acompanamiento con un docente, coordinacion academica, bienestar universitario "
    "o una persona de confianza de tu entorno. Desde aqui si puedo ayudarte a "
    "organizar tus pendientes academicos inmediatos para reducir un poco la carga."
)


def decide_scope(
    text: str | None = None,
    *,
    classification: InputClassification | None = None,
    media_types: list[str] | tuple[str, ...] | set[str] | None = None,
    has_prior_context: bool = False,
    recent_messages: list[str] | None = None,
) -> ScopeDecision:
    """Aplica el arbol de decision de alcance definido para Lara."""

    input_classification = classification or classify_input(text, media_types=media_types)
    normalized = input_classification.normalized_text

    if _is_greeting(normalized):
        return _decision(
            input_classification,
            category="in_scope",
            action="normal",
            allowed=True,
            domain="smalltalk_contextual",
            intent="smalltalk_greeting",
            reason="greeting_detected",
            confidence=0.95,
        )

    if _is_human_support_case(normalized):
        return _decision(
            input_classification,
            category="human_support_case",
            action="escalate",
            allowed=False,
            domain="risk_or_wellbeing",
            intent="wellbeing_or_crisis_signal",
            reason="human_support_signal",
            response_text=_HUMAN_SUPPORT_RESPONSE,
            requires_human_support=True,
            confidence=0.94,
        )

    if _is_forbidden_evaluation_solution(normalized):
        return _decision(
            input_classification,
            category="in_scope",
            action="normal",
            allowed=True,
            domain="guided_academic_support",
            intent="request_guided_academic_help",
            reason="evaluation_solution_redirected_to_guided",
            confidence=0.93,
        )

    if contains_any(normalized, _GUIDED_EVALUATION_TERMS) and contains_any(normalized, _EVALUATION_TERMS):
        return _decision(
            input_classification,
            category="in_scope",
            action="normal",
            allowed=True,
            domain="guided_academic_support",
            intent="request_guided_academic_help",
            reason="evaluation_planning_or_guidance",
            confidence=0.88,
        )

    if (
        input_classification.possible_intent
        in {"request_guided_academic_help", "enter_socratic_mode"}
        or is_guided_academic_support_message(normalized)
    ):
        return _decision(
            input_classification,
            category="in_scope",
            action="normal",
            allowed=True,
            domain="guided_academic_support",
            intent=(
                "enter_socratic_mode"
                if input_classification.possible_intent == "enter_socratic_mode"
                or is_socratic_mode_message(normalized)
                else "request_guided_academic_help"
            ),
            reason="guided_academic_support_request",
            confidence=max(input_classification.confidence, 0.82),
        )

    if contains_any(normalized, _REDIRECTABLE_TERMS):
        return _decision(
            input_classification,
            category="redirectable_out_of_scope",
            action="redirect",
            allowed=False,
            domain="out_of_scope",
            intent="redirect_to_academic_planning",
            reason="diffuse_academic_need",
            response_text=_REDIRECT_RESPONSE,
            confidence=0.82,
        )

    if input_classification.possible_intent in {
        "update_student_profile",
        "manage_fixed_schedule",
        "manage_academic_activity",
        "track_study_session",
        "request_replan",
        "sync_study_calendar",
        "sync_study_todo",
        "request_guided_academic_help",
        "enter_socratic_mode",
        "prioritize_academic_work",
        "weekly_planning",
        "calendar_action",
    }:
        return _decision(
            input_classification,
            category="in_scope",
            action="normal",
            allowed=True,
            domain=_domain_from_classification(input_classification),
            intent=input_classification.possible_intent,
            reason="known_academic_intent",
            confidence=max(input_classification.confidence, 0.78),
        )

    if input_classification.possible_intent == "study_method_recommendation":
        return _decision(
            input_classification,
            category="partially_in_scope",
            action="limited",
            allowed=True,
            domain="study_method_recommendation",
            intent="study_method_recommendation",
            reason="study_method_guidance",
            response_text=_LIMITED_RESPONSE,
            confidence=max(input_classification.confidence, 0.78),
        )

    if contains_any(normalized, _GENERAL_OUT_OF_SCOPE_TERMS):
        return _decision(
            input_classification,
            category="hard_out_of_scope",
            action="reject",
            allowed=False,
            domain="out_of_scope",
            intent="general_out_of_scope_request",
            reason="generalist_request",
            response_text=_GENERAL_REJECTION_RESPONSE,
            confidence=0.86,
        )

    if input_classification.input_type in {"sticker_only", "emoji_only"}:
        return _decision(
            input_classification,
            category="redirectable_out_of_scope",
            action="redirect",
            allowed=False,
            domain="smalltalk_contextual",
            intent="noise_or_smalltalk",
            reason="non_actionable_input",
            response_text=_REDIRECT_RESPONSE,
            confidence=0.72,
        )

    if contains_any(normalized, _PARTIAL_SCOPE_TERMS):
        return _decision(
            input_classification,
            category="partially_in_scope",
            action="limited",
            allowed=True,
            domain=_domain_from_classification(input_classification),
            intent=input_classification.possible_intent or "limited_academic_guidance",
            reason="limited_academic_guidance",
            response_text=_LIMITED_RESPONSE,
            confidence=0.78,
        )

    if contains_any(normalized, _ACADEMIC_SCOPE_TERMS) or input_classification.input_type in {
        "image_only",
        "mixed",
        "document",
    }:
        return _decision(
            input_classification,
            category="in_scope",
            action="normal",
            allowed=True,
            domain=_domain_from_classification(input_classification),
            intent=input_classification.possible_intent or "academic_request",
            reason="academic_scope_match",
            confidence=max(input_classification.confidence, 0.76),
        )

    if has_prior_context and _classify_followup_with_llm(recent_messages or [], text or ""):
        return _decision(
            input_classification,
            category="in_scope",
            action="normal",
            allowed=True,
            domain="guided_academic_support",
            intent="followup_in_context",
            reason="followup_with_prior_context",
            confidence=0.75,
        )

    if not normalized:
        return _decision(
            input_classification,
            category="redirectable_out_of_scope",
            action="redirect",
            allowed=False,
            domain="out_of_scope",
            intent="empty_or_non_text_input",
            reason="empty_or_non_actionable_input",
            response_text=_REDIRECT_RESPONSE,
            confidence=0.64,
        )

    return _decision(
        input_classification,
        category="hard_out_of_scope",
        action="reject",
        allowed=False,
        domain="out_of_scope",
        intent="general_out_of_scope_request",
        reason="no_academic_scope_match",
        response_text=_GENERAL_REJECTION_RESPONSE,
        confidence=0.68,
    )


def should_answer_scope_boundary(decision: ScopeDecision) -> bool:
    """Indica si el input debe ir al nodo de politica de alcance."""

    return decision.category in {
        "redirectable_out_of_scope",
        "hard_out_of_scope",
        "human_support_case",
    }


def render_scope_response(decision: ScopeDecision) -> str:
    """Devuelve la respuesta permitida para decisiones no normales."""

    if decision.reason == "greeting_detected":
        return _GREETING_RESPONSE
    if decision.response_text:
        return decision.response_text
    if decision.action == "limited":
        return _LIMITED_RESPONSE
    if decision.action == "redirect":
        return _REDIRECT_RESPONSE
    if decision.action == "escalate":
        return _HUMAN_SUPPORT_RESPONSE
    return _GENERAL_REJECTION_RESPONSE


def _is_greeting(normalized_text: str) -> bool:
    return len(normalized_text.split()) <= 5 and contains_any(normalized_text, _GREETING_TOKENS)


def _classify_followup_with_llm(recent_messages: list[str], text: str) -> bool:
    from integrations.ai._llm_impl import maybe_get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    if not recent_messages or not text.strip():
        return False
    llm = maybe_get_llm(temperature=0.0)
    if not llm:
        return False
    history = "\n".join(f"- {msg[:100]}" for msg in recent_messages[-2:])
    user_prompt = (
        f"Historial reciente:\n{history}\n\n"
        f"Mensaje actual del estudiante:\n{text}\n\n"
        "¿Este mensaje es una continuación o pregunta sobre el tema anterior, "
        "o es un tema completamente nuevo sin relación?"
    )
    try:
        response = llm.bind(max_tokens=5).invoke([
            SystemMessage(content="Eres un clasificador binario. Responde solo: FOLLOWUP o NEW."),
            HumanMessage(content=user_prompt),
        ])
        content = getattr(response, "content", "") or ""
        return str(content).strip().upper().startswith("FOLLOWUP")
    except Exception:
        return False


def _is_human_support_case(normalized_text: str) -> bool:
    if contains_any(normalized_text, _HUMAN_SUPPORT_TERMS):
        return True
    return "desbordado" in normalized_text and "no se con quien hablar" in normalized_text


def _is_forbidden_evaluation_solution(normalized_text: str) -> bool:
    return contains_any(normalized_text, _EVALUATION_TERMS) and contains_any(
        normalized_text,
        _FORBIDDEN_SOLUTION_TERMS,
    )


def _domain_from_classification(classification: InputClassification) -> str:
    if not classification.signals:
        return "guided_academic_support"
    signal = classification.signals[0]
    if signal in {
        "student_profile",
        "schedule_management",
        "activity_management",
        "session_tracking",
        "replanning",
        "calendar_sync",
        "todo_sync",
        "guided_academic_support",
    }:
        return signal
    if signal in {
        "prioritization",
        "study_method_recommendation",
        "weekly_planning",
        "calendar_action",
        "todo_action",
        "request_guided_academic_help",
        "enter_socratic_mode",
        "risk_or_wellbeing",
    }:
        return signal
    return "guided_academic_support"


def _decision(
    classification: InputClassification,
    *,
    category: str,
    action: str,
    allowed: bool,
    domain: str,
    intent: str,
    reason: str,
    response_text: str | None = None,
    requires_human_support: bool = False,
    confidence: float | None = None,
) -> ScopeDecision:
    signals = list(dict.fromkeys([*classification.signals, reason]))
    return ScopeDecision(
        category=category,
        action=action,
        allowed=allowed,
        domain=domain,
        intent=intent,
        confidence=classification.confidence if confidence is None else confidence,
        reason=reason,
        response_text=response_text,
        requires_human_support=requires_human_support,
        classification=classification,
        signals=signals,
    )


__all__ = ["decide_scope", "render_scope_response", "should_answer_scope_boundary"]
