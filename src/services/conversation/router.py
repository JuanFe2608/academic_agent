"""Router conversacional hibrido de Lara."""

from __future__ import annotations

from schemas.conversation import (
    ConversationRouteDecision,
    InputClassification,
    InteractionState,
    ScopeDecision,
)

from .input_classifier import classify_input
from .llm_intent_classifier import classify_intent_with_llm
from .scope_policy import decide_scope, render_scope_response, should_answer_scope_boundary
from .state_helpers import ensure_interaction_state
from .text_normalization import normalize_text

_SCOPE_INTENT_TO_ROUTE: dict[str, str] = {
    "request_weekly_prioritization": "collect_priorities",
    "prioritize_academic_work": "collect_priorities",
    "register_academic_activity": "handle_academic_update",
    "manage_academic_activity": "handle_academic_update",
    "track_study_session": "handle_academic_update",
    "view_weekly_agenda": "view_weekly_agenda",
    "view_tasks": "view_tasks",
    "request_replan": "request_replan",
    "sync_study_calendar": "sync_study_calendar",
    "sync_study_todo": "sync_study_todo",
    "view_fixed_schedule": "manage_fixed_schedule",
    "update_fixed_schedule": "manage_fixed_schedule",
    "delete_fixed_schedule_item": "manage_fixed_schedule",
    "manage_fixed_schedule": "manage_fixed_schedule",
    "request_study_method_recommendation": "answer_study_recommendation",
    "study_method_recommendation": "answer_study_recommendation",
    "request_guided_academic_help": "guided_academic_support",
    "enter_socratic_mode": "guided_academic_support",
    "followup_in_context": "guided_academic_support",
    "academic_request": "guided_academic_support",
    "limited_academic_guidance": "guided_academic_support",
}

_YES_CONFIRMATIONS = {
    "si",
    "sip",
    "ok",
    "vale",
    "listo",
    "confirmo",
    "confirmar",
    "de acuerdo",
    "correcto",
}
_NO_CONFIRMATIONS = {"no", "nop", "negativo", "rechazo", "cancelar", "cancela"}
_SMALLTALK_TOKENS = {"gracias", "ok", "jaja", "jeje", "hola", "buenas", "listo"}
_ACTIVE_PHASE_ROUTES = {
    "consent": "welcome_consent",
    "profile": "collect_profile",
    "microsoft_oauth": "request_microsoft_oauth",
    "profile_confirm": "confirm_profile",
    "profile_persist": "persist_profile",
    "schedules": "request_schedules",
    "extras": "ask_extracurricular",
    "draft": "build_draft_schedule",
    "validate": "validate_schedule",
    "schedule_edit": "apply_schedule_correction",
    "schedule_persist": "persist_schedule",
    "schedule_sync": "sync_fixed_schedule",
    "schedule_renewal": "renew_fixed_schedule",
    "schedule_repair": "repair_fixed_schedule",
    "fixed_schedule_management": "manage_fixed_schedule",
    "academic_activity_management": "handle_academic_update",
    "replan": "request_replan",
    "calendar_sync": "sync_study_calendar",
    "todo_sync": "sync_study_todo",
    "guided_academic_support": "guided_academic_support",
    "study_profile": "collect_study_profile",
    "study_profile_tiebreaker": "collect_study_profile_tiebreaker",
    "study_profile_persist": "persist_study_profile",
    "priorities": "collect_priorities",
    "study_plan": "build_study_plan",
    "running": "end",
}
_ACTIVE_INTENT_TO_ROUTE: dict[str, str] = {
    "register_academic_activity": "handle_academic_update",
    "manage_academic_activity": "handle_academic_update",
    "track_study_session": "handle_academic_update",
    "request_replan": "request_replan",
    "sync_study_calendar": "sync_study_calendar",
    "sync_study_todo": "sync_study_todo",
    "view_fixed_schedule": "manage_fixed_schedule",
    "update_fixed_schedule": "manage_fixed_schedule",
    "delete_fixed_schedule_item": "manage_fixed_schedule",
    "manage_fixed_schedule": "manage_fixed_schedule",
    "request_weekly_prioritization": "collect_priorities",
    "prioritize_academic_work": "collect_priorities",
    "request_guided_academic_help": "guided_academic_support",
    "enter_socratic_mode": "guided_academic_support",
}
_PHASE_DOMAINS = {
    "consent": "student_profile",
    "profile": "student_profile",
    "microsoft_oauth": "student_profile",
    "profile_confirm": "student_profile",
    "profile_persist": "student_profile",
    "schedules": "schedule_management",
    "extras": "schedule_management",
    "draft": "schedule_management",
    "validate": "schedule_management",
    "schedule_edit": "schedule_management",
    "schedule_persist": "schedule_management",
    "schedule_sync": "calendar_action",
    "schedule_renewal": "schedule_management",
    "schedule_repair": "schedule_management",
    "fixed_schedule_management": "schedule_management",
    "academic_activity_management": "activity_management",
    "replan": "replanning",
    "calendar_sync": "calendar_action",
    "todo_sync": "todo_action",
    "guided_academic_support": "guided_academic_support",
    "study_profile": "study_method_recommendation",
    "study_profile_tiebreaker": "study_method_recommendation",
    "study_profile_persist": "study_method_recommendation",
    "priorities": "prioritization",
    "study_plan": "weekly_planning",
    "running": "weekly_planning",
}


