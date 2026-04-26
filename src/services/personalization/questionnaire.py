"""Configuracion versionada del Radar de estudio y su desempate."""

from __future__ import annotations

from .models import (
    ChoiceOptionDefinition,
    QuestionDefinition,
    SignalRuleDefinition,
    TechniqueBoost,
    TechniqueDefinition,
    TechniqueWeight,
    TiebreakerQuestionDefinition,
)

QUESTIONNAIRE_VERSION = "v3"
SCORING_VERSION = "v3"

PRIMARY_WEIGHT = 100
SECONDARY_WEIGHT = 40
TIEBREAKER_BOOST_WEIGHT = 100

LIKERT_OPTIONS = {
    0: "Nunca",
    1: "Pocas veces",
    2: "Seguido",
    3: "Siempre",
}

LIKERT_ALIASES = {
    0: {"0", "nunca", "casi nunca", "jamas", "jamás", "nunca o casi nunca"},
    1: {"1", "pocas veces", "a veces", "rara vez", "raramente"},
    2: {"2", "seguido", "me pasa seguido", "frecuentemente", "con frecuencia"},
    3: {"3", "siempre", "casi siempre", "me pasa casi siempre"},
}

RADAR_INTRO = (
    "Vamos a activar tu Radar de estudio 🧭\n"
    "Te haré 10 preguntas para detectar qué obstáculos aparecen cuando estudias "
    "y qué técnicas pueden ayudarte más.\n"
    "No hay respuestas buenas o malas: la idea es entender cómo estudias hoy "
    "para construir un método más personalizado para ti.\n\n"
    "Responde pensando en cómo has estudiado en las últimas 2 o 3 semanas."
)

QUESTION_OPTIONS_PROMPT = (
    "Responde con un número:\n"
    "0 = Nunca\n"
    "1 = Pocas veces\n"
    "2 = Seguido\n"
    "3 = Siempre"
)

INVALID_ANSWER_PROMPT = (
    "Necesito que me respondas solo con un número del 0 al 3 para seguir con tu Radar 🧭\n"
    "0 = Nunca\n"
    "1 = Pocas veces\n"
    "2 = Seguido\n"
    "3 = Siempre"
)

MICROFEEDBACK_BY_ANSWERED_COUNT = {
    1: "Bien, ya voy entendiendo cómo estudias 👌",
    3: "Perfecto, continuemos con la siguiente pregunta.",
    5: "Buen avance, esto me ayuda a personalizar mejor tus recomendaciones.",
    7: "Vamos muy bien, ya casi completamos tu radar.",
    9: "Último tramo, una respuesta más y cierro tu radar.",
}

TIEBREAKER_INTRO = (
    "Tu Radar quedó con señales bastante parejas, así que voy a hacerte 3 preguntas adicionales "
    "para afinar mejor tu perfil de estudio 🎯\n"
    "Con esto podré priorizar con más precisión las técnicas que más te pueden ayudar.\n\n"
    "Responde con un número del 1 al 4."
)

TIEBREAKER_INVALID_ANSWER_PROMPT = (
    "Para afinar bien tu perfil necesito una opción del 1 al 4 🎯\n"
    "Respóndeme solo con un número para seguir."
)

TIEBREAKER_MICROFEEDBACK_BY_ANSWERED_COUNT = {
    1: "Bien, esto ya me da una pista mucho más clara 👌",
    2: "Perfecto, voy con la última pregunta adicional.",
}


def _weights(
    primary_technique_id: str,
    secondary_technique_id: str | None = None,
) -> list[TechniqueWeight]:
    weights = [
        TechniqueWeight(
            technique_id=primary_technique_id,
            weight=PRIMARY_WEIGHT,
            role="primary",
        )
    ]
    if secondary_technique_id:
        weights.append(
            TechniqueWeight(
                technique_id=secondary_technique_id,
                weight=SECONDARY_WEIGHT,
                role="secondary",
            )
        )
    return weights


def _boost(technique_id: str, boost: int = TIEBREAKER_BOOST_WEIGHT) -> list[TechniqueBoost]:
    return [TechniqueBoost(technique_id=technique_id, boost=boost)]


