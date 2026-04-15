"""Servicio de aplicación para captura conversacional de prioridades."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.priorities.config import load_priorities_config
from agents.support.priorities.formatter import (
    build_difficult_subjects_prompt,
    build_priorities_invalid_prompt,
    build_priorities_processing_message,
    build_priorities_prompt,
    build_subject_urgency_prompt,
    build_top_subjects_prompt,
    build_weekly_priority_summary_prompt,
)
from agents.support.priorities.parser import parse_subject_catalog
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.priorities import (
    build_weekly_priorities,
    current_week_bounds,
    ensure_priorities_state,
    parse_number_selection,
    parse_priority_command,
    parse_urgency_details,
    resolve_prioritized_subjects,
    subject_items_to_update,
    update_priorities_state,
)


def handle_priorities_turn(state: AgentState) -> dict:
    """Coordina el subflujo semanal de prioridades."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    config = load_priorities_config()
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))
    timezone = state.get("timezone", "America/Bogota")
    reference_date = _reference_date(timezone)
    week_start, week_end = current_week_bounds(reference_date)
    priorities_state = ensure_priorities_state(state.get("priorities", {}))
    priorities = resolve_prioritized_subjects(
        schedule_blocks=list(schedule_state.blocks),
        subjects=list(state.get("subjects", [])),
        primary_technique_id=_primary_technique_id(study_profile),
    )
    current_subjects = subject_items_to_update(priorities.subject_items)
    subject_count = len(current_subjects)

    if not has_new_input:
        return {
            "subjects": current_subjects,
            "priorities": update_priorities_state(
                state.get("priorities", {}),
                status="collecting",
                prompt_version=_prompt_version(config.prompt_version),
                source=priorities.source,
                last_error=None,
                capture_stage="ask_update",
                week_start=week_start,
                week_end=week_end,
                draft=_seed_draft(priorities_state.draft, current_subjects),
            ),
            "phase": "priorities",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_priorities_prompt(
                    current_subjects,
                    source=priorities.source,
                    week_start=week_start,
                    week_end=week_end,
                ),
            ),
        }

    command = parse_priority_command(last_text)
    if command == "omitir":
        return {
            "subjects": current_subjects,
            "priorities": update_priorities_state(
                state.get("priorities", {}),
                status="skipped",
                prompt_version=_prompt_version(config.prompt_version),
                source=priorities.source,
                last_error=None,
                capture_stage=None,
                week_start=week_start,
                week_end=week_end,
            ),
            "phase": "end",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "Perfecto. Dejamos el ajuste fino de prioridades para la siguiente iteración.",
            ),
        }

    if command == "usar_horario":
        return _complete_with_schedule(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=priorities.source,
            prompt_version=_prompt_version(config.prompt_version),
            week_start=week_start,
            week_end=week_end,
        )

    if "|" in str(last_text or "") and (priorities_state.capture_stage in {None, "ask_update"}):
        return _handle_legacy_catalog(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            schedule_blocks=list(schedule_state.blocks),
            study_profile=study_profile,
            source=priorities.source,
            prompt_version=_prompt_version(config.prompt_version),
            week_start=week_start,
            week_end=week_end,
        )

    stage = priorities_state.capture_stage or "ask_update"
    draft = _seed_draft(priorities_state.draft, current_subjects)

    if stage == "ask_update":
        if command == "no" or _looks_like_later_choice(last_text):
            return _complete_with_schedule(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
            )
        if command == "confirmar" or _looks_like_yes(last_text) or _looks_like_update_choice(last_text):
            return _ask_top_subjects(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
            )
        selection = _parse_top_selection(last_text, subject_count)
        if selection.is_valid and selection.numbers:
            draft["importance_order"] = selection.numbers
            return _ask_urgent_subjects(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
            )
        return _invalid_update(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=priorities.source,
            prompt_version=_prompt_version(config.prompt_version),
            week_start=week_start,
            week_end=week_end,
            draft=draft,
            error="Responde `Sí, actualizarlas` o `Después`.",
            prompt=build_priorities_prompt(
                current_subjects,
                source=priorities.source,
                week_start=week_start,
                week_end=week_end,
            ),
        )

    if stage == "ask_top3":
        selection = _parse_top_selection(last_text, subject_count)
        if not selection.is_valid:
            return _invalid_update(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
                error=selection.error or "No pude leer ese ranking.",
                prompt=build_top_subjects_prompt(current_subjects),
            )
        draft["importance_order"] = selection.numbers
        return _ask_urgent_subjects(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=priorities.source,
            prompt_version=_prompt_version(config.prompt_version),
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        )

    if stage == "ask_urgent_subjects":
        subject_number = _current_urgency_subject_number(draft, subject_count)
        if subject_number is None:
            return _ask_difficult_subjects(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
            )
        if command in {"ninguna", "no"} or _looks_like_no_urgency(last_text):
            return _advance_subject_urgency(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
                subject_number=subject_number,
            )

        parsed_details = parse_urgency_details(
            last_text,
            subject_count=subject_count,
            reference_date=reference_date,
            timezone=timezone,
            required_subject_numbers=[subject_number],
            default_subject_number=subject_number,
        )
        if not parsed_details.is_valid:
            return _invalid_update(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
                error=parsed_details.error or "No pude leer ese evento.",
                prompt=build_subject_urgency_prompt(current_subjects, subject_number),
            )
        urgency_details = _draft_urgency_details(draft)
        urgency_details.extend(detail.__dict__ for detail in parsed_details.details)
        draft["urgency_details"] = urgency_details
        return _advance_subject_urgency(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=priorities.source,
            prompt_version=_prompt_version(config.prompt_version),
            week_start=week_start,
            week_end=week_end,
            draft=draft,
            subject_number=subject_number,
        )

    if stage == "ask_urgency_details":
        pending = [int(value) for value in list(draft.get("urgent_subject_numbers") or [])]
        parsed_details = parse_urgency_details(
            last_text,
            subject_count=subject_count,
            reference_date=reference_date,
            timezone=timezone,
            required_subject_numbers=pending,
        )
        if not parsed_details.is_valid:
            return _invalid_update(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
                error=parsed_details.error or "No pude leer los detalles.",
                prompt=build_subject_urgency_prompt(
                    current_subjects,
                    pending[0] if pending else 1,
                ),
            )
        draft["urgency_details"] = [
            detail.__dict__ for detail in parsed_details.details
        ]
        return _ask_difficult_subjects(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=priorities.source,
            prompt_version=_prompt_version(config.prompt_version),
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        )

    if stage == "ask_difficult_subjects":
        selection = parse_number_selection(
            last_text,
            subject_count=subject_count,
            min_count=0,
            max_count=min(3, subject_count),
            allow_none=True,
        )
        if not selection.is_valid:
            return _invalid_update(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
                error=selection.error or "No pude leer las materias dificiles.",
                prompt=build_difficult_subjects_prompt(current_subjects),
            )
        draft["difficult_subject_numbers"] = selection.numbers
        result = build_weekly_priorities(
            subjects=current_subjects,
            importance_order=[int(value) for value in list(draft.get("importance_order") or [])],
            urgency_details=list(draft.get("urgency_details") or []),
            difficult_subject_numbers=selection.numbers,
            reference_date=reference_date,
            timezone=timezone,
            source="weekly_flow",
        )
        draft["summary"] = result.summary
        return {
            "subjects": subject_items_to_update(result.subjects),
            "priorities": update_priorities_state(
                state.get("priorities", {}),
                status="collecting",
                prompt_version=_prompt_version(config.prompt_version),
                source="weekly_flow",
                last_error=None,
                capture_stage="confirm_summary",
                week_start=week_start,
                week_end=week_end,
                draft=draft,
            ),
            "phase": "priorities",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_weekly_priority_summary_prompt(result.subjects),
            ),
        }

    if stage == "confirm_summary":
        if command in {"confirmar"} or _looks_like_yes(last_text):
            return {
                "subjects": current_subjects,
                "priorities": update_priorities_state(
                    state.get("priorities", {}),
                    status="completed",
                    prompt_version=_prompt_version(config.prompt_version),
                    source="weekly_flow",
                    last_error=None,
                    capture_stage=None,
                    week_start=week_start,
                    week_end=week_end,
                    draft=draft,
                ),
                "phase": "study_plan",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": False,
                "messages": append_message(
                    messages,
                    "assistant",
                    build_priorities_processing_message(current_subjects),
                ),
            }
        if command == "editar" or command == "no":
            return _ask_top_subjects(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=current_subjects,
                source=priorities.source,
                prompt_version=_prompt_version(config.prompt_version),
                week_start=week_start,
                week_end=week_end,
                draft=draft,
            )
        return _invalid_update(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=priorities.source,
            prompt_version=_prompt_version(config.prompt_version),
            week_start=week_start,
            week_end=week_end,
            draft=draft,
            error="Responde `confirmar` para pasar al plan semanal o `editar` para ajustar.",
            prompt=build_weekly_priority_summary_prompt(current_subjects),
        )

    return _ask_top_subjects(
        state=state,
        messages=messages,
        current_count=current_count,
        last_text=last_text,
        subjects=current_subjects,
        source=priorities.source,
        prompt_version=_prompt_version(config.prompt_version),
        week_start=week_start,
        week_end=week_end,
        draft=draft,
    )


