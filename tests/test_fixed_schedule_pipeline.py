"""Pruebas del pipeline unificado para horario fijo."""

from __future__ import annotations

from agents.support.scheduling.conflicts import detect_schedule_conflicts
from agents.support.scheduling.pipeline import (
    parse_extracurricular_section,
    parse_fixed_schedule_section,
)


def test_parse_fixed_schedule_section_accepts_simple_academic_line_without_meridiem() -> None:
    result = parse_fixed_schedule_section(
        "Lunes - Cálculo - 7 a 9",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Cálculo", "monday", "07:00", "09:00"),
    ]


def test_parse_fixed_schedule_section_handles_work_range_with_natural_language() -> None:
    result = parse_fixed_schedule_section(
        "Trabajo todos los días de lunes a viernes de 7 am a 9 pm.",
        "work",
    )

    assert result.needs_clarification is False
    assert len(result.blocks) == 5
    assert all(block.title == "Trabajo" for block in result.blocks)
    assert all(block.start_time == "07:00" for block in result.blocks)
    assert all(block.end_time == "21:00" for block in result.blocks)


def test_parse_fixed_schedule_section_tolerates_minor_day_typo_in_academic_text() -> None:
    result = parse_fixed_schedule_section(
        "Marte y viernes - Calculo - 15:00 a 19:30",
        "academic",
    )

    assert result.needs_clarification is False
    assert [
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in result.blocks
    ] == [
        ("Calculo", "tuesday", "15:00", "19:30"),
        ("Calculo", "friday", "15:00", "19:30"),
    ]


def test_parse_fixed_schedule_section_tolerates_minor_day_typo_in_work_exception() -> None:
    result = parse_fixed_schedule_section(
        "trabajo todos los dias menos vierne de 4 pm a 11 pm",
        "work",
    )

    assert result.needs_clarification is False
    assert [block.day_of_week for block in result.blocks] == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "saturday",
        "sunday",
    ]
    assert all(block.start_time == "16:00" for block in result.blocks)
    assert all(block.end_time == "23:00" for block in result.blocks)


def test_parse_fixed_schedule_section_splits_multiple_classes_with_same_day_context() -> None:
    result = parse_fixed_schedule_section(
        "Los lunes tengo cálculo de 7 a 9 y luego física de 10 a 12",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Cálculo", "monday", "07:00", "09:00"),
        ("Física", "monday", "10:00", "12:00"),
    ]


def test_parse_fixed_schedule_section_splits_multiple_entries_with_distinct_days() -> None:
    result = parse_fixed_schedule_section(
        "martes 10-12 física y jueves 2-4 pm química",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Física", "tuesday", "10:00", "12:00"),
        ("Química", "thursday", "14:00", "16:00"),
    ]


def test_parse_fixed_schedule_section_splits_multiple_classes_after_single_day() -> None:
    result = parse_fixed_schedule_section(
        (
            "Martes Gerencia de proyectos 7 a 9, Android de 11am a 1pm, "
            "solución de problemas con IA 4 pm a 6 pm"
        ),
        "academic",
    )

    assert result.needs_clarification is False
    assert [
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in result.blocks
    ] == [
        ("Gerencia Proyectos", "tuesday", "07:00", "09:00"),
        ("Android", "tuesday", "11:00", "13:00"),
        ("Solución Problemas Con Ia", "tuesday", "16:00", "18:00"),
    ]


def test_parse_fixed_schedule_section_accepts_natural_class_sentence() -> None:
    result = parse_fixed_schedule_section(
        "Tengo clase de Bases de Datos los lunes de 8:00 a.m. a 10:00 a.m.",
        "academic",
    )

    assert result.needs_clarification is False
    assert [
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in result.blocks
    ] == [("Bases Datos", "monday", "08:00", "10:00")]


def test_parse_fixed_schedule_section_ignores_equivalent_military_time_explanation() -> None:
    result = parse_fixed_schedule_section(
        (
            "Los lunes tengo Bases de Datos de 8 am a 10 am y los miércoles tengo "
            "Ingeniería de Software de 2pm a 4pm o en horario militar de 14:00 a 16:00"
        ),
        "academic",
    )

    assert result.needs_clarification is False
    assert [
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in result.blocks
    ] == [
        ("Bases Datos", "monday", "08:00", "10:00"),
        ("Ingeniería Software", "wednesday", "14:00", "16:00"),
    ]


def test_parse_fixed_schedule_section_accepts_compact_day_title_time_order() -> None:
    result = parse_fixed_schedule_section(
        "jueves laboratorio 18-21",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Laboratorio", "thursday", "18:00", "21:00"),
    ]


def test_parse_fixed_schedule_section_marks_missing_title() -> None:
    result = parse_fixed_schedule_section(
        "lunes 7-9",
        "academic",
    )

    assert result.needs_clarification is True
    assert result.pending_schedule_items
    assert "nombre de la materia o actividad" in result.pending_schedule_items[0].missing_fields


