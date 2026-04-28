"""Helpers tipados para el subestado de scheduling y sus entradas crudas.

Estos helpers permiten trabajar internamente con modelos Pydantic del dominio,
pero siguen devolviendo diccionarios compatibles con el contrato actual del
grafo y con las pruebas existentes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from agents.support.state import AgentState
from services.scheduling.models import (
    ScheduleFlowState,
    ensure_schedule_conflict,
    ensure_weekly_block,
)
from services.scheduling.event_projection import blocks_to_schedule_events
from services.scheduling.raw_input_sync import (
    sync_schedule_blocks_to_raw_inputs,
)
from schemas.scheduling import (
    Event,
    ExtracurricularItem,
    PendingExtracurricularItem,
    PendingScheduleItem,
    RawInputs,
    SchedulePreview,
)

FixedScheduleTarget = Literal["academic", "work"]
_SCHEDULING_FIELDS = set(AgentState.field_groups()["scheduling"])


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


def ensure_scheduling_state(
    raw_state: AgentState | Mapping[str, object] | None,
) -> Any:
    """Coacciona la partición completa de scheduling a su vista tipada actual."""

    if isinstance(raw_state, AgentState):
        return raw_state.scheduling_state
    return AgentState(**dict(raw_state or {})).scheduling_state


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
        "editing_block_id": schedule_state.editing_block_id,
        "editing_field": schedule_state.editing_field,
        "pending_correction_text": schedule_state.pending_correction_text,
        "conflicts_accepted": schedule_state.conflicts_accepted,
        "schedule_end_date": schedule_state.schedule_end_date,
        "persisted_profile_id": schedule_state.persisted_profile_id,
        "persistence_error": schedule_state.persistence_error,
        "renewal_stage": schedule_state.renewal_stage,
        "repair_stage": schedule_state.repair_stage,
    }


def scheduling_state_to_update(
    raw_state: AgentState | Mapping[str, object] | None,
) -> dict[str, object]:
    """Serializa la partición de scheduling al contrato plano del grafo."""

    normalized = ensure_scheduling_state(raw_state)
    return {
        "raw_inputs": raw_inputs_to_update(normalized.raw_inputs),
        "extras_collect_stage": normalized.extras_collect_stage,
        "extras_pending_is_variable": normalized.extras_pending_is_variable,
        "extras_pending_items": list(normalized.extras_pending_items),
        "academic_pending_items": list(normalized.academic_pending_items),
        "work_pending_items": list(normalized.work_pending_items),
        "extracurricular": list(normalized.extracurricular),
        "schedule_preview": normalized.schedule_preview.model_dump(mode="python"),
        "schedule": schedule_flow_state_to_update(normalized.schedule),
    }


def update_scheduling_state(
    raw_state: AgentState | Mapping[str, object] | None,
    **changes: object,
) -> dict[str, object]:
    """Valida cambios de scheduling y devuelve solo los campos modificados."""

    if not changes:
        return {}

    unexpected = sorted(set(changes) - _SCHEDULING_FIELDS)
    if unexpected:
        joined = ", ".join(unexpected)
        raise KeyError(f"Campos scheduling desconocidos: {joined}")

    normalized = ensure_scheduling_state(raw_state)
    normalized_changes = _normalize_scheduling_changes(changes)
    data = normalized.model_dump(mode="python")
    data.update(normalized_changes)
    updated = normalized.__class__(**data)

    payload: dict[str, object] = {}
    for field_name in normalized_changes:
        payload[field_name] = _serialize_scheduling_field(updated, field_name)
    return payload


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
        editing_block_id=None,
        editing_field=None,
        pending_correction_text=None,
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=None,
        renewal_stage="idle",
        repair_stage="idle",
    )


def ensure_raw_inputs(raw_inputs: RawInputs | dict | None) -> RawInputs:
    """Coacciona `raw_inputs` al modelo canónico del estado."""

    if isinstance(raw_inputs, RawInputs):
        return raw_inputs.model_copy(deep=True)
    return RawInputs(**dict(raw_inputs or {}))


def ensure_schedule_preview(
    raw_preview: SchedulePreview | dict | None,
) -> SchedulePreview:
    """Coacciona `schedule_preview` al modelo canónico del estado."""

    if isinstance(raw_preview, SchedulePreview):
        return raw_preview.model_copy(deep=True)
    return SchedulePreview(**dict(raw_preview or {}))


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
    return sync_schedule_blocks_to_raw_inputs(
        raw_inputs,
        target,
        normalized_blocks,
    ).model_dump(mode="python")


def _schedule_input_field(target: FixedScheduleTarget) -> str:
    return "horario_academico_text" if target == "academic" else "horario_laboral_text"


def ensure_event(raw_event: Event | dict) -> Event:
    """Coacciona un evento derivado del horario a su modelo canónico."""

    if isinstance(raw_event, Event):
        return raw_event.model_copy(deep=True)
    return Event(**dict(raw_event))


def ensure_extracurricular_item(
    raw_item: ExtracurricularItem | dict,
) -> ExtracurricularItem:
    """Coacciona una actividad extracurricular a su modelo canónico."""

    if isinstance(raw_item, ExtracurricularItem):
        return raw_item.model_copy(deep=True)
    return ExtracurricularItem(**dict(raw_item))


def ensure_pending_extracurricular_item(
    raw_item: PendingExtracurricularItem | dict,
) -> PendingExtracurricularItem:
    """Coacciona un pendiente extracurricular a su modelo canónico."""

    if isinstance(raw_item, PendingExtracurricularItem):
        return raw_item.model_copy(deep=True)
    return PendingExtracurricularItem(**dict(raw_item))


def ensure_pending_schedule_item(
    raw_item: PendingScheduleItem | dict,
) -> PendingScheduleItem:
    """Coacciona un pendiente académico/laboral a su modelo canónico."""

    if isinstance(raw_item, PendingScheduleItem):
        return raw_item.model_copy(deep=True)
    return PendingScheduleItem(**dict(raw_item))


def _normalize_scheduling_changes(changes: dict[str, object]) -> dict[str, object]:
    normalized = dict(changes)
    if "raw_inputs" in normalized and normalized["raw_inputs"] is not None:
        normalized["raw_inputs"] = ensure_raw_inputs(normalized["raw_inputs"])
    if "schedule_preview" in normalized and normalized["schedule_preview"] is not None:
        normalized["schedule_preview"] = ensure_schedule_preview(normalized["schedule_preview"])
    if "schedule" in normalized and normalized["schedule"] is not None:
        normalized["schedule"] = ensure_schedule_flow_state(normalized["schedule"])
    if "extracurricular" in normalized and normalized["extracurricular"] is not None:
        normalized["extracurricular"] = [
            ensure_extracurricular_item(item)
            for item in list(normalized["extracurricular"])
        ]
    if "extras_pending_items" in normalized and normalized["extras_pending_items"] is not None:
        normalized["extras_pending_items"] = [
            ensure_pending_extracurricular_item(item)
            for item in list(normalized["extras_pending_items"])
        ]
    if "academic_pending_items" in normalized and normalized["academic_pending_items"] is not None:
        normalized["academic_pending_items"] = [
            ensure_pending_schedule_item(item)
            for item in list(normalized["academic_pending_items"])
        ]
    if "work_pending_items" in normalized and normalized["work_pending_items"] is not None:
        normalized["work_pending_items"] = [
            ensure_pending_schedule_item(item)
            for item in list(normalized["work_pending_items"])
        ]
    return normalized


def _serialize_scheduling_field(state: Any, field_name: str) -> object:
    value = getattr(state, field_name)
    if field_name == "raw_inputs":
        return raw_inputs_to_update(value)
    if field_name == "schedule_preview":
        return value.model_dump(mode="python")
    if field_name == "schedule":
        return schedule_flow_state_to_update(value)
    if field_name in {
        "extracurricular",
        "extras_pending_items",
        "academic_pending_items",
        "work_pending_items",
    }:
        return list(value)
    return value


def get_all_schedule_events(state: AgentState | Mapping[str, object]) -> list[Event]:
    """Deriva todos los eventos del horario a partir de bloques y extracurriculares.

    schedule.blocks es la fuente de verdad para el horario fijo (académico/laboral).
    Los eventos extracurriculares se recuperan del campo `tentativo` de cada item,
    que se popula en el nodo generate_tentative_extracurricular durante el setup.
    """
    from services.scheduling.extracurricular_events import build_fixed_events

    raw_schedule = (
        state.get("schedule", {}) if hasattr(state, "get") else getattr(state, "schedule", {})
    )
    schedule_state = ensure_schedule_flow_state(raw_schedule)
    block_events: list[Event] = blocks_to_schedule_events(list(schedule_state.blocks))

    tz = str(
        state.get("timezone", "America/Bogota")
        if hasattr(state, "get")
        else getattr(state, "timezone", "America/Bogota")
    )
    raw_extras = (
        state.get("extracurricular", []) if hasattr(state, "get") else getattr(state, "extracurricular", [])
    )
    extra_events: list[Event] = []
    for raw_item in raw_extras:
        item = ensure_extracurricular_item(raw_item)
        if item.tentativo:
            extra_events.extend(item.tentativo)
        elif not item.es_variable and item.dias and item.hora_inicio:
            extra_events.extend(build_fixed_events(item, tz))

    return block_events + extra_events
