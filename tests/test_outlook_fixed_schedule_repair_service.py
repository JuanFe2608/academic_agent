"""Pruebas de reparación del horario fijo sincronizado con Outlook."""

from __future__ import annotations

from datetime import date

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
from services.sync.outlook_fixed_schedule_reconciliation_service import (
    OutlookFixedScheduleReconciliationService,
)
from services.sync.outlook_fixed_schedule_repair_service import (
    OutlookFixedScheduleRepairService,
)
from services.sync.outlook_fixed_schedule_sync_service import (
    OutlookFixedScheduleSyncService,
)


class _FakeOutlookCalendarClient:
    def __init__(self) -> None:
        self.upserts: list[OutlookCalendarEventUpsert] = []

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
                external_event_id=event.existing_external_event_id or f"new:{event.external_key}",
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


def _repair_service(
    repository: InMemoryScheduleRepository,
    state_repository: InMemoryMicrosoftGraphStateRepository,
    client: _FakeOutlookCalendarClient,
) -> OutlookFixedScheduleRepairService:
    auth_client = _oauth_client(state_repository)
    reconciliation_service = OutlookFixedScheduleReconciliationService(
        repository=repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,  # type: ignore[arg-type]
    )
    sync_service = OutlookFixedScheduleSyncService(
        repository=repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,  # type: ignore[arg-type]
    )
    return OutlookFixedScheduleRepairService(
        repository=repository,
        reconciliation_service=reconciliation_service,
        sync_service=sync_service,
    )


def test_repair_service_restores_drifted_blocks_with_existing_event_id() -> None:
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
                external_sync_status="drifted",
                external_sync_metadata={"external_change_key": "manual"},
            )
        ]
    )

    client = _FakeOutlookCalendarClient()
    service = _repair_service(repository, InMemoryMicrosoftGraphStateRepository(), client)

    result = service.repair_schedule_profile(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_id="calendar-1",
        reconcile_first=False,
    )

    updated_block = repository.list_student_schedule_blocks(student_id=7)[0]
    assert result.repaired is True
    assert result.restored_count == 1
    assert result.recreated_count == 0
    assert client.upserts[0].existing_external_event_id == "outlook:block-1"
    assert updated_block.external_sync_status == "active"
    assert updated_block.external_event_id == "outlook:block-1"


def test_repair_service_recreates_missing_blocks_with_new_event_id() -> None:
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
                external_series_id="outlook:old",
                external_event_id="outlook:old",
                external_sync_status="missing",
                external_sync_metadata={"external_change_key": "old"},
            )
        ]
    )

    client = _FakeOutlookCalendarClient()
    service = _repair_service(repository, InMemoryMicrosoftGraphStateRepository(), client)

    result = service.repair_schedule_profile(
        student_id=7,
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_id="calendar-1",
        reconcile_first=False,
    )

    updated_block = repository.list_student_schedule_blocks(student_id=7)[0]
    assert result.repaired is True
    assert result.restored_count == 0
    assert result.recreated_count == 1
    assert client.upserts[0].existing_external_event_id is None
    assert updated_block.external_sync_status == "active"
    assert updated_block.external_event_id == "new:block-1"
    assert updated_block.external_sync_metadata["repair_previous_external_event_id"] == "outlook:old"