def route_conversation_input(
    text: str | None = None,
    *,
    interaction: InteractionState | dict[str, object] | None = None,
    phase: str | None = None,
    media_types: list[str] | tuple[str, ...] | set[str] | None = None,
    classification: InputClassification | None = None,
    scope_decision: ScopeDecision | None = None,
    recent_messages: list[str] | None = None,
) -> ConversationRouteDecision:
    """Decide intent, dominio y ruta de alto nivel para un input del usuario."""

    normalized_interaction = ensure_interaction_state(interaction)
    input_classification = classification or classify_input(text, media_types=media_types)
    active_phase = str(phase or "").strip() or None
    active_subflow = str(normalized_interaction.active_subflow or "").strip() or None
    if active_subflow and active_phase in {None, "end", "running"}:
        active_phase = active_subflow
    current_domain = _PHASE_DOMAINS.get(active_phase or "", "")
    has_prior_context = bool(
        active_phase
        or normalized_interaction.active_intent
        or (normalized_interaction.current_domain and current_domain not in {"out_of_scope", ""})
    )
    policy = scope_decision or decide_scope(
        text,
        classification=input_classification,
        media_types=media_types,
        has_prior_context=has_prior_context,
        recent_messages=recent_messages,
    )
    has_active_context = _has_active_context(active_phase, normalized_interaction)

    if policy.category == "human_support_case":
        return _decision(
            intent="wellbeing_or_crisis_signal",
            domain="risk_or_wellbeing",
            action="answer_policy",
            route_name="answer_scope_boundary",
            priority=1,
            reason=policy.reason,
            classification=input_classification,
            scope_decision=policy,
            confidence=policy.confidence,
        )

    confirmation_decision = _route_confirmation(
        normalized_interaction,
        input_classification,
        active_phase,
    )
    if confirmation_decision is not None:
        return confirmation_decision

    if should_answer_scope_boundary(policy) and _is_blocking_policy(policy):
        return _policy_boundary_decision(policy, input_classification)

    if _is_critical_command(input_classification):
        if has_active_context and normalized_interaction.active_intent:
            return _active_interrupt_decision(
                input_classification,
                active_phase,
                normalized_interaction,
                policy,
                reason="critical_command_interrupts_active_block",
            )
        return _route_new_intent(
            text,
            input_classification,
            policy,
            active_phase,
            reason="critical_command_interrupts_active_block",
            interrupts_active_block=bool(active_phase and active_phase != "end"),
            recent_messages=recent_messages,
            active_domain=normalized_interaction.current_domain or current_domain or None,
            active_intent=normalized_interaction.active_intent,
        )

    if normalized_interaction.missing_fields_json:
        if _is_contextual_smalltalk(input_classification):
            return _active_block_decision(
                intent="smalltalk_contextual",
                action="continue_active_block",
                phase=active_phase,
                interaction=normalized_interaction,
                classification=input_classification,
                scope_decision=policy,
                reason="smalltalk_preserves_missing_data_block",
                confidence=0.72,
            )
        if input_classification.is_useful:
            return _active_block_decision(
                intent="provide_missing_data",
                action="provide_missing_data",
                phase=active_phase,
                interaction=normalized_interaction,
                classification=input_classification,
                scope_decision=policy,
                reason="missing_fields_pending",
                confidence=max(input_classification.confidence, 0.82),
                missing_fields=normalized_interaction.missing_fields_json,
            )

    if has_active_context and _is_interruptible_question(input_classification, policy):
        return _interrupt_and_return_decision(policy, input_classification)

    if has_active_context:
        if _is_contextual_smalltalk(input_classification):
            return _active_block_decision(
                intent="smalltalk_contextual",
                action="continue_active_block",
                phase=active_phase,
                interaction=normalized_interaction,
                classification=input_classification,
                scope_decision=policy,
                reason="smalltalk_preserves_active_block",
                confidence=0.72,
            )
        return _active_block_decision(
            intent=normalized_interaction.active_intent or "continue_active_block",
            action="continue_active_block",
            phase=active_phase,
            interaction=normalized_interaction,
            classification=input_classification,
            scope_decision=policy,
            reason="active_block_has_priority",
            confidence=max(input_classification.confidence, 0.7),
        )

    if should_answer_scope_boundary(policy):
        return _policy_boundary_decision(policy, input_classification)

    # Intents ya resueltos por scope_policy o input_classifier: rutar directamente
    # sin re-clasificar con el LLM para evitar fallbacks incorrectos.
    if _is_study_method_question(input_classification, policy):
        return _decision(
            intent="request_study_method_recommendation",
            domain="study_method_recommendation",
            action="route",
            route_name="answer_study_recommendation",
            priority=7,
            reason="study_method_question_direct_route",
            classification=input_classification,
            scope_decision=policy,
            confidence=max(input_classification.confidence, policy.confidence, 0.80),
        )

    if policy.intent == "answer_academic_concept_question" or input_classification.possible_intent == "answer_academic_concept_question":
        return _decision(
            intent="answer_academic_concept_question",
            domain="guided_academic_support",
            action="route",
            route_name="answer_study_recommendation",
            priority=7,
            reason="academic_concept_question_direct_route",
            classification=input_classification,
            scope_decision=policy,
            confidence=max(input_classification.confidence, 0.80),
        )

    return _route_new_intent(
        text,
        input_classification,
        policy,
        active_phase,
        reason="new_intent_detection",
        recent_messages=recent_messages,
        active_domain=normalized_interaction.current_domain or current_domain or None,
        active_intent=normalized_interaction.active_intent,
    )


