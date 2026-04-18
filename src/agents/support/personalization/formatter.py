"""Formateadores deterministas del Radar de estudio."""

from __future__ import annotations

from typing import Any

from services.personalization.questionnaire import (
    get_intro_prompt,
    get_invalid_answer_prompt,
    get_microfeedback,
    get_question_options_prompt,
    get_technique,
    get_tiebreaker_intro_prompt,
    get_tiebreaker_invalid_answer_prompt,
    get_tiebreaker_microfeedback,
)

_FILLED_STEP = "🟩"
_EMPTY_STEP = "⬜"


def build_question_prompt(
    question: Any,
    *,
    question_number: int,
    total_questions: int,
    include_intro: bool = False,
    invalid_answer: bool = False,
    answered_count: int = 0,
) -> str:
    """Construye un reto del Radar de estudio en formato WhatsApp."""

    lines: list[str] = []
    if include_intro:
        lines.append(get_intro_prompt())
        lines.append("")

    if invalid_answer:
        lines.append(get_invalid_answer_prompt())
        lines.append("")
    else:
        microfeedback = get_microfeedback(answered_count)
        if microfeedback:
            lines.append(microfeedback)
            lines.append("")

    challenge_title = str(_value(question, "challenge_title", "Radar de estudio")).strip()
    challenge_emoji = str(_value(question, "challenge_emoji", "🧭")).strip()
    question_prompt = str(_value(question, "prompt", "")).strip()

    lines.append(f"Reto {question_number}/{total_questions} · {challenge_title} {challenge_emoji}")
    lines.append(f"Progreso {question_number}/{total_questions}: {build_progress_bar(question_number, total_questions)}")
    lines.append("")
    lines.append(question_prompt)
    lines.append("")
    lines.append(get_question_options_prompt())
    return "\n".join(lines).strip()


def build_tiebreaker_prompt(
    question: Any,
    *,
    question_number: int,
    total_questions: int,
    include_intro: bool = False,
    invalid_answer: bool = False,
    answered_count: int = 0,
) -> str:
    """Construye un reto extra del desempate en formato WhatsApp."""

    lines: list[str] = []
    if include_intro:
        lines.append(get_tiebreaker_intro_prompt())
        lines.append("")

    if invalid_answer:
        lines.append(get_tiebreaker_invalid_answer_prompt())
        lines.append("")
    else:
        microfeedback = get_tiebreaker_microfeedback(answered_count)
        if microfeedback:
            lines.append(microfeedback)
            lines.append("")

    challenge_title = str(_value(question, "challenge_title", "Afinando tu radar")).strip()
    challenge_emoji = str(_value(question, "challenge_emoji", "🎯")).strip()
    question_prompt = str(_value(question, "prompt", "")).strip()
    option_lines = _choice_option_lines(question)

    lines.append(f"{challenge_title} {challenge_emoji}")
    lines.append(f"Progreso {question_number}/{total_questions}: {build_progress_bar(question_number, total_questions)}")
    lines.append("")
    lines.append(question_prompt)
    lines.append("")
    lines.extend(option_lines)
    lines.append("")
    lines.append("Responde con un número del 1 al 4.")
    return "\n".join(lines).strip()


def build_personalization_summary(
    result: Any,
    *,
    pedagogical_guidance: str | None = None,
    pedagogical_cautions: list[str] | None = None,
) -> str:
    """Construye el cierre final del Radar de estudio."""

    scores = list(_value(result, "scores", []))
    if len(scores) < 3:
        return "Ya terminé tu Radar de estudio, pero no pude construir el ranking completo."

    # La plantilla final solo muestra la guia practica, no cautelas separadas.
    _ = pedagogical_cautions
    top_ids = [_score_technique_id(scores[index]) for index in range(3)]
    guidance = _practical_guidance(top_ids, pedagogical_guidance)
    lines = ["Listo, ya identifiqué cómo puedes estudiar de forma más efectiva según tu perfil 📘"]

    lines.extend(
        [
            "",
            "Lo que más te conviene fortalecer ahora es esto:",
            "",
            _strengthening_line(top_ids[0]),
            _strengthening_line(top_ids[1]),
            _strengthening_line(top_ids[2]),
            "",
            _learning_style_sentence(top_ids),
            _method_mix_sentence(top_ids),
        ]
    )
    if guidance:
        lines.extend(["", "Para llevarlo a la práctica:", guidance])
    return "\n".join(lines)


def build_progress_bar(current_step: int, total_steps: int) -> str:
    """Renderiza una barra de progreso limpia para WhatsApp."""

    bounded_total = max(int(total_steps), 1)
    bounded_current = min(max(int(current_step), 0), bounded_total)
    return (_FILLED_STEP * bounded_current) + (_EMPTY_STEP * (bounded_total - bounded_current))


def _score_technique_id(score: Any) -> str:
    return str(_value(score, "technique_id", "")).strip()


def _support_hint(score: Any) -> str:
    technique_id = _score_technique_id(score)
    if not technique_id:
        return "un refuerzo más claro del estudio"
    try:
        return get_technique(technique_id).support_hint
    except KeyError:
        return technique_id


