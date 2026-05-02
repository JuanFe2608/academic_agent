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
from agents.support.media import materialize_image_reference
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.state import AgentState
from services.scheduling.ai_support import llm_extract_schedule_from_image
from schemas.scheduling import PendingScheduleItem

from agents.support.scheduling.state_helpers import (
    append_schedule_input_text,
    ensure_schedule_flow_state,
    update_scheduling_state,
    update_schedule_flow_state,
)
from agents.support.scheduling.pipeline import parse_fixed_schedule_section
from services.scheduling.correction_sync import merge_completed_fixed_section
from services.scheduling.pending_schedule_support import build_schedule_pending_prompt
from services.scheduling.pending_slot_state import schedule_pending_interaction_update

from .schedule_pending_resolution_service import (
    coerce_schedule_pending_items,
    has_block_type,
    resolve_capture_pending_reply,
)
from .section_confirmation_service import (
    SectionReviewCompletion,
    handle_section_review_turn,
    has_active_section_review,
    start_section_review,
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
_MORE_ACADEMIC_INLINE_PREFIXES = (
    re.compile(
        r"^\s*(?:1(?:[\).\:-]?\s*)?)?(?:(?:si|sí)\s*,?\s*)?quiero\s+agregar\s+m[aá]s\s+materias[\s:,\-]+(?P<content>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:1(?:[\).\:-]?\s*)?)?agregar\s+m[aá]s\s+materias[\s:,\-]+(?P<content>.+)$",
        re.IGNORECASE,
    ),
)
_MORE_WORK_INLINE_PREFIXES = (
    re.compile(
        r"^\s*(?:1(?:[\).\:-]?\s*)?)?(?:(?:si|sí)\s*,?\s*)?quiero\s+agregar\s+m[aá]s\s+horarios?(?:\s+de\s+trabajo)?[\s:,\-]+(?P<content>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:1(?:[\).\:-]?\s*)?)?agregar\s+m[aá]s\s+horarios?(?:\s+de\s+trabajo)?[\s:,\-]+(?P<content>.+)$",
        re.IGNORECASE,
    ),
)


def handle_schedule_capture_turn(
    state: AgentState,
    *,
    has_new_input: bool,
    last_text: str | None,
    last_images: list[str] | None = None,
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
    image_refs = _sanitize_image_refs(last_images or [])
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
            last_images=image_refs if has_new_input else None,
            prompt=prompts.occupation,
        )

    if occupation == "ninguna":
        profile["occupation"] = None
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
            last_images=image_refs if has_new_input else None,
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

    if has_active_section_review(state) and str(schedule_state.correction_target or "") in {
        "academic",
        "work",
    }:
        return handle_section_review_turn(
            state,
            has_new_input=has_new_input,
            last_text=last_text,
            current_count=current_count,
            completion=_section_review_completion(
                occupation=occupation,
                target=str(schedule_state.correction_target or ""),
                prompts=prompts,
            ),
        )

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
            last_images=image_refs if has_new_input else None,
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
            last_images=image_refs if has_new_input else None,
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

    if has_new_input and image_refs and capture_target in {"academic", "work"}:
        raw_inputs = _store_schedule_image(raw_inputs, capture_target, image_refs[-1])
        if not schedule_input_text or not _looks_like_schedule_content(schedule_input_text):
            extracted_text = _extract_schedule_text_from_image(
                image_refs[-1],
                target=capture_target,
            )
            if extracted_text:
                schedule_input_text = extracted_text
            else:
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
                    awaiting_user_input=True,
                    current_count=current_count,
                    last_text=last_text,
                    last_images=image_refs,
                    prompt=_image_unreadable_prompt(capture_target),
                )

    if capture_stage == "awaiting_more":
        if has_new_input and schedule_input_text:
            decision = _parse_more_decision(schedule_input_text)
            if decision == "continue":
                return start_section_review(
                    state,
                    target=capture_target,  # type: ignore[arg-type]
                    phase="schedules",
                    current_count=current_count,
                    last_text=last_text,
                )
            content_payload = _extract_schedule_content_from_more_reply(
                schedule_input_text,
                target=capture_target,
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
                    last_images=image_refs if has_new_input else None,
                    prompts=prompts,
                )
            if decision in {"more", None} and _looks_like_schedule_content(
                schedule_input_text
            ):
                isolated_update = _apply_isolated_more_schedule_content(
                    state,
                    profile=profile,
                    raw_inputs=raw_inputs,
                    schedule_state=schedule_state,
                    academic_pending_items=academic_pending_items,
                    work_pending_items=work_pending_items,
                    target=capture_target,
                    text=content_payload or schedule_input_text,
                    current_count=current_count,
                    last_text=last_text,
                )
                if isolated_update is not None:
                    return isolated_update
                raw_inputs = _append_schedule_text(
                    raw_inputs, capture_target, content_payload or schedule_input_text
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
            last_images=image_refs if has_new_input else None,
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
            last_images=image_refs if has_new_input else None,
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
        last_images=None,
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
    last_images: list[str] | None,
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
        last_images=last_images,
        prompt=_prompt_for_target(target, occupation, prompts),
    )


