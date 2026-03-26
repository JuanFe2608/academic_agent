"""Prompts del bloque de caracterizacion academica."""

from __future__ import annotations

INTRO_PROMPT = (
    "Ahora voy a hacerte unas preguntas breves para entender como estudias "
    "y que dificultades se te presentan. Con eso podre recomendarte tecnicas "
    "y luego construir un metodo de estudio mas personalizado para ti.\n\n"
    "Responde cada afirmacion con un numero:\n"
    "0. Nunca o casi nunca\n"
    "1. A veces\n"
    "2. Frecuentemente\n"
    "3. Casi siempre"
)

QUESTION_OPTIONS_PROMPT = (
    "Responde con un numero:\n"
    "0. Nunca o casi nunca\n"
    "1. A veces\n"
    "2. Frecuentemente\n"
    "3. Casi siempre"
)

INVALID_ANSWER_PROMPT = (
    "Necesito que respondas solo con un numero entre 0 y 3.\n"
    "0. Nunca o casi nunca\n"
    "1. A veces\n"
    "2. Frecuentemente\n"
    "3. Casi siempre"
)


def build_question_prompt(
    question_number: int,
    total_questions: int,
    question_text: str,
    *,
    include_intro: bool = False,
    invalid_answer: bool = False,
) -> str:
    """Construye el prompt de una pregunta del cuestionario."""

    lines: list[str] = []
    if include_intro:
        lines.append(INTRO_PROMPT)
        lines.append("")
    if invalid_answer:
        lines.append(INVALID_ANSWER_PROMPT)
        lines.append("")
    lines.append(f"Pregunta {question_number} de {total_questions}")
    lines.append(question_text)
    lines.append(QUESTION_OPTIONS_PROMPT)
    return "\n".join(lines)

