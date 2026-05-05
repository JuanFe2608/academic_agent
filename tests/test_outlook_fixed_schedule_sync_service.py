"""Pruebas del sync del horario fijo recurrente hacia Outlook."""

from __future__ import annotations

from datetime import date
from datetime import datetime as real_datetime

from services.scheduling.end_date_support import fallback_schedule_end_date

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
)
from integrations.microsoft_graph.models import (
    OutlookCalendarEventUpsert,
    UpsertedOutlookCalendarEvent,
)
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
)
from repositories.scheduling.repository import (
    InMemoryScheduleRepository,
    RecurringScheduleBlockSyncUpdate,
)
from services.scheduling import ScheduleService, WeeklyScheduleBlock
import services.sync.fixed_schedule_outlook_projection as fixed_schedule_projection_module
import services.sync.outlook_fixed_schedule_sync_service as fixed_schedule_sync_module
from services.sync.outlook_fixed_schedule_sync_service import (
    OutlookFixedScheduleSyncService,
)


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 4, 10, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base

    @classmethod
    def utcnow(cls):
        return real_datetime(2026, 4, 10, 13, 0)


class _FakeOutlookCalendarClient:
    def __init__(self) -> None:
        self.upserts: list[OutlookCalendarEventUpsert] = []
        self.deletes: list[str] = []

    def upsert_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        events: list[OutlookCalendarEventUpsert],
    ) -> list[UpsertedOutlookCalendarEvent]:
        assert access_token.startswith("access-token")
        assert calendar_id == "calendar-1"
        self.upserts.extend(events)
        return [
            UpsertedOutlookCalendarEvent(
                external_key=event.external_key,
                external_event_id=f"outlook:{event.external_key}",
                external_change_key=f"ck:{event.external_key}",
            )
            for event in events
        ]

    def delete_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        external_event_ids: list[str],
    ) -> list[str]:
        assert access_token.startswith("access-token")
        assert calendar_id == "calendar-1"
        self.deletes.extend(external_event_ids)
        return list(external_event_ids)


def _oauth_client(state_repository: InMemoryMicrosoftGraphStateRepository) -> MicrosoftOAuthClient:
    client = MicrosoftOAuthClient(
        config=MicrosoftOAuthConfig(
            client_id="client-123",
            tenant_id="tenant-456",
            redirect_uri="https://example.com/oauth/callback",
        ),
        token_store=MicrosoftGraphStateTokenStore(state_repository),
    )
    client.save_manual_token(
        student_id=7,
        access_token="access-token-1234567890",
        refresh_token="refresh-token-1234567890",
        expires_in_seconds=3600,
        calendar_id="calendar-1",
        email="student@example.edu",
    )
    return client