def _append_schedule_text(raw_inputs: dict, target: str, text: str) -> dict:
    return append_schedule_input_text(raw_inputs, target, text)  # type: ignore[arg-type]


def _apply_isolated_more_schedule_content(
    state: AgentState,
    *,
    profile: dict,
    raw_inputs: dict,
    schedule_state: object,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    target: str,
    text: str,
    current_count: int,
    last_text: str | None,
) -> dict | None:
    if target not in {"academic", "work"}:
        return None

    section_result = parse_fixed_schedule_section(
        text,
        target,  # type: ignore[arg-type]
        timezone=str(state.get("timezone", "America/Bogota")),
    )
    if section_result.needs_clarification:
        pending_items = list(section_result.pending_schedule_items)
        if not pending_items:
            return None
        academic_items = pending_items if target == "academic" else academic_pending_items
        work_items = pending_items if target == "work" else work_pending_items
        update = _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=update_schedule_flow_state(
                schedule_state,
                capture_target=target,
                capture_stage="awaiting_input",
            ),
            academic_pending_items=academic_items,
            work_pending_items=work_items,
            phase="schedules",
            awaiting_user_input=True,
            current_count=current_count,
            last_text=last_text,
            prompt=build_schedule_pending_prompt(target, pending_items),  # type: ignore[arg-type]
        )
        update.update(
            schedule_pending_interaction_update(
                state,
                academic_pending_items=academic_items,
                work_pending_items=work_items,
            )
        )
        return update

    if not section_result.blocks:
        return None

    sync_result = merge_completed_fixed_section(
        _existing_blocks_for_isolated_add(
            raw_inputs,
            schedule_state,
            target=target,
            timezone=str(state.get("timezone", "America/Bogota")),
        ),
        raw_inputs,
        target,  # type: ignore[arg-type]
        list(section_result.blocks),
    )
    return _build_schedule_update(
        state,
        profile=profile,
        raw_inputs=sync_result.raw_inputs.model_dump(mode="python"),
        schedule_state=update_schedule_flow_state(
            schedule_state,
            blocks=sync_result.schedule_blocks,
            capture_target=target,
            capture_stage="awaiting_input",
        ),
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
        phase="schedules",
        awaiting_user_input=False,
        current_count=current_count,
        last_text=last_text,
    )


def _existing_blocks_for_isolated_add(
    raw_inputs: dict,
    schedule_state: object,
    *,
    target: str,
    timezone: str,
) -> list:
    schedule_flow_state = ensure_schedule_flow_state(schedule_state)
    existing_blocks = list(schedule_flow_state.blocks)
    if has_block_type(existing_blocks, target):
        return existing_blocks

    field_name = "horario_laboral_text" if target == "work" else "horario_academico_text"
    existing_text = str(raw_inputs.get(field_name) or "").strip()
    if not existing_text:
        return existing_blocks

    parsed = parse_fixed_schedule_section(
        existing_text,
        target,  # type: ignore[arg-type]
        timezone=timezone,
    )
    if parsed.needs_clarification or not parsed.blocks:
        return existing_blocks
    return existing_blocks + list(parsed.blocks)


