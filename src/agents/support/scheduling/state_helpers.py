"""Helpers tipados para el subestado de scheduling y sus entradas crudas.

Estos helpers permiten trabajar internamente con modelos Pydantic del dominio,
pero siguen devolviendo diccionarios compatibles con el contrato actual del
grafo y con las pruebas existentes.
"""

from __future__ import annotations

from typing import Literal

from agents.support.scheduling.contextual_parser import serialize_blocks_for_schedule_type
from agents.support.scheduling.models import (
    ScheduleFlowState,
    ensure_schedule_conflict,
    ensure_weekly_block,
)
from agents.support.state import RawInputs

FixedScheduleTarget = Literal["academic", "work"]


def ensure_schedule_flow_state(
    raw_state: ScheduleFlowState | dict | None,
) -> ScheduleFlowState:
    """Coacciona el subestado `schedule` a su modelo canónico."""

    if isinstance(raw_state, ScheduleFlowState):
        return raw_state.model_copy(deep=True)

    data = dict(raw_state or {})
    data["blocks"] = [
        ensure_weekly_block(block) for block in data.get("blocks", [])
    ]
    data["conflicts"] = [
        ensure_schedule_conflict(conflict)
        for conflict in data.get("conflicts", [])
    ]
    return ScheduleFlowState(**data)


def schedule_flow_state_to_update(schedule_state: ScheduleFlowState) -> dict[str, object]:
    """Serializa `ScheduleFlowState` preservando bloques/conflictos como modelos."""

    return {
        "blocks": list(schedule_state.blocks),
        "conflicts": list(schedule_state.conflicts),
        "summary_text": schedule_state.summary_text,
        "review_stage": schedule_state.review_stage,
        "capture_target": schedule_state.capture_target,
        "capture_stage": schedule_state.capture_stage,
        "correction_target": schedule_state.correction_target,
        "pending_correction_text": schedule_state.pending_correction_text,
        "conflicts_accepted": schedule_state.conflicts_accepted,
        "persisted_profile_id": schedule_state.persisted_profile_id,
        "persistence_error": schedule_state.persistence_error,
    }


def update_schedule_flow_state(
    raw_state: ScheduleFlowState | dict | None,
    **changes: object,
) -> dict[str, object]:
    """Aplica cambios al subestado de scheduling y devuelve un update compatible."""

    schedule_state = ensure_schedule_flow_state(raw_state)
    if "blocks" in changes and changes["blocks"] is not None:
        changes["blocks"] = [
            ensure_weekly_block(block) for block in list(changes["blocks"])
        ]
    if "conflicts" in changes and changes["conflicts"] is not None:
        changes["conflicts"] = [
            ensure_schedule_conflict(conflict)
            for conflict in list(changes["conflicts"])
        ]
    updated_state = schedule_state.model_copy(update=changes)
    return schedule_flow_state_to_update(updated_state)


def reset_schedule_review_state(
    raw_state: ScheduleFlowState | dict | None,
    blocks: list | None = None,
) -> dict[str, object]:
    """Limpia metadatos de revisión sin alterar el contrato del estado."""

    schedule_state = ensure_schedule_flow_state(raw_state)
    updated_blocks = schedule_state.blocks if blocks is None else list(blocks)
    return update_schedule_flow_state(
        schedule_state,
        blocks=updated_blocks,
        summary_text=None,
        review_stage="idle",
        correction_target=None,
        pending_correction_text=None,
        conflicts=[],
        conflicts_accepted=False,
    )


def ensure_raw_inputs(raw_inputs: RawInputs | dict | None) -> RawInputs:
    """Coacciona `raw_inputs` al modelo canónico del estado."""

    if isinstance(raw_inputs, RawInputs):
        return raw_inputs.model_copy(deep=True)
    return RawInputs(**dict(raw_inputs or {}))


def raw_inputs_to_update(raw_inputs: RawInputs) -> dict[str, object]:
    """Serializa `RawInputs` preservando el formato esperado por el grafo."""

    return raw_inputs.model_dump(mode="python")


def append_schedule_input_text(
    raw_inputs: RawInputs | dict | None,
    target: FixedScheduleTarget,
    text: str,
) -> dict[str, object]:
    """Concatena texto adicional de horario a la sección correspondiente."""

    updated = ensure_raw_inputs(raw_inputs)
    clean_text = str(text or "").strip()
    if not clean_text:
        return raw_inputs_to_update(updated)

    field = _schedule_input_field(target)
    existing = str(getattr(updated, field) or "").strip()
    combined = "\n".join(part for part in [existing, clean_text] if part)
    return raw_inputs_to_update(
        updated.model_copy(update={field: combined or None})
    )


def replace_schedule_input_text(
    raw_inputs: RawInputs | dict | None,
    target: FixedScheduleTarget,
    text: str,
) -> dict[str, object]:
    """Reemplaza el texto crudo de una sección fija del horario."""

    updated = ensure_raw_inputs(raw_inputs)
    field = _schedule_input_field(target)
    clean_text = str(text or "").strip() or None
    return raw_inputs_to_update(updated.model_copy(update={field: clean_text}))


def serialize_schedule_blocks_to_raw_inputs(
    raw_inputs: RawInputs | dict | None,
    target: FixedScheduleTarget,
    blocks: list,
) -> dict[str, object]:
    """Sincroniza `raw_inputs` desde bloques ya normalizados."""

    normalized_blocks = [ensure_weekly_block(block) for block in blocks]
    serialized = serialize_blocks_for_schedule_type(normalized_blocks, target)
    return replace_schedule_input_text(raw_inputs, target, serialized)


def _schedule_input_field(target: FixedScheduleTarget) -> str:
    return "horario_academico_text" if target == "academic" else "horario_laboral_text"
