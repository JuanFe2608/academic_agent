"""Cliente LLM para extraccion estructurada (Azure OpenAI u OpenAI)."""

from __future__ import annotations

import ast
import base64
import json
import mimetypes
import os
import re
import unicodedata
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI

_LAST_LLM_ERROR: str | None = None


def get_azure_llm() -> AzureChatOpenAI:
    """Crea el cliente de Azure OpenAI usando variables de entorno."""
    endpoint = _get_env("AZURE_OPENAI_ENDPOINT")
    api_key = _get_env("AZURE_OPENAI_API_KEY")
    deployment = _get_env("AZURE_OPENAI_DEPLOYMENT_NAME")
    api_version = _get_env("OPENAI_API_VERSION")

    if not endpoint or not api_key or not deployment or not api_version:
        raise ValueError("Missing Azure OpenAI environment variables")

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        azure_deployment=deployment,
        api_version=api_version,
        temperature=0,
    )


def get_openai_llm() -> ChatOpenAI:
    """Crea el cliente OpenAI estandar usando variables de entorno."""
    api_key = _get_env("OPENAI_API_KEY")
    model = _get_env("OPENAI_MODEL") or "gpt-4o-mini"
    base_url = _get_env("OPENAI_BASE_URL")

    if not api_key:
        raise ValueError("Missing OpenAI environment variables")

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "temperature": 0,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def maybe_get_llm() -> AzureChatOpenAI | ChatOpenAI | None:
    """Retorna cliente Azure/OpenAI o None si falta configuracion."""
    try:
        return get_azure_llm()
    except ValueError:
        pass
    try:
        return get_openai_llm()
    except ValueError:
        return None


def llm_extract_json(prompt: str) -> dict[str, Any] | None:
    """Invoca el LLM y retorna un dict si la respuesta es JSON valido."""
    llm = maybe_get_llm()
    if not llm:
        return None

    _set_last_llm_error(None)
    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        _set_last_llm_error(exc)
        return None

    content = getattr(response, "content", response)
    return _safe_json_loads_from_content(content)


def llm_generate_text(prompt: str) -> str | None:
    """Invoca el LLM y retorna el texto generado."""
    llm = maybe_get_llm()
    if not llm:
        return None
    _set_last_llm_error(None)
    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        _set_last_llm_error(exc)
        return None
    content = getattr(response, "content", response)
    text = _content_to_text(content).strip()
    return text or None


def llm_normalize_schedule(text: str, schedule_hint: str | None = None) -> str | None:
    """Normaliza un horario al formato por dias usando LLM."""
    llm = maybe_get_llm()
    if not llm:
        return None

    hint = _normalize_schedule_hint(schedule_hint)
    prompt = (
        "Convierte el siguiente horario al formato por dias.\n"
        "Reglas:\n"
        "- Una clase por linea.\n"
        "- Formato exacto: <Dia> <HH:MM>-<HH:MM> <Nombre de la materia>.\n"
        "- Dias validos: Lunes, Martes, Miercoles, Jueves, Viernes, Sabado, Domingo.\n"
        "- Usa horario de 24 horas.\n"
        "- Conserva literal el periodo indicado por el usuario: 5 am->05:00, 5 pm->17:00, 05:00->05:00, 17:00->17:00.\n"
        "- Nunca inventes PM para horas ambiguas ni cambies 05:00 por 17:00.\n"
        "- No repitas clases duplicadas.\n"
        "- Si el contexto es laboral, usa titulo 'Trabajo' cuando no exista un titulo claro.\n"
        "- No incluyas texto adicional ni listas numeradas.\n"
        f"- Contexto del horario: {hint}.\n"
        f"Horario:\n{text}\n"
    )

    _set_last_llm_error(None)
    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        _set_last_llm_error(exc)
        return None

    content = getattr(response, "content", response)
    normalized = _content_to_text(content).strip()
    return _filter_day_lines(normalized) or None


