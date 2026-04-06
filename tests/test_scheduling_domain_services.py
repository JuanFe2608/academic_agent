"""Pruebas directas para utilidades puras del dominio scheduling."""

from __future__ import annotations

from services.scheduling.contextual_schedule_parsing import (
    complete_pending_schedule_item,
    parse_schedule_section_with_context,
)
from services.scheduling.correction_sync import (
    merge_completed_fixed_section,
    sync_fixed_section_result,
)
from services.scheduling.extracurricular_parsing import (
    parse_extracurricular_items_with_context,
)
from services.scheduling.extracurricular_state import (
    build_extracurricular_items_source_text,
    merge_extracurricular_items,
)
from services.scheduling.parsing_results import SectionPipelineResult
from services.scheduling import WeeklyScheduleBlock


def _academic_block(title: str = "Calculo", day: str = "monday") -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day,  # type: ignore[arg-type]
        start_time="08:00",
        end_time="10:00",
        source_text="bloque",
    )


def _work_block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="work",
        title="Trabajo",
        day_of_week="monday",
        start_time="09:00",
        end_time="18:00",
        source_text="bloque",
    )


def test_merge_completed_fixed_section_syncs_schedule_and_raw_inputs() -> None:
    initial_academic = _academic_block("Calculo")
    completed = [_academic_block("Programacion", "tuesday")]

    result = merge_completed_fixed_section(
        [initial_academic, _work_block()],
        {"horario_academico_text": "Lunes 08:00-10:00 Calculo"},
        "academic",
        completed,
    )

    assert any(block.block_type == "work" for block in result.schedule_blocks)
    assert any(block.title == "Programacion" for block in result.target_blocks)
    assert "Martes 08:00-10:00 Programacion" in str(result.raw_inputs.horario_academico_text)


def test_sync_fixed_section_result_replaces_only_target_section() -> None:
    result = sync_fixed_section_result(
        [_academic_block("Calculo"), _work_block()],
        {"horario_academico_text": "Lunes 08:00-10:00 Calculo"},
        "academic",
        SectionPipelineResult(blocks=[_academic_block("Fisica", "wednesday")]),
    )

    academic_titles = [block.title for block in result.schedule_blocks if block.block_type == "academic"]
    assert academic_titles == ["Fisica"]
    assert any(block.block_type == "work" for block in result.schedule_blocks)
    assert "Miercoles 08:00-10:00 Fisica" in str(result.raw_inputs.horario_academico_text)


def test_merge_extracurricular_items_dedupes_and_serializes_stably() -> None:
    merged = merge_extracurricular_items(
        [
            {
                "nombre": "Gimnasio",
                "es_variable": False,
                "detalle": "Gimnasio martes 18:00-19:00",
                "dias": ["martes"],
                "hora_inicio": "18:00",
                "hora_fin": "19:00",
            }
        ],
        [
            {
                "nombre": "gimnasio",
                "es_variable": False,
                "detalle": "Gimnasio martes 18:00-19:00",
                "dias": ["martes"],
                "hora_inicio": "18:00",
                "hora_fin": "19:00",
            },
            {
                "nombre": "Natacion",
                "es_variable": False,
                "detalle": "Natacion jueves 06:00-07:00",
                "dias": ["jueves"],
                "hora_inicio": "06:00",
                "hora_fin": "07:00",
            },
        ],
    )

    assert [item.nombre for item in merged] == ["Gimnasio", "Natacion"]
    serialized = build_extracurricular_items_source_text(merged)
    assert "Gimnasio martes 18:00-19:00" in serialized
    assert "Natacion jueves 06:00-07:00" in serialized


def test_contextual_schedule_parser_completes_pending_academic_item() -> None:
    _blocks, _clarifications, pending_items = parse_schedule_section_with_context(
        "Martes y jueves de 6 a 8",
        "academic",
    )

    completed_blocks, _clarifications, updated_pending = complete_pending_schedule_item(
        "Programacion",
        pending_items[0],
    )

    assert updated_pending is None
    assert {(block.day_of_week, block.title) for block in completed_blocks} == {
        ("tuesday", "Programacion"),
        ("thursday", "Programacion"),
    }


def test_extracurricular_parser_keeps_valid_items_and_pending_context() -> None:
    items, missing, pending = parse_extracurricular_items_with_context(
        "voy los dias sabados al gimnasio de 10 am a 12 pm y los domingos voy a la iglesia"
    )

    assert [item.nombre for item in items] == ["Gimnasio"]
    assert pending
    assert pending[0].nombre == "Iglesia"
    assert "Iglesia: hora de inicio y fin" in missing
