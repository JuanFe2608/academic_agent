"""Mensajes reutilizables para orientar la captura de horarios."""

from __future__ import annotations


def build_schedule_capture_prompt(
    intro: str,
    recommendations: list[str],
    examples: list[str],
) -> str:
    """Compone un prompt guiado con recomendaciones y ejemplos válidos."""

    lines = [intro, "", "Antes de enviarlo, ten en cuenta estas recomendaciones:", ""]
    lines.extend(f"• {item}" for item in recommendations)
    if examples:
        lines.extend(["", "Ejemplos válidos:", ""])
        lines.extend(examples)
    return "\n".join(lines).strip()
