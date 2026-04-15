"""Servicios deterministas para acompanamiento diario de estudio."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from schemas.planning import SubjectItem
from .state_helpers import ensure_study_profile


@dataclass(frozen=True)
class DailyFocusResult:
    """Mensaje y metadatos para el enfoque diario."""

    should_send: bool
    message: str = ""
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DailyCompletionParseResult:
    """Resultado de interpretar el cumplimiento reportado por el estudiante."""

    is_valid: bool
    status: str | None = None
    completion_pct: int | None = None
    replan_signal: bool = False
    error: str | None = None


def build_daily_focus(
    *,
    plan_instances: list[dict[str, Any]],
    subjects: list[SubjectItem | dict],
    study_profile: object,
    today: date,
) -> DailyFocusResult:
    """Construye un enfoque corto sin ejecutar el bloque semanal."""

    todays_instances = [
        item
        for item in list(plan_instances or [])
        if _instance_date(item) == today.isoformat()
        and str(item.get("status") or "scheduled") in {"scheduled", "in_progress"}
    ]
    if not todays_instances:
        return DailyFocusResult(
            should_send=False,
            payload={"reason": "no_active_instances_for_today"},
        )

    profile = ensure_study_profile(study_profile)
    technique = profile.top_techniques[0] if profile.top_techniques else None
    prioritized_subjects = sorted(
        [SubjectItem(**dict(item)) if isinstance(item, dict) else item for item in subjects],
        key=lambda item: (-(item.computed_priority_score or 0.0), item.nombre.lower()),
    )
    subject_hint = prioritized_subjects[0].nombre if prioritized_subjects else None
    first_instance = todays_instances[0]
    title = str(first_instance.get("title") or first_instance.get("titulo") or "tu bloque")
    start = first_instance.get("starts_at") or first_instance.get("inicio")

    pieces = [f"Hoy enfocate en {subject_hint or title}."]
    if start:
        pieces.append(f"Primer bloque: {title} ({start}).")
    if technique:
        pieces.append(f"Metodo sugerido: {technique}.")
    return DailyFocusResult(
        should_send=True,
        message=" ".join(pieces),
        payload={
            "flow": "daily_accompaniment",
            "today": today.isoformat(),
            "instance_count": len(todays_instances),
            "primary_subject": subject_hint,
            "primary_technique_id": technique,
            "does_not_rerun_weekly_priorities": True,
        },
    )


def parse_daily_completion_response(text: str | None) -> DailyCompletionParseResult:
    """Interpreta respuestas como completado, a medias o no pude."""

    normalized = _normalize(text)
    if not normalized:
        return DailyCompletionParseResult(
            is_valid=False,
            error="Responde `completado`, `a medias` o `no pude`.",
        )
    if any(token in normalized for token in {"completado", "complete", "listo", "terminado"}):
        return DailyCompletionParseResult(is_valid=True, status="completed", completion_pct=100)
    if any(token in normalized for token in {"a medias", "mitad", "parcial"}):
        pct = _first_percentage(normalized) or 50
        return DailyCompletionParseResult(
            is_valid=True,
            status="completed",
            completion_pct=pct,
            replan_signal=pct < 60,
        )
    if any(token in normalized for token in {"no pude", "no estudie", "no alcance", "omitir"}):
        return DailyCompletionParseResult(
            is_valid=True,
            status="skipped",
            completion_pct=0,
            replan_signal=True,
        )
    return DailyCompletionParseResult(
        is_valid=False,
        error="No pude leer el cumplimiento. Usa `completado`, `a medias` o `no pude`.",
    )


def _instance_date(item: dict[str, Any]) -> str | None:
    if item.get("planned_date"):
        return str(item["planned_date"])[:10]
    starts_at = item.get("starts_at")
    if starts_at:
        return str(starts_at)[:10]
    return None


def _first_percentage(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*%", text)
    if match is None:
        return None
    return max(0, min(int(match.group(1)), 100))


def _normalize(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(text.split())