def _primary_technique_id(study_profile: dict) -> str | None:
    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _complete_with_schedule(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
) -> dict:
    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="completed",
            prompt_version=prompt_version,
            source=source,
            last_error=None,
            capture_stage=None,
            week_start=week_start,
            week_end=week_end,
            draft=_seed_draft({}, subjects),
        ),
        "phase": "study_plan",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            build_priorities_processing_message(subjects),
        ),
    }


def _handle_legacy_catalog(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    schedule_blocks: list,
    study_profile: dict,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
) -> dict:
    parsed = parse_subject_catalog(last_text or "")
    if not parsed.is_valid:
        current_subjects = subject_items_to_update(
            resolve_prioritized_subjects(
                schedule_blocks=schedule_blocks,
                subjects=list(state.get("subjects", [])),
                primary_technique_id=_primary_technique_id(study_profile),
            ).subject_items
        )
        return _invalid_update(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=source,
            prompt_version=prompt_version,
            week_start=week_start,
            week_end=week_end,
            draft=_seed_draft({}, current_subjects),
            error=parsed.error or "No pude procesar tus materias.",
            prompt=build_priorities_invalid_prompt(
                parsed.error or "No pude procesar tus materias.",
                current_subjects,
                source=source,
            ),
        )

    normalized_manual = resolve_prioritized_subjects(
        schedule_blocks=schedule_blocks,
        subjects=parsed.subjects,
        primary_technique_id=_primary_technique_id(study_profile),
    )
    subjects = subject_items_to_update(normalized_manual.subject_items)
    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="completed",
            prompt_version=prompt_version,
            source="legacy_manual",
            last_error=None,
            capture_stage=None,
            week_start=week_start,
            week_end=week_end,
            draft=_seed_draft({}, subjects),
        ),
        "phase": "study_plan",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            build_priorities_processing_message(subjects),
        ),
    }