def _policy_boundary_decision(
    policy: ScopeDecision,
    classification: InputClassification,
) -> ConversationRouteDecision:
    return _decision(
        intent="out_of_scope_request",
        domain="out_of_scope",
        action="answer_policy",
        route_name="answer_scope_boundary",
        priority=2,
        reason=policy.reason,
        classification=classification,
        scope_decision=policy,
        confidence=policy.confidence,
    )


def route_name_for_conversation_decision(decision: ConversationRouteDecision) -> str:
    """Adapta una decision conversacional al nombre de nodo del grafo actual."""

    return decision.route_name or "answer_scope_boundary"


def _route_confirmation(
    interaction: InteractionState,
    classification: InputClassification,
    phase: str | None,
) -> ConversationRouteDecision | None:
    if not interaction.confirmation_pending:
        return None

    normalized = normalize_text(classification.normalized_text)
    if normalized in _YES_CONFIRMATIONS:
        return _active_block_decision(
            intent="confirm_action",
            action="confirm_action",
            phase=phase,
            interaction=interaction,
            classification=classification,
            reason="confirmation_pending_accepted",
            confidence=0.9,
        )
    if normalized in _NO_CONFIRMATIONS:
        return _active_block_decision(
            intent="reject_action",
            action="reject_action",
            phase=phase,
            interaction=interaction,
            classification=classification,
            reason="confirmation_pending_rejected",
            confidence=0.9,
        )
    return None