def test_parse_fixed_schedule_section_rejects_image_placeholder_as_academic_title() -> None:
    result = parse_fixed_schedule_section(
        "Lunes 06:00-07:00 Image",
        "academic",
    )

    assert result.needs_clarification is True
    assert result.blocks == []
    assert result.pending_schedule_items
    pending = result.pending_schedule_items[0]
    assert pending.title == ""
    assert pending.raw_text == "Lunes 06:00-07:00"
    assert "nombre de la materia o actividad" in pending.missing_fields


def test_parse_fixed_schedule_section_ignores_image_placeholder_subject_line() -> None:
    result = parse_fixed_schedule_section(
        "Image\nLunes de 6:00 a 7:00",
        "academic",
    )

    assert result.needs_clarification is True
    assert result.blocks == []
    assert result.pending_schedule_items
    assert result.pending_schedule_items[0].title == ""
    assert "nombre de la materia o actividad" in result.pending_schedule_items[0].missing_fields


def test_parse_fixed_schedule_section_preserves_subject_across_image_lines() -> None:
    result = parse_fixed_schedule_section(
        "\n".join(
            [
                "Código asignatura: CT10068",
                "",
                "GERENCIA DE PROYECTOS DE TI",
                "3.0 créditos, Grupo D-2",
                "Image",
                "MAR,VIE 07:00:00-09:00:00, MAR,VIE 07:00:00-09:00:00,",
                "Image",
                "03-02-2026- 29-05-2026",
                "Image",
                "BOGOTA | Bloque AA | Salón 714AA,",
                "Código asignatura: CT13009",
                "",
                "TRABAJO DE GRADO II",
                "4.0 créditos, Grupo D-5",
                "Image",
                "MIE 07:00:00-11:00:00, MIE 07:00:00-11:00:00,",
            ]
        ),
        "academic",
    )

    assert result.needs_clarification is False
    assert result.pending_schedule_items == []
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Gerencia De Proyectos De Ti", "tuesday", "07:00", "09:00"),
        ("Gerencia De Proyectos De Ti", "friday", "07:00", "09:00"),
        ("Trabajo De Grado Ii", "wednesday", "07:00", "11:00"),
    ]


def test_parse_fixed_schedule_section_accepts_full_university_email_paste() -> None:
    result = parse_fixed_schedule_section(
        "\n".join(
            [
                "Hola JUAN FELIPE JARAMILLO RODRIGUEZ:",
                "¡Tenemos buenas noticias!, tu horario para el periodo académico 2026-1 se ha guardado.",
                "Te presentamos el detalle de tu horario:",
                "67000912",
                "JUAN FELIPE JARAMILLO RODRIGUEZ",
                "INGENIERÍA DE SISTEMAS Y COMPUTACIÓN",
                "Total asignaturas inscritas: 5",
                "Código asignatura: CT10068",
                "GERENCIA DE PROYECTOS DE TI",
                "3.0 créditos, Grupo D-2",
                "Image",
                "MAR,VIE 07:00:00-09:00:00, MAR,VIE 07:00:00-09:00:00,",
                "Image",
                "03-02-2026- 29-05-2026",
                "Image",
                "BOGOTA | Bloque AA | Salón 714AA,",
                "Código asignatura: CT13009",
                "TRABAJO DE GRADO II",
                "4.0 créditos, Grupo D-5",
                "Image",
                "MIE 07:00:00-11:00:00, MIE 07:00:00-11:00:00,",
                "Código asignatura: CT10126",
                "Programación para dispositivos Android",
                "3.0 créditos, Grupo D-651",
                "Image",
                "MAR,JUE 11:00:00-13:00:00, MAR,JUE 11:00:00-13:00:00,",
                "Código asignatura: CT10159",
                "PROBLEM DISCOVERY & SOLUTION DESIGN WITH ARTIFICIAL INTELLIGENCE",
                "3.0 créditos, Grupo D-537",
                "Image",
                "MAR 16:00:00-18:00:00, MAR 16:00:00-18:00:00,",
                "Código asignatura: CT10160",
                "DATA SCIENCE FUNDAMENTALS",
                "3.0 créditos, Grupo D-740",
                "Image",
                "LUN,MAR,MIE 06:00:00-07:00:00, LUN,MAR,MIE 06:00:00-07:00:00.",
            ]
        ),
        "academic",
    )

    assert result.needs_clarification is False
    assert result.pending_schedule_items == []
    assert len(result.blocks) == 9


