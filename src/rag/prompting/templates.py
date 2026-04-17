"""Deterministic answer templates for grounded RAG output."""

from __future__ import annotations

from schemas.rag import StudyRecommendationQuery


def render_fallback_answer(query: StudyRecommendationQuery, *, intent: str) -> str:
    """Return an honest fallback when retrieval produced no usable sources."""

    target = query.query_text.strip() or query.subject_name or "esta solicitud"
    if intent == "session_guidance":
        return (
            f"No tengo suficientes fuentes internas para armar una guia de sesion sobre {target}. "
            "Agrega tecnica, materia, actividad y tiempo disponible para recuperar una fuente util."
        )
    return (
        f"No tengo suficientes fuentes internas para responder de forma confiable sobre {target}. "
        "La recomendacion debe quedar pendiente hasta recuperar una tecnica, metodo o contexto mas especifico."
    )


def render_grounded_answer(
    *,
    query: StudyRecommendationQuery,
    intent: str,
    primary_text: str,
    supporting_facts: list[str],
    cautions: list[str],
    has_blocking_contraindication: bool,
) -> str:
    """Render a concise grounded answer from retrieved facts and explicit cautions."""

    pieces: list[str] = []
    if has_blocking_contraindication and cautions:
        pieces.append(f"No recomiendo esa combinacion tal como esta planteada. {cautions[0]}")
        if primary_text:
            pieces.append(primary_text)
    elif primary_text:
        pieces.append(primary_text)
    else:
        pieces.append(
            "Las fuentes internas recuperadas son relevantes, pero no contienen una respuesta directa reusable."
        )

    support = _first_non_redundant(supporting_facts, pieces[0])
    if support and intent in {
        "recommend_technique",
        "recommend_method",
        "session_guidance",
        "adapt_method",
        "combine_techniques",
        "contraindication_check",
    }:
        pieces.append(support)

    if cautions and not has_blocking_contraindication:
        pieces.append(f"Cuidado: {cautions[0]}")

    next_action = _next_action(query=query, intent=intent, has_blocking=has_blocking_contraindication)
    if next_action:
        pieces.append(next_action)

    return _shorten(" ".join(piece.strip() for piece in pieces if piece.strip()), max_chars=1200)


def _next_action(
    *,
    query: StudyRecommendationQuery,
    intent: str,
    has_blocking: bool,
) -> str:
    if has_blocking:
        return "El siguiente paso es elegir otra combinacion o usar una sola tecnica con un objetivo claro."
    if intent == "session_guidance":
        if query.available_minutes:
            return (
                f"Con {query.available_minutes} minutos, conviertelo en una sesion concreta con "
                "inicio, actividad activa y cierre de verificacion."
            )
        return "Para una sesion, define una actividad activa y un cierre de verificacion."
    if intent == "recommend_method":
        return "Usalo como estructura de varios pasos, no como una tecnica aislada."
    if intent == "recommend_technique":
        return "Aplicala en una tarea concreta y verifica al final si produjo aprendizaje observable."
    if intent == "combine_techniques":
        return "Combina solo las tecnicas que tengan roles distintos y una secuencia clara."
    return ""


def _first_non_redundant(facts: list[str], base: str) -> str:
    base_prefix = base[:120].lower()
    for fact in facts:
        if fact[:120].lower() != base_prefix:
            return fact
    return ""


def _shorten(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cutoff = text.rfind(".", 0, max_chars)
    if cutoff < int(max_chars * 0.55):
        cutoff = max_chars
    return text[:cutoff].rstrip(" .,;:") + "..."


__all__ = ["render_fallback_answer", "render_grounded_answer"]
