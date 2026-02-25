"""Cliente LLM para extraccion estructurada con Azure OpenAI."""

from __future__ import annotations

import json
import os
import re
from typing import Any
import unicodedata
import re

from langchain_openai import AzureChatOpenAI


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


def maybe_get_azure_llm() -> AzureChatOpenAI | None:
    """Retorna el cliente LLM o None si falta configuracion."""
    try:
        return get_azure_llm()
    except ValueError:
        return None


def llm_extract_json(prompt: str) -> dict[str, Any] | None:
    """Invoca el LLM y retorna un dict si la respuesta es JSON valido."""
    llm = maybe_get_azure_llm()
    if not llm:
        return None

    try:
        response = llm.invoke(prompt)
    except Exception:
        return None

    content = getattr(response, "content", None)
    if content is None:
        content = str(response)

    return _safe_json_loads(str(content))


def llm_generate_text(prompt: str) -> str | None:
    """Invoca el LLM y retorna el texto generado."""
    llm = maybe_get_azure_llm()
    if not llm:
        return None
    try:
        response = llm.invoke(prompt)
    except Exception:
        return None
    content = getattr(response, "content", None)
    return str(content).strip() if content is not None else None


def llm_normalize_schedule(text: str) -> str | None:
    """Normaliza un horario al formato por dias usando LLM."""
    llm = maybe_get_azure_llm()
    if not llm:
        return None

    prompt = (
        "Convierte el siguiente horario al formato por dias.\n"
        "Reglas:\n"
        "- Una clase por linea.\n"
        "- Formato exacto: <Dia> <HH:MM>-<HH:MM> <Nombre de la materia>.\n"
        "- Dias validos: Lunes, Martes, Miercoles, Jueves, Viernes, Sabado, Domingo.\n"
        "- Usa horario de 24 horas.\n"
        "- No repitas clases duplicadas.\n"
        "- No incluyas texto adicional ni listas numeradas.\n"
        f"Horario:\n{text}\n"
    )

    try:
        response = llm.invoke(prompt)
    except Exception:
        return None

    content = getattr(response, "content", None)
    normalized = str(content).strip() if content is not None else ""
    return _filter_day_lines(normalized) or None


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    """Intenta cargar JSON directo o extrae un bloque JSON."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
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
