"""Apoyo academico guiado y modo socratico controlado."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.ingestion.normalization import slugify_identifier

GUIDED_SUPPORT_DOMAIN = "guided_academic_support"
SOCRATIC_MAX_TURNS = 3


@dataclass(frozen=True)
class GuidedAcademicSupportResult:
    """Resultado conversacional para ayuda academica sin resolver la tarea."""

    detected: bool
    intent: str = "request_guided_academic_help"
    interaction_mode: str = "guided"
    message: str = ""
    slots: dict[str, object] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    pending_payload: dict[str, object] = field(default_factory=dict)
    requires_clarification: bool = False
    requires_follow_up: bool = False
    output_kind: str = "none"
    turn_count: int = 0


def is_guided_academic_support_message(text: str | None) -> bool:
    """Detecta ayuda permitida sobre actividades academicas concretas."""

    normalized = slugify_identifier(str(text or ""))
    if not normalized:
        return False
    if _is_forbidden_solution_request(normalized):
        return False
    return _looks_like_socratic_request(normalized) or (
        _contains_any(normalized, _GUIDED_HELP_TERMS)
        and (
            _detect_activity_type(normalized) is not None
            or _contains_any(normalized, _ACADEMIC_TASK_TERMS)
        )
    )


def is_socratic_mode_message(text: str | None) -> bool:
    """Detecta solicitudes explicitas de modo socratico."""

    normalized = slugify_identifier(str(text or ""))
    return bool(normalized and _looks_like_socratic_request(normalized))


def build_guided_academic_support_result(
    text: str | None,
    *,
    pending_payload: dict[str, object] | None = None,
    study_profile: dict[str, object] | None = None,
) -> GuidedAcademicSupportResult:
    """Construye la siguiente salida permitida del flujo guiado."""

    normalized = slugify_identifier(str(text or ""))
    pending = _valid_pending_payload(pending_payload)
    if not normalized and not pending:
        return GuidedAcademicSupportResult(detected=False)

    is_forbidden = bool(normalized and _is_forbidden_solution_request(normalized))
    intent = _resolve_intent(normalized, pending)
    if not pending and intent is None:
        if not is_forbidden:
            return GuidedAcademicSupportResult(detected=False)
        intent = "request_guided_academic_help"

    dominant_technique = _dominant_technique(study_profile or {}, pending)
    interaction_mode = "socratic" if intent == "enter_socratic_mode" else "guided"
    slots = _merge_slots(dict(pending.get("slots") or {}), _extract_slots(text))
    turn_count = _int_or_zero(pending.get("turn_count"))
    missing = _missing_fields(slots)
    payload = {
        "domain": GUIDED_SUPPORT_DOMAIN,
        "intent": intent or "request_guided_academic_help",
        "interaction_mode": interaction_mode,
        "slots": slots,
        "turn_count": turn_count,
        "dominant_technique": dominant_technique,
    }
    if missing:
        activity_type = str(slots.get("activity_type") or "").strip()
        subject = str(slots.get("subject_name") or "").strip()
        recognition = (
            _build_step1_recognition(activity_type, subject)
            if (activity_type or is_forbidden)
            else ""
        )
        clarification = _missing_prompt(missing, interaction_mode=interaction_mode)
        message = f"{recognition}\n{clarification}".strip() if recognition else clarification
        return GuidedAcademicSupportResult(
            detected=True,
            intent=intent or "request_guided_academic_help",
            interaction_mode=interaction_mode,
            message=message,
            slots=slots,
            missing_fields=missing,
            pending_payload=payload,
            requires_clarification=True,
            output_kind="clarification",
            turn_count=turn_count,
        )

    if interaction_mode == "socratic":
        return _socratic_result(
            slots=slots,
            turn_count=turn_count,
            payload=payload,
            dominant_technique=dominant_technique,
        )
    return _guided_result(
        slots=slots,
        payload=payload,
        dominant_technique=dominant_technique,
        is_first=(turn_count == 0),
    )


_GUIDED_HELP_TERMS = {
    "ayudame",
    "ayuda",
    "guiame",
    "guia",
    "orientame",
    "orientacion",
    "sin_resolver",
    "no_me_lo_resuelvas",
    "no_me_des_la_respuesta",
    "primeros_pasos",
    "por_donde_empiezo",
    "descomponer",
    "checklist",
    "lista_de_pasos",
    "abordar",
}
_SOCRATIC_TERMS = {
    "modo_socratico",
    "socratico",
    "socratica",
    "hazme_preguntas",
    "hacerme_preguntas",
    "preguntas_orientadoras",
    "con_preguntas",
    "guiame_con_preguntas",
}
_ACADEMIC_TASK_TERMS = {
    "actividad",
    "actividades",
    "ejercicio",
    "ejercicios",
    "evaluacion",
    "evaluaciones",
    "universidad",
    "materia",
    "tema",
    "consigna",
}
_ACTIVITY_ALIASES: dict[str, set[str]] = {
    "parcial": {"parcial", "examen", "evaluacion", "final"},
    "quiz": {"quiz", "quices", "control", "prueba_corta"},
    "taller": {"taller", "laboratorio", "practica"},
    "tarea": {"tarea", "deber"},
    "entrega": {"entrega", "trabajo"},
    "exposicion": {"exposicion", "presentacion"},
    "proyecto": {"proyecto"},
    "lectura": {"lectura", "sintesis", "resumen"},
}
_FORBIDDEN_ACTION_TERMS = {
    "resuelveme",
    "resuelve",
    "resolverme",
    "soluciona",
    "solucionalo",
    "hazme",
    "hacerme",
    "haz_el",
    "haz_la",
    "redacta",
    "redactame",
    "escribe",
    "escribeme",
    "dame_la_respuesta",
    "respuesta_exacta",
    "respuesta_final",
    "para_copiar",
    "copiar_y_pegar",
    "solucion_completa",
    "contesta_por_mi",
    "pasame_la_respuesta",
}
_EVALUATION_TERMS = {
    "quiz",
    "parcial",
    "taller",
    "tarea",
    "ejercicio",
    "examen",
    "evaluacion",
    "entrega",
    "trabajo",
    "proyecto",
    "laboratorio",
    "practica",
    "exposicion",
    "presentacion",
    "resumen",
    "sintesis",
    "informe",
    "ensayo",
}


def _build_step1_recognition(activity_type: str, subject: str) -> str:
    """Mensaje de reconocimiento (Paso 1 del modo socratico)."""
    label = (activity_type or "actividad").replace("_", " ")
    base = f"Entiendo que tienes un {label}"
    if subject:
        base += f" de {subject}"
    return (
        base + ". No te voy a dar la respuesta directamente, "
        "pero si puedo guiarte para que tu llegues a ella. ¿Empezamos?"
    )


def _dominant_technique(
    study_profile: dict[str, object],
    pending: dict[str, object],
) -> str:
    """Extrae la tecnica dominante del perfil o del payload pendiente."""
    cached = str(pending.get("dominant_technique") or "").strip().lower()
    if cached:
        return cached
    techniques = study_profile.get("top_techniques")
    if isinstance(techniques, list) and techniques:
        return str(techniques[0]).strip().lower()
    return str(
        study_profile.get("dominant_technique")
        or study_profile.get("primary_technique")
        or ""
    ).strip().lower()


def _resolve_intent(normalized_text: str, pending: dict[str, object]) -> str | None:
    pending_intent = str(pending.get("intent") or "").strip()
    if pending_intent in {"request_guided_academic_help", "enter_socratic_mode"}:
        return pending_intent
    if _looks_like_socratic_request(normalized_text):
        return "enter_socratic_mode"
    if is_guided_academic_support_message(normalized_text):
        return "request_guided_academic_help"
    return None


def _socratic_result(
    *,
    slots: dict[str, object],
    turn_count: int,
    payload: dict[str, object],
    dominant_technique: str = "",
) -> GuidedAcademicSupportResult:
    if turn_count >= SOCRATIC_MAX_TURNS:
        return GuidedAcademicSupportResult(
            detected=True,
            intent="enter_socratic_mode",
            interaction_mode="socratic",
            message=(
                "Cierro esta ronda socratica para mantener la ayuda acotada. "
                "Con tus respuestas, escribe tu siguiente intento y luego revisamos la planificacion si hace falta."
            ),
            slots=slots,
            pending_payload=_payload_with_turn(payload, turn_count),
            output_kind="socratic_limit_reached",
            turn_count=turn_count,
        )

    next_turn = turn_count + 1
    question = _socratic_question(slots, next_turn, dominant_technique=dominant_technique)
    follow_up = next_turn < SOCRATIC_MAX_TURNS
    suffix = (
        "Respondeme con tu intento y seguimos con la siguiente pregunta."
        if follow_up
        else "Despues de responderla, convierte tus ideas en tu propio intento de solucion."
    )
    parts: list[str] = []
    if turn_count == 0:
        activity_type = str(slots.get("activity_type") or "actividad")
        subject = str(slots.get("subject_name") or "").strip()
        parts.append(_build_step1_recognition(activity_type, subject))
    parts.append(f"Modo socratico para {_context_label(slots)}.")
    parts.append(f"Pregunta {next_turn}: {question}")
    parts.append(suffix)
    return GuidedAcademicSupportResult(
        detected=True,
        intent="enter_socratic_mode",
        interaction_mode="socratic",
        message="\n".join(parts),
        slots=slots,
        pending_payload=_payload_with_turn(payload, next_turn),
        requires_follow_up=follow_up,
        output_kind="socratic_question",
        turn_count=next_turn,
    )


def _guided_result(
    *,
    slots: dict[str, object],
    payload: dict[str, object],
    dominant_technique: str = "",
    is_first: bool = True,
) -> GuidedAcademicSupportResult:
    checklist = _checklist_for_activity(slots)
    first_question = _socratic_question(slots, 1, dominant_technique=dominant_technique)
    activity_type = str(slots.get("activity_type") or "actividad")
    subject = str(slots.get("subject_name") or "").strip()
    message_lines: list[str] = []
    if is_first:
        message_lines.append(_build_step1_recognition(activity_type, subject))
    message_lines.append("Checklist inicial:")
    message_lines.extend(f"{index}. {item}" for index, item in enumerate(checklist, start=1))
    message_lines.append(f"Primera pregunta orientadora: {first_question}")
    return GuidedAcademicSupportResult(
        detected=True,
        intent="request_guided_academic_help",
        interaction_mode="guided",
        message="\n".join(message_lines),
        slots=slots,
        pending_payload=_payload_with_turn(payload, 1),
        output_kind="guided_checklist",
        turn_count=1,
    )


def _extract_slots(text: str | None) -> dict[str, object]:
    raw = str(text or "")
    normalized = slugify_identifier(raw)
    slots: dict[str, object] = {}
    activity_type = _detect_activity_type(normalized)
    if activity_type:
        slots["activity_type"] = activity_type

    subject = _extract_subject(raw)
    topic = _extract_topic(raw)
    objective = _extract_objective(raw)
    comma_subject, comma_topic = _extract_comma_context(raw)
    if subject or comma_subject:
        slots["subject_name"] = subject or comma_subject
    if topic or comma_topic:
        slots["topic"] = topic or comma_topic
    if objective:
        slots["objective"] = objective
    return slots


def _merge_slots(base: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in incoming.items():
        if value not in {None, ""}:
            merged[key] = value
    return merged


def _missing_fields(slots: dict[str, object]) -> list[str]:
    missing: list[str] = []
    if not str(slots.get("activity_type") or "").strip():
        missing.append("activity_type")
    if not str(slots.get("subject_name") or "").strip():
        missing.append("subject_name")
    if not str(slots.get("topic") or "").strip():
        missing.append("topic")
    return missing


def _missing_prompt(missing: list[str], *, interaction_mode: str) -> str:
    labels = {
        "activity_type": "tipo de actividad",
        "subject_name": "materia",
        "topic": "tema",
    }
    requested = ", ".join(labels.get(field, field) for field in missing)
    mode_text = "con preguntas socraticas" if interaction_mode == "socratic" else "sin resolverla"
    return (
        f"Puedo guiarte {mode_text}, pero necesito ubicar mejor la actividad. "
        f"Dime: {requested}. Si tienes un objetivo concreto, agregalo tambien."
    )


def _detect_activity_type(normalized_text: str) -> str | None:
    for activity_type, aliases in _ACTIVITY_ALIASES.items():
        if _contains_any(normalized_text, aliases):
            return activity_type
    return None


def _extract_subject(raw_text: str) -> str | None:
    match = re.search(
        r"\b(?:de|para|en)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ]+?)(?:\s+sobre\b|\s+tema\b|\s+con\b|\s+objetivo\b|[,.?]|$)",
        raw_text,
        flags=re.IGNORECASE,
    )
    if match:
        candidate = _clean_slot_text(match.group(1))
        if candidate and slugify_identifier(candidate) not in _ACTIVITY_ALIASES:
            return candidate
    return None


def _extract_topic(raw_text: str) -> str | None:
    match = re.search(
        r"\b(?:sobre|tema|acerca de)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ]+?)(?:\s+objetivo\b|\s+para\b|[,.?]|$)",
        raw_text,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_slot_text(match.group(1))
    return None


def _extract_objective(raw_text: str) -> str | None:
    match = re.search(
        r"\b(?:objetivo|quiero|necesito|busco)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ]+?)(?:[,.?]|$)",
        raw_text,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_slot_text(match.group(1))
    if "por dónde empiezo" in raw_text.lower() or "por donde empiezo" in raw_text.lower():
        return "definir por donde empezar"
    return None


def _extract_comma_context(raw_text: str) -> tuple[str | None, str | None]:
    parts = [_clean_slot_text(part) for part in raw_text.split(",")]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


def _checklist_for_activity(slots: dict[str, object]) -> list[str]:
    activity_type = str(slots.get("activity_type") or "actividad")
    if activity_type in {"taller", "tarea", "quiz", "parcial"}:
        return [
            "Reescribe la consigna con tus palabras y separa datos, tema y producto esperado.",
            "Marca lo que ya sabes resolver y el primer punto donde te bloqueas.",
            "Intenta un primer paso pequeno antes de revisar apuntes o ejemplos.",
        ]
    if activity_type in {"exposicion", "proyecto", "entrega"}:
        return [
            "Define la idea central y el resultado que debes entregar.",
            "Divide el trabajo en introduccion, desarrollo y verificacion.",
            "Prepara una evidencia, ejemplo o criterio para validar cada parte.",
        ]
    if activity_type == "lectura":
        return [
            "Divide el texto en secciones pequenas.",
            "Extrae una idea clave por seccion con tus palabras.",
            "Cierra con una sintesis propia y una duda concreta.",
        ]
    return [
        "Aclara que pide la actividad.",
        "Divide el trabajo en pasos pequenos.",
        "Verifica cada paso con una pregunta o ejemplo propio.",
    ]


def _socratic_question(
    slots: dict[str, object],
    turn_number: int,
    *,
    dominant_technique: str = "",
) -> str:
    topic = str(slots.get("topic") or "ese tema")
    activity_type = str(slots.get("activity_type") or "actividad").replace("_", " ")
    tech = dominant_technique.lower()
    if turn_number == 1:
        if "feynman" in tech:
            return (
                f"¿Puedes explicarme con tus propias palabras que pide el {activity_type} sobre {topic}?"
            )
        if "cornell" in tech:
            return (
                f"¿Cual es la pregunta principal que debes responder en el {activity_type} sobre {topic}? "
                "¿Que informacion ya tienes disponible?"
            )
        if any(t in tech for t in {"active_recall", "repeticion_espaciada", "interleaving"}):
            return f"¿Que ya sabes sobre {topic}? Empieza por ahi antes de revisar cualquier apunte."
        return f"Que te pide exactamente el {activity_type} sobre {topic}, escrito con tus propias palabras?"
    if turn_number == 2:
        return "Que dato, concepto o regla ya tienes claro y cual es el primer punto donde dudas?"
    return "Como comprobarias si tu primer paso es correcto sin pedirme la respuesta final?"


def _context_label(slots: dict[str, object]) -> str:
    activity_type = str(slots.get("activity_type") or "la actividad").replace("_", " ")
    subject = str(slots.get("subject_name") or "").strip()
    topic = str(slots.get("topic") or "").strip()
    label = activity_type
    if subject:
        label += f" de {subject}"
    if topic:
        label += f" sobre {topic}"
    return label


def _looks_like_socratic_request(normalized_text: str) -> bool:
    return _contains_any(normalized_text, _SOCRATIC_TERMS)


def _is_forbidden_solution_request(normalized_text: str) -> bool:
    return _contains_any(normalized_text, _EVALUATION_TERMS) and _contains_any(
        normalized_text,
        _FORBIDDEN_ACTION_TERMS,
    )


def _valid_pending_payload(payload: dict[str, object] | None) -> dict[str, object]:
    data = dict(payload or {})
    if data.get("domain") != GUIDED_SUPPORT_DOMAIN:
        return {}
    return data


def _payload_with_turn(payload: dict[str, object], turn_count: int) -> dict[str, object]:
    updated = dict(payload)
    updated["turn_count"] = turn_count
    return updated


def _contains_any(normalized_text: str, terms: set[str]) -> bool:
    padded = f"_{normalized_text}_"
    for term in terms:
        slug = slugify_identifier(term)
        if not slug:
            continue
        if f"_{slug}_" in padded or slug in normalized_text:
            return True
    return False


def _clean_slot_text(value: str | None) -> str | None:
    text = " ".join(str(value or "").replace("?", " ").split()).strip(" ,;:.")
    return text[:100] or None


def _int_or_zero(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


__all__ = [
    "GUIDED_SUPPORT_DOMAIN",
    "GuidedAcademicSupportResult",
    "SOCRATIC_MAX_TURNS",
    "build_guided_academic_support_result",
    "is_guided_academic_support_message",
    "is_socratic_mode_message",
]
