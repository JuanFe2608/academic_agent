"""Formateadores deterministas del resultado conversacional."""

from __future__ import annotations

from typing import Any

from agents.support.personalization.questionnaire import get_technique


def build_personalization_summary(result: Any) -> str:
    """Construye el mensaje final a partir del resultado estructurado."""

    scores = list(_value(result, "scores", []))
    confidence = str(_value(result, "confidence", "baja"))
    observations = list(_value(result, "observations", []))
    if len(scores) < 3:
        return "Ya termine la caracterizacion, pero no pude construir el ranking completo."

    principal = _score_label(scores[0])
    secondary = _score_label(scores[1])
    support = _score_label(scores[2])
    lines = [
        "Listo. Ya tengo una primera caracterizacion de como estudias.",
        f"Tecnica principal: {principal}.",
        f"Tecnica secundaria: {secondary}.",
        f"Tecnica de apoyo: {support}.",
        f"Confianza de la recomendacion: {confidence}.",
    ]
    if observations:
        lines.append("Observaciones detectadas:")
        lines.extend(f"- {observation}" for observation in observations)
    lines.append(
        "Voy a dejar este resultado guardado para usarlo despues en la construccion de tu metodo de estudio personalizado."
    )
    return "\n".join(lines)


def _score_label(score: Any) -> str:
    technique_id = str(_value(score, "technique_id", "")).strip()
    if not technique_id:
        return "Sin tecnica"
    try:
        return get_technique(technique_id).display_name
    except KeyError:
        return technique_id


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)

