"""Pruebas del payload de Outlook Calendar sobre Microsoft Graph."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from integrations.microsoft_graph._clients_impl import GraphOutlookCalendarClient
from integrations.microsoft_graph.models import (
    OutlookCalendarEventUpsert,
    OutlookEventRecurrence,
)


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert access_token == "token-123"
        self.calls.append((method, url, json_payload))
        if method == "GET":
            return {
                "id": "outlook-event-1",
                "subject": "Calculo",
                "start": {"dateTime": "2026-04-13T12:00:00Z", "timeZone": "UTC"},
                "end": {"dateTime": "2026-04-13T14:00:00Z", "timeZone": "UTC"},
                "recurrence": {
                    "pattern": {
                        "type": "weekly",
                        "interval": 1,
                        "daysOfWeek": ["monday"],
                        "firstDayOfWeek": "monday",
                    },
                    "range": {
                        "type": "endDate",
                        "startDate": "2026-04-13",
                        "endDate": "2026-06-30",
                    },
                },
                "changeKey": "ck-1",
                "isCancelled": False,
                "webLink": "https://outlook.office.com/calendar/item/1",
            }
        return {"id": "outlook-event-1", "changeKey": "ck-1"}

    def request_no_content(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, object] | None = None,
    ) -> None:
        raise AssertionError("delete no esperado en esta prueba")


def test_graph_outlook_calendar_client_serializes_weekly_recurrence_in_local_timezone() -> None:
    transport = _FakeTransport()
    client = GraphOutlookCalendarClient(transport=transport)

    client.upsert_events(
        access_token="token-123",
        calendar_id="calendar-1",
        events=[
            OutlookCalendarEventUpsert(
                external_key="block-1",
                subject="Calculo",
                body_preview="Horario fijo",
                starts_at=datetime(2026, 4, 13, 7, 0, tzinfo=ZoneInfo("America/Bogota")),
                ends_at=datetime(2026, 4, 13, 9, 0, tzinfo=ZoneInfo("America/Bogota")),
                timezone="America/Bogota",
                recurrence=OutlookEventRecurrence(
                    pattern_type="weekly",
                    interval=1,
                    days_of_week=("monday",),
                    start_date=date(2026, 4, 13),
                ),
                use_local_timezone=True,
            )
        ],
    )

    assert len(transport.calls) == 1
    method, url, payload = transport.calls[0]
    assert method == "POST"
    assert url.endswith("/me/calendars/calendar-1/events")
    assert payload is not None
    assert payload["start"] == {
        "dateTime": "2026-04-13T07:00:00",
        "timeZone": "America/Bogota",
    }
    assert payload["end"] == {
        "dateTime": "2026-04-13T09:00:00",
        "timeZone": "America/Bogota",
    }
    assert payload["recurrence"] == {
        "pattern": {
            "type": "weekly",
            "interval": 1,
            "daysOfWeek": ["monday"],
            "firstDayOfWeek": "monday",
        },
        "range": {
            "type": "noEnd",
            "startDate": "2026-04-13",
        },
    }
    assert payload["transactionId"] == "block-1"


def test_graph_outlook_calendar_client_reads_existing_event_snapshot() -> None:
    transport = _FakeTransport()
    client = GraphOutlookCalendarClient(transport=transport)

    snapshot = client.get_event(
        access_token="token-123",
        calendar_id="calendar-1",
        external_event_id="outlook-event-1",
    )

    assert snapshot is not None
    assert snapshot.external_event_id == "outlook-event-1"
    assert snapshot.subject == "Calculo"
    assert snapshot.start == {
        "dateTime": "2026-04-13T12:00:00Z",
        "timeZone": "UTC",
    }
    assert snapshot.recurrence is not None
    assert snapshot.external_change_key == "ck-1"
    assert snapshot.web_link == "https://outlook.office.com/calendar/item/1"