def _route_new_intent(
    text: str | None,
    classification: InputClassification,
    scope_decision: ScopeDecision,
    phase: str | None,
    *,
    reason: str,
    interrupts_active_block: bool = False,
    recent_messages: list[str] | None = None,
    active_domain: str | None = None,
    active_intent: str | None = None,
) -> ConversationRouteDecision:
    if _is_contextual_smalltalk(classification) and scope_decision.reason != "greeting_detected":
        return _decision(
            intent="smalltalk_contextual",
            domain="smalltalk_contextual",
            action="answer_policy",
            route_name="answer_scope_boundary",
            priority=12,
            reason="smalltalk_without_active_block",
            classification=classification,
            scope_decision=scope_decision,
            confidence=max(classification.confidence, 0.68),
        )

    llm_result = classify_intent_with_llm(
        text or "",
        recent_messages=recent_messages,
        active_domain=active_domain,
        active_intent=active_intent,
    )

    # Cuando el LLM falla o devuelve out_of_scope pero la scope policy ya validó
    # que el mensaje es académico, no rechazar al estudiante. Estrategia en dos pasos:
    # 1. Si el scope detectó un intent específico con ruta conocida, usarlo directamente.
    # 2. Si el intent es ambiguo, caer a guided_academic_support como fallback seguro.
    # Crítico en WhatsApp donde mensajes informales o con errores de tipeo son la norma.
    if llm_result.route_name == "answer_scope_boundary" and scope_decision.allowed:
        intent, domain = _canonical_route_identity(
            text or classification.normalized_text,
            scope_decision.intent,
            scope_decision.domain,
        )
        scope_route = _SCOPE_INTENT_TO_ROUTE.get(intent) or _SCOPE_INTENT_TO_ROUTE.get(scope_decision.intent or "")
        if scope_route:
            return _decision(
                intent=intent,
                domain=domain,
                action="route",
                route_name=scope_route,
                priority=9,
                reason=reason,
                classification=classification,
                scope_decision=scope_decision,
                confidence=0.62,
                interrupts_active_block=interrupts_active_block,
            )
        return _decision(
            intent="followup_in_context",
            domain="guided_academic_support",
            action="route",
            route_name="guided_academic_support",
            priority=9,
            reason=f"llm_out_of_scope_overridden_by_scope_policy:{llm_result.source}",
            classification=classification,
            scope_decision=scope_decision,
            confidence=0.55,
            interrupts_active_block=interrupts_active_block,
        )

    action = "answer_policy" if llm_result.route_name == "answer_scope_boundary" else "route"
    intent, domain = _canonical_route_identity(
        text or classification.normalized_text,
        llm_result.intent,
        llm_result.domain,
    )
    route_name = _SCOPE_INTENT_TO_ROUTE.get(intent, llm_result.route_name)
    return _decision(
        intent=intent,
        domain=domain,
        action=action,
        route_name=route_name,
        priority=9,
        reason=reason if action == "route" else f"llm_classifier:{llm_result.source}",
        classification=classification,
        scope_decision=scope_decision,
        confidence=llm_result.confidence,
        interrupts_active_block=interrupts_active_block,
    )


