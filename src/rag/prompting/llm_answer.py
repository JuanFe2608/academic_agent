"""LLM synthesis for grounded RAG answers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from bootstrap.settings import RagSettings
from integrations.ai import maybe_get_llm
from rag.retrieval.models import GroundedContextPackage, RagRetrievedChunk

from .context_package import (
    GroundedPromptContext,
    clean_chunk_text,
    format_entity_name,
    summarize_chunk_for_prompt,
)


class GroundedAnswerGenerator(Protocol):
    """Boundary for turning retrieved evidence into a final user answer."""

    def generate(
        self,
        *,
        package: GroundedContextPackage,
        prompt_context: GroundedPromptContext,
    ) -> str | None: ...


@dataclass(frozen=True)
class LlmGroundedAnswerGenerator:
    """Generate a user-facing answer with an LLM using RAG context as evidence."""

    llm: Any
    max_context_chars: int = 5200
    max_answer_chars: int = 1600

    def generate(
        self,
        *,
        package: GroundedContextPackage,
        prompt_context: GroundedPromptContext,
    ) -> str | None:
        """Invoke the configured chat model and return sanitized plain text."""

        if not package.has_sufficient_sources:
            prompt = render_no_sources_prompt(package)
        else:
            prompt = render_grounded_answer_prompt(
                package=package,
                prompt_context=prompt_context,
                max_context_chars=self.max_context_chars,
            )
        response = self.llm.invoke(prompt)
        text = _response_to_text(response)
        return _sanitize_answer(text, max_chars=self.max_answer_chars)


def build_llm_grounded_answer_generator_from_env(
    settings: RagSettings,
) -> LlmGroundedAnswerGenerator | None:
    """Build the runtime answer generator when a chat LLM is configured."""

    try:
        llm = maybe_get_llm(temperature=settings.answer_temperature)
    except Exception:  # noqa: BLE001 - missing/invalid LLM config must not break RAG
        return None
    if llm is None:
        return None
    return LlmGroundedAnswerGenerator(llm=llm)


def render_grounded_answer_prompt(
    *,
    package: GroundedContextPackage,
    prompt_context: GroundedPromptContext,
    max_context_chars: int = 5200,
) -> str:
    """Render the prompt sent to the LLM synthesis step."""

    query = package.query
    understanding = package.understanding
    context_blocks = _context_blocks(package.selected_chunks)
    relation_blocks = _relation_blocks(package)
    caution_text = "\n".join(f"- {caution}" for caution in prompt_context.cautions) or "- Ninguna."
    support_text = (
        "\n".join(f"- {fact}" for fact in prompt_context.supporting_facts)
        or "- No hay hechos adicionales."
    )
    detected_entities = (
        ", ".join(format_entity_name(entity) for entity in understanding.detected_entities)
        or "sin entidad explicita"
    )
    student_signals = ", ".join(understanding.detected_signals) or "sin senales explicitas"
    context_text = _fit_text("\n\n".join(context_blocks), max_chars=max_context_chars)
    relations_text = _fit_text("\n".join(relation_blocks), max_chars=1200) or "- Ninguna."

    return (
        "Eres LARA, un agente academico especializado en metodos y tecnicas de estudio.\n\n"
        "REGLAS:\n"
        "- Responde en espanol claro y natural.\n"
        "- Usa el CONTEXTO RAG como punto de partida si contiene informacion relevante "
        "para la pregunta. Si no la tiene o es insuficiente, responde con tu propio "
        "conocimiento academico sobre tecnicas y metodos de estudio.\n"
        "- Trata los chunks como evidencia y contexto, no como respuesta directa.\n"
        "- Sintetiza y adapta, no copies chunks literalmente.\n"
        "- No menciones IDs de chunks ni nombres de archivos.\n"
        "- No inventes estudios ni fuentes citadas. Si puedes usar conocimiento general "
        "de pedagogia y tecnicas de aprendizaje.\n"
        "- Mantente en el dominio: gestion academica, metodos de estudio, planificacion.\n"
        "- Respuesta breve: 2 a 5 frases + siguiente paso accionable si aplica.\n"
        "- Si el contexto RAG es relevante, usalo. Si no, ignoralo y responde igual.\n\n"
        "PREGUNTA DEL USUARIO:\n"
        f"{query.query_text.strip() or '(sin pregunta textual)'}\n\n"
        "ENTENDIMIENTO DEL QUERY:\n"
        f"- intencion: {understanding.intent}\n"
        f"- entidades detectadas: {detected_entities}\n"
        f"- senales del estudiante: {student_signals}\n"
        f"- materia: {query.subject_name or 'no indicada'}\n"
        f"- tipo de actividad: {query.activity_type or 'no indicado'}\n"
        f"- tiempo disponible: {query.available_minutes or 'no indicado'}\n\n"
        "CONTEXTO RAG RECUPERADO:\n"
        f"{context_text or '- No hay contexto recuperado.'}\n\n"
        "HECHOS DE APOYO EXTRAIDOS:\n"
        f"{support_text}\n\n"
        "CAUTELAS / CONTRAINDICACIONES:\n"
        f"{caution_text}\n\n"
        "RELACIONES RAG RELEVANTES:\n"
        f"{relations_text}\n\n"
        "RESPUESTA FINAL:"
    )


def render_no_sources_prompt(package: GroundedContextPackage) -> str:
    """Prompt para cuando el RAG no retornó fuentes suficientes."""

    query = package.query
    understanding = package.understanding
    return (
        "Eres LARA, un agente academico especializado en metodos y tecnicas de estudio.\n\n"
        "No se encontro contexto especifico en la base de conocimiento. "
        "Responde desde tu conocimiento general sobre el tema academico preguntado, "
        "dentro del dominio de metodos de estudio y planificacion academica.\n\n"
        "REGLAS:\n"
        "- Responde en espanol claro y natural.\n"
        "- Usa tu conocimiento general de pedagogia y tecnicas de aprendizaje.\n"
        "- No inventes estudios ni fuentes citadas.\n"
        "- Mantente en el dominio: gestion academica, metodos de estudio, planificacion.\n"
        "- Respuesta breve: 2 a 5 frases + siguiente paso accionable si aplica.\n\n"
        "PREGUNTA DEL USUARIO:\n"
        f"{query.query_text.strip() or '(sin pregunta textual)'}\n\n"
        f"INTENCION DETECTADA: {understanding.intent}\n\n"
        "RESPUESTA:"
    )


def _context_blocks(chunks: list[RagRetrievedChunk]) -> list[str]:
    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        text = summarize_chunk_for_prompt(chunk, max_chars=900)
        blocks.append(
            f"[{index}] chunk_id={chunk.chunk_id}; entidad={format_entity_name(chunk.entity_id)}; "
            f"tipo={chunk.chunk_kind}; score={chunk.final_score:.3f}\n{text}"
        )
    return blocks


def _relation_blocks(package: GroundedContextPackage) -> list[str]:
    blocks: list[str] = []
    for relation in package.relations[:12]:
        source = format_entity_name(relation.source_id)
        target = format_entity_name(relation.target_id)
        evidence = clean_chunk_text(relation.evidence_text, max_chars=220)
        blocks.append(
            f"- {source} {relation.relation_type} {target}: {evidence}"
        )
    return blocks


def _response_to_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        value = content.get("text") or content.get("content")
        return _response_to_text(value)
    if isinstance(content, (list, tuple)):
        return "\n".join(_response_to_text(item).strip() for item in content).strip()
    return str(content)


def _sanitize_answer(text: str, *, max_chars: int) -> str | None:
    answer = text.strip()
    if not answer:
        return None
    answer = re.sub(r"^```(?:\w+)?", "", answer).strip()
    answer = re.sub(r"```$", "", answer).strip()
    answer = re.sub(r"^(respuesta final|respuesta)\s*:\s*", "", answer, flags=re.I).strip()
    answer = re.sub(r"[ \t]+", " ", answer)
    answer = re.sub(r"\n{3,}", "\n\n", answer).strip()
    if not answer:
        return None
    return _fit_text(answer, max_chars=max_chars)


def _fit_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cutoff = text.rfind(".", 0, max_chars)
    if cutoff < int(max_chars * 0.55):
        cutoff = text.rfind("\n", 0, max_chars)
    if cutoff < int(max_chars * 0.55):
        cutoff = max_chars
    return text[:cutoff].rstrip(" .,;:") + "..."


__all__ = [
    "GroundedAnswerGenerator",
    "LlmGroundedAnswerGenerator",
    "build_llm_grounded_answer_generator_from_env",
    "render_grounded_answer_prompt",
]
