"""Compatibilidad de prompts del perfil."""

from agents.support.onboarding.messages import build_field_prompt
from services.onboarding import load_onboarding_config

_CONFIG = load_onboarding_config()

PROMPTS_BY_FIELD = {
    "full_name": build_field_prompt("full_name", _CONFIG),
    "student_code": build_field_prompt("student_code", _CONFIG),
    "age": build_field_prompt("age", _CONFIG),
    "institutional_email": build_field_prompt("institutional_email", _CONFIG),
    "semester": build_field_prompt("semester", _CONFIG),
    "average_grade": build_field_prompt("average_grade", _CONFIG),
}

FALLBACK_PROMPT = PROMPTS_BY_FIELD["full_name"]
