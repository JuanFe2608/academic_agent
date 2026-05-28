"""Nodo para persistir el resultado final de personalizacion academica."""

from __future__ import annotations

from agents.support.dependencies import (
    get_personalization_service,
    get_study_recommendation_service,
)
from agents.support.nodes.utils import append_message
from agents.support.personalization.formatter import build_personalization_summary
from agents.support.priorities.config import is_post_radar_flow_enabled
from agents.support.state import AgentState
from schemas.rag import StudyRecommendationQuery
from services.personalization.parser import likert_label
from services.personalization.questionnaire import get_question_by_id


_OPERATIONAL_WELCOME = (
    "✨ Ya entiendo mejor cómo estudias y eso me ayudará a acompañarte "
    "de una forma más útil y personalizada. 📚\n\n"
    "Desde ahora puedo apoyarte en:\n\n"
    "📅 Organizar tus actividades académicas en el calendario\n"
    "📝 Registrar y dar seguimiento a tus tareas pendientes\n"
    "🧠 Recomendarte cómo aplicar tu método de estudio\n"
    "🗓️ Ayudarte a planear tu semana sin que se te acumulen entregas o parciales\n\n"
    "Puedes escribirme de forma natural. Por ejemplo:\n"
    "- \"Ayúdame a organizar mi semana\"\n"
    "- \"¿Cómo aplico mi técnica para un parcial?\"\n"
    "- \"Agrega grupo de estudio el miércoles de 4 a 6 pm\"\n\n"
    "Cuando falte información, solo te preguntaré lo necesario. "
    "Antes de hacer cambios, siempre te mostraré lo que entendí para que confirmes."
)


def persist_study_profile(state: AgentState) -> dict:
    """Guarda el Radar final y cierra el flujo de personalizacion."""

    messages = state.get("messages", [])
    profile = dict(state.get("student_profile", {}))
    schedule_state = dict(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))

    result = get_personalization_service().persist_study_profile(
        student_id=profile.get("persisted_student_id"),
        schedule_profile_id=schedule_state.get("persisted_profile_id"),
        study_profile=study_profile,
    )

    if result.persisted:
        study_profile["persisted_profile_id"] = result.personalization_profile_id
        study_profile["persistence_error"] = None
        next_phase = "running" if is_post_radar_flow_enabled() else "end"
        return {
            "study_profile": study_profile,
            "phase": next_phase,
            "awaiting_user_input": next_phase == "running",
            "messages": (
                append_message(
                    messages,
                    "assistant",
                    _build_personalization_summary_with_rag(study_profile),
                )
                + append_message(messages, "assistant", _OPERATIONAL_WELCOME)
            ),
        }

    study_profile["persistence_error"] = result.error_code
    if result.error_code == "personalization_permission_denied":
        message = (
            "No pude guardar tu Radar de estudio porque el usuario actual de la base de datos "
            "no tiene permisos sobre las tablas del modulo de personalizacion.\n"
            f"Detalle tecnico: {result.detail or 'desconocido'}"
        )
    else:
        message = (
            "No pude guardar tu Radar de estudio en la base de datos.\n"
            f"Detalle tecnico: {result.detail or result.error_code or 'desconocido'}"
        )
    return {
        "study_profile": study_profile,
        "phase": "end",
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            message,
        ),
    }


def _primary_technique_id(study_profile: dict) -> str | None:
    """Retorna la técnica principal actual del Radar, si existe."""

    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _build_personalization_summary_with_rag(study_profile: dict) -> str:
    """Enriquece el cierre del Radar sin exponer detalles internos del RAG."""

    primary_technique = _primary_technique_id(study_profile)
    if not primary_technique:
        return build_personalization_summary(study_profile)

    try:
        recommendation_service = get_study_recommendation_service()
        if not recommendation_service.status.ready:
            return build_personalization_summary(study_profile)
        result = recommendation_service.answer_query(
            _build_radar_recommendation_query(study_profile)
        )
    except Exception:
        return build_personalization_summary(study_profile)

    if not result.source_chunks or not result.answer.strip():
        return build_personalization_summary(study_profile)

    return build_personalization_summary(
        study_profile,
        pedagogical_guidance=_compact_rag_answer(result.answer),
    )


