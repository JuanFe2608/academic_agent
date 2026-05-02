"""Tests de parseo de fecha limite para horarios fijos."""

from __future__ import annotations

from datetime import date

from services.scheduling.end_date_support import parse_schedule_end_date


def test_parse_schedule_end_date_accepts_day_month_short_year_with_spaces() -> None:
    parsed = parse_schedule_end_date(
        "30 06 26",
        timezone_name="America/Bogota",
        min_date=date(2026, 5, 3),
    )

    assert parsed == date(2026, 6, 30)


def test_parse_schedule_end_date_accepts_day_month_short_year_with_slashes() -> None:
    parsed = parse_schedule_end_date(
        "30/06/26",
        timezone_name="America/Bogota",
        min_date=date(2026, 5, 3),
    )

    assert parsed == date(2026, 6, 30)


def test_parse_schedule_end_date_keeps_day_month_year_order() -> None:
    parsed = parse_schedule_end_date(
        "06 30 26",
        timezone_name="America/Bogota",
        min_date=date(2026, 5, 3),
    )

    assert parsed is None


def test_parse_schedule_end_date_still_accepts_iso_format() -> None:
    parsed = parse_schedule_end_date(
        "2026-06-30",
        timezone_name="America/Bogota",
        min_date=date(2026, 5, 3),
    )

    assert parsed == date(2026, 6, 30)