def _active_block_decision(
    *,
    intent: str,
    action: str,
    phase: str | None,
    interaction: InteractionState,
    classification: InputClassification,
    reason: str,
    scope_decision: ScopeDecision | None = None,
    confidence: float = 0.0,
    missing_fields: list[object] | None = None,
) -> ConversationRouteDecision:
    route_name = _route_for_active_context(phase, interaction, intent=intent)
    domain = (
        interaction.current_domain
        or _PHASE_DOMAINS.get(str(phase or ""))
        or "guided_academic_support"
    )
    return _decision(
        intent=intent,
        domain=domain,
        action=action,
        route_name=route_name,
        priority=4 if action == "continue_active_block" else 5,
        reason=reason,
        classification=classification,
        scope_decision=scope_decision,
        confidence=confidence,
        preserves_active_block=True,
        missing_fields=missing_fields,
    )


def _decision(
    *,
    intent: str,
    domain: str,
    action: str,
    route_name: str | None,
    priority: int,
    reason: str,
    classification: InputClassification,
    scope_decision: ScopeDecision | None = None,
    confidence: float = 0.0,
    preserves_active_block: bool = False,
    interrupts_active_block: bool = False,
    missing_fields: list[object] | None = None,
) -> ConversationRouteDecision:
    signals = list(
        dict.fromkeys(
            [
                *classification.signals,
                *(scope_decision.signals if scope_decision else []),
                reason,
            ]
        )
    )
    return ConversationRouteDecision(
        intent=intent,
        domain=domain,
        action=action,
        route_name=route_name,
        confidence=confidence,
        priority=priority,
        reason=reason,
        preserves_active_block=preserves_active_block,
        interrupts_active_block=interrupts_active_block,
        classification=classification,
        scope_decision=scope_decision,
        missing_fields_json=missing_fields or [],
        signals=signals,
    )


def _is_critical_command(classification: InputClassification) -> bool:
    return classification.utility == "command"


def _is_contextual_smalltalk(classification: InputClassification) -> bool:
    normalized = normalize_text(classification.normalized_text)
    return (
        classification.utility == "noise"
        or classification.input_type in {"emoji_only", "sticker_only"}
        or normalized in _SMALLTALK_TOKENS
    )


def _is_blocking_policy(policy: ScopeDecision) -> bool:
    return policy.reason in {
        "evaluation_solution_request",
        "generalist_request",
        "human_support_signal",
    }


def _has_active_block(phase: str | None) -> bool:
    return bool(phase and phase not in {"end", "running"})


def _has_active_context(phase: str | None, interaction: InteractionState) -> bool:
    if _has_active_block(phase):
        return True
    return bool(
        str(phase or "") == "running"
        and interaction.active_intent
        and interaction.current_domain
    )


def _route_for_active_context(
    phase: str | None,
    interaction: InteractionState,
    *,
    intent: str | None = None,
) -> str | None:
    for candidate_intent in (intent, interaction.active_intent):
        canonical_intent, _domain = _canonical_route_identity(
            "",
            candidate_intent or "",
            interaction.current_domain or "",
        )
        if canonical_intent in _ACTIVE_INTENT_TO_ROUTE:
            return _ACTIVE_INTENT_TO_ROUTE[canonical_intent]
    active_subflow = str(interaction.active_subflow or "").strip()
    if active_subflow in _ACTIVE_PHASE_ROUTES:
        return _ACTIVE_PHASE_ROUTES[active_subflow]
    return _ACTIVE_PHASE_ROUTES.get(str(phase or ""))


def _active_interrupt_decision(
    classification: InputClassification,
    phase: str | None,
    interaction: InteractionState,
    scope_decision: ScopeDecision,
    *,
    reason: str,
) -> ConversationRouteDecision:
    intent, domain = _canonical_route_identity(
        classification.normalized_text,
        interaction.active_intent or classification.possible_intent or "continue_active_block",
        interaction.current_domain or _PHASE_DOMAINS.get(str(phase or ""), ""),
    )
    return _decision(
        intent=intent,
        domain=domain or "guided_academic_support",
        action="route",
        route_name=_route_for_active_context(phase, interaction, intent=intent),
        priority=4,
        reason=reason,
        classification=classification,
        scope_decision=scope_decision,
        confidence=max(classification.confidence, 0.78),
        interrupts_active_block=True,
    )


