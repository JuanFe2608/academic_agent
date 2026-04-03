"""Parser determinista para captura manual de materias priorizadas."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from agents.support.state import SubjectItem


@dataclass(frozen=True)
class ParsedSubjectCatalog:
    """Resultado del parser de materias enviadas por el estudiante."""

    subjects: list[SubjectItem]
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.subjects)


def parse_subject_catalog(text: str) -> ParsedSubjectCatalog:
    """Parsea materias en formato `Materia | prioridad | dificultad | urgencia | carga`."""

    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ParsedSubjectCatalog(subjects=[], error="No encontré materias para procesar.")

    subjects: list[SubjectItem] = []
    seen_names: set[str] = set()
    for line in lines:
        clean_line = line.lstrip("-•* ").strip()
        parts = [part.strip() for part in clean_line.split("|")]
        if len(parts) != 5:
            return ParsedSubjectCatalog(
                subjects=[],
                error=(
                    "Cada línea debe venir así: Materia | prioridad | dificultad | urgencia | carga semanal."
                ),
            )

        nombre, prioridad_raw, dificultad_raw, urgencia_raw, carga_raw = parts
        if not nombre:
            return ParsedSubjectCatalog(subjects=[], error="Cada materia necesita un nombre.")

        prioridad = _parse_priority(prioridad_raw)
        if prioridad is None:
            return ParsedSubjectCatalog(subjects=[], error="La prioridad debe ser alta, media o baja.")

        urgencia = _parse_priority(urgencia_raw)
        if urgencia is None:
            return ParsedSubjectCatalog(subjects=[], error="La urgencia debe ser alta, media o baja.")

        dificultad = _parse_difficulty(dificultad_raw)
        if dificultad is None:
            return ParsedSubjectCatalog(
                subjects=[],
                error="La dificultad debe ser un número entero entre 1 y 5.",
            )

        carga = _parse_load_minutes(carga_raw)
        if carga is None:
            return ParsedSubjectCatalog(
                subjects=[],
                error="La carga semanal debe venir en minutos o en horas, por ejemplo 180 o 3h.",
            )

        normalized_name = _normalize_text(nombre)
        if normalized_name in seen_names:
            return ParsedSubjectCatalog(
                subjects=[],
                error=f"La materia '{nombre}' está repetida. Envíala una sola vez.",
            )
        seen_names.add(normalized_name)
        subjects.append(
            SubjectItem(
                nombre=nombre.strip(),
                prioridad=prioridad,
                dificultad=dificultad,
                urgencia=urgencia,
                carga_semanal_min=carga,
                origen="manual",
            )
        )

    return ParsedSubjectCatalog(subjects=subjects)


def _parse_priority(value: str) -> str | None:
    normalized = _normalize_text(value)
    aliases = {
        "alta": "alta",
        "high": "alta",
        "media": "media",
        "medium": "media",
        "baja": "baja",
        "low": "baja",
    }
    return aliases.get(normalized)


def _parse_difficulty(value: str) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    if not match:
        return None
    parsed = int(match.group(0))
    if 1 <= parsed <= 5:
        return parsed
    return None


def _parse_load_minutes(value: str) -> int | None:
    raw = str(value or "").strip().lower().replace(",", ".")
    if not raw:
        return None

    minutes_match = re.fullmatch(r"(\d+)\s*(?:m|min|minuto|minutos)?", raw)
    if minutes_match:
        parsed = int(minutes_match.group(1))
        return parsed if parsed >= 30 else None

    hours_minutes_match = re.fullmatch(
        r"(\d+)\s*h(?:oras?)?\s*(\d+)\s*(?:m|min|minutos?)",
        raw,
    )
    if hours_minutes_match:
        total = int(hours_minutes_match.group(1)) * 60 + int(hours_minutes_match.group(2))
        return total if total >= 30 else None

    hours_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*h(?:oras?)?", raw)
    if hours_match:
        total = int(float(hours_match.group(1)) * 60)
        return total if total >= 30 else None
    return None


def _normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.lower().strip().split())