def _ask_top_subjects(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
    draft: dict,
) -> dict:
    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="collecting",
            prompt_version=prompt_version,
            source=source,
            last_error=None,
            capture_stage="ask_top3",
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        ),
        "phase": "priorities",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", build_top_subjects_prompt(subjects)),
    }


def _ask_urgent_subjects(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
    draft: dict,
) -> dict:
    if not subjects:
        return _ask_difficult_subjects(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=subjects,
            source=source,
            prompt_version=prompt_version,
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        )
    subject_number = _current_urgency_subject_number(draft, len(subjects)) or 1
    draft["urgency_subject_index"] = subject_number
    draft.setdefault("urgency_details", [])
    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="collecting",
            prompt_version=prompt_version,
            source=source,
            last_error=None,
            capture_stage="ask_urgent_subjects",
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        ),
        "phase": "priorities",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            build_subject_urgency_prompt(subjects, subject_number),
        ),
    }


def _ask_difficult_subjects(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
    draft: dict,
) -> dict:
    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="collecting",
            prompt_version=prompt_version,
            source=source,
            last_error=None,
            capture_stage="ask_difficult_subjects",
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        ),
        "phase": "priorities",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            build_difficult_subjects_prompt(subjects),
        ),
    }


def _invalid_update(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
    draft: dict,
    error: str,
    prompt: str,
) -> dict:
    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="collecting",
            prompt_version=prompt_version,
            source=source,
            last_error=error,
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        ),
        "phase": "priorities",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", f"{error}\n\n{prompt}"),
    }


