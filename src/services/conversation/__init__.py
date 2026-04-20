"""Servicios del estado conversacional operativo."""

from .guided_academic_support import (
    GUIDED_SUPPORT_DOMAIN,
    GuidedAcademicSupportResult,
    build_guided_academic_support_result,
    is_guided_academic_support_message,
    is_socratic_mode_message,
)
from .input_classifier import classify_input
from .observability import (
    build_buffer_audit_event,
    build_router_audit_event,
    text_audit_stats,
)
from .router import route_conversation_input, route_name_for_conversation_decision
from .scope_policy import decide_scope, render_scope_response, should_answer_scope_boundary
from .state_helpers import (
    ensure_interaction_state,
    interaction_state_to_update,
    reset_interaction_state,
    update_interaction_state,
)

__all__ = [
    "GUIDED_SUPPORT_DOMAIN",
    "GuidedAcademicSupportResult",
    "build_guided_academic_support_result",
    "build_buffer_audit_event",
    "build_router_audit_event",
    "classify_input",
    "decide_scope",
    "ensure_interaction_state",
    "interaction_state_to_update",
    "is_guided_academic_support_message",
    "is_socratic_mode_message",
    "render_scope_response",
    "reset_interaction_state",
    "route_conversation_input",
    "route_name_for_conversation_decision",
    "should_answer_scope_boundary",
    "text_audit_stats",
    "update_interaction_state",
]
