"""Nodo para recolectar el perfil del estudiante."""

from __future__ import annotations

import re

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
)
from agents.support.state import AgentState, Ocupacion, StudentProfile
from agents.support.tools.llm import llm_extract_json

from .prompt import FALLBACK_PROMPT, PROMPTS_BY_FIELD

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def collect_profile(state: AgentState) -> dict:
    """Recolecta datos personales y avanza cuando el perfil esta completo."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    profile = dict(state.get("student_profile", {}))
    errors: list[str] = []

    missing_before = _missing_profile_fields(profile)
    target_field = missing_before[0] if missing_before else None

    if has_new_input and last_text and target_field:
        updates, issues = _apply_target_field(last_text, target_field, profile)
        profile.update(updates)
        for issue in issues:
            if issue not in errors:
                errors.append(issue)

    missing = _missing_profile_fields(profile)
    if missing or errors:
        next_field = missing[0] if missing else (target_field or "nombre")
        prompt = _build_step_prompt(next_field, errors)
        return {
            "student_profile": profile,
            "phase": "profile",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    return {
        "student_profile": profile,
        "phase": "profile_confirm",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": False,
    }


def _extract_profile_updates(text: str, profile: StudentProfile) -> tuple[dict, list[str]]:
    """Extrae campos del perfil desde el texto del usuario."""
    updates: dict = {}
    issues: list[str] = []
    normalized = normalize_text(text)

    nombre = _extract_value(normalized, r"nombre\s*[:\-]?\s*([a-z\s]+)")
    if nombre and not profile.get("nombre"):
        updates["nombre"] = nombre.strip().title()

    correo = _extract_allowed_email(text)
    if correo and not profile.get("correo"):
        updates["correo"] = correo

    edad = _extract_value(normalized, r"edad\s*[:\-]?\s*(\d{1,2})")
    if not edad:
        edad = _extract_value(normalized, r"(\d{1,2})\s*anos")
    if edad and not profile.get("edad"):
        edad_val = int(edad)
        if 14 <= edad_val <= 90:
            updates["edad"] = edad_val
        else:
            issues.append("edad debe estar entre 14 y 90")

    codigo = _extract_value(normalized, r"codigo\s*[:\-]?\s*([a-z0-9-]+)")
    if codigo and not profile.get("codigo"):
        updates["codigo"] = codigo

    programa_raw = _extract_value(
        normalized, r"(programa|carrera)\s*[:\-]?\s*([a-z\s]+)", 2
    )
    programa = _normalize_programa(programa_raw or normalized)
    if programa and not profile.get("programa"):
        updates["programa"] = programa
    elif programa_raw and not programa:
        issues.append("programa debe ser Ingenieria de Sistemas y Computacion")

    semestre = _extract_value(normalized, r"semestre\s*[:\-]?\s*(\d+)")
    if semestre and not profile.get("semestre"):
        semestre_val = int(semestre)
        if 1 <= semestre_val <= 10:
            updates["semestre"] = semestre_val
        else:
            issues.append("semestre debe estar entre 1 y 10")

    promedio = _extract_value(
        normalized, r"promedio\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)"
    )
    if promedio and not profile.get("promedio"):
        promedio_val = float(promedio.replace(",", "."))
        if 1 <= promedio_val <= 100:
            updates["promedio"] = promedio_val
        else:
            issues.append("promedio debe estar entre 1 y 100")

    ocupacion = _parse_ocupacion(normalized)
    if ocupacion and not profile.get("ocupacion"):
        updates["ocupacion"] = ocupacion

    return updates, issues


def _extract_profile_with_llm(text: str, profile: StudentProfile) -> tuple[dict, list[str]]:
    """Usa el LLM para extraer campos faltantes del perfil."""
    prompt = (
        "Extrae un JSON con campos: nombre, edad, correo, codigo, programa, "
        "semestre, promedio, ocupacion. Usa null si falta. "
        "programa solo si es Ingenieria de Sistemas y Computacion; si no, null. "
        "ocupacion debe ser uno de: solo_estudio, solo_trabajo, ambos, ninguna, o null. "
        "promedio es numero entre 1 y 100. "
        "Devuelve solo JSON sin texto extra.\n"
        f"Texto: {text}"
    )
    data = llm_extract_json(prompt)
    if not data:
        return {}, []

    updates: dict = {}
    issues: list[str] = []

    nombre = data.get("nombre")
    if nombre and not profile.get("nombre"):
        updates["nombre"] = str(nombre).strip().title()

    correo = data.get("correo")
    if correo and not profile.get("correo"):
        allowed = _extract_allowed_email(str(correo))
        if allowed:
            updates["correo"] = allowed
        else:
            issues.append("correo invalido (dominio no permitido)")

    edad = data.get("edad")
    if edad and not profile.get("edad"):
        try:
            edad_val = int(float(edad))
            if 14 <= edad_val <= 90:
                updates["edad"] = edad_val
            else:
                issues.append("edad debe estar entre 14 y 90")
        except (TypeError, ValueError):
            issues.append("edad debe ser numero")

    codigo = data.get("codigo")
    if codigo and not profile.get("codigo"):
        updates["codigo"] = str(codigo).strip()

    programa_raw = data.get("programa")
    if programa_raw and not profile.get("programa"):
        programa = _normalize_programa(str(programa_raw))
        if programa:
            updates["programa"] = programa
        else:
            issues.append("programa debe ser Ingenieria de Sistemas y Computacion")

    semestre = data.get("semestre")
    if semestre and not profile.get("semestre"):
        try:
            semestre_val = int(float(semestre))
            if 1 <= semestre_val <= 10:
                updates["semestre"] = semestre_val
            else:
                issues.append("semestre debe estar entre 1 y 10")
        except (TypeError, ValueError):
            issues.append("semestre debe ser numero")

    promedio = data.get("promedio")
    if promedio and not profile.get("promedio"):
        try:
            promedio_val = float(promedio)
            if 1 <= promedio_val <= 100:
                updates["promedio"] = promedio_val
            else:
                issues.append("promedio debe estar entre 1 y 100")
        except (TypeError, ValueError):
            issues.append("promedio debe ser numero")

    ocupacion = data.get("ocupacion")
    if ocupacion and not profile.get("ocupacion"):
        normalized = _normalize_ocupacion(str(ocupacion))
        if normalized:
            updates["ocupacion"] = normalized
        else:
            issues.append("ocupacion invalida")

    return updates, issues


def _extract_value(text: str, pattern: str, group: int = 1) -> str:
    match = re.search(pattern, text)
    return match.group(group) if match else ""


def _parse_ocupacion(text: str) -> Ocupacion | None:
    if re.match(r"^\s*1\s*[).:-]?\s*$", text):
        return "solo_estudio"
    if re.match(r"^\s*2\s*[).:-]?\s*$", text):
        return "solo_trabajo"
    if re.match(r"^\s*3\s*[).:-]?\s*$", text):
        return "ambos"
    if re.match(r"^\s*4\s*[).:-]?\s*$", text):
        return "ninguna"
    if "solo estudio" in text or "solo estudiar" in text or text.strip() == "1":
        return "solo_estudio"
    if "solo trabajo" in text or "solo trabajar" in text or text.strip() == "2":
        return "solo_trabajo"
    if "ambos" in text or "estudio y trabajo" in text or text.strip() == "3":
        return "ambos"
    if "ninguna" in text or "no estudio ni trabajo" in text or text.strip() == "4":
        return "ninguna"
    if text.strip().startswith("1"):
        return "solo_estudio"
    if text.strip().startswith("2"):
        return "solo_trabajo"
    if text.strip().startswith("3"):
        return "ambos"
    if text.strip().startswith("4"):
        return "ninguna"
    return None


def _normalize_ocupacion(value: str) -> Ocupacion | None:
    normalized = normalize_text(value)
    if normalized in ("solo_estudio", "solo_trabajo", "ambos", "ninguna"):
        return normalized  # type: ignore[return-value]
    return _parse_ocupacion(normalized)


def _normalize_programa(text: str) -> str:
    normalized = normalize_text(text)
    if "sistemas" in normalized:
        return "Ingenieria de Sistemas y Computacion"
    if "sistemas" in normalized and "computacion" in normalized:
        return "Ingenieria de Sistemas y Computacion"
    if "ingenieria de sistemas" in normalized:
        return "Ingenieria de Sistemas y Computacion"
    if "ing sistemas" in normalized:
        return "Ingenieria de Sistemas y Computacion"
    return ""


def _missing_profile_fields(profile: StudentProfile) -> list[str]:
    required = [
        "nombre",
        "edad",
        "correo",
        "codigo",
        "programa",
        "semestre",
        "promedio",
        "ocupacion",
    ]
    return [field for field in required if not profile.get(field)]


def _apply_target_field(
    text: str, field: str, profile: StudentProfile
) -> tuple[dict, list[str]]:
    if profile.get(field):
        return {}, []

    updates: dict = {}
    issues: list[str] = []
    normalized = normalize_text(text)

    if field == "nombre":
        candidate = _extract_name(text)
        if candidate:
            updates["nombre"] = candidate.title()
        else:
            issues.append("nombre y apellidos requeridos")
        return updates, issues

    if field == "edad":
        match = re.search(r"\d{1,3}", normalized)
        if match:
            age = int(match.group(0))
            if 14 <= age <= 90:
                updates["edad"] = age
            else:
                issues.append("edad debe estar entre 14 y 90")
        else:
            issues.append("edad debe ser numero")
        return updates, issues

    if field == "correo":
        email = _extract_allowed_email(text)
        if email:
            updates["correo"] = email
        else:
            issues.append("correo invalido (dominio no permitido)")
        return updates, issues

    if field == "codigo":
        match = re.search(r"[a-z0-9-]{3,}", normalized)
        if match:
            updates["codigo"] = match.group(0)
        else:
            issues.append("codigo invalido")
        return updates, issues

    if field == "programa":
        programa = _normalize_programa(text)
        if programa:
            updates["programa"] = programa
        else:
            issues.append("programa debe ser Ingenieria de Sistemas y Computacion")
        return updates, issues

    if field == "semestre":
        match = re.search(r"\d{1,2}", normalized)
        if match:
            semester = int(match.group(0))
            if 1 <= semester <= 10:
                updates["semestre"] = semester
            else:
                issues.append("semestre debe estar entre 1 y 10")
        else:
            issues.append("semestre debe ser numero")
        return updates, issues

    if field == "promedio":
        match = re.search(r"[0-9]+(?:[.,][0-9]+)?", normalized)
        if match:
            promedio_val = float(match.group(0).replace(",", "."))
            if 1 <= promedio_val <= 100:
                updates["promedio"] = promedio_val
            else:
                issues.append("promedio debe estar entre 1 y 100")
        else:
            issues.append("promedio debe ser numero")
        return updates, issues

    if field == "ocupacion":
        ocupacion = _parse_ocupacion(normalized)
        if ocupacion:
            updates["ocupacion"] = ocupacion
        else:
            issues.append("ocupacion invalida")
        return updates, issues

    return updates, issues


def _extract_name(text: str) -> str:
    patterns = [
        r"nombre\s*[:\-]?\s*([a-zA-ZÀ-ÿ'\s-]+)",
        r"me llamo\s+([a-zA-ZÀ-ÿ'\s-]+)",
        r"soy\s+([a-zA-ZÀ-ÿ'\s-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            return _clean_name(candidate)
    return _clean_name(text)


def _clean_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-ZÀ-ÿ'\s-]", "", value).strip()
    cleaned = " ".join(cleaned.split())
    if len(cleaned) < 2:
        return ""
    parts = [part for part in cleaned.split(" ") if part]
    if len(parts) < 3:
        return ""
    return cleaned


def _extract_allowed_email(text: str) -> str:
    match = _EMAIL_PATTERN.search(text)
    if not match:
        return ""
    email = match.group(0).strip()
    domain = email.split("@")[-1].lower()
    allowed = {"ucatolica.edu.co", "gmail.com", "outlook.com"}
    return email if domain in allowed else ""


def _build_step_prompt(field: str, errors: list[str]) -> str:
    prompt = PROMPTS_BY_FIELD.get(field, FALLBACK_PROMPT)
    if errors:
        prompt = f"El dato anterior no es válido. {prompt}"
        prompt += "\nRevisa: " + "; ".join(errors) + "."
    return prompt
