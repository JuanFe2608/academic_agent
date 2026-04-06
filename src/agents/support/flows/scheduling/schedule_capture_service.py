"""Servicio de aplicación para la captura conversacional del horario fijo.

Mantiene la compatibilidad con el estado y prompts actuales, pero concentra la
coordinación del flujo fuera del nodo LangGraph para que el nodo quede como un
coordinador fino.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.support.nodes.utils import (
    append_message,
    contains_normalized_phrase,
    has_time_range,
    normalize_text,
)
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.state import AgentState
from schemas.scheduling import PendingScheduleItem

from agents.support.scheduling.state_helpers import (
    append_schedule_input_text,
    ensure_schedule_flow_state,
    update_scheduling_state,
    update_schedule_flow_state,
)

from .schedule_pending_resolution_service import (
    coerce_schedule_pending_items,
    has_block_type,
    resolve_capture_pending_reply,
)


@dataclass(frozen=True)
class ScheduleCapturePrompts:
    """Prompt bundle para preservar la UX actual del flujo de captura."""

    occupation: str
    academic: str
    work: str
    none: str
    more_academic: str
    more_work: str


_CONTINUE_TOKENS = {
    "seguimos",
    "seguir",
    "siguiente",
    "continuemos",
    "continuar",
    "listo",
    "ya termine",
    "ya terminé",
    "terminado",
    "eso es todo",
    "nada mas",
    "nada más",
}
_DAY_HINT_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|lun|mar|mie|jue|vie|sab|dom)\b",
    re.IGNORECASE,
)


def handle_schedule_capture_turn(
    state: AgentState,
    *,
    has_new_input: bool,
    last_text: str | None,
    current_count: int,
    prompts: ScheduleCapturePrompts,
) -> dict:
    """Gestiona un turno del flujo de captura de horarios académico/laboral."""

    raw_inputs = dict(state.get("raw_inputs", {}))
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    profile = dict(state.get("student_profile", {}))
    occupation = profile.get("occupation")
    academic_pending_items = coerce_schedule_pending_items(
        state.get("academic_pending_items", [])
    )
    work_pending_items = coerce_schedule_pending_items(
        state.get("work_pending_items", [])
    )
    schedule_input_text = last_text
    occupation_reply_consumed = False

    if not occupation and has_new_input and last_text:
        parsed_occupation, extracted_schedule_text = _extract_occupation_reply(last_text)
        if parsed_occupation:
            occupation = parsed_occupation
            profile["occupation"] = parsed_occupation
            schedule_input_text = extracted_schedule_text
            occupation_reply_consumed = not bool(extracted_schedule_text)

    if not occupation:
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=update_schedule_flow_state(schedule_state),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="schedules",
            awaiting_user_input=True,
            current_count=(
                current_count if has_new_input else state.get("user_message_count", 0)
            ),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=prompts.occupation,
        )

    if occupation == "ninguna":
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=update_schedule_flow_state(schedule_state),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="end",
            awaiting_user_input=False,
            current_count=(
                current_count if has_new_input else state.get("user_message_count", 0)
            ),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=prompts.none,
        )

    capture_target = _resolve_capture_target(
        occupation=occupation,
        raw_inputs=raw_inputs,
        schedule_state=schedule_state,
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
    )
    capture_stage = str(schedule_state.capture_stage or "idle")

    if occupation_reply_consumed:
        return _prompt_for_section_input(
            state,
            profile=profile,
            occupation=occupation,
            target=capture_target,
            raw_inputs=raw_inputs,
            schedule_state=schedule_state,
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            current_count=current_count,
            last_text=last_text,
            prompts=prompts,
        )

    if capture_target is None:
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=update_schedule_flow_state(
                schedule_state,
                capture_target=None,
                capture_stage="idle",
            ),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="extras",
            awaiting_user_input=False,
            current_count=(
                current_count if has_new_input else state.get("user_message_count", 0)
            ),
            last_text=last_text if has_new_input else state.get("last_user_text"),
        )

    if has_new_input and schedule_input_text and (
        academic_pending_items or work_pending_items
    ):
        pending_update = resolve_capture_pending_reply(
            state,
            raw_inputs=raw_inputs,
            schedule_state=schedule_state.model_copy(update={"capture_target": capture_target}),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            response_text=schedule_input_text,
            current_count=current_count,
            more_prompt=_prompt_for_more(
                "academic" if academic_pending_items else "work",
                prompts,
            ),
        )
        if pending_update is not None:
            pending_update["student_profile"] = profile
            return pending_update

    if capture_stage == "awaiting_more":
        if has_new_input and schedule_input_text:
            decision = _parse_more_decision(schedule_input_text)
            if decision == "continue":
                return _advance_after_section(
                    state,
                    occupation=occupation,
                    current_target=capture_target,
                    raw_inputs=raw_inputs,
                    schedule_state=schedule_state,
                    academic_pending_items=academic_pending_items,
                    work_pending_items=work_pending_items,
                    current_count=current_count,
                    last_text=last_text,
                    prompts=prompts,
                )
            if decision == "more" and not _looks_like_schedule_content(schedule_input_text):
                return _prompt_for_section_input(
                    state,
                    profile=profile,
                    occupation=occupation,
                    target=capture_target,
                    raw_inputs=raw_inputs,
                    schedule_state=schedule_state,
                    academic_pending_items=academic_pending_items,
                    work_pending_items=work_pending_items,
                    current_count=current_count,
                    last_text=last_text,
                    prompts=prompts,
                )
            if decision in {"more", None} and _looks_like_schedule_content(
                schedule_input_text
            ):
                raw_inputs = _append_schedule_text(
                    raw_inputs, capture_target, schedule_input_text
                )
                return _build_schedule_update(
                    state,
                    profile=profile,
                    raw_inputs=raw_inputs,
                    schedule_state=update_schedule_flow_state(
                        schedule_state,
                        capture_target=capture_target,
                        capture_stage="awaiting_input",
                    ),
                    academic_pending_items=academic_pending_items,
                    work_pending_items=work_pending_items,
                    phase="schedules",
                    awaiting_user_input=False,
                    current_count=current_count,
                    last_text=last_text,
                )
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=update_schedule_flow_state(
                schedule_state,
                capture_target=capture_target,
                capture_stage="awaiting_more",
            ),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="schedules",
            awaiting_user_input=True,
            current_count=(
                current_count if has_new_input else state.get("user_message_count", 0)
            ),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=_prompt_for_more(capture_target, prompts),
        )

    if has_new_input and schedule_input_text:
        raw_inputs = _append_schedule_text(raw_inputs, capture_target, schedule_input_text)
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=update_schedule_flow_state(
                schedule_state,
                capture_target=capture_target,
                capture_stage="awaiting_input",
            ),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="schedules",
            awaiting_user_input=False,
            current_count=current_count,
            last_text=last_text,
        )

    return _prompt_for_section_input(
        state,
        profile=profile,
        occupation=occupation,
        target=capture_target,
        raw_inputs=raw_inputs,
        schedule_state=schedule_state,
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
        current_count=state.get("user_message_count", 0),
        last_text=state.get("last_user_text"),
        prompts=prompts,
    )


def _prompt_for_section_input(
    state: AgentState,
    *,
    profile: dict,
    occupation: str,
    target: str,
    raw_inputs: dict,
    schedule_state: object,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    current_count: int,
    last_text: str | None,
    prompts: ScheduleCapturePrompts,
) -> dict:
    return _build_schedule_update(
        state,
        profile=profile,
        raw_inputs=raw_inputs,
        schedule_state=update_schedule_flow_state(
            schedule_state,
            capture_target=target,
            capture_stage="awaiting_input",
        ),
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
        phase="schedules",
        awaiting_user_input=True,
        current_count=current_count,
        last_text=last_text,
        prompt=_prompt_for_target(target, occupation, prompts),
    )


def _advance_after_section(
    state: AgentState,
    *,
    occupation: str,
    current_target: str,
    raw_inputs: dict,
    schedule_state: object,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    current_count: int,
    last_text: str | None,
    prompts: ScheduleCapturePrompts,
    ) -> dict:
    next_target = _next_section_target(current_target, occupation)
    if next_target is None:
        return _build_schedule_update(
            state,
            profile=dict(state.get("student_profile", {})),
            raw_inputs=raw_inputs,
            schedule_state=update_schedule_flow_state(
                schedule_state,
                capture_target=None,
                capture_stage="idle",
            ),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="extras",
            awaiting_user_input=False,
            current_count=current_count,
            last_text=last_text,
        )

    return _build_schedule_update(
        state,
        profile=dict(state.get("student_profile", {})),
        raw_inputs=raw_inputs,
        schedule_state=update_schedule_flow_state(
            schedule_state,
            capture_target=next_target,
            capture_stage="awaiting_input",
        ),
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
        phase="schedules",
        awaiting_user_input=True,
        current_count=current_count,
        last_text=last_text,
        prompt=_prompt_for_target(next_target, occupation, prompts),
    )


def _append_schedule_text(raw_inputs: dict, target: str, text: str) -> dict:
    return append_schedule_input_text(raw_inputs, target, text)  # type: ignore[arg-type]


def _resolve_capture_target(
    *,
    occupation: str,
    raw_inputs: dict,
    schedule_state: object,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
) -> str | None:
    current_schedule_state = ensure_schedule_flow_state(schedule_state)
    current_target = str(current_schedule_state.capture_target or "").strip()
    if current_target in {"academic", "work"}:
        return current_target

    blocks = list(current_schedule_state.blocks)
    has_academic = bool(raw_inputs.get("horario_academico_text")) or has_block_type(
        blocks, "academic"
    )
    has_work = bool(raw_inputs.get("horario_laboral_text")) or has_block_type(
        blocks, "work"
    )

    if academic_pending_items:
        return "academic"
    if work_pending_items:
        return "work"
    if not has_academic:
        return "academic"
    if occupation == "ambos" and not has_work:
        return "work"
    return None


def _prompt_for_target(
    target: str,
    occupation: str,
    prompts: ScheduleCapturePrompts,
) -> str:
    if target == "work":
        return prompts.work
    return prompts.academic if occupation in {"solo_estudio", "ambos"} else prompts.academic


def _prompt_for_more(target: str, prompts: ScheduleCapturePrompts) -> str:
    return prompts.more_work if target == "work" else prompts.more_academic


def _next_section_target(current_target: str, occupation: str) -> str | None:
    if current_target == "academic" and occupation == "ambos":
        return "work"
    return None


def _parse_occupation(text: str) -> str | None:
    normalized = normalize_text(text)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .:-")

    if _matches_occupation_choice(normalized, "1", {"solo estudio", "solo estudiar"}):
        return "solo_estudio"
    if _matches_occupation_choice(
        normalized,
        "2",
        {"ambos", "estudio y trabajo", "trabajo y estudio"},
    ):
        return "ambos"
    if _matches_occupation_choice(
        normalized,
        "3",
        {"ninguna", "ninguna de las anteriores"},
    ):
        return "ninguna"
    return None


def _extract_occupation_reply(text: str) -> tuple[str | None, str | None]:
    raw_text = str(text or "").strip()
    if not raw_text:
        return None, None

    direct_match = _parse_occupation(raw_text)
    if direct_match is not None:
        return direct_match, None

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return None, None

    first_line_match = _parse_occupation(lines[0])
    if first_line_match is None:
        return None, None

    remainder = "\n".join(lines[1:]).strip()
    return first_line_match, remainder or None


def _matches_occupation_choice(
    normalized: str,
    option_number: str,
    labels: set[str],
) -> bool:
    if normalized in labels:
        return True
    if normalized == option_number:
        return True

    option_match = re.fullmatch(
        rf"(?:la\s+)?(?:opcion\s+)?{option_number}(?:\s+(?P<label>.+))?",
        normalized,
    )
    if option_match is None:
        return False

    label = str(option_match.group("label") or "").strip(" .:-")
    return not label or label in labels


def _parse_more_decision(text: str | None) -> str | None:
    normalized = normalize_text(text or "")
    if not normalized:
        return None
    if normalized in _CONTINUE_TOKENS or any(
        contains_normalized_phrase(normalized, token) for token in _CONTINUE_TOKENS
    ):
        return "continue"
    if any(
        contains_normalized_phrase(normalized, token)
        for token in ("si", "sí", "claro", "agregar", "mas", "más", "otro", "otra")
    ):
        return "more"
    return None


def _looks_like_schedule_content(text: str | None) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    return has_time_range(raw) or bool(_DAY_HINT_PATTERN.search(raw))


def _build_schedule_update(
    state: AgentState,
    *,
    profile: dict,
    raw_inputs: dict,
    schedule_state: dict,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    phase: str,
    awaiting_user_input: bool,
    current_count: int,
    last_text: str | None,
    prompt: str | None = None,
) -> dict:
    conversation_changes: dict[str, object] = {
        "phase": phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": awaiting_user_input,
    }
    if prompt:
        conversation_changes["messages"] = append_message(
            state.get("messages", []),
            "assistant",
            prompt,
        )

    update = {
        "student_profile": profile,
        **update_scheduling_state(
            state,
            raw_inputs=raw_inputs,
            schedule=schedule_state,
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
        ),
        **update_conversation_state(state, **conversation_changes),
    }
    return update