def test_parse_fixed_schedule_section_accepts_current_university_email_format() -> None:
    result = parse_fixed_schedule_section(
        "\n".join(
            [
                "Código asignatura: CB01034",
                "CÁLCULO VECTORIAL",
                "3.0 créditos, Grupo D-265",
                "MAR,JUE 07:00:00-09:00:00, MAR,JUE 07:00:00-09:00:00,",
                "03-02-2026- 28-05-2026",
                "BOGOTA | Bloque AA | Salón 801AA,",
                "Código asignatura: CB03021",
                "FÍSICA II",
                "3.0 créditos, Grupo D-264",
                "MAR,JUE 12:00:00-14:00:00, MAR,JUE 12:00:00-14:00:00,",
                "03-02-2026- 28-05-2026",
                "BOGOTA | Bloque AA | Salón 511AA,",
                "Código asignatura: CT10029",
                "BASES DE DATOS",
                "3.0 créditos, Grupo D-1",
                "LUN,MIE 09:00:00-11:00:00, LUN,MIE 09:00:00-11:00:00,",
                "02-02-2026- 27-05-2026",
                "BOGOTA | Bloque O | Sala de Cómputo No. 7,",
                "Código asignatura: CT10040",
                "SISTEMAS OPERATIVOS",
                "3.0 créditos, Grupo D-5",
                "LUN,VIE 07:00:00-09:00:00, LUN,VIE 07:00:00-09:00:00,",
                "02-02-2026- 29-05-2026",
                "BOGOTA | Bloque O | Sala de Cómputo No. 5,",
                "Código asignatura: CH03001",
                "ÉTICA GENERAL",
                "2.0 créditos, Grupo D-284",
                "LUN 13:00:00-15:00:00, LUN 13:00:00-15:00:00,",
                "02-02-2026- 25-05-2026",
                "BOGOTA | Bloque AA | Salón 701AA,",
                "Código asignatura: CT10085",
                "ANÁLISIS Y DISEÑO DE ALGORITMOS",
                "3.0 créditos, Grupo D-3",
                "MAR,JUE 09:00:00-11:00:00, MAR,JUE 09:00:00-11:00:00,",
                "03-02-2026- 28-05-2026",
                "BOGOTA | Bloque O | Sala de Cómputo No. 7,",
            ]
        ),
        "academic",
    )

    assert result.needs_clarification is False
    assert result.pending_schedule_items == []
    assert len(result.blocks) == 11
    assert ("Cálculo Vectorial", "tuesday", "07:00", "09:00") in [
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in result.blocks
    ]
    assert ("Análisis Y Diseño De Algoritmos", "thursday", "09:00", "11:00") in [
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in result.blocks
    ]


def test_parse_fixed_schedule_section_does_not_use_image_as_work_title() -> None:
    result = parse_fixed_schedule_section(
        "Lunes 06:00-07:00 Image",
        "work",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Trabajo", "monday", "06:00", "07:00"),
    ]


def test_parse_fixed_schedule_section_marks_missing_time() -> None:
    result = parse_fixed_schedule_section(
        "miércoles 9 matemáticas",
        "academic",
    )

    assert result.needs_clarification is True
    assert result.pending_schedule_items
    assert "hora de inicio y fin" in result.pending_schedule_items[0].missing_fields


def test_parse_extracurricular_section_generates_clear_short_title() -> None:
    result = parse_extracurricular_section(
        "Voy de compras con mis amigas los sábados de 3 pm a 6 pm",
    )

    assert result.needs_clarification is False
    assert [item.nombre for item in result.extracurricular_items] == ["Compras con amigas"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Compras con amigas", "saturday", "15:00", "18:00"),
    ]


def test_parse_extracurricular_section_tolerates_minor_day_typo_and_keeps_title() -> None:
    result = parse_extracurricular_section(
        "Marte y viernes - curso frances - 15:00 a 19:30",
    )

    assert result.needs_clarification is False
    assert [item.nombre for item in result.extracurricular_items] == ["Curso Frances"]
    assert result.extracurricular_items[0].dias == ["Martes", "Viernes"]
    assert [
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in result.blocks
    ] == [
        ("Curso Frances", "tuesday", "15:00", "19:30"),
        ("Curso Frances", "friday", "15:00", "19:30"),
    ]


def test_parse_extracurricular_section_strips_day_connector_from_title() -> None:
    result = parse_extracurricular_section(
        "Martes y viernes - curso frances - 15:00 a 19:30",
    )

    assert result.needs_clarification is False
    assert [item.nombre for item in result.extracurricular_items] == ["Curso Frances"]
    assert [block.day_of_week for block in result.blocks] == ["tuesday", "friday"]


def test_parse_extracurricular_section_splits_overnight_midnight_ranges() -> None:
    result = parse_extracurricular_section(
        "Voy al gimnasio los lunes martes domingos y sabados de 10 pm a 12 am",
    )

    assert result.needs_clarification is False
    assert [item.nombre for item in result.extracurricular_items] == ["Gimnasio"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Gimnasio", "monday", "22:00", "23:59"),
        ("Gimnasio", "tuesday", "22:00", "23:59"),
        ("Gimnasio", "sunday", "22:00", "23:59"),
        ("Gimnasio", "saturday", "22:00", "23:59"),
    ]


def test_detect_schedule_conflicts_marks_internal_overlap() -> None:
    result = parse_fixed_schedule_section(
        "lunes matemáticas 7 a 9 y física 8 a 10",
        "academic",
    )

    updated_blocks, conflicts = detect_schedule_conflicts(result.blocks)

    assert len(conflicts) == 1
    assert conflicts[0].overlap_start == "08:00"
    assert conflicts[0].overlap_end == "09:00"
    assert all(block.has_conflict for block in updated_blocks)
    assert updated_blocks[0].metadata["conflicts"]
