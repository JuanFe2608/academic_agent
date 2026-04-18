"""Tests for LLM-backed grounded RAG answer synthesis."""

from __future__ import annotations

from types import SimpleNamespace

from rag.prompting import (
    LlmGroundedAnswerGenerator,
    build_grounded_study_recommendation_result,
    render_grounded_answer_prompt,
)
from rag.prompting.context_package import build_grounded_prompt_context
from rag.retrieval.models import (
    GroundedContextPackage,
    QueryUnderstanding,
    RagCitation,
    RagRetrievedChunk,
)
from schemas.rag import StudyRecommendationQuery


class _FakeAnswerGenerator:
    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.calls = []

    def generate(self, *, package, prompt_context):
        self.calls.append((package, prompt_context))
        return self.answer


class _FakeLlm:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.response)


def test_grounded_result_uses_llm_synthesis_when_generator_is_available() -> None:
    package = _package()
    generator = _FakeAnswerGenerator(
        "Pomodoro te conviene para iniciar con bloques cortos y pausas. "
        "Usalo con una tarea concreta y revisa al final que aprendiste."
    )

    result = build_grounded_study_recommendation_result(
        package,
        answer_generator=generator,
    )

    assert result.answer.startswith("Pomodoro te conviene")
    assert result.answer != package.selected_chunks[0].content
    assert result.source_chunks == ["technique.pomodoro::answer"]
    assert "answer:llm_synthesis" in result.groundedness_notes
    assert "answer:deterministic_template" not in result.groundedness_notes
    assert generator.calls[0][0] is package
    assert generator.calls[0][1].primary_text


def test_grounded_result_falls_back_to_template_when_llm_synthesis_is_empty() -> None:
    package = _package()

    result = build_grounded_study_recommendation_result(
        package,
        answer_generator=_FakeAnswerGenerator(None),
    )

    assert "Pomodoro organiza" in result.answer
    assert "answer:deterministic_template" in result.groundedness_notes


def test_llm_prompt_contains_user_query_and_marks_chunks_as_evidence() -> None:
    package = _package()
    prompt_context = build_grounded_prompt_context(package)

    prompt = render_grounded_answer_prompt(
        package=package,
        prompt_context=prompt_context,
    )

    assert "PREGUNTA DEL USUARIO" in prompt
    assert "Que hago si procrastino al estudiar?" in prompt
    assert "CONTEXTO RAG RECUPERADO" in prompt
    assert "chunk_id=technique.pomodoro::answer" in prompt
    assert "no como respuesta directa" in prompt


def test_llm_generator_invokes_model_and_sanitizes_answer_prefix() -> None:
    package = _package()
    prompt_context = build_grounded_prompt_context(package)
    llm = _FakeLlm("Respuesta final: Usa Pomodoro en un bloque corto y cierra verificando.")
    generator = LlmGroundedAnswerGenerator(llm=llm)

    answer = generator.generate(package=package, prompt_context=prompt_context)

    assert answer == "Usa Pomodoro en un bloque corto y cierra verificando."
    assert "Que hago si procrastino al estudiar?" in llm.prompts[0]


def _package() -> GroundedContextPackage:
    chunk = RagRetrievedChunk(
        chunk_id="technique.pomodoro::answer",
        document_id="technique.pomodoro",
        knowledge_type="technique",
        document_type="study_technique",
        entity_id="pomodoro",
        section_title="Respuesta corta reusable para RAG",
        chunk_kind="answer_ready",
        content=(
            "## Respuesta corta reusable para RAG\n"
            "Pomodoro organiza el estudio en bloques cortos con pausas. "
            "Es util cuando procrastinas o te distraes facil."
        ),
        metadata={
            "confidence_level": "alto",
            "evidence_level": "alto",
            "source_path": "raw/techniques/tecnica_pomodoro_rag.md",
        },
        token_estimate=30,
        final_score=3.5,
    )
    return GroundedContextPackage(
        query=StudyRecommendationQuery(
            query_text="Que hago si procrastino al estudiar?",
            intent="recommend_technique",
            student_signals=["procrastination"],
            top_techniques=["pomodoro"],
        ),
        understanding=QueryUnderstanding(
            intent="recommend_technique",
            query_text="Que hago si procrastino al estudiar?",
            detected_entities=["pomodoro"],
            detected_techniques=["pomodoro"],
            detected_signals=["procrastination"],
        ),
        selected_chunks=[chunk],
        relations=[],
        citations=[
            RagCitation(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                section_title=chunk.section_title,
                source_path=str(chunk.metadata["source_path"]),
            )
        ],
        groundedness_notes=["sources:1"],
    )
