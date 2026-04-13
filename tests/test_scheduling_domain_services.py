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
    complete_pending_extracurricular_item,
)
from services.scheduling.extracurricular_state import (
    build_extracurricular_items_source_text,
    merge_extracurricular_items,
)
from services.scheduling.pending_extracurricular_support import (
    build_extracurricular_pending_prompt,
)
from services.scheduling.pending_schedule_support import build_schedule_pending_prompt
from services.scheduling.parsing_results import SectionPipelineResult
from services.scheduling import WeeklyScheduleBlock
from schemas.scheduling import PendingExtracurricularItem, PendingScheduleItem


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


def test_contextual_schedule_parser_respects_new_inline_title_after_subject_context() -> None:
    blocks, clarifications, pending_items = parse_schedule_section_with_context(
        "\n".join(
            [
                "Problem Discovery & Solution Design With Artificial Intelligence",
                "Martes de 4:00 p.m. a 6:00 p.m.",
                "Lunes - Cálculo - 07:00 a 09:00",
            ]
        ),
        "academic",
    )

    assert clarifications == []
    assert pending_items == []
    assert {(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks} == {
        (
            "Problem Discovery & Solution Design With Artificial Intelligence",
            "tuesday",
            "16:00",
            "18:00",
        ),
        ("Cálculo", "monday", "07:00", "09:00"),
    }


def test_build_schedule_pending_prompt_uses_friendly_copy_and_sanitized_title() -> None:
    prompt = build_schedule_pending_prompt(
        "academic",
        [
            PendingScheduleItem(
                schedule_type="academic",
                title="Cálculo - 07:00 A",
                days=["Lunes"],
                missing_fields=["hora de inicio y fin"],
                raw_text="Lunes - Cálculo - 07:00 a",
            )
        ],
    )

    assert "necesito algunos datos para cerrar bien esta materia" in prompt.lower()
    assert "\nCálculo\n" in prompt
    assert "me falta: hora de inicio y fin" in prompt.lower()
    assert "Lunes - Cálculo - 07:00 a 09:00" in prompt


def test_complete_pending_schedule_item_prefers_full_replacement_reply() -> None:
    blocks, _clarifications, updated_pending = complete_pending_schedule_item(
        "Lunes - Cálculo - 07:00 a 09:00",
        PendingScheduleItem(
            schedule_type="academic",
            title="Cálculo - 07:00 A",
            days=["Lunes"],
            missing_fields=["hora de inicio y fin"],
            raw_text="Lunes - Cálculo - 07:00 a",
        ),
    )

    assert updated_pending is None
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Cálculo", "monday", "07:00", "09:00")
    ]


def test_complete_pending_work_item_uses_same_replacement_logic() -> None:
    blocks, _clarifications, updated_pending = complete_pending_schedule_item(
        "Martes - Trabajo - 09:00 a 17:00",
        PendingScheduleItem(
            schedule_type="work",
            title="Trabajo",
            days=["Lunes"],
            missing_fields=["hora de inicio y fin"],
            raw_text="Lunes - Trabajo - 07:00 a",
        ),
    )

    assert updated_pending is None
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Trabajo", "tuesday", "09:00", "17:00")
    ]


def test_build_extracurricular_pending_prompt_uses_friendly_copy() -> None:
    prompt = build_extracurricular_pending_prompt(
        [
            PendingExtracurricularItem(
                nombre="Iglesia",
                dias=["Domingo"],
                missing_fields=["hora de inicio y fin"],
                es_variable=False,
                raw_text="Domingo - Iglesia",
            )
        ]
    )

    assert "necesito algunos datos para cerrar bien esta actividad" in prompt.lower()
    assert "\nIglesia\n" in prompt
    assert "Domingo - Iglesia - 07:00 a 09:00" in prompt


def test_complete_pending_extracurricular_item_prefers_full_replacement_reply() -> None:
    item, missing = complete_pending_extracurricular_item(
        "Lunes - Cálculo - 07:00 a 09:00",
        PendingExtracurricularItem(
            nombre="Cálculo - 07:00 A",
            dias=["Lunes"],
            missing_fields=["hora de inicio y fin"],
            es_variable=False,
            raw_text="Lunes - Cálculo - 07:00 a",
        ),
        expected_is_variable=False,
    )

    assert missing == []
    assert item.nombre == "Calculo"
    assert item.dias == ["Lunes"]
    assert item.hora_inicio == "07:00"
    assert item.hora_fin == "09:00"


def test_extracurricular_parser_keeps_valid_items_and_pending_context() -> None:
    items, missing, pending = parse_extracurricular_items_with_context(
        "voy los dias sabados al gimnasio de 10 am a 12 pm y los domingos voy a la iglesia"
    )

    assert [item.nombre for item in items] == ["Gimnasio"]
    assert pending
    assert pending[0].nombre == "Iglesia"
    assert "Iglesia: hora de inicio y fin" in missing