def llm_normalize_extracurricular_items(text: str) -> list[dict[str, Any]] | None:
    """Normaliza actividades extracurriculares a estructura JSON."""
    llm = maybe_get_llm()
    if not llm:
        return None

    prompt = (
        "Extrae actividades extracurriculares desde el texto y responde SOLO JSON valido.\n"
        "Formato esperado:\n"
        '{"items":[{"nombre":"string","es_variable":true|false,"detalle":"string"}]}\n'
        "Reglas:\n"
        "- Si hay varias actividades, separalas en items.\n"
        "- es_variable=true para actividades no fijas; false para fijas/estables.\n"
        "- detalle debe conservar la informacion de dias/horas/frecuencia si existe.\n"
        "- Conserva literal AM/PM y las horas en 24h; no cambies 05:00 por 17:00.\n"
        "- Si no hay actividades claras, responde {\"items\":[]}.\n"
        "- No incluyas markdown ni texto fuera del JSON.\n"
        f"Texto:\n{text}\n"
    )

    _set_last_llm_error(None)
    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        _set_last_llm_error(exc)
        return None

    raw_content = getattr(response, "content", response)
    parsed = _safe_json_value_from_content(raw_content)
    items = _normalize_extracurricular_payload(parsed)
    return items or None


def llm_extract_schedule_blocks(
    text: str,
    schedule_type: str,
) -> dict[str, Any] | None:
    """Normaliza texto libre a bloques semanales recurrentes en JSON."""

    llm = maybe_get_llm()
    if not llm:
        return None

    raw_type = _strip_accents(str(schedule_type or "").lower()).strip()
    normalized_type = {
        "academic": "academic",
        "academico": "academic",
        "work": "work",
        "laboral": "work",
        "extracurricular": "extracurricular",
    }.get(raw_type, "unknown")
    prompt = (
        "Convierte el siguiente texto en bloques recurrentes semanales y responde SOLO JSON valido.\n"
        "Formato exacto:\n"
        '{'
        '"blocks":['
        '{"title":"string","day_of_week":"monday|tuesday|wednesday|thursday|friday|saturday|sunday",'
        '"start_time":"HH:MM","end_time":"HH:MM","source_text":"string","confidence":0.0,'
        '"ambiguity_flags":["string"]}'
        '],'
        '"needs_clarification":false,'
        '"clarifications":["string"]'
        '}\n'
        "Reglas:\n"
        "- schedule_type esperado: academic, work o extracurricular.\n"
        "- Solo crea bloques con día y rango horario exactos.\n"
        "- Convierte horas a 24h.\n"
        "- Expande rangos o listas de días en bloques separados.\n"
        "- Si falta dia, hora de inicio o fin, no inventes datos: usa needs_clarification=true.\n"
        "- Usa title='Trabajo' si el tipo es work y no hay un nombre mejor.\n"
        "- No incluyas markdown ni texto fuera del JSON.\n"
        f"- Tipo esperado: {normalized_type}.\n"
        f"Texto:\n{text}\n"
    )

    _set_last_llm_error(None)
    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        _set_last_llm_error(exc)
        return None

    raw_content = getattr(response, "content", response)
    payload = _safe_json_loads_from_content(raw_content)
    if not payload:
        return None
    return _normalize_schedule_blocks_payload(payload)


def llm_extract_schedule_from_image(
    image_ref: str, schedule_hint: str | None = None
) -> dict[str, Any] | None:
    """Detecta si una imagen es horario y extrae texto normalizado."""
    llm = maybe_get_llm()
    if not llm:
        return None

    image_url = _coerce_image_url(image_ref)
    if not image_url:
        return None

    hint = _normalize_schedule_hint(schedule_hint)
    prompt = (
        "Analiza la imagen y responde SOLO JSON valido con este formato:\n"
        '{"is_schedule": boolean, "schedule_type": "academico|laboral|desconocido", '
        '"extracted_text": "string"}\n'
        "Reglas:\n"
        "- is_schedule=true solo si hay evidencia clara de horario con dias y horas.\n"
        "- schedule_type debe ser academico, laboral o desconocido.\n"
        "- extracted_text debe ir en una o varias lineas con formato: "
        "<Dia> <HH:MM>-<HH:MM> <Titulo>.\n"
        "- Usa dias en espanol: Lunes..Domingo y horas en 24h.\n"
        "- Si no es horario o no es legible, usa extracted_text vacio.\n"
        "- No incluyas markdown ni texto adicional fuera del JSON.\n"
        f"- Pista de contexto: {hint}.\n"
    )

    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
    _set_last_llm_error(None)
    try:
        response = llm.invoke([HumanMessage(content=content)])
    except Exception as exc:
        _set_last_llm_error(exc)
        return None

    raw_content = getattr(response, "content", response)
    data = _safe_json_loads_from_content(raw_content)
    if not data:
        return None
    return _normalize_image_schedule_payload(data)


