"""Nodo para recolectar el perfil base del estudiante."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    copy_onboarding_state,
    detect_new_input,
)
from agents.support.onboarding.config import load_onboarding_config
from agents.support.onboarding.messages import (
    build_field_prompt,
    build_out_of_scope_program_message,
    build_student_code_scope_prompt,
    build_prompt_with_error,
)
from agents.support.onboarding.validators import (
    get_first_name,
    get_missing_profile_fields,
    parse_yes_no,
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
    onboarding = copy_onboarding_state(state)

    missing_before = get_missing_profile_fields(profile)
    target_field = missing_before[0] if missing_before else None
    onboarding["current_field"] = target_field
    onboarding["persistence_error"] = None

    if onboarding.get("pending_student_code_scope_confirmation"):
        decision = parse_yes_no(last_text or "") if has_new_input else None
        if decision is True:
            onboarding["pending_student_code_scope_confirmation"] = False
            return {
                "student_profile": profile,
                "onboarding": onboarding,
                "user_status": "start",
                "phase": "profile",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    build_field_prompt("student_code", config, get_first_name(profile)),
                ),
            }
        if decision is False:
            onboarding["pending_student_code_scope_confirmation"] = False
            return {
                "student_profile": profile,
                "onboarding": onboarding,
                "phase": "end",
                "user_status": "out_of_scope",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": False,
                "messages": append_message(
                    messages,
                    "assistant",
                    build_out_of_scope_program_message(config),
                ),
            }
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_student_code_scope_prompt(config),
            ),
        }

    validation_failed = False
    should_send_verification = False

    if has_new_input and last_text and target_field:
        result = validate_profile_field(target_field, last_text, config)
        if result.is_valid:
            profile[target_field] = result.value
            if target_field == "student_code":
                profile["supported_program"] = True
                profile["academic_program"] = config.supported_program_name
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
        else:
            if target_field == "student_code" and result.error == "unsupported_student_code":
                onboarding["pending_student_code_scope_confirmation"] = True
                return {
                    "student_profile": profile,
                    "onboarding": onboarding,
                    "phase": "profile",
                    "user_status": "start",
                    "user_message_count": current_count,
                    "last_user_text": last_text,
                    "awaiting_user_input": True,
                    "messages": append_message(
                        messages,
                        "assistant",
                        build_student_code_scope_prompt(config),
                    ),
                }
            validation_failed = True

    if profile.get("student_code"):
        profile["supported_program"] = True
        profile["academic_program"] = config.supported_program_name

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
            )
        else:
            prompt = build_field_prompt(
                prompt_field,
                config,
                get_first_name(profile),
            )
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "user_status": state.get("user_status", "start")
            if profile.get("student_code") in (None, "")
            else "valid",
            "phase": "profile",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    return {
        "student_profile": profile,
        "onboarding": onboarding,
        "user_status": "valid",
        "phase": "profile_confirm",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": False,
    }
