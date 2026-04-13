"""Pruebas de reconciliación del horario fijo contra Outlook."""

from __future__ import annotations

from datetime import date

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
)
from integrations.microsoft_graph.models import OutlookCalendarEventSnapshot
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
)
from repositories.scheduling.repository import (
    InMemoryScheduleRepository,
    RecurringScheduleBlockSyncUpdate,
)
from services.scheduling import ScheduleService, WeeklyScheduleBlock
from services.sync.outlook_fixed_schedule_reconciliation_service import (
    OutlookFixedScheduleReconciliationService,
)


class _FakeOutlookCalendarClient:
    def __init__(self, snapshots: dict[str, OutlookCalendarEventSnapshot | None]) -> None:
        self.snapshots = snapshots

    def get_event(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        external_event_id: str,
    ) -> OutlookCalendarEventSnapshot | None:
        assert access_token.startswith("access-token")
        assert calendar_id == "calendar-1"
        return self.snapshots.get(external_event_id)


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


def _block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_id="block-1",
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="07:00",
        end_time="09:00",
        timezone="America/Bogota",
        source_text="Lunes cálculo 7-9",
        user_confirmed=True,
    )


def test_reconciliation_service_marks_aligned_blocks_as_active() -> None:
    repository = InMemoryScheduleRepository()
    schedule_service = ScheduleService(repository=repository)
    persist_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[_block()],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 6, 30),
    )
    persisted_block = repository.list_student_schedule_blocks(student_id=7)[0]
    repository.update_block_sync_metadata(
        updates=[
            RecurringScheduleBlockSyncUpdate(
                block_id=persisted_block.id,
                external_provider="outlook",
                external_series_id="outlook:block-1",
                external_event_id="outlook:block-1",
                external_sync_status="active",
                external_sync_metadata={
                    "series_start_date": "2026-04-13",
                    "external_change_key": "ck:block-1",
                },
            )
        ]
    )

    state_repository = InMemoryMicrosoftGraphStateRepository()
    service = OutlookFixedScheduleReconciliationService(
        repository=repository,
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=_FakeOutlookCalendarClient(
            {
                "outlook:block-1": OutlookCalendarEventSnapshot(
                    external_event_id="outlook:block-1",
                    subject="Calculo",
                    start={"dateTime": "2026-04-13T12:00:00Z", "timeZone": "UTC"},
                    end={"dateTime": "2026-04-13T14:00:00Z", "timeZone": "UTC"},
                    recurrence={
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
                    external_change_key="ck:block-1",
                    is_cancelled=False,
                    web_link="https://outlook.office.com/calendar/item/1",
                )
            }
        ),
    )

    result = service.reconcile_schedule_profile(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    updated_block = repository.list_student_schedule_blocks(student_id=7)[0]
    assert result.reconciled is True
    assert result.aligned_count == 1
    assert result.drifted_count == 0
    assert updated_block.external_sync_status == "active"
    assert updated_block.external_sync_metadata["reconciliation_status"] == "active"


def test_reconciliation_service_marks_drifted_blocks() -> None:
    repository = InMemoryScheduleRepository()
    schedule_service = ScheduleService(repository=repository)
    persist_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[_block()],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 6, 30),
    )
    persisted_block = repository.list_student_schedule_blocks(student_id=7)[0]
    repository.update_block_sync_metadata(
        updates=[
            RecurringScheduleBlockSyncUpdate(
                block_id=persisted_block.id,
                external_provider="outlook",
                external_series_id="outlook:block-1",
                external_event_id="outlook:block-1",
                external_sync_status="active",
                external_sync_metadata={
                    "series_start_date": "2026-04-13",
                    "external_change_key": "ck:block-1",
                },
            )
        ]
    )

    state_repository = InMemoryMicrosoftGraphStateRepository()
    service = OutlookFixedScheduleReconciliationService(
        repository=repository,
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=_FakeOutlookCalendarClient(
            {
                "outlook:block-1": OutlookCalendarEventSnapshot(
                    external_event_id="outlook:block-1",
                    subject="Calculo editado",
                    start={"dateTime": "2026-04-13T12:00:00Z", "timeZone": "UTC"},
                    end={"dateTime": "2026-04-13T15:00:00Z", "timeZone": "UTC"},
                    recurrence={
                        "pattern": {
                            "type": "weekly",
                            "interval": 1,
                            "daysOfWeek": ["monday"],
                            "firstDayOfWeek": "monday",
                        },
                        "range": {
                            "type": "endDate",
                            "startDate": "2026-04-13",
                            "endDate": "2026-07-15",
                        },
                    },
                    external_change_key="ck:manual",
                    is_cancelled=False,
                    web_link="https://outlook.office.com/calendar/item/1",
                )
            }
        ),
    )

    result = service.reconcile_schedule_profile(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    updated_block = repository.list_student_schedule_blocks(student_id=7)[0]
    assert result.reconciled is True
    assert result.drifted_count == 1
    assert result.findings[0].status == "drifted"
    assert "subject" in result.findings[0].drift_fields
    assert "end" in result.findings[0].drift_fields
    assert updated_block.external_sync_status == "drifted"
    assert updated_block.external_sync_metadata["reconciliation_status"] == "drifted"


def test_reconciliation_service_marks_missing_blocks() -> None:
    repository = InMemoryScheduleRepository()
    schedule_service = ScheduleService(repository=repository)
    persist_result = schedule_service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[_block()],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 6, 30),
    )
    persisted_block = repository.list_student_schedule_blocks(student_id=7)[0]
    repository.update_block_sync_metadata(
        updates=[
            RecurringScheduleBlockSyncUpdate(
                block_id=persisted_block.id,
                external_provider="outlook",
                external_series_id="outlook:block-1",
                external_event_id="outlook:block-1",
                external_sync_status="active",
                external_sync_metadata={
                    "series_start_date": "2026-04-13",
                    "external_change_key": "ck:block-1",
                },
            )
        ]
    )

    state_repository = InMemoryMicrosoftGraphStateRepository()
    service = OutlookFixedScheduleReconciliationService(
        repository=repository,
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=_FakeOutlookCalendarClient({"outlook:block-1": None}),
    )

    result = service.reconcile_schedule_profile(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_id="calendar-1",
    )

    updated_block = repository.list_student_schedule_blocks(student_id=7)[0]
    assert result.reconciled is True
    assert result.missing_count == 1
    assert result.findings[0].status == "missing"
    assert updated_block.external_sync_status == "missing"
