"""Tests de parseo de fecha limite para horarios fijos."""

from __future__ import annotations

from datetime import date

from services.scheduling.end_date_support import (
    SCHEDULE_END_DATE_MAX_MONTHS,
    fallback_schedule_end_date,
    parse_schedule_end_date,
)


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


def test_fallback_schedule_end_date_adds_max_months() -> None:
    from_date = date(2026, 4, 13)
    result = fallback_schedule_end_date(from_date)

    expected_month = (from_date.month - 1 + SCHEDULE_END_DATE_MAX_MONTHS) % 12 + 1
    expected_year = from_date.year + (from_date.month - 1 + SCHEDULE_END_DATE_MAX_MONTHS) // 12
    assert result == date(expected_year, expected_month, from_date.day)


def test_fallback_schedule_end_date_respects_custom_max_months() -> None:
    from_date = date(2026, 4, 13)
    result = fallback_schedule_end_date(from_date, max_months=3)

    assert result == date(2026, 7, 13)


def test_fallback_schedule_end_date_handles_month_overflow() -> None:
    # Jan 31 + 1 month → Feb 28 (no Feb 31)
    from_date = date(2026, 1, 31)
    result = fallback_schedule_end_date(from_date, max_months=1)

    assert result == date(2026, 2, 28)
