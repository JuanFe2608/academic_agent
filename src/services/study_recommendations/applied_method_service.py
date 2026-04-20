"""Aplicacion operativa de metodos de estudio a actividades concretas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from rag.ingestion.normalization import (
    normalize_signals,
    normalize_technique_id,
    slugify_identifier,
)
from schemas.rag import StudyRecommendationQuery, StudyRecommendationResult


class StudyRecommendationBackend(Protocol):
    """Frontera minima consumida por el servicio aplicado."""

    def answer_query(self, query: StudyRecommendationQuery) -> StudyRecommendationResult: ...


@dataclass(frozen=True)
class AppliedStudyMethodRequest:
    """Contexto academico necesario para aplicar un metodo a una actividad."""

    subject_name: str | None = None
    subject_type: str | None = None
    activity_type: str | None = None
    activity_title: str | None = None
    available_minutes: int | None = None
    urgency: str | None = None
    difficulty: str | int | None = None
    student_signals: list[str] = field(default_factory=list)
    top_techniques: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AppliedStudyMethodResult:
    """Resultado estructurado listo para plan, sesion o respuesta directa."""

    applied: bool
    status: str
    subject_name: str | None = None
    activity_type: str | None = None
    activity_title: str | None = None
    selected_technique_id: str | None = None
    selected_method_id: str | None = None
    steps: list[str] = field(default_factory=list)
    summary: str = ""
    source_chunks: list[str] = field(default_factory=list)
    relations_used: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    confidence: str = "baja"
    grounded_answer: str = ""
    error_code: str | None = None
    detail: str | None = None

    def to_rule_payload(self) -> dict[str, object]:
        """Serializa una version estable para `study_plan.rules`."""

        return {
            "status": self.status,
            "subject_name": self.subject_name,
            "activity_type": self.activity_type,
            "activity_title": self.activity_title,
            "selected_technique_id": self.selected_technique_id,
            "selected_method_id": self.selected_method_id,
            "steps": list(self.steps),
            "summary": self.summary,
            "source_chunks": list(self.source_chunks),
            "relations_used": list(self.relations_used),
            "cautions": list(self.cautions),
            "confidence": self.confidence,
        }


class AppliedStudyMethodService:
    """Convierte recomendaciones RAG/Radar en pasos accionables por actividad."""

    def __init__(self, recommendation_service: StudyRecommendationBackend) -> None:
        self.recommendation_service = recommendation_service

    def apply_to_activity(
        self,
        request: AppliedStudyMethodRequest | dict[str, object],
    ) -> AppliedStudyMethodResult:
        """Genera pasos concretos solo si hay soporte en fuentes RAG."""

        normalized_request = ensure_applied_method_request(request)
        top_techniques = _normalize_techniques(normalized_request.top_techniques)
        signals = normalize_signals(normalized_request.student_signals)
        activity_type = _normalize_activity_type(normalized_request.activity_type)
        selected_method_id = _select_method_id(normalized_request, activity_type=activity_type)
        primary_technique_id = top_techniques[0] if top_techniques else None

        if not selected_method_id and not primary_technique_id:
            return _not_applied(
                normalized_request,
                activity_type=activity_type,
                status="skipped_missing_profile_context",
                error_code="missing_profile_context",
                detail="No hay tecnica Radar ni metodo de actividad para aplicar.",
            )

        query = StudyRecommendationQuery(
            query_text=_build_query_text(
                request=normalized_request,
                activity_type=activity_type,
                selected_method_id=selected_method_id,
                primary_technique_id=primary_technique_id,
            ),
            intent="adapt_method" if selected_method_id else "session_guidance",
            student_signals=signals,
            top_techniques=top_techniques,
            subject_name=normalized_request.subject_name,
            subject_type=slugify_identifier(normalized_request.subject_type or "") or None,
            activity_type=activity_type,
            available_minutes=normalized_request.available_minutes,
            difficulty=_optional_str(normalized_request.difficulty),
            urgency=_optional_str(normalized_request.urgency),
            max_chunks=5,
        )
        try:
            recommendation = self.recommendation_service.answer_query(query)
        except Exception as exc:  # noqa: BLE001 - no se debe romper el flujo principal
            return _not_applied(
                normalized_request,
                activity_type=activity_type,
                status="error",
                selected_method_id=selected_method_id,
                selected_technique_id=primary_technique_id,
                error_code="study_recommendation_error",
                detail=exc.__class__.__name__,
            )

        supported_method = _supported_entity(
            selected_method_id,
            recommendation.source_chunks,
            knowledge_type="study_method",
        )
        supported_technique = _first_supported_technique(
            [
                primary_technique_id,
                *list(recommendation.recommended_techniques or []),
                *top_techniques,
            ],
            recommendation.source_chunks,
        )
        if not supported_method and not supported_technique:
            return _not_applied(
                normalized_request,
                activity_type=activity_type,
                status="skipped_missing_grounding",
                selected_method_id=selected_method_id,
                selected_technique_id=primary_technique_id,
                error_code="missing_grounded_sources",
                detail="La respuesta RAG no trajo fuentes para el metodo o tecnica seleccionada.",
                recommendation=recommendation,
            )

        effective_method_id = selected_method_id if supported_method else None
        effective_technique_id = supported_technique
        steps = _build_steps(
            request=normalized_request,
            activity_type=activity_type,
            selected_method_id=effective_method_id,
            selected_technique_id=effective_technique_id,
        )
        return AppliedStudyMethodResult(
            applied=True,
            status="generated",
            subject_name=normalized_request.subject_name,
            activity_type=activity_type,
            activity_title=normalized_request.activity_title,
            selected_technique_id=effective_technique_id,
            selected_method_id=effective_method_id,
            steps=steps,
            summary=_build_summary(
                request=normalized_request,
                activity_type=activity_type,
                selected_method_id=effective_method_id,
                selected_technique_id=effective_technique_id,
            ),
            source_chunks=list(recommendation.source_chunks),
            relations_used=list(recommendation.relations_used),
            cautions=list(recommendation.cautions[:2]),
            confidence=recommendation.confidence,
            grounded_answer=_clean_text(recommendation.answer),
        )


def ensure_applied_method_request(
    request: AppliedStudyMethodRequest | dict[str, object],
) -> AppliedStudyMethodRequest:
    if isinstance(request, AppliedStudyMethodRequest):
        return request
    data = dict(request or {})
    return AppliedStudyMethodRequest(
        subject_name=_optional_str(data.get("subject_name")),
        subject_type=_optional_str(data.get("subject_type")),
        activity_type=_optional_str(data.get("activity_type")),
        activity_title=_optional_str(data.get("activity_title")),
        available_minutes=_optional_int(data.get("available_minutes")),
        urgency=_optional_str(data.get("urgency")),
        difficulty=data.get("difficulty"),
        student_signals=[str(value) for value in list(data.get("student_signals") or [])],
        top_techniques=[str(value) for value in list(data.get("top_techniques") or [])],
    )


def build_applied_method_request_from_text(
    text: str | None,
    *,
    study_profile: dict[str, object] | None = None,
) -> AppliedStudyMethodRequest:
    """Extrae contexto ligero para respuestas directas de metodo aplicado."""

    profile = dict(study_profile or {})
    raw = str(text or "")
    normalized = slugify_identifier(raw)
    activity_type = _detect_activity_type(normalized)
    return AppliedStudyMethodRequest(
        subject_name=_extract_subject_name(raw, activity_type=activity_type),
        subject_type=_detect_subject_type(normalized),
        activity_type=activity_type,
        activity_title=_extract_activity_title(raw, activity_type=activity_type),
        available_minutes=_extract_available_minutes(normalized),
        urgency=_detect_urgency(normalized),
        difficulty=_extract_difficulty(normalized),
        student_signals=[str(value) for value in list(profile.get("weakness_tags") or [])],
        top_techniques=[str(value) for value in list(profile.get("top_techniques") or [])],
    )


def is_applied_study_method_message(text: str | None) -> bool:
    """Detecta preguntas sobre como abordar una actividad academica."""

    normalized = slugify_identifier(str(text or ""))
    if not normalized:
        return False
    has_activity = bool(_detect_activity_type(normalized))
    if any(term in normalized for term in _DIRECT_GUIDANCE_TERMS):
        return bool(has_activity or any(term in normalized for term in _STUDY_TERMS))
    if has_activity and any(term in normalized for term in _METHOD_REQUEST_PATTERNS):
        return True
    return False


def format_applied_study_method_for_user(result: AppliedStudyMethodResult) -> str:
    """Renderiza el resultado aplicado para WhatsApp o el nodo directo."""

    if not result.applied:
        return (
            "No pude convertir esa consulta en pasos confiables todavia. "
            "Dime la materia, tipo de actividad y tiempo disponible."
        )
    lines = [result.summary]
    if result.steps:
        lines.append("Pasos sugeridos:")
        lines.extend(f"{index}. {step}" for index, step in enumerate(result.steps, start=1))
    if result.cautions:
        lines.append(f"Cuidado: {result.cautions[0]}")
    return "\n".join(line for line in lines if line)


def build_applied_study_method_service(
    recommendation_service: StudyRecommendationBackend,
) -> AppliedStudyMethodService:
    return AppliedStudyMethodService(recommendation_service)


_DIRECT_GUIDANCE_TERMS = {
    "como_estudio",
    "como_estudiar",
    "como_preparo",
    "como_preparar",
    "como_abordo",
    "como_abordar",
    "como_divido",
    "como_dividir",
    "paso_a_paso",
    "guia",
    "guiame",
    "plan_para_estudiar",
    "ayudame_a_estudiar",
}
_METHOD_REQUEST_PATTERNS = {
    "que_metodo",
    "cual_metodo",
    "metodo_uso",
    "metodo_usar",
    "metodo_conviene",
    "que_estrategia",
    "cual_estrategia",
    "estrategia_uso",
    "estrategia_usar",
    "estrategia_conviene",
}
_STUDY_TERMS = {"estudiar", "repasar", "preparar", "abordar", "dividir", "sintetizar"}
_NUMERIC_TERMS = {
    "calculo",
    "fisica",
    "estadistica",
    "algebra",
    "matematica",
    "matematicas",
    "numerico",
    "numerica",
    "ejercicio",
    "ejercicios",
    "problema",
    "problemas",
    "procedimiento",
}
_READING_TERMS = {"lectura", "leer", "sintesis", "resumen", "articulo", "capitulo", "texto"}
_ACTIVITY_TYPE_ALIASES: dict[str, set[str]] = {
    "parcial": {"parcial", "examen", "evaluacion", "final"},
    "quiz": {"quiz", "quices", "prueba_corta", "control"},
    "taller": {"taller", "laboratorio", "practica"},
    "tarea": {"tarea", "deber"},
    "entrega": {"entrega", "trabajo"},
    "exposicion": {"exposicion", "presentacion"},
    "proyecto": {"proyecto"},
    "lectura": {"lectura", "sintesis", "resumen"},
    "repaso_semanal": {"repaso_semanal", "repaso"},
}
_METHOD_BY_ACTIVITY = {
    "parcial": "metodo_parcial_teorico",
    "quiz": "metodo_parcial_teorico",
    "lectura": "metodo_lectura_y_sintesis",
    "repaso_semanal": "metodo_repaso_semanal",
}
_METHOD_LABELS = {
    "metodo_evaluacion_numerica_breve": "metodo de evaluacion numerica breve",
    "metodo_lectura_y_sintesis": "metodo de lectura y sintesis",
    "metodo_parcial_teorico": "metodo para parcial teorico",
    "metodo_repaso_semanal": "metodo de repaso semanal",
}
_TECHNIQUE_LABELS = {
    "active_recall": "recuperacion activa",
    "cornell": "Cornell",
    "feynman": "Feynman",
    "interleaving": "interleaving",
    "mapas_conceptuales": "mapas conceptuales",
    "mnemotecnia": "mnemotecnia",
    "pomodoro": "Pomodoro",
    "repeticion_espaciada": "repeticion espaciada",
}


def _select_method_id(
    request: AppliedStudyMethodRequest,
    *,
    activity_type: str | None,
) -> str | None:
    subject_type = slugify_identifier(request.subject_type or "")
    context = slugify_identifier(
        " ".join(
            [
                str(request.subject_name or ""),
                str(request.subject_type or ""),
                str(request.activity_type or ""),
                str(request.activity_title or ""),
            ]
        )
    )
    numeric_context = subject_type not in {"teorica", "teorico", "conceptual"} and _contains_any(
        context,
        _NUMERIC_TERMS,
    )
    if activity_type in {"taller", "tarea"} and numeric_context:
        return "metodo_evaluacion_numerica_breve"
    if activity_type in {"parcial", "quiz"} and numeric_context:
        return "metodo_evaluacion_numerica_breve"
    if activity_type in {"entrega", "proyecto", "exposicion"}:
        return "metodo_lectura_y_sintesis"
    if activity_type == "taller":
        return "metodo_evaluacion_numerica_breve"
    if activity_type == "tarea" and _contains_any(context, _READING_TERMS):
        return "metodo_lectura_y_sintesis"
    return _METHOD_BY_ACTIVITY.get(str(activity_type or ""))


def _build_query_text(
    *,
    request: AppliedStudyMethodRequest,
    activity_type: str | None,
    selected_method_id: str | None,
    primary_technique_id: str | None,
) -> str:
    parts = ["Como aplicar"]
    if selected_method_id:
        parts.append(_METHOD_LABELS.get(selected_method_id, selected_method_id.replace("_", " ")))
    elif primary_technique_id:
        parts.append(_TECHNIQUE_LABELS.get(primary_technique_id, primary_technique_id))
    if primary_technique_id:
        parts.append(f"con tecnica Radar {_TECHNIQUE_LABELS.get(primary_technique_id, primary_technique_id)}")
    if activity_type:
        parts.append(f"para {activity_type}")
    if request.subject_name:
        parts.append(f"de {request.subject_name}")
    if request.available_minutes:
        parts.append(f"en {request.available_minutes} minutos")
    if request.urgency:
        parts.append(f"con urgencia {request.urgency}")
    return " ".join(parts) + "?"


def _build_steps(
    *,
    request: AppliedStudyMethodRequest,
    activity_type: str | None,
    selected_method_id: str | None,
    selected_technique_id: str | None,
) -> list[str]:
    minutes = _bounded_minutes(request.available_minutes)
    steps = [
        _goal_step(request, activity_type=activity_type),
        _method_step(selected_method_id, activity_type=activity_type),
        _technique_step(selected_technique_id, minutes=minutes),
        _verification_step(activity_type=activity_type),
    ]
    return [step for step in steps if step][:4]


def _goal_step(request: AppliedStudyMethodRequest, *, activity_type: str | None) -> str:
    label = _activity_label(activity_type)
    subject = f" de {request.subject_name}" if request.subject_name else ""
    if request.available_minutes:
        return f"Define una meta verificable para el {label}{subject} y reserva {request.available_minutes} min para trabajar solo en eso."
    return f"Define una meta verificable para el {label}{subject}: tema, producto esperado y criterio de cierre."


def _method_step(selected_method_id: str | None, *, activity_type: str | None) -> str:
    if selected_method_id == "metodo_evaluacion_numerica_breve":
        return "Clasifica los ejercicios por tipo, resuelve uno guiado y luego uno sin mirar el procedimiento."
    if selected_method_id == "metodo_lectura_y_sintesis":
        return "Divide el material en tramos cortos, extrae ideas clave y escribe una sintesis propia antes de pulir el producto."
    if selected_method_id == "metodo_parcial_teorico":
        return "Lista temas probables, responde preguntas sin mirar apuntes y marca los vacios que debes corregir."
    if selected_method_id == "metodo_repaso_semanal":
        return "Ordena los temas de la semana y reparte repasos breves empezando por lo mas dificil o urgente."
    if activity_type == "exposicion":
        return "Arma un guion de tres partes: idea central, evidencia o ejemplo, y cierre que puedas explicar sin leer."
    return ""


def _technique_step(selected_technique_id: str | None, *, minutes: int) -> str:
    if selected_technique_id == "pomodoro":
        return f"Trabaja en un bloque de {minutes} min sin cambiar de tarea y deja una pausa breve al terminar."
    if selected_technique_id == "active_recall":
        return "Cierra el material y responde 3 a 5 preguntas de memoria antes de revisar tus apuntes."
    if selected_technique_id == "feynman":
        return "Explica el tema en voz alta con palabras simples y anota donde tu explicacion se rompe."
    if selected_technique_id == "cornell":
        return "Organiza apuntes en claves, notas y resumen; convierte cada clave en pregunta de repaso."
    if selected_technique_id == "mapas_conceptuales":
        return "Dibuja relaciones entre conceptos y marca dependencias antes de memorizar detalles sueltos."
    if selected_technique_id == "mnemotecnia":
        return "Crea una pista de memoria solo para datos exactos y compruebala sin mirar la fuente."
    if selected_technique_id == "repeticion_espaciada":
        return "Agenda un repaso breve posterior y prioriza lo que no pudiste recordar hoy."
    if selected_technique_id == "interleaving":
        return "Alterna tipos de ejercicio o tema para comprobar que eliges el procedimiento correcto."
    return ""


def _verification_step(*, activity_type: str | None) -> str:
    if activity_type in {"taller", "tarea", "quiz", "parcial"}:
        return "Cierra con una prueba corta: un ejercicio o pregunta sin ayuda y una lista de errores a corregir."
    if activity_type in {"exposicion", "proyecto", "entrega"}:
        return "Cierra revisando el entregable contra una lista breve: claridad, evidencia y siguiente ajuste."
    return "Cierra verificando que puedes explicar o aplicar lo trabajado sin depender de la fuente."


def _build_summary(
    *,
    request: AppliedStudyMethodRequest,
    activity_type: str | None,
    selected_method_id: str | None,
    selected_technique_id: str | None,
) -> str:
    subject = f" de {request.subject_name}" if request.subject_name else ""
    activity = _activity_label(activity_type)
    method = _METHOD_LABELS.get(selected_method_id or "", "")
    technique = _TECHNIQUE_LABELS.get(selected_technique_id or "", "")
    if method and technique:
        return f"Para el {activity}{subject}, usa {method} apoyado en {technique}."
    if method:
        return f"Para el {activity}{subject}, usa {method}."
    if technique:
        return f"Para el {activity}{subject}, aplica {technique} con una meta verificable."
    return f"Para el {activity}{subject}, trabaja con pasos verificables."


def _not_applied(
    request: AppliedStudyMethodRequest,
    *,
    activity_type: str | None,
    status: str,
    error_code: str,
    detail: str,
    selected_method_id: str | None = None,
    selected_technique_id: str | None = None,
    recommendation: StudyRecommendationResult | None = None,
) -> AppliedStudyMethodResult:
    return AppliedStudyMethodResult(
        applied=False,
        status=status,
        subject_name=request.subject_name,
        activity_type=activity_type,
        activity_title=request.activity_title,
        selected_method_id=selected_method_id,
        selected_technique_id=selected_technique_id,
        source_chunks=list(recommendation.source_chunks if recommendation else []),
        relations_used=list(recommendation.relations_used if recommendation else []),
        cautions=list(recommendation.cautions[:2] if recommendation else []),
        confidence=recommendation.confidence if recommendation else "baja",
        grounded_answer=_clean_text(recommendation.answer) if recommendation else "",
        error_code=error_code,
        detail=detail,
    )


def _detect_activity_type(normalized_text: str) -> str | None:
    for activity_type, aliases in _ACTIVITY_TYPE_ALIASES.items():
        if _contains_any(normalized_text, aliases):
            return activity_type
    return None


def _normalize_activity_type(value: str | None) -> str | None:
    slug = slugify_identifier(value or "")
    if not slug:
        return None
    return _detect_activity_type(slug) or slug


def _detect_subject_type(normalized_text: str) -> str | None:
    if _contains_any(normalized_text, {"teorico", "teorica", "conceptual"}):
        return "teorica"
    if _contains_any(normalized_text, _NUMERIC_TERMS):
        return "numerica"
    if _contains_any(normalized_text, _READING_TERMS):
        return "lectura_sintesis"
    return None


def _detect_urgency(normalized_text: str) -> str | None:
    if _contains_any(normalized_text, {"hoy", "manana", "urgente", "ya", "esta_semana"}):
        return "alta"
    if _contains_any(normalized_text, {"despues", "luego", "proxima_semana"}):
        return "media"
    return None


def _extract_subject_name(raw_text: str, *, activity_type: str | None) -> str | None:
    if not raw_text.strip():
        return None
    normalized = slugify_identifier(raw_text)
    if activity_type:
        aliases = _ACTIVITY_TYPE_ALIASES.get(activity_type, {activity_type})
        for alias in aliases:
            alias_pattern = re.escape(alias).replace("_", r"\s+")
            pattern = (
                rf"\b{alias_pattern}\s+"
                r"(?:de|para|sobre|en)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ]+)"
            )
            match = re.search(pattern, raw_text, flags=re.IGNORECASE)
            if match:
                candidate = _trim_subject_candidate(match.group(1))
                if candidate:
                    return candidate
        if slugify_identifier(next(iter(aliases))) not in normalized:
            return None
    match = re.search(r"\b(?:de|para|sobre|en)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ]+)", raw_text)
    if match:
        return _trim_subject_candidate(match.group(1))
    return None


def _extract_activity_title(raw_text: str, *, activity_type: str | None) -> str | None:
    if not activity_type:
        return None
    return _activity_label(activity_type)


def _extract_available_minutes(normalized_text: str) -> int | None:
    hour_match = re.search(r"(?<!\d)(\d{1,2})[_\s]*(?:h|hora|horas)\b", normalized_text)
    if hour_match:
        return int(hour_match.group(1)) * 60
    minute_match = re.search(
        r"(?<!\d)(\d{1,3})[_\s]*(?:min|minuto|minutos)\b",
        normalized_text,
    )
    if minute_match:
        return int(minute_match.group(1))
    return None


def _extract_difficulty(normalized_text: str) -> str | None:
    match = re.search(r"\bdificultad[_\s]*(\d)(?!\d)", normalized_text)
    if match:
        return match.group(1)
    if _contains_any(normalized_text, {"dificil", "complejo", "complicado"}):
        return "alta"
    if _contains_any(normalized_text, {"facil", "sencillo"}):
        return "baja"
    return None


def _trim_subject_candidate(value: str) -> str | None:
    normalized_words = []
    for word in value.replace("?", " ").replace(".", " ").split():
        slug = slugify_identifier(word)
        if slug in {
            "en",
            "con",
            "hoy",
            "manana",
            "urgente",
            "dificultad",
            "durante",
            "por",
            "favor",
        }:
            break
        if re.fullmatch(r"\d+", slug):
            break
        normalized_words.append(word.strip(" ,;:"))
    candidate = " ".join(word for word in normalized_words if word).strip()
    return candidate[:80] or None


def _normalize_techniques(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        technique = normalize_technique_id(str(value or ""))
        if not technique or technique in seen:
            continue
        seen.add(technique)
        normalized.append(technique)
    return normalized


def _first_supported_technique(
    values: list[str | None],
    source_chunks: list[str],
) -> str | None:
    for value in values:
        technique = normalize_technique_id(str(value or ""))
        if _supported_entity(technique, source_chunks, knowledge_type="technique"):
            return technique
    return None


def _supported_entity(
    entity_id: str | None,
    source_chunks: list[str],
    *,
    knowledge_type: str,
) -> bool:
    normalized = slugify_identifier(entity_id or "")
    if not normalized:
        return False
    prefix = f"{knowledge_type}.{normalized}::"
    document_prefix = f"{knowledge_type}.{normalized}"
    return any(
        str(chunk_id).startswith(prefix) or str(chunk_id) == document_prefix
        for chunk_id in source_chunks
    )


def _contains_any(normalized_text: str, terms: set[str]) -> bool:
    padded = f"_{normalized_text}_"
    for term in terms:
        slug = slugify_identifier(term)
        if not slug:
            continue
        if f"_{slug}_" in padded or slug in normalized_text:
            return True
    return False


def _bounded_minutes(value: int | None) -> int:
    if value is None:
        return 25
    return max(15, min(int(value), 50))


def _activity_label(activity_type: str | None) -> str:
    if not activity_type:
        return "actividad"
    labels = {
        "repaso_semanal": "repaso semanal",
        "estudio_pendiente": "estudio pendiente",
    }
    return labels.get(activity_type, activity_type.replace("_", " "))


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split())


__all__ = [
    "AppliedStudyMethodRequest",
    "AppliedStudyMethodResult",
    "AppliedStudyMethodService",
    "build_applied_method_request_from_text",
    "build_applied_study_method_service",
    "ensure_applied_method_request",
    "format_applied_study_method_for_user",
    "is_applied_study_method_message",
]