def _parse_top_selection(text: str | None, subject_count: int):
    expected = min(3, max(1, subject_count))
    return parse_number_selection(
        text,
        subject_count=subject_count,
        min_count=expected,
        max_count=expected,
        ordered=True,
    )


def _advance_subject_urgency(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
    draft: dict,
    subject_number: int,
) -> dict:
    next_subject_number = subject_number + 1
    if next_subject_number > len(subjects):
        draft.pop("urgency_subject_index", None)
        return _ask_difficult_subjects(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=subjects,
            source=source,
            prompt_version=prompt_version,
            week_start=week_start,
            week_end=week_end,
            draft=draft,
        )
    draft["urgency_subject_index"] = next_subject_number
    return _ask_urgent_subjects(
        state=state,
        messages=messages,
        current_count=current_count,
        last_text=last_text,
        subjects=subjects,
        source=source,
        prompt_version=prompt_version,
        week_start=week_start,
        week_end=week_end,
        draft=draft,
    )


def _current_urgency_subject_number(draft: dict, subject_count: int) -> int | None:
    raw_value = draft.get("urgency_subject_index", 1)
    try:
        subject_number = int(raw_value)
    except (TypeError, ValueError):
        subject_number = 1
    if 1 <= subject_number <= subject_count:
        return subject_number
    return None


def _draft_urgency_details(draft: dict) -> list[dict[str, object]]:
    return [dict(item) for item in list(draft.get("urgency_details") or [])]


def _seed_draft(raw_draft: dict | None, subjects: list) -> dict[str, object]:
    draft = dict(raw_draft or {})
    draft.setdefault("subject_names", [subject.nombre for subject in subjects])
    return draft


def _prompt_version(config_value: str) -> str:
    return config_value if config_value and config_value != "v1" else "v2"


def _reference_date(timezone: str):
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota"))).date()
    except Exception:
        return datetime.now().date()


def _looks_like_yes(text: str | None) -> bool:
    return " ".join(str(text or "").strip().lower().split()) in {
        "si",
        "sí",
        "s",
        "ok",
        "listo",
        "dale",
    }


def _looks_like_update_choice(text: str | None) -> bool:
    return " ".join(str(text or "").strip().lower().split()) in {
        "1",
        "si actualizarlas",
        "sí actualizarlas",
        "si, actualizarlas",
        "sí, actualizarlas",
        "actualizarlas",
        "actualizar",
    }


def _looks_like_later_choice(text: str | None) -> bool:
    return " ".join(str(text or "").strip().lower().split()) in {
        "2",
        "despues",
        "después",
        "dejarlo por ahora",
        "mas tarde",
        "más tarde",
        "luego",
    }


def _looks_like_no_urgency(text: str | None) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    return normalized.startswith("no tengo") or normalized.startswith("no hay")