TECHNIQUES: tuple[TechniqueDefinition, ...] = (
    TechniqueDefinition(
        technique_id="pomodoro",
        display_name="Pomodoro",
        priority_order=1,
        rationale_tags=["procrastination", "distraction"],
        observation="Hay señales de dificultad para iniciar y sostener sesiones con foco.",
        support_hint="sesiones más estructuradas y más fáciles de arrancar",
    ),
    TechniqueDefinition(
        technique_id="feynman",
        display_name="Feynman",
        priority_order=2,
        rationale_tags=["explanation_gap"],
        observation="Entiendes parte del contenido, pero aún cuesta explicarlo con claridad.",
        support_hint="explicar los temas con tus propias palabras para detectar vacíos reales",
    ),
    TechniqueDefinition(
        technique_id="active_recall",
        display_name="Active Recall",
        priority_order=3,
        rationale_tags=["passive_review_dependence"],
        observation="Aparece dependencia de relectura en vez de recuperación activa.",
        support_hint="comprobar mejor lo que recuerdas sin mirar apuntes",
    ),
    TechniqueDefinition(
        technique_id="cornell",
        display_name="Método Cornell",
        priority_order=4,
        rationale_tags=["note_organization"],
        observation="Tus apuntes necesitan una estructura más útil para repasar.",
        support_hint="convertir tus apuntes en material útil de repaso",
    ),
    TechniqueDefinition(
        technique_id="mapas_conceptuales",
        display_name="Mapas conceptuales",
        priority_order=5,
        rationale_tags=["concept_connections"],
        observation="Te ayudaría visualizar relaciones y jerarquías entre ideas.",
        support_hint="ordenar temas amplios viendo conexiones entre ideas",
    ),
    TechniqueDefinition(
        technique_id="mnemotecnia",
        display_name="Mnemotecnia",
        priority_order=6,
        rationale_tags=["exact_memory"],
        observation="Hay fricción al recordar detalles, listas o definiciones exactas.",
        support_hint="retener definiciones y listas exactas con más precisión",
    ),
    TechniqueDefinition(
        technique_id="repeticion_espaciada",
        display_name="Spaced Repetition",
        priority_order=7,
        rationale_tags=["rapid_forgetting"],
        observation="Necesitas repasos distribuidos para reducir el olvido rápido.",
        support_hint="distribuir el repaso para no olvidar tan rápido",
    ),
    TechniqueDefinition(
        technique_id="interleaving",
        display_name="Interleaving",
        priority_order=8,
        rationale_tags=["difficulty_switching_topics"],
        observation="Alternar materias o tipos de ejercicio todavía te exige mucho ajuste mental.",
        support_hint="alternar materias y tipos de ejercicios sin perder el hilo",
    ),
)

