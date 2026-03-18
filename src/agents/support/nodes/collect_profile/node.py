"""Nodo para recolectar el perfil base del estudiante."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.onboarding.config import load_onboarding_config
from agents.support.onboarding.messages import (
    build_field_prompt,
    build_program_scope_note,
    build_prompt_with_error,
)
from agents.support.onboarding.validators import (
    get_first_name,
    get_missing_profile_fields,
    validate_profile_field,
)
from agents.support.state import AgentState


def collect_profile(state: AgentState) -> dict:
    """Recolecta datos personales validados paso a paso."""

    config = load_onboarding_config()
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    profile = dict(state.get("student_profile", {}))
    onboarding = _onboarding_dict(state)

    missing_before = get_missing_profile_fields(profile)
    target_field = missing_before[0] if missing_before else None
    onboarding["current_field"] = target_field
    onboarding["persistence_error"] = None

    validation_failed = False
    should_send_verification = False
    extra_note = None

    if has_new_input and last_text and target_field:
        result = validate_profile_field(target_field, last_text, config)
        if result.is_valid:
            profile[target_field] = result.value
            if target_field == "institutional_email":
                profile["email_verified"] = False
                onboarding["email_verification"] = {
                    "status": "idle",
                    "attempts": 0,
                    "resend_count": 0,
                    "expires_at": None,
                    "last_error": None,
                }
                should_send_verification = True
            elif target_field == "supported_program":
                profile["academic_program"] = (
                    config.supported_program_name if result.value else None
                )
                if result.value is False:
                    extra_note = build_program_scope_note(config)
        else:
            validation_failed = True

    missing_after = get_missing_profile_fields(profile)
    next_field = missing_after[0] if missing_after else None
    onboarding["current_field"] = next_field

    if should_send_verification:
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
        }

    if next_field or validation_failed:
        prompt_field = target_field if validation_failed and target_field else next_field or "full_name"
        if validation_failed:
            prompt = build_prompt_with_error(
                prompt_field,
                config,
                get_first_name(profile),
                extra_note,
            )
        else:
            prompt = build_field_prompt(
                prompt_field,
                config,
                get_first_name(profile),
            )
        if not validation_failed and extra_note and prompt_field != "supported_program":
            prompt = f"{extra_note}\n{prompt}"
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    return {
        "student_profile": profile,
        "onboarding": onboarding,
        "phase": "profile_confirm",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": False,
    }


def _onboarding_dict(state: AgentState) -> dict:
    onboarding_state = state.get("onboarding", {})
    onboarding = dict(onboarding_state)
    email_verification = dict(onboarding_state.get("email_verification", {}))
    onboarding["email_verification"] = email_verification
    return onboarding