def _sanitize_image_refs(image_refs: list[str]) -> list[str]:
    return [
        materialize_image_reference(str(image_ref))
        for image_ref in image_refs
        if str(image_ref or "").strip()
    ]


def _store_schedule_image(raw_inputs: dict, target: str, image_ref: str) -> dict:
    updated = dict(raw_inputs)
    field_name = "horario_laboral_img" if target == "work" else "horario_academico_img"
    updated[field_name] = materialize_image_reference(image_ref)
    return updated


def _extract_schedule_text_from_image(image_ref: str, *, target: str) -> str:
    schedule_hint = "laboral" if target == "work" else "academico"
    result = llm_extract_schedule_from_image(image_ref, schedule_hint)
    if not result or not result.get("is_schedule"):
        return ""
    return str(result.get("extracted_text") or "").strip()


def _image_unreadable_prompt(target: str) -> str:
    label = "laboral" if target == "work" else "academico"
    return (
        f"Puedo recibir imagenes, pero no logre leer ese horario {label}. "
        "Enviamelo por texto con dias y horas, por ejemplo: "
        "Lunes 08:00-10:00 Calculo."
    )


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
    option = _parse_binary_more_option(text)
    if option == 1:
        return "more"
    if option == 2:
        return "continue"
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


def _parse_binary_more_option(text: str | None) -> int | None:
    clean = str(text or "").strip()
    if not clean:
        return None
    first_line = normalize_text(clean.splitlines()[0].strip())
    if first_line.startswith("1"):
        return 1
    if first_line.startswith("2"):
        return 2
    return None


def _extract_schedule_content_from_more_reply(
    text: str,
    *,
    target: str,
) -> str:
    raw = str(text or "").strip()
    if not raw:
        return raw

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) > 1 and _parse_more_decision(lines[0]) == "more":
        remainder = "\n".join(lines[1:]).strip()
        if remainder and _looks_like_schedule_content(remainder):
            return remainder

    prefix_patterns = (
        _MORE_WORK_INLINE_PREFIXES if target == "work" else _MORE_ACADEMIC_INLINE_PREFIXES
    )
    for pattern in prefix_patterns:
        match = pattern.match(raw)
        if match is None:
            continue
        candidate = str(match.group("content") or "").strip()
        if candidate and _looks_like_schedule_content(candidate):
            return candidate

    if _parse_more_decision(raw) == "more":
        match = _DAY_HINT_PATTERN.search(raw)
        if match is not None and match.start() > 0:
            candidate = raw[match.start() :].strip(" \n\t,;:-")
            if candidate and _looks_like_schedule_content(candidate):
                return candidate

    return raw


def _section_review_completion(
    *,
    occupation: str,
    target: str,
    prompts: ScheduleCapturePrompts,
) -> SectionReviewCompletion:
    if target == "academic" and occupation == "ambos":
        return SectionReviewCompletion(
            phase="schedules",
            awaiting_user_input=True,
            prompt=prompts.work,
            schedule_changes={
                "capture_target": "work",
                "capture_stage": "awaiting_input",
            },
        )
    if target in {"academic", "work"}:
        return SectionReviewCompletion(
            phase="extras",
            awaiting_user_input=False,
            schedule_changes={
                "capture_target": None,
                "capture_stage": "idle",
            },
        )
    return SectionReviewCompletion(
        phase="schedules",
        awaiting_user_input=True,
        prompt=_prompt_for_target("academic", occupation, prompts),
    )


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
    last_images: list[str] | None = None,
    prompt: str | None = None,
) -> dict:
    conversation_changes: dict[str, object] = {
        "phase": phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": awaiting_user_input,
    }
    if last_images is not None:
        conversation_changes["last_user_images"] = list(last_images)
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