QUESTIONS: tuple[QuestionDefinition, ...] = (
    QuestionDefinition(
        question_id="Q01",
        challenge_title="Encender el modo estudio",
        challenge_emoji="🚀",
        prompt=(
            "Cuando tengo actividades académicas pendientes, me cuesta iniciar y dar "
            "el primer paso para estudiar."
        ),
        technique_id="pomodoro",
        technique_weights=_weights("pomodoro"),
        measurement_tags=["start_friction", "procrastination"],
    ),
    QuestionDefinition(
        question_id="Q02",
        challenge_title="Mantener el foco",
        challenge_emoji="🎯",
        prompt=(
            "Cuando estudio, pierdo la concentración con facilidad, ya sea por "
            "distracciones externas como el celular o redes sociales, o porque mi "
            "mente se dispersa."
        ),
        technique_id="pomodoro",
        technique_weights=_weights("pomodoro"),
        measurement_tags=["distraction", "focus"],
    ),
    QuestionDefinition(
        question_id="Q03",
        challenge_title="Explicar para entender",
        challenge_emoji="🗣️",
        prompt=(
            "Después de estudiar un tema, suele pasarme que no logro explicarlo con "
            "mis propias palabras de forma clara."
        ),
        technique_id="feynman",
        technique_weights=_weights("feynman", "active_recall"),
        measurement_tags=["explanation_gap", "retrieval_gap"],
    ),
    QuestionDefinition(
        question_id="Q04",
        challenge_title="Recordar sin mirar",
        challenge_emoji="🧠",
        prompt=(
            "Cuando repaso, suelo limitarme a releer o subrayar, y después se me "
            "dificulta responder preguntas sin mirar los apuntes."
        ),
        technique_id="active_recall",
        technique_weights=_weights("active_recall"),
        measurement_tags=["passive_review_dependence", "retrieval_gap"],
    ),
    QuestionDefinition(
        question_id="Q05",
        challenge_title="Apuntes que sí ayuden",
        challenge_emoji="📝",
        prompt=(
            "Mis apuntes no me ayudan mucho a repasar después, porque me cuesta "
            "identificar ideas clave, conexiones entre temas, preguntas importantes "
            "o resúmenes claros."
        ),
        technique_id="cornell",
        technique_weights=_weights("cornell", "active_recall"),
        measurement_tags=["note_organization", "review_design"],
    ),
    QuestionDefinition(
        question_id="Q06",
        challenge_title="Ver el mapa completo",
        challenge_emoji="🗺️",
        prompt=(
            "Cuando un tema es amplio o teórico, me cuesta organizar las ideas, "
            "recordar sus significados principales y entender cómo se conectan entre sí."
        ),
        technique_id="mapas_conceptuales",
        technique_weights=_weights("mapas_conceptuales"),
        measurement_tags=["concept_connections", "theory_structure"],
    ),
    QuestionDefinition(
        question_id="Q07",
        challenge_title="Recordar detalles clave",
        challenge_emoji="🔑",
        prompt=(
            "Me cuesta recordar con precisión definiciones, listas, "
            "clasificaciones, pasos o términos importantes."
        ),
        technique_id="mnemotecnia",
        technique_weights=_weights("mnemotecnia"),
        measurement_tags=["exact_memory", "detail_recall"],
    ),
    QuestionDefinition(
        question_id="Q08",
        challenge_title="No olvidar tan rápido",
        challenge_emoji="⏳",
        prompt=(
            "Cuando pasan varios días sin repasar un tema, suelo olvidar gran parte "
            "de lo que había estudiado."
        ),
        technique_id="repeticion_espaciada",
        technique_weights=_weights("repeticion_espaciada"),
        measurement_tags=["rapid_forgetting", "review_decay"],
    ),
    QuestionDefinition(
        question_id="Q09",
        challenge_title="Equilibrar varias materias",
        challenge_emoji="⚖️",
        prompt=(
            "Cuando tengo varias materias o tipos de ejercicios, suelo dedicar "
            "demasiado tiempo a una sola y dejo las demás para después."
        ),
        technique_id="interleaving",
        technique_weights=_weights("interleaving"),
        measurement_tags=["subject_balance", "practice_variety"],
    ),
    QuestionDefinition(
        question_id="Q10",
        challenge_title="Cambiar de chip",
        challenge_emoji="🔄",
        prompt=(
            "Cuando cambio de una materia a otra, o de un tipo de ejercicio a otro, "
            "me cuesta reconocer qué procedimiento, fórmula o estrategia debo usar."
        ),
        technique_id="interleaving",
        technique_weights=_weights("interleaving"),
        measurement_tags=["difficulty_switching_topics", "strategy_switching"],
    ),
)

