"""Utilidades para emparejar texto libre con actividades existentes."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable, Mapping

from agents.support.nodes.utils import normalize_text
from agents.support.tools.llm import llm_extract_json


def resolve_best_title_key(
    events: Iterable[Mapping[str, object]],
    query_text: str,
    min_score: float = 0.58,
    ambiguity_margin: float = 0.06,
) -> str:
    """Retorna el titulo normalizado mas probable o cadena vacia."""
    normalized_query = normalize_text(query_text)
    if not normalized_query:
        return ""

    scored = _score_titles(events, normalized_query)
    if not scored:
        return ""

    best_key, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    if best_score >= min_score and (best_score - second_score) >= ambiguity_margin:
        return best_key

    llm_key = _resolve_title_key_with_llm(events, normalized_query)
    if llm_key:
        return llm_key

    if best_score >= max(min_score, 0.72):
        return best_key
    return ""


def suggest_similar_titles(
    events: Iterable[Mapping[str, object]],
    query_text: str,
    limit: int = 3,
    min_score: float = 0.5,
) -> list[str]:
    """Retorna una lista corta de titulos similares para mostrar al usuario."""
    normalized_query = normalize_text(query_text)
    if not normalized_query:
        return []

    title_map = _build_title_map(events)
    scored = [
        (title_map[key], score)
        for key, score in _score_titles(events, normalized_query)
        if score >= min_score
    ]
    suggestions: list[str] = []
    for title, _score in scored:
        if title not in suggestions:
            suggestions.append(title)
        if len(suggestions) >= limit:
            break
    return suggestions


def _score_titles(
    events: Iterable[Mapping[str, object]],
    normalized_query: str,
) -> list[tuple[str, float]]:
    title_map = _build_title_map(events)
    scored = [
        (key, _score_title_similarity(key, normalized_query))
        for key in title_map
        if key
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def _build_title_map(events: Iterable[Mapping[str, object]]) -> dict[str, str]:
    title_map: dict[str, str] = {}
    for event in events:
        title = str(event.get("titulo") or "").strip()
        key = normalize_text(title)
        if key and key not in title_map:
            title_map[key] = title
    return title_map


def _score_title_similarity(candidate: str, query: str) -> float:
    if not candidate or not query:
        return 0.0
    if candidate == query:
        return 1.0

    candidate_tokens = [token for token in candidate.split() if token]
    query_tokens = [token for token in query.split() if token]
    candidate_set = set(candidate_tokens)
    query_set = set(query_tokens)
    overlap = len(candidate_set & query_set)

    token_subset_score = 0.0
    if query_tokens and all(token in candidate_set for token in query_set):
        token_subset_score = 0.93 if len(query_set) >= 2 else 0.72
    elif candidate_tokens and all(token in query_set for token in candidate_set):
        token_subset_score = 0.88
    elif query_tokens:
        token_subset_score = overlap / len(query_set)

    containment_score = 0.0
    if query in candidate or candidate in query:
        containment_score = 0.96 if len(query_tokens) >= 2 else 0.82

    sequence_score = SequenceMatcher(None, query, candidate).ratio()
    compact_sequence_score = SequenceMatcher(
        None,
        query.replace(" ", ""),
        candidate.replace(" ", ""),
    ).ratio()

    return max(
        containment_score,
        token_subset_score,
        (token_subset_score * 0.7) + (sequence_score * 0.3),
        compact_sequence_score,
        sequence_score,
    )


def _resolve_title_key_with_llm(
    events: Iterable[Mapping[str, object]],
    normalized_query: str,
) -> str:
    title_map = _build_title_map(events)
    if not title_map:
        return ""

    titles = list(title_map.values())
    prompt = (
        "Elige el titulo existente que mejor coincide con la referencia del estudiante.\n"
        'Responde SOLO JSON valido con formato {"title":"string|null"}.\n'
        "Reglas:\n"
        "- title debe ser exactamente uno de los titulos proporcionados.\n"
        "- Puedes considerar abreviaciones, errores ortograficos leves y coincidencias parciales.\n"
        "- Si ninguna opcion corresponde claramente, responde title=null.\n"
        f"Referencia del estudiante: {normalized_query}\n"
        "Titulos disponibles:\n"
        + "\n".join(f"- {title}" for title in titles)
    )
    data = llm_extract_json(prompt)
    if not data:
        return ""
    title = str(data.get("title") or "").strip()
    key = normalize_text(title)
    if key in title_map:
        return key
    return ""