def _strengthening_line(technique_id: str) -> str:
    return {
        "active_recall": "Evaluar lo que realmente recuerdas sin depender tanto de releer.",
        "cornell": "Transformar tus apuntes en preguntas, ideas clave y resúmenes útiles para repasar.",
        "feynman": "Convertir lo que entiendes en explicaciones claras y propias.",
        "interleaving": "Alternar materias o tipos de ejercicios sin perder claridad sobre qué estrategia usar.",
        "mapas_conceptuales": "Organizar mejor temas largos o teóricos para no estudiarlos de forma desordenada.",
        "mnemotecnia": "Recordar definiciones, listas o pasos importantes con apoyos más precisos.",
        "pomodoro": "Iniciar tus sesiones con bloques claros para reducir la fricción y sostener mejor el foco.",
        "repeticion_espaciada": "Revisar los temas en varios momentos para reducir el olvido rápido.",
    }.get(technique_id, _support_hint({"technique_id": technique_id}).capitalize() + ".")


def _learning_style_sentence(technique_ids: list[str]) -> str:
    return (
        "Tu perfil sugiere que aprendes mejor cuando estudias "
        f"{_join_hints([_technique_learning_action(technique_id) for technique_id in technique_ids])}, "
        "no solo leyendo."
    )


def _method_mix_sentence(technique_ids: list[str]) -> str:
    return (
        "Por eso, tu método de estudio debería combinar "
        f"{_join_hints([_technique_method_piece(technique_id) for technique_id in technique_ids])}."
    )


def _technique_learning_action(technique_id: str) -> str:
    return {
        "active_recall": "recuperando información",
        "cornell": "organizando tus apuntes",
        "feynman": "explicando con tus propias palabras",
        "interleaving": "alternando tipos de práctica",
        "mapas_conceptuales": "conectando ideas visualmente",
        "mnemotecnia": "creando pistas de memoria",
        "pomodoro": "trabajando en bloques de foco",
        "repeticion_espaciada": "repasando en momentos separados",
    }.get(technique_id, _support_hint({"technique_id": technique_id}))


def _technique_method_piece(technique_id: str) -> str:
    return {
        "active_recall": "memoria activa",
        "cornell": "apuntes estructurados",
        "feynman": "explicación propia",
        "interleaving": "práctica variada",
        "mapas_conceptuales": "organización visual",
        "mnemotecnia": "pistas de memoria",
        "pomodoro": "bloques de foco",
        "repeticion_espaciada": "repaso distribuido",
    }.get(technique_id, _support_hint({"technique_id": technique_id}))


def _practical_guidance(
    technique_ids: list[str],
    pedagogical_guidance: str | None,
) -> str:
    """Construye una guia accionable sin exponer etiquetas o nombres internos."""

    if not str(pedagogical_guidance or "").strip():
        return ""

    steps = [_practice_step(technique_id) for technique_id in technique_ids]
    unique_steps = _unique([step for step in steps if step])
    if not unique_steps:
        return ""
    return "\n".join(
        f"{index}. {step}"
        for index, step in enumerate(unique_steps[:3], start=1)
    )


def _practice_step(technique_id: str) -> str:
    return {
        "active_recall": (
            "Después de revisar un tema, cierra el material y respóndete preguntas "
            "sin mirar. Luego compara tus respuestas y corrige solo lo que falló."
        ),
        "cornell": (
            "Convierte tus apuntes en material de repaso: escribe preguntas al lado "
            "de las ideas importantes y termina con un resumen breve en tus palabras."
        ),
        "feynman": (
            "Elige un concepto pequeño y explícalo con palabras simples, como si se "
            "lo contaras a otra persona. Si te trabas, marca esa parte y vuelve a revisarla."
        ),
        "interleaving": (
            "Mezcla ejercicios o temas parecidos y, antes de resolver cada uno, decide "
            "qué estrategia corresponde y por qué."
        ),
        "mapas_conceptuales": (
            "Organiza el tema conectando ideas principales, detalles y ejemplos. Usa "
            "las conexiones para detectar qué parte todavía está suelta."
        ),
        "mnemotecnia": (
            "Para definiciones, listas o pasos, crea una pista fácil de recordar y "
            "pruébate después sin mirar para confirmar que realmente la puedes recuperar."
        ),
        "pomodoro": (
            "Empieza cada sesión con un objetivo pequeño, trabaja en un bloque corto "
            "sin cambiar de tarea y cierra anotando qué quedó pendiente."
        ),
        "repeticion_espaciada": (
            "Agenda repasos breves en distintos días. En cada repaso intenta recordar "
            "primero y revisa el material solo después."
        ),
    }.get(technique_id, "")


def _choice_option_lines(question: Any) -> list[str]:
    options = list(_value(question, "options", []))
    lines: list[str] = []
    for option in options:
        option_id = _value(option, "option_id", "")
        label = str(_value(option, "label", "")).strip()
        lines.append(f"{option_id}. {label}")
    return lines


def _join_hints(hints: list[str]) -> str:
    filtered = [hint for hint in hints if hint]
    if not filtered:
        return "reforzar tu forma de estudiar"
    if len(filtered) == 1:
        return filtered[0]
    if len(filtered) == 2:
        return f"{filtered[0]} y {filtered[1]}"
    return f"{filtered[0]}, {filtered[1]} y {filtered[2]}"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