def _build_radar_recommendation_query(study_profile: dict) -> StudyRecommendationQuery:
    """Construye una consulta RAG con el contexto real del Radar del estudiante."""

    top_techniques = [
        str(value)
        for value in list(study_profile.get("top_techniques") or [])
        if value
    ]
    weakness_tags = [
        str(value)
        for value in list(study_profile.get("weakness_tags") or [])
        if value
    ]
    query_parts = [
        "Recomienda como estudiar despues del Radar de estudio.",
        _score_context(study_profile),
        _signal_context(study_profile),
        _answer_context(study_profile),
        _tiebreaker_context(study_profile),
        (
            "La respuesta debe explicar por que la recomendacion encaja con sus "
            "puntajes y respuestas, y debe dar pasos concretos para empezar."
        ),
    ]
    return StudyRecommendationQuery(
        query_text=" ".join(part for part in query_parts if part).strip(),
        intent="recommend_technique",
        student_signals=weakness_tags,
        top_techniques=top_techniques,
        preferred_language="es",
        max_chunks=5,
    )


def _score_context(study_profile: dict) -> str:
    scores = list(study_profile.get("scores") or [])[:5]
    if not scores:
        return ""
    parts: list[str] = []
    for score in scores:
        technique_name = str(_value(score, "technique_name", "") or "").strip()
        technique_id = str(_value(score, "technique_id", "") or "").strip()
        label = technique_name or technique_id.replace("_", " ")
        percentage = _value(score, "percentage_score", None)
        if percentage is None:
            normalized = _value(score, "normalized_score", None)
            percentage = (
                round(float(normalized) * 100, 2)
                if normalized is not None
                else None
            )
        if percentage is None:
            parts.append(label)
        else:
            parts.append(f"{label}: {percentage}%")
    confidence = str(study_profile.get("confidence") or "").strip()
    confidence_text = f" Confianza del ranking: {confidence}." if confidence else ""
    return "Ranking del Radar: " + "; ".join(parts) + "." + confidence_text


def _signal_context(study_profile: dict) -> str:
    signals = list(study_profile.get("signals") or [])[:4]
    if signals:
        labels = [
            str(
                _value(signal, "message", "")
                or _value(signal, "label", "")
                or ""
            ).strip()
            for signal in signals
        ]
        labels = [label for label in labels if label]
        if labels:
            return "Senales detectadas: " + " ".join(labels)
    observations = [
        str(value).strip()
        for value in list(study_profile.get("observations") or [])
        if str(value).strip()
    ]
    if observations:
        return "Observaciones del Radar: " + " ".join(observations[:4])
    return ""


def _answer_context(study_profile: dict) -> str:
    answers = dict(study_profile.get("answers") or {})
    if not answers:
        return ""
    strong_answers: list[tuple[int, str]] = []
    for question_id, raw_value in answers.items():
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value < 2:
            continue
        try:
            question = get_question_by_id(str(question_id))
        except KeyError:
            continue
        strong_answers.append(
            (
                value,
                f"{question.challenge_title}: {likert_label(value)} ante '{question.prompt}'",
            )
        )
    strong_answers.sort(key=lambda item: -item[0])
    if not strong_answers:
        return ""
    return "Respuestas fuertes del estudiante: " + " ".join(
        text for _, text in strong_answers[:5]
    )


def _tiebreaker_context(study_profile: dict) -> str:
    tiebreaker = dict(study_profile.get("tiebreaker") or {})
    if not tiebreaker.get("activated"):
        return ""
    details = list(tiebreaker.get("answer_details") or [])
    selected = [
        str(_value(detail, "selected_option_label", "") or "").strip()
        for detail in details
    ]
    selected = [label for label in selected if label]
    confidence_after = str(tiebreaker.get("confidence_after") or "").strip()
    context = "El desempate del Radar fue aplicado."
    if selected:
        context += " Respuestas de desempate: " + " ".join(selected[:3])
    if confidence_after:
        context += f" Confianza despues del desempate: {confidence_after}."
    return context


def _value(item: object, key: str, default: object = None) -> object:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _compact_rag_answer(text: str, *, max_chars: int = 520) -> str:
    """Mantiene el cierre del Radar breve sin cortar frases a medias."""

    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    cutoff = cleaned.rfind(".", 0, max_chars)
    if cutoff >= int(max_chars * 0.55):
        return cleaned[: cutoff + 1].strip()
    return cleaned
