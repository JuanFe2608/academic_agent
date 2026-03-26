"""Catalogo versionado de preguntas y tecnicas de estudio."""

from __future__ import annotations

from agents.support.personalization.models import QuestionDefinition, TechniqueDefinition

QUESTIONNAIRE_VERSION = "v1"
SCORING_VERSION = "v1"

LIKERT_OPTIONS = {
    0: "Nunca o casi nunca",
    1: "A veces",
    2: "Frecuentemente",
    3: "Casi siempre",
}

TECHNIQUES: tuple[TechniqueDefinition, ...] = (
    TechniqueDefinition(
        technique_id="pomodoro",
        display_name="Pomodoro",
        priority_order=1,
        rationale_tags=["procrastination", "distraction"],
        observation="Dificultades de concentracion o procrastinacion.",
    ),
    TechniqueDefinition(
        technique_id="feynman",
        display_name="Feynman",
        priority_order=2,
        rationale_tags=["explanation_gap"],
        observation="Entiende parcialmente, pero le cuesta explicar con claridad.",
    ),
    TechniqueDefinition(
        technique_id="active_recall",
        display_name="Active Recall",
        priority_order=3,
        rationale_tags=["passive_review_dependence"],
        observation="Depende demasiado de releer y le cuesta recuperar informacion sin apoyo.",
    ),
    TechniqueDefinition(
        technique_id="cornell",
        display_name="Metodo Cornell",
        priority_order=4,
        rationale_tags=["note_organization"],
        observation="Necesita mejorar la organizacion y el repaso de sus apuntes.",
    ),
    TechniqueDefinition(
        technique_id="mapas_conceptuales",
        display_name="Mapas conceptuales",
        priority_order=5,
        rationale_tags=["concept_connections"],
        observation="Necesita visualizar relaciones y jerarquias entre conceptos.",
    ),
    TechniqueDefinition(
        technique_id="mnemotecnia",
        display_name="Mnemotecnia",
        priority_order=6,
        rationale_tags=["exact_memory"],
        observation="Presenta dificultad para recordar informacion puntual o exacta.",
    ),
    TechniqueDefinition(
        technique_id="repeticion_espaciada",
        display_name="Repeticion espaciada",
        priority_order=7,
        rationale_tags=["rapid_forgetting"],
        observation="Olvida con rapidez si no distribuye repasos en el tiempo.",
    ),
    TechniqueDefinition(
        technique_id="interleaving",
        display_name="Interleaving",
        priority_order=8,
        rationale_tags=["difficulty_switching_topics"],
        observation="Le cuesta alternar materias o tipos de ejercicios de forma eficiente.",
    ),
)

QUESTIONS: tuple[QuestionDefinition, ...] = (
    QuestionDefinition(
        question_id="Q01",
        prompt="Me cuesta empezar a estudiar, aunque se que tengo cosas pendientes.",
        technique_id="pomodoro",
    ),
    QuestionDefinition(
        question_id="Q02",
        prompt="Cuando estudio, me distraigo facilmente con el celular, redes sociales o interrupciones.",
        technique_id="pomodoro",
    ),
    QuestionDefinition(
        question_id="Q03",
        prompt="Despues de estudiar un tema, siento que lo entendi, pero me cuesta explicarlo con mis propias palabras.",
        technique_id="feynman",
    ),
    QuestionDefinition(
        question_id="Q04",
        prompt="Cuando repaso, suelo releer o subrayar, pero me cuesta responder preguntas sin mirar los apuntes.",
        technique_id="active_recall",
    ),
    QuestionDefinition(
        question_id="Q05",
        prompt="Mis apuntes suelen quedar desordenados y despues no se bien como repasarlos.",
        technique_id="cornell",
    ),
    QuestionDefinition(
        question_id="Q06",
        prompt="Cuando un tema es amplio o teorico, me cuesta ver como se conectan las ideas entre si.",
        technique_id="mapas_conceptuales",
    ),
    QuestionDefinition(
        question_id="Q07",
        prompt="Me cuesta recordar listas, clasificaciones, definiciones, formulas o pasos exactos.",
        technique_id="mnemotecnia",
    ),
    QuestionDefinition(
        question_id="Q08",
        prompt="Si no repaso en varios dias, olvido rapido lo que habia estudiado.",
        technique_id="repeticion_espaciada",
    ),
    QuestionDefinition(
        question_id="Q09",
        prompt="Cuando tengo varias materias o diferentes tipos de ejercicios, estudio una sola por mucho tiempo y luego confundo las demas.",
        technique_id="interleaving",
    ),
    QuestionDefinition(
        question_id="Q10",
        prompt="Me cuesta alternar entre temas o tipos de problemas dentro de una misma sesion de estudio.",
        technique_id="interleaving",
    ),
)

_QUESTION_BY_ID = {question.question_id: question for question in QUESTIONS}
_TECHNIQUE_BY_ID = {technique.technique_id: technique for technique in TECHNIQUES}


def get_question_by_index(index: int) -> QuestionDefinition:
    """Retorna la pregunta en una posicion fija del cuestionario."""

    return QUESTIONS[index]


def get_question_by_id(question_id: str) -> QuestionDefinition:
    """Retorna una pregunta por identificador."""

    return _QUESTION_BY_ID[question_id]


def get_questions() -> tuple[QuestionDefinition, ...]:
    """Retorna el catalogo completo de preguntas."""

    return QUESTIONS


def get_question_count() -> int:
    """Retorna la cantidad fija de preguntas del cuestionario."""

    return len(QUESTIONS)


def get_techniques() -> tuple[TechniqueDefinition, ...]:
    """Retorna el catalogo completo de tecnicas."""

    return TECHNIQUES


def get_technique(technique_id: str) -> TechniqueDefinition:
    """Retorna la definicion de una tecnica por identificador."""

    return _TECHNIQUE_BY_ID[technique_id]


def get_questions_for_technique(technique_id: str) -> list[QuestionDefinition]:
    """Retorna las preguntas asociadas a una tecnica."""

    return [question for question in QUESTIONS if question.technique_id == technique_id]

