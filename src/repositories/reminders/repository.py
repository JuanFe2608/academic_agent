"""Repositorios para persistencia de políticas y despachos de recordatorios."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url


class RemindersRepositoryError(Exception):
    """Error base del repositorio de recordatorios."""


@dataclass(frozen=True)
class ReminderPolicySpec:
    """Especificación deseada de una política de recordatorio."""

    channel: str
    reminder_type: str
    lead_minutes: int
    followup_minutes: int | None
    quiet_hours: dict[str, object]
    enabled: bool
    timezone: str
    metadata_json: dict[str, object]


@dataclass(frozen=True)
class PersistedReminderPolicy:
    """Política persistida lista para generar despachos."""

    id: int
    student_id: int
    channel: str
    reminder_type: str
    lead_minutes: int
    followup_minutes: int | None
    enabled: bool
    timezone: str


@dataclass(frozen=True)
class ReminderSchedulableInstance:
    """Instancia materializada apta para generar recordatorios."""

    id: int
    student_id: int
    study_plan_profile_id: int
    starts_at: datetime
    ends_at: datetime
    timezone: str
    source_instance_key: str
    title: str
    payload: dict[str, object]


@dataclass(frozen=True)
class ReminderDispatchSeed:
    """Despacho aún no persistido generado por el servicio."""

    student_id: int
    reminder_policy_id: int | None
    study_plan_event_instance_id: int | None
    dispatch_type: str
    channel: str
    scheduled_for: datetime
    payload: dict[str, object]


@dataclass(frozen=True)
class LeasedReminderDispatch:
    """Despacho tomado temporalmente por un worker."""

    id: int
    student_id: int
    reminder_policy_id: int | None
    study_plan_event_instance_id: int | None
    dispatch_type: str
    channel: str
    scheduled_for: datetime
    payload: dict[str, object]
    attempt_count: int = 0


class RemindersRepository(Protocol):
    """Contrato para sincronizar políticas, cola durable y workers."""

    def upsert_policies(
        self,
        *,
        student_id: int,
        policies: list[ReminderPolicySpec],
    ) -> list[PersistedReminderPolicy]: ...

    def list_schedulable_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int,
    ) -> list[ReminderSchedulableInstance]: ...

    def sync_dispatches(self, *, dispatches: list[ReminderDispatchSeed]) -> int: ...

    def cancel_dispatches_for_superseded_instances(self, *, student_id: int) -> int: ...

    def cancel_stale_activity_dispatches(
        self,
        *,
        student_id: int,
        valid_source_keys: set[str],
    ) -> int: ...

    def lease_due_dispatches(
        self,
        *,
        as_of: datetime,
        limit: int,
    ) -> list[LeasedReminderDispatch]: ...

    def mark_dispatch_sent(
        self,
        *,
        dispatch_id: int,
        sent_at: datetime,
        provider_message_id: str | None,
    ) -> None: ...

    def mark_dispatch_failed(
        self,
        *,
        dispatch_id: int,
        failure_reason: str,
        retry_at: datetime | None = None,
    ) -> None: ...


class InMemoryRemindersRepository:
    """Repositorio en memoria para pruebas del dominio de reminders."""

    def __init__(self, *, instances_repository: Any | None = None) -> None:
        self.instances_repository = instances_repository
        self._policies_by_key: dict[tuple[int, str, str, int], dict[str, Any]] = {}
        self._dispatches_by_id: dict[int, dict[str, Any]] = {}
        self._next_policy_id = 1
        self._next_dispatch_id = 1

    def upsert_policies(
        self,
        *,
        student_id: int,
        policies: list[ReminderPolicySpec],
    ) -> list[PersistedReminderPolicy]:
        persisted: list[PersistedReminderPolicy] = []
        for spec in policies:
            key = (student_id, spec.channel, spec.reminder_type, spec.lead_minutes)
            payload = self._policies_by_key.get(key)
            if payload is None:
                payload = {
                    "id": self._next_policy_id,
                    "student_id": student_id,
                }
                self._next_policy_id += 1
            payload.update(
                {
                    "channel": spec.channel,
                    "reminder_type": spec.reminder_type,
                    "lead_minutes": spec.lead_minutes,
                    "followup_minutes": spec.followup_minutes,
                    "quiet_hours": dict(spec.quiet_hours),
                    "enabled": spec.enabled,
                    "timezone": spec.timezone,
                    "metadata_json": dict(spec.metadata_json),
                    "updated_at": datetime.now(),
                }
            )
            self._policies_by_key[key] = payload
            persisted.append(
                PersistedReminderPolicy(
                    id=int(payload["id"]),
                    student_id=student_id,
                    channel=spec.channel,
                    reminder_type=spec.reminder_type,
                    lead_minutes=spec.lead_minutes,
                    followup_minutes=spec.followup_minutes,
                    enabled=spec.enabled,
                    timezone=spec.timezone,
                )
            )
        return persisted

    def list_schedulable_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int,
    ) -> list[ReminderSchedulableInstance]:
        if self.instances_repository is None:
            return []

        results: list[ReminderSchedulableInstance] = []
        for payload in self.instances_repository._instances_by_key.values():
            if payload["student_id"] != student_id:
                continue
            if payload["study_plan_profile_id"] != study_plan_profile_id:
                continue
            if payload["status"] != "scheduled":
                continue
            raw_payload = dict(payload.get("instance_payload") or {})
            event_payload = dict(raw_payload.get("event") or {})
            results.append(
                ReminderSchedulableInstance(
                    id=int(payload["id"]),
                    student_id=student_id,
                    study_plan_profile_id=study_plan_profile_id,
                    starts_at=payload["starts_at"],
                    ends_at=payload["ends_at"],
                    timezone=str(payload["timezone"]),
                    source_instance_key=str(payload["source_instance_key"]),
                    title=str(event_payload.get("titulo") or raw_payload.get("title") or "Sesion"),
                    payload=raw_payload,
                )
            )

        results.sort(key=lambda item: (item.scheduled_for if hasattr(item, "scheduled_for") else item.starts_at, item.id))
        return results

    def sync_dispatches(self, *, dispatches: list[ReminderDispatchSeed]) -> int:
        created = 0
        existing_keys = {
            (
                row["student_id"],
                row["channel"],
                row["reminder_policy_id"],
                row["study_plan_event_instance_id"],
                row["dispatch_type"],
                row["scheduled_for"],
            )
            for row in self._dispatches_by_id.values()
        }

        for dispatch in dispatches:
            key = (
                dispatch.student_id,
                dispatch.channel,
                dispatch.reminder_policy_id,
                dispatch.study_plan_event_instance_id,
                dispatch.dispatch_type,
                dispatch.scheduled_for,
            )
            if key in existing_keys:
                if row := next(
                    (
                        item
                        for item in self._dispatches_by_id.values()
                        if (
                            item["student_id"],
                            item["channel"],
                            item["reminder_policy_id"],
                            item["study_plan_event_instance_id"],
                            item["dispatch_type"],
                            item["scheduled_for"],
                        ) == key
                    ),
                    None,
                ):
                    if row["status"] in {"pending", "leased", "retryable"}:
                        row["payload"] = dict(dispatch.payload)
                        row["updated_at"] = datetime.now(tz=dispatch.scheduled_for.tzinfo)
                continue
            self._dispatches_by_id[self._next_dispatch_id] = {
                "id": self._next_dispatch_id,
                "student_id": dispatch.student_id,
                "reminder_policy_id": dispatch.reminder_policy_id,
                "study_plan_event_instance_id": dispatch.study_plan_event_instance_id,
                "dispatch_type": dispatch.dispatch_type,
                "channel": dispatch.channel,
                "scheduled_for": dispatch.scheduled_for,
                "leased_at": None,
                "sent_at": None,
                "acknowledged_at": None,
                "status": "pending",
                "provider_message_id": None,
                "failure_reason": None,
                "attempt_count": 0,
                "next_attempt_at": None,
                "payload": dict(dispatch.payload),
                "created_at": datetime.now(tz=dispatch.scheduled_for.tzinfo),
                "updated_at": datetime.now(tz=dispatch.scheduled_for.tzinfo),
            }
            existing_keys.add(key)
            self._next_dispatch_id += 1
            created += 1

        return created

    def cancel_dispatches_for_superseded_instances(self, *, student_id: int) -> int:
        if self.instances_repository is None:
            return 0

        superseded_instance_ids = {
            int(payload["id"])
            for payload in self.instances_repository._instances_by_key.values()
            if payload["student_id"] == student_id and payload["status"] == "superseded"
        }
        canceled = 0
        for row in self._dispatches_by_id.values():
            if row["student_id"] != student_id:
                continue
            if row["study_plan_event_instance_id"] not in superseded_instance_ids:
                continue
            if row["status"] not in {"pending", "leased", "retryable"}:
                continue
            row["status"] = "canceled"
            row["failure_reason"] = row["failure_reason"] or "instance_superseded"
            row["updated_at"] = datetime.now(tz=row["scheduled_for"].tzinfo)
            canceled += 1
        return canceled

    def cancel_stale_activity_dispatches(
        self,
        *,
        student_id: int,
        valid_source_keys: set[str],
    ) -> int:
        canceled = 0
        valid = {str(key) for key in valid_source_keys if str(key).strip()}
        for row in self._dispatches_by_id.values():
            if row["student_id"] != student_id:
                continue
            if row["status"] not in {"pending", "leased", "retryable"}:
                continue
            payload = dict(row.get("payload") or {})
            if payload.get("reminder_domain") != "academic_activity":
                continue
            source_key = str(payload.get("reminder_source") or "")
            if source_key in valid:
                continue
            row["status"] = "canceled"
            row["failure_reason"] = row["failure_reason"] or "academic_activity_dispatch_stale"
            row["updated_at"] = datetime.now(tz=row["scheduled_for"].tzinfo)
            canceled += 1
        return canceled

    def lease_due_dispatches(
        self,
        *,
        as_of: datetime,
        limit: int,
    ) -> list[LeasedReminderDispatch]:
        leased: list[LeasedReminderDispatch] = []
        pending = sorted(
            (
                row
                for row in self._dispatches_by_id.values()
                if (
                    row["status"] == "pending" and row["scheduled_for"] <= as_of
                )
                or (
                    row["status"] == "retryable"
                    and row.get("next_attempt_at") is not None
                    and row["next_attempt_at"] <= as_of
                )
            ),
            key=lambda item: (item["scheduled_for"], item["id"]),
        )
        for row in pending[: max(1, int(limit))]:
            row["status"] = "leased"
            row["leased_at"] = as_of
            row["next_attempt_at"] = None
            row["updated_at"] = datetime.now(tz=as_of.tzinfo)
            leased.append(_leased_dispatch_from_row(row))
        return leased

    def mark_dispatch_sent(
        self,
        *,
        dispatch_id: int,
        sent_at: datetime,
        provider_message_id: str | None,
    ) -> None:
        row = self._dispatches_by_id[dispatch_id]
        row["status"] = "sent"
        row["sent_at"] = sent_at
        row["provider_message_id"] = provider_message_id
        row["failure_reason"] = None
        row["next_attempt_at"] = None
        row["updated_at"] = datetime.now(tz=sent_at.tzinfo)

    def mark_dispatch_failed(
        self,
        *,
        dispatch_id: int,
        failure_reason: str,
        retry_at: datetime | None = None,
    ) -> None:
        row = self._dispatches_by_id[dispatch_id]
        row["status"] = "retryable" if retry_at is not None else "failed"
        row["failure_reason"] = failure_reason
        row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        row["next_attempt_at"] = retry_at
        if retry_at is not None:
            row["leased_at"] = None
        row["updated_at"] = datetime.now(tz=row["scheduled_for"].tzinfo)


class PostgresRemindersRepository:
    """Repositorio PostgreSQL de políticas y despachos."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def upsert_policies(
        self,
        *,
        student_id: int,
        policies: list[ReminderPolicySpec],
    ) -> list[PersistedReminderPolicy]:
        persisted: list[PersistedReminderPolicy] = []
        with self._connect() as conn:
            for spec in policies:
                row = conn.execute(
                    """
                    INSERT INTO reminder_policies (
                        student_id,
                        channel,
                        reminder_type,
                        lead_minutes,
                        followup_minutes,
                        quiet_hours,
                        enabled,
                        timezone,
                        metadata_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (student_id, channel, reminder_type, lead_minutes)
                    DO UPDATE SET
                        followup_minutes = EXCLUDED.followup_minutes,
                        quiet_hours = EXCLUDED.quiet_hours,
                        enabled = EXCLUDED.enabled,
                        timezone = EXCLUDED.timezone,
                        metadata_json = EXCLUDED.metadata_json,
                        updated_at = NOW()
                    RETURNING id, student_id, channel, reminder_type, lead_minutes,
                              followup_minutes, enabled, timezone
                    """,
                    (
                        student_id,
                        spec.channel,
                        spec.reminder_type,
                        spec.lead_minutes,
                        spec.followup_minutes,
                        json.dumps(spec.quiet_hours),
                        spec.enabled,
                        spec.timezone,
                        json.dumps(spec.metadata_json),
                    ),
                ).fetchone()
                persisted.append(
                    PersistedReminderPolicy(
                        id=int(_row_value(row, "id")),
                        student_id=int(_row_value(row, "student_id")),
                        channel=str(_row_value(row, "channel")),
                        reminder_type=str(_row_value(row, "reminder_type")),
                        lead_minutes=int(_row_value(row, "lead_minutes")),
                        followup_minutes=(
                            int(_row_value(row, "followup_minutes"))
                            if _row_value(row, "followup_minutes") is not None
                            else None
                        ),
                        enabled=bool(_row_value(row, "enabled")),
                        timezone=str(_row_value(row, "timezone")),
                    )
                )
            conn.commit()
        return persisted

    def list_schedulable_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int,
    ) -> list[ReminderSchedulableInstance]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    student_id,
                    study_plan_profile_id,
                    starts_at,
                    ends_at,
                    timezone,
                    source_instance_key,
                    instance_payload
                FROM study_plan_event_instances
                WHERE student_id = %s
                  AND study_plan_profile_id = %s
                  AND status = 'scheduled'
                ORDER BY starts_at, id
                """,
                (student_id, study_plan_profile_id),
            ).fetchall()

        results: list[ReminderSchedulableInstance] = []
        for row in rows:
            payload = dict(_row_value(row, "instance_payload", {}) or {})
            event_payload = dict(payload.get("event") or {})
            results.append(
                ReminderSchedulableInstance(
                    id=int(_row_value(row, "id")),
                    student_id=int(_row_value(row, "student_id")),
                    study_plan_profile_id=int(_row_value(row, "study_plan_profile_id")),
                    starts_at=_row_value(row, "starts_at"),
                    ends_at=_row_value(row, "ends_at"),
                    timezone=str(_row_value(row, "timezone")),
                    source_instance_key=str(_row_value(row, "source_instance_key")),
                    title=str(event_payload.get("titulo") or payload.get("title") or "Sesion"),
                    payload=payload,
                )
            )
        return results

    def sync_dispatches(self, *, dispatches: list[ReminderDispatchSeed]) -> int:
        created = 0
        with self._connect() as conn:
            for dispatch in dispatches:
                cursor = conn.execute(
                    """
                    INSERT INTO reminder_dispatches (
                        student_id,
                        reminder_policy_id,
                        study_plan_event_instance_id,
                        dispatch_type,
                        channel,
                        scheduled_for,
                        status,
                        payload
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, 'pending', %s::jsonb
                    )
                    ON CONFLICT (
                        student_id,
                        channel,
                        (COALESCE(reminder_policy_id, -1)),
                        (COALESCE(study_plan_event_instance_id, -1)),
                        dispatch_type,
                        scheduled_for
                    )
                    DO UPDATE SET
                        payload = CASE
                            WHEN reminder_dispatches.status IN ('pending', 'leased', 'retryable')
                                THEN EXCLUDED.payload
                            ELSE reminder_dispatches.payload
                        END,
                        updated_at = CASE
                            WHEN reminder_dispatches.status IN ('pending', 'leased', 'retryable')
                                THEN NOW()
                            ELSE reminder_dispatches.updated_at
                        END
                    RETURNING id, (xmax = 0) AS inserted
                    """,
                    (
                        dispatch.student_id,
                        dispatch.reminder_policy_id,
                        dispatch.study_plan_event_instance_id,
                        dispatch.dispatch_type,
                        dispatch.channel,
                        dispatch.scheduled_for,
                        json.dumps(dispatch.payload),
                    ),
                )
                row = cursor.fetchone()
                if row is not None and bool(_row_value(row, "inserted", False)):
                    created += 1
            conn.commit()
        return created

    def cancel_dispatches_for_superseded_instances(self, *, student_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                WITH canceled AS (
                    UPDATE reminder_dispatches AS rd
                    SET status = 'canceled',
                        failure_reason = COALESCE(rd.failure_reason, 'instance_superseded'),
                        updated_at = NOW()
                    FROM study_plan_event_instances AS spi
                    WHERE rd.study_plan_event_instance_id = spi.id
                      AND rd.student_id = %s
                    AND spi.student_id = %s
                    AND spi.status = 'superseded'
                      AND rd.status IN ('pending', 'leased', 'retryable')
                    RETURNING rd.id
                )
                SELECT COUNT(*) AS total FROM canceled
                """,
                (student_id, student_id),
            ).fetchone()
            conn.commit()
        return int(_row_value(row, "total", 0))

    def cancel_stale_activity_dispatches(
        self,
        *,
        student_id: int,
        valid_source_keys: set[str],
    ) -> int:
        valid = [str(key) for key in valid_source_keys if str(key).strip()]
        with self._connect() as conn:
            row = conn.execute(
                """
                WITH canceled AS (
                    UPDATE reminder_dispatches
                    SET status = 'canceled',
                        failure_reason = COALESCE(
                            failure_reason,
                            'academic_activity_dispatch_stale'
                        ),
                        updated_at = NOW()
                    WHERE student_id = %s
                      AND status IN ('pending', 'leased', 'retryable')
                      AND payload->>'reminder_domain' = 'academic_activity'
                      AND NOT (COALESCE(payload->>'reminder_source', '') = ANY(%s))
                    RETURNING id
                )
                SELECT COUNT(*) AS total FROM canceled
                """,
                (student_id, valid),
            ).fetchone()
            conn.commit()
        return int(_row_value(row, "total", 0))

    def lease_due_dispatches(
        self,
        *,
        as_of: datetime,
        limit: int,
    ) -> list[LeasedReminderDispatch]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH due AS (
                    SELECT id
                    FROM reminder_dispatches
                    WHERE (
                        status = 'pending'
                        AND scheduled_for <= %s
                    )
                    OR (
                        status = 'retryable'
                        AND next_attempt_at IS NOT NULL
                        AND next_attempt_at <= %s
                    )
                    ORDER BY scheduled_for, id
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE reminder_dispatches AS rd
                SET status = 'leased',
                    leased_at = %s,
                    next_attempt_at = NULL,
                    updated_at = NOW()
                FROM due
                WHERE rd.id = due.id
                RETURNING rd.id, rd.student_id, rd.reminder_policy_id,
                          rd.study_plan_event_instance_id, rd.dispatch_type,
                          rd.channel, rd.scheduled_for, rd.payload,
                          rd.attempt_count
                """,
                (as_of, as_of, max(1, int(limit)), as_of),
            ).fetchall()
            conn.commit()
        return [_leased_dispatch_from_row(row) for row in rows]

    def mark_dispatch_sent(
        self,
        *,
        dispatch_id: int,
        sent_at: datetime,
        provider_message_id: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reminder_dispatches
                SET status = 'sent',
                    sent_at = %s,
                    provider_message_id = %s,
                    failure_reason = NULL,
                    next_attempt_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (sent_at, provider_message_id, dispatch_id),
            )
            conn.commit()

    def mark_dispatch_failed(
        self,
        *,
        dispatch_id: int,
        failure_reason: str,
        retry_at: datetime | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reminder_dispatches
                SET status = CASE WHEN %s IS NULL THEN 'failed' ELSE 'retryable' END,
                    failure_reason = %s,
                    attempt_count = attempt_count + 1,
                    next_attempt_at = %s,
                    leased_at = CASE WHEN %s IS NULL THEN leased_at ELSE NULL END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (retry_at, failure_reason, retry_at, retry_at, dispatch_id),
            )
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise RemindersRepositoryError(str(exc)) from exc


def build_reminders_repository(database_url: str) -> RemindersRepository:
    """Construye el repositorio PostgreSQL o falla explícitamente."""

    return PostgresRemindersRepository(require_database_url(database_url))


def _leased_dispatch_from_row(row: Any) -> LeasedReminderDispatch:
    payload = dict(_row_value(row, "payload", {}) or {})
    return LeasedReminderDispatch(
        id=int(_row_value(row, "id")),
        student_id=int(_row_value(row, "student_id")),
        reminder_policy_id=(
            int(_row_value(row, "reminder_policy_id"))
            if _row_value(row, "reminder_policy_id") is not None
            else None
        ),
        study_plan_event_instance_id=(
            int(_row_value(row, "study_plan_event_instance_id"))
            if _row_value(row, "study_plan_event_instance_id") is not None
            else None
        ),
        dispatch_type=str(_row_value(row, "dispatch_type")),
        channel=str(_row_value(row, "channel")),
        scheduled_for=_row_value(row, "scheduled_for"),
        payload=payload,
        attempt_count=int(_row_value(row, "attempt_count", 0) or 0),
    )


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    mapping = {
        "id": 0,
        "student_id": 1,
        "channel": 2,
        "reminder_type": 3,
        "lead_minutes": 4,
        "followup_minutes": 5,
        "enabled": 6,
        "timezone": 7,
        "study_plan_profile_id": 2,
        "starts_at": 3,
        "ends_at": 4,
        "source_instance_key": 6,
        "instance_payload": 7,
        "reminder_policy_id": 2,
        "study_plan_event_instance_id": 3,
        "dispatch_type": 4,
        "scheduled_for": 6,
        "payload": 7,
        "attempt_count": 8,
        "inserted": 1,
        "total": 0,
    }
    index = mapping.get(key)
    if index is None or len(row) <= index:
        return default
    return row[index]