def llm_extract_text_from_image(image_ref: str) -> str | None:
    """Extrae texto libre de una imagen usando un modelo multimodal."""
    llm = maybe_get_llm()
    if not llm:
        return None

    image_url = _coerce_image_url(image_ref)
    if not image_url:
        return None

    prompt = (
        "Extrae el texto legible de la imagen.\n"
        "Reglas:\n"
        "- Devuelve solo texto plano.\n"
        "- Mantén saltos de linea cuando ayuden a preservar estructura.\n"
        "- No agregues explicaciones ni etiquetas.\n"
        "- Si no hay texto legible, responde vacio.\n"
    )
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
    _set_last_llm_error(None)
    try:
        response = llm.invoke([HumanMessage(content=content)])
    except Exception as exc:
        _set_last_llm_error(exc)
        return None

    raw_content = getattr(response, "content", response)
    text = _content_to_text(raw_content).strip()
    return text or None


def _safe_json_loads_from_content(content: Any) -> dict[str, Any] | None:
    """Convierte contenido heterogeneo en JSON util."""
    if isinstance(content, dict):
        return content
    text = _content_to_text(content)
    return _safe_json_loads(text)


def _safe_json_value_from_content(content: Any) -> Any:
    """Convierte contenido heterogeneo en JSON/lista util cuando sea posible."""
    if isinstance(content, (dict, list)):
        return content
    text = _content_to_text(content)
    return _safe_json_value(text)


def _content_to_text(content: Any) -> str:
    """Convierte bloques de contenido (str/list/dict) a texto plano."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        text_value = content.get("text")
        if isinstance(text_value, str):
            return text_value
        if isinstance(text_value, dict):
            for key in ("value", "text"):
                value = text_value.get(key)
                if isinstance(value, str):
                    return value
        nested = content.get("content")
        if nested is not None:
            return _content_to_text(nested)
        try:
            return json.dumps(content, ensure_ascii=False)
        except TypeError:
            return str(content)
    if isinstance(content, (list, tuple)):
        parts = [_content_to_text(item).strip() for item in content]
        return "\n".join(part for part in parts if part)
    text_attr = getattr(content, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    return str(content)


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    """Intenta cargar JSON directo o extrae un bloque JSON."""
    data = _safe_json_value(text)
    if isinstance(data, dict):
        return data
    return None


def _safe_json_value(text: str) -> Any:
    """Intenta cargar JSON/lista o extraer bloque serializado."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        pass

    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        pass

    try:
        return ast.literal_eval(match.group(0))
    except (ValueError, SyntaxError):
        return None


def _get_env(name: str) -> str:
    value = os.getenv(name, "")
    return value.strip()