TIEBREAKER_QUESTIONS: tuple[TiebreakerQuestionDefinition, ...] = (
    TiebreakerQuestionDefinition(
        question_id="TB01",
        challenge_title="Pregunta adicional 1 · ¿Qué te frena más?",
        challenge_emoji="🚦",
        prompt="Cuando vas a estudiar, ¿qué sientes que más te frena en este momento?",
        options=[
            ChoiceOptionDefinition(
                option_id=1,
                label="Me cuesta empezar.",
                technique_boosts=_boost("pomodoro"),
            ),
            ChoiceOptionDefinition(
                option_id=2,
                label="Me cuesta concentrarme y sostener el foco.",
                technique_boosts=_boost("pomodoro"),
            ),
            ChoiceOptionDefinition(
                option_id=3,
                label="Me cuesta recordar sin mirar apuntes.",
                technique_boosts=_boost("active_recall"),
            ),
            ChoiceOptionDefinition(
                option_id=4,
                label="Olvido rápido si pasan varios días.",
                technique_boosts=_boost("repeticion_espaciada"),
            ),
        ],
    ),
    TiebreakerQuestionDefinition(
        question_id="TB02",
        challenge_title="Pregunta adicional 2 · ¿Dónde se enreda más el estudio?",
        challenge_emoji="🧩",
        prompt="¿En cuál de estas situaciones sientes más dificultad?",
        options=[
            ChoiceOptionDefinition(
                option_id=1,
                label="En temas amplios o teóricos, porque no veo cómo se conectan las ideas.",
                technique_boosts=_boost("mapas_conceptuales"),
            ),
            ChoiceOptionDefinition(
                option_id=2,
                label="En definiciones, listas, clasificaciones o términos exactos.",
                technique_boosts=_boost("mnemotecnia"),
            ),
            ChoiceOptionDefinition(
                option_id=3,
                label="En apuntes que luego no me sirven bien para repasar.",
                technique_boosts=_boost("cornell"),
            ),
            ChoiceOptionDefinition(
                option_id=4,
                label="En explicar con mis propias palabras lo que supuestamente entendí.",
                technique_boosts=_boost("feynman"),
            ),
        ],
    ),
    TiebreakerQuestionDefinition(
        question_id="TB03",
        challenge_title="Pregunta adicional 3 · Cambiar de estrategia",
        challenge_emoji="🔄",
        prompt="Cuando estudias varias materias o tipos de ejercicios, ¿qué te cuesta más?",
        options=[
            ChoiceOptionDefinition(
                option_id=1,
                label="Me quedo demasiado tiempo en una sola materia.",
                technique_boosts=_boost("interleaving"),
            ),
            ChoiceOptionDefinition(
                option_id=2,
                label="Me cuesta cambiar entre tipos de problemas o enfoques.",
                technique_boosts=_boost("interleaving"),
            ),
            ChoiceOptionDefinition(
                option_id=3,
                label="Prefiero releer antes que probar si realmente recuerdo.",
                technique_boosts=_boost("active_recall"),
            ),
            ChoiceOptionDefinition(
                option_id=4,
                label="Necesito una forma más clara de organizar el estudio por bloques.",
                technique_boosts=_boost("pomodoro"),
            ),
        ],
    ),
)

SIGNAL_RULES: tuple[SignalRuleDefinition, ...] = (
    SignalRuleDefinition(
        signal_id="start_and_focus_friction",
        label="Inicio y foco",
        message="Aparece dificultad para iniciar y sostener sesiones de estudio con foco.",
        question_ids=["Q01", "Q02"],
        threshold=2,
        min_matches=2,
        priority_order=1,
        related_techniques=["pomodoro"],
        weakness_tags=["procrastination", "distraction"],
    ),
    SignalRuleDefinition(
        signal_id="explanation_gap",
        label="Explicación poco sólida",
        message="Entender un tema no siempre se traduce en poder explicarlo con claridad.",
        question_ids=["Q03"],
        threshold=2,
        min_matches=1,
        priority_order=2,
        related_techniques=["feynman", "active_recall"],
        weakness_tags=["explanation_gap"],
    ),
    SignalRuleDefinition(
        signal_id="passive_review_dependence",
        label="Dependencia de relectura",
        message="Hay dependencia de relectura en lugar de recuperar la información activamente.",
        question_ids=["Q04"],
        threshold=2,
        min_matches=1,
        priority_order=3,
        related_techniques=["active_recall"],
        weakness_tags=["passive_review_dependence"],
    ),
    SignalRuleDefinition(
        signal_id="notes_not_helping",
        label="Apuntes poco útiles",
        message="Tus apuntes hoy no te están ayudando lo suficiente para repasar con rapidez.",
        question_ids=["Q05"],
        threshold=2,
        min_matches=1,
        priority_order=4,
        related_techniques=["cornell", "active_recall"],
        weakness_tags=["note_organization"],
    ),
    SignalRuleDefinition(
        signal_id="concept_connection_gap",
        label="Conectar ideas",
        message="En temas amplios o teóricos cuesta conectar ideas y ver la estructura completa.",
        question_ids=["Q06"],
        threshold=2,
        min_matches=1,
        priority_order=5,
        related_techniques=["mapas_conceptuales"],
        weakness_tags=["concept_connections"],
    ),
    SignalRuleDefinition(
        signal_id="exact_memory_gap",
        label="Memoria de detalle",
        message="Recordar definiciones, listas o pasos exactos requiere apoyo adicional.",
        question_ids=["Q07"],
        threshold=2,
        min_matches=1,
        priority_order=6,
        related_techniques=["mnemotecnia"],
        weakness_tags=["exact_memory"],
    ),
    SignalRuleDefinition(
        signal_id="rapid_forgetting",
        label="Olvido rápido",
        message="Si no vuelves sobre un tema en los días siguientes, tiendes a olvidarlo rápido.",
        question_ids=["Q08"],
        threshold=2,
        min_matches=1,
        priority_order=7,
        related_techniques=["repeticion_espaciada"],
        weakness_tags=["rapid_forgetting"],
    ),
    SignalRuleDefinition(
        signal_id="interleaving_friction",
        label="Alternar materias",
        message="Alternar materias o cambiar de tipo de problema todavía te exige mucho ajuste mental.",
        question_ids=["Q09", "Q10"],
        threshold=2,
        min_matches=1,
        priority_order=8,
        related_techniques=["interleaving"],
        weakness_tags=["difficulty_switching_topics"],
    ),
)

