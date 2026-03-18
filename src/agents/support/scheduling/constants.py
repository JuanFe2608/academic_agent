"""Constantes compartidas para horarios recurrentes."""

from __future__ import annotations

from typing import Literal

DayOfWeek = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

ScheduleBlockType = Literal["academic", "work", "extracurricular"]
ScheduleReviewStage = Literal[
    "idle",
    "awaiting_conflict_decision",
    "awaiting_confirmation",
    "awaiting_correction_target",
    "awaiting_correction_payload",
]
CorrectionTarget = Literal["academic", "work", "extracurricular"]

DAY_ORDER: list[DayOfWeek] = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

DAY_LABELS = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

SPANISH_TO_ENGLISH = {
    "Lunes": "monday",
    "Martes": "tuesday",
    "Miercoles": "wednesday",
    "Jueves": "thursday",
    "Viernes": "friday",
    "Sabado": "saturday",
    "Domingo": "sunday",
}

BLOCK_TYPE_TO_EVENT_CATEGORY = {
    "academic": "academico",
    "work": "laboral",
    "extracurricular": "extracurricular",
}