def _filter_day_lines(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned: list[str] = []
    for line in lines:
        line = re.sub(r"^\s*[-*•\d\.\)]\s*", "", line).strip()
        normalized = _strip_accents(line.lower())
        if normalized.startswith(
            (
                "lunes ",
                "martes ",
                "miercoles ",
                "miércoles ",
                "jueves ",
                "viernes ",
                "sabado ",
                "sábado ",
                "domingo ",
            )
        ):
            cleaned.append(line)
    return "\n".join(cleaned)


def _strip_accents(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _normalize_image_schedule_payload(data: dict[str, Any]) -> dict[str, Any]:
    raw_is_schedule = data.get("is_schedule")
    is_schedule = _coerce_bool(raw_is_schedule)

    raw_type = str(data.get("schedule_type") or "").strip().lower()
    if raw_type not in {"academico", "laboral", "desconocido"}:
        raw_type = "desconocido"

    raw_text = (
        data.get("extracted_text")
        or data.get("normalized_text")
        or data.get("text")
        or ""
    )
    extracted_text = str(raw_text).strip()

    return {
        "is_schedule": is_schedule,
        "schedule_type": raw_type,
        "extracted_text": extracted_text,
    }


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _strip_accents(str(value or "").lower()).strip()
    return normalized in {"1", "true", "yes", "si", "schedule", "horario"}


def _coerce_extracurricular_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = _strip_accents(str(value or "").lower()).strip()
    if normalized in {"1", "true", "yes", "si", "variable", "flexible", "rotativo"}:
        return True
    if normalized in {"0", "false", "no", "fijo", "fija", "estable"}:
        return False
    return None


def _normalize_schedule_hint(schedule_hint: str | None) -> str:
    hint = _strip_accents(str(schedule_hint or "").lower()).strip()
    if hint in {"academico", "laboral"}:
        return hint
    return "desconocido"


def _normalize_extracurricular_payload(data: Any) -> list[dict[str, Any]]:
    items_raw: Any = data
    if isinstance(data, dict):
        items_raw = data.get("items")
    if not isinstance(items_raw, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        nombre = str(item.get("nombre") or item.get("actividad") or "").strip()
        detalle = str(item.get("detalle") or item.get("descripcion") or "").strip()
        es_variable = _coerce_extracurricular_bool(item.get("es_variable"))
        if es_variable is None:
            es_variable = _coerce_extracurricular_bool(item.get("tipo"))
        if not nombre or not detalle or es_variable is None:
            continue
        normalized.append(
            {
                "nombre": nombre,
                "es_variable": es_variable,
                "detalle": detalle,
            }
        )
    return normalized


def _normalize_schedule_blocks_payload(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    blocks_raw = data.get("blocks")
    if not isinstance(blocks_raw, list):
        blocks_raw = []

    normalized_blocks: list[dict[str, Any]] = []
    for item in blocks_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("nombre") or "").strip()
        day_of_week = str(item.get("day_of_week") or item.get("day") or "").strip().lower()
        start_time = str(item.get("start_time") or item.get("start") or "").strip()
        end_time = str(item.get("end_time") or item.get("end") or "").strip()
        source_text = str(item.get("source_text") or item.get("source") or "").strip()
        confidence = item.get("confidence")
        ambiguity_flags = item.get("ambiguity_flags") or []
        if not isinstance(ambiguity_flags, list):
            ambiguity_flags = [str(ambiguity_flags)]
        normalized_blocks.append(
            {
                "title": title,
                "day_of_week": day_of_week,
                "start_time": start_time,
                "end_time": end_time,
                "source_text": source_text,
                "confidence": confidence,
                "ambiguity_flags": [str(flag).strip() for flag in ambiguity_flags if str(flag).strip()],
            }
        )

    clarifications = data.get("clarifications") or []
    if not isinstance(clarifications, list):
        clarifications = [str(clarifications)]

    return {
        "blocks": normalized_blocks,
        "needs_clarification": bool(data.get("needs_clarification")),
        "clarifications": [str(item).strip() for item in clarifications if str(item).strip()],
    }


def _coerce_image_url(image_ref: str) -> str:
    raw = str(image_ref or "").strip()
    if not raw:
        return ""
    if raw.startswith("data:image"):
        return raw
    if raw.startswith(("http://", "https://")):
        return raw
    if os.path.exists(raw):
        return _path_to_data_url(raw)
    return ""


def _path_to_data_url(path: str) -> str:
    mime_type = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as file:
        encoded = base64.b64encode(file.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def get_last_llm_error() -> str | None:
    """Retorna el ultimo error de invocacion LLM capturado."""
    return _LAST_LLM_ERROR


def _set_last_llm_error(error: Exception | str | None) -> None:
    global _LAST_LLM_ERROR
    if error is None:
        _LAST_LLM_ERROR = None
        return
    _LAST_LLM_ERROR = str(error).strip() or type(error).__name__