_QUESTION_BY_ID = {question.question_id: question for question in QUESTIONS}
_TECHNIQUE_BY_ID = {technique.technique_id: technique for technique in TECHNIQUES}
_TIEBREAKER_QUESTION_BY_ID = {
    question.question_id: question for question in TIEBREAKER_QUESTIONS
}


def get_question_by_index(index: int) -> QuestionDefinition:
    return QUESTIONS[index]


def get_question_by_id(question_id: str) -> QuestionDefinition:
    return _QUESTION_BY_ID[question_id]


def get_questions() -> tuple[QuestionDefinition, ...]:
    return QUESTIONS


def get_question_count() -> int:
    return len(QUESTIONS)


def get_techniques() -> tuple[TechniqueDefinition, ...]:
    return TECHNIQUES


def get_technique(technique_id: str) -> TechniqueDefinition:
    return _TECHNIQUE_BY_ID[technique_id]


def get_questions_for_technique(technique_id: str) -> list[QuestionDefinition]:
    return [
        question
        for question in QUESTIONS
        if any(weight.technique_id == technique_id for weight in question.technique_weights)
    ]


def get_signal_rules() -> tuple[SignalRuleDefinition, ...]:
    return SIGNAL_RULES


def get_intro_prompt() -> str:
    return RADAR_INTRO


def get_question_options_prompt() -> str:
    return QUESTION_OPTIONS_PROMPT


def get_invalid_answer_prompt() -> str:
    return INVALID_ANSWER_PROMPT


def get_microfeedback(answered_count: int) -> str | None:
    return MICROFEEDBACK_BY_ANSWERED_COUNT.get(answered_count)


def get_tiebreaker_questions() -> tuple[TiebreakerQuestionDefinition, ...]:
    return TIEBREAKER_QUESTIONS


def get_tiebreaker_question_count() -> int:
    return len(TIEBREAKER_QUESTIONS)


def get_tiebreaker_question_by_index(index: int) -> TiebreakerQuestionDefinition:
    return TIEBREAKER_QUESTIONS[index]


def get_tiebreaker_question_by_id(question_id: str) -> TiebreakerQuestionDefinition:
    return _TIEBREAKER_QUESTION_BY_ID[question_id]


def get_tiebreaker_intro_prompt() -> str:
    return TIEBREAKER_INTRO


def get_tiebreaker_invalid_answer_prompt() -> str:
    return TIEBREAKER_INVALID_ANSWER_PROMPT


def get_tiebreaker_microfeedback(answered_count: int) -> str | None:
    return TIEBREAKER_MICROFEEDBACK_BY_ANSWERED_COUNT.get(answered_count)


def get_tiebreaker_max_boost_for_technique(technique_id: str) -> int:
    """Retorna el maximo boost posible para una tecnica en el subbloque extra."""

    total = 0
    for question in TIEBREAKER_QUESTIONS:
        per_question = 0
        for option in question.options:
            option_boost = sum(
                boost.boost
                for boost in option.technique_boosts
                if boost.technique_id == technique_id
            )
            per_question = max(per_question, option_boost)
        total += per_question
    return total