def _canonical_route_identity(text: str | None, intent: str | None, domain: str | None) -> tuple[str, str]:
    normalized_intent = str(intent or "").strip()
    normalized_domain = str(domain or "").strip()

    if normalized_intent == "manage_fixed_schedule":
        normalized_intent = _fixed_schedule_intent_from_text(text)
    elif normalized_intent == "manage_academic_activity":
        normalized_intent = "register_academic_activity"
    elif normalized_intent == "prioritize_academic_work":
        normalized_intent = "request_weekly_prioritization"
    elif normalized_intent == "study_method_recommendation":
        normalized_intent = "request_study_method_recommendation"

    if normalized_domain == "calendar_sync":
        normalized_domain = "calendar_action"
    elif normalized_domain == "todo_sync":
        normalized_domain = "todo_action"
    elif normalized_intent == "request_study_method_recommendation":
        normalized_domain = "study_method_recommendation"
    elif normalized_intent in {
        "view_fixed_schedule",
        "update_fixed_schedule",
        "delete_fixed_schedule_item",
    }:
        normalized_domain = "schedule_management"

    return normalized_intent, normalized_domain


def _fixed_schedule_intent_from_text(text: str | None) -> str:
    normalized = normalize_text(text)
    if any(term in normalized for term in ("eliminar", "borra", "borrar", "quita", "quitar")):
        return "delete_fixed_schedule_item"
    if any(
        term in normalized
        for term in (
            "cambiar",
            "cambia",
            "modificar",
            "ajustar",
            "mover",
            "reprogramar",
            "agregar",
            "anadir",
            "añadir",
        )
    ):
        return "update_fixed_schedule"
    if any(term in normalized for term in ("mostrar", "muestra", "ver", "consultar", "listar")):
        return "view_fixed_schedule"
    return "manage_fixed_schedule"


def _is_study_method_question(
    classification: InputClassification,
    policy: ScopeDecision,
) -> bool:
    if classification.possible_intent == "study_method_recommendation":
        return True
    if policy.intent == "study_method_recommendation":
        return True
    if policy.intent == "request_study_method_recommendation":
        return True
    if (
        classification.possible_intent != "answer_academic_concept_question"
        and policy.intent != "answer_academic_concept_question"
    ):
        return False
    normalized = normalize_text(classification.normalized_text)
    return any(
        term in normalized
        for term in (
            "pomodoro",
            "feynman",
            "cornell",
            "active recall",
            "spaced repetition",
            "repeticion espaciada",
            "mapa conceptual",
            "mapas conceptuales",
            "mnemotecnia",
            "interleaving",
            "tecnica",
            "tecnicas",
            "metodo",
            "metodos",
            "estudiar",
            "repasar",
            "memorizar",
        )
    )


def _is_interruptible_question(
    classification: InputClassification,
    policy: ScopeDecision,
) -> bool:
    """Detecta preguntas conceptuales académicas que pueden interrumpir un flujo activo."""
    interruptible_intents = {
        "answer_academic_concept_question",
        "study_method_recommendation",
        "request_study_method_recommendation",
    }
    return (
        classification.possible_intent in interruptible_intents
        or policy.intent in interruptible_intents
    )


def _interrupt_and_return_decision(
    policy: ScopeDecision,
    classification: InputClassification,
) -> ConversationRouteDecision:
    """Ruta a answer_study_recommendation preservando el flujo activo para reanudar después."""
    return _decision(
        intent="answer_academic_concept_question",
        domain="guided_academic_support",
        action="route",
        route_name="answer_study_recommendation",
        priority=6,
        reason="academic_question_interrupts_active_block",
        classification=classification,
        scope_decision=policy,
        confidence=max(classification.confidence, 0.80),
        preserves_active_block=True,
    )



__all__ = ["route_conversation_input", "route_name_for_conversation_decision"]