def _freeze_sync_now(monkeypatch) -> None:
    monkeypatch.setattr(fixed_schedule_sync_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(fixed_schedule_projection_module, "datetime", _FrozenDateTime)


def _block(
    *,
    block_id: str,
    day_of_week: str,
    start_time: str,
    end_time: str,
    title: str,
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_id=block_id,
        block_type="academic",
        title=title,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        timezone="America/Bogota",
        source_text=f"{day_of_week} {title} {start_time}-{end_time}",
        user_confirmed=True,
    )


def test_outlook_fixed_schedule_sync_service_upserts_recurring_blocks(monkeypatch) -> None:
    _freeze_sync_now(monkeypatch)
    repository = InMemoryScheduleRepository()
    schedule_service = ScheduleService(repository=repository)
    persist_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[
            _block(
                block_id="block-1",
                day_of_week="monday",
                start_time="07:00",
                end_time="09:00",
                title="Calculo",
            )
        ],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 6, 30),
    )

    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeOutlookCalendarClient()
    service = OutlookFixedScheduleSyncService(
        repository=repository,
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    result = service.sync_schedule_profile(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    synced_blocks = repository.list_student_schedule_blocks(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        only_current_profile=True,
        external_provider="outlook",
    )
    assert result.synced is True
    assert result.upserted_count == 1
    assert result.deleted_count == 0
    assert result.synced_event_map == {"block-1": "outlook:block-1"}
    assert len(client.upserts) == 1
    assert client.upserts[0].subject == "Calculo"
    assert client.upserts[0].recurrence is not None
    assert client.upserts[0].recurrence.days_of_week == ("monday",)
    assert client.upserts[0].recurrence.start_date.isoformat() == "2026-04-13"
    assert client.upserts[0].recurrence.range_type == "endDate"
    assert client.upserts[0].recurrence.end_date == date(2026, 6, 30)
    assert client.upserts[0].use_local_timezone is True
    assert synced_blocks[0].external_event_id == "outlook:block-1"
    assert synced_blocks[0].external_series_id == "outlook:block-1"
    assert synced_blocks[0].external_sync_status == "active"


def test_outlook_fixed_schedule_sync_service_deletes_superseded_schedule_blocks(
    monkeypatch,
) -> None:
    _freeze_sync_now(monkeypatch)
    repository = InMemoryScheduleRepository()
    schedule_service = ScheduleService(repository=repository)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeOutlookCalendarClient()
    service = OutlookFixedScheduleSyncService(
        repository=repository,
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    first_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario inicial",
        blocks=[
            _block(
                block_id="block-old",
                day_of_week="monday",
                start_time="07:00",
                end_time="09:00",
                title="Calculo",
            )
        ],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 5, 15),
    )
    sync_first = service.sync_schedule_profile(
        student_id=7,
        schedule_profile_id=first_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    second_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario actualizado",
        blocks=[
            _block(
                block_id="block-new",
                day_of_week="tuesday",
                start_time="10:00",
                end_time="12:00",
                title="Fisica",
            )
        ],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 6, 30),
    )
    sync_second = service.sync_schedule_profile(
        student_id=7,
        schedule_profile_id=second_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    old_blocks = repository.list_student_schedule_blocks(
        student_id=7,
        schedule_profile_id=first_result.schedule_profile_id,
    )
    new_blocks = repository.list_student_schedule_blocks(
        student_id=7,
        schedule_profile_id=second_result.schedule_profile_id,
    )

    assert sync_first.synced is True
    assert sync_second.synced is True
    assert sync_second.upserted_count == 1
    assert sync_second.deleted_count == 1
    assert client.deletes == ["outlook:block-old"]
    assert old_blocks[0].profile_is_current is False
    assert old_blocks[0].external_sync_status == "deleted"
    assert new_blocks[0].profile_is_current is True
    assert new_blocks[0].external_event_id == "outlook:block-new"


def test_outlook_fixed_schedule_sync_service_marks_stale_missing_blocks_deleted(
    monkeypatch,
) -> None:
    _freeze_sync_now(monkeypatch)
    repository = InMemoryScheduleRepository()
    schedule_service = ScheduleService(repository=repository)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeOutlookCalendarClient()
    service = OutlookFixedScheduleSyncService(
        repository=repository,
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    first_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario inicial",
        blocks=[
            _block(
                block_id="block-old",
                day_of_week="monday",
                start_time="07:00",
                end_time="09:00",
                title="Calculo",
            )
        ],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 5, 15),
    )
    service.sync_schedule_profile(
        student_id=7,
        schedule_profile_id=first_result.schedule_profile_id,
        calendar_id="calendar-1",
    )
    old_block = repository.list_student_schedule_blocks(
        student_id=7,
        schedule_profile_id=first_result.schedule_profile_id,
    )[0]
    repository.update_block_sync_metadata(
        updates=[
            RecurringScheduleBlockSyncUpdate(
                block_id=old_block.id,
                external_provider="outlook",
                external_series_id=old_block.external_series_id,
                external_event_id=old_block.external_event_id,
                external_sync_status="missing",
                external_sync_metadata=old_block.external_sync_metadata,
            )
        ]
    )

    second_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario actualizado",
        blocks=[
            _block(
                block_id="block-new",
                day_of_week="tuesday",
                start_time="10:00",
                end_time="12:00",
                title="Fisica",
            )
        ],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 6, 30),
    )
    sync_second = service.sync_schedule_profile(
        student_id=7,
        schedule_profile_id=second_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    old_blocks = repository.list_student_schedule_blocks(
        student_id=7,
        schedule_profile_id=first_result.schedule_profile_id,
    )

    assert sync_second.synced is True
    assert sync_second.deleted_count == 0
    assert client.deletes == []
    assert old_blocks[0].external_sync_status == "deleted"
    assert old_blocks[0].external_sync_metadata["delete_reason"] == "stale_missing_event"


def test_outlook_sync_uses_fallback_end_date_when_schedule_end_date_is_null(
    monkeypatch,
) -> None:
    """Bloque sin schedule_end_date → Outlook recibe endDate (nunca noEnd)."""
    _freeze_sync_now(monkeypatch)
    repository = InMemoryScheduleRepository()
    schedule_service = ScheduleService(repository=repository)
    persist_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario sin fecha límite",
        blocks=[
            _block(
                block_id="block-null-end",
                day_of_week="monday",
                start_time="08:00",
                end_time="10:00",
                title="Algebra",
            )
        ],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=None,
    )

    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeOutlookCalendarClient()
    service = OutlookFixedScheduleSyncService(
        repository=repository,
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    result = service.sync_schedule_profile(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    # Series start: next Monday from 2026-04-10 (frozen) = 2026-04-13
    series_start = date(2026, 4, 13)
    expected_fallback = fallback_schedule_end_date(series_start)

    assert result.synced is True
    assert result.upserted_count == 1
    assert len(client.upserts) == 1
    recurrence = client.upserts[0].recurrence
    assert recurrence is not None
    assert recurrence.range_type == "endDate", (
        "Un bloque sin schedule_end_date debe usar endDate, nunca noEnd"
    )
    assert recurrence.end_date == expected_fallback
