"""Repositorios para persistencia y sync de horarios recurrentes."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url


class ScheduleRepositoryError(Exception):
    """Error base del repositorio de horarios."""


@dataclass(frozen=True)
class PersistedScheduleProfile:
    """Resultado mínimo de persistencia del horario."""

    schedule_profile_id: int
    block_count: int
    schedule_end_date: date | None = None


@dataclass(frozen=True)
class PersistedScheduleProfileRecord:
    """Snapshot persistido del perfil horario del estudiante."""

    id: int
    student_id: int
    version_number: int
    occupation: str
    base_timezone: str
    summary_text: str | None = None
    has_conflicts: bool = False
    conflicts_accepted: bool = False
    confirmed_by_user: bool = True
    confirmed_at: datetime | None = None
    is_current: bool = True
    is_active: bool = True
    schedule_end_date: date | None = None


@dataclass(frozen=True)
class PersistedRecurringScheduleBlock:
    """Bloque recurrente persistido con metadatos de sincronización externa."""

    id: int
    schedule_profile_id: int
    student_id: int
    source_block_id: str
    block_type: str
    title: str
    day_of_week: str
    start_time: str
    end_time: str
    frequency: str
    timezone: str
    source_text: str
    is_active: bool = True
    confirmed_by_user: bool = True
    has_conflict: bool = False
    conflict_accepted: bool = False
    profile_is_current: bool = True
    schedule_end_date: date | None = None
    external_provider: str | None = None
    external_series_id: str | None = None
    external_event_id: str | None = None
    external_sync_status: str | None = None
    external_sync_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RecurringScheduleBlockSyncUpdate:
    """Actualización de sync externo sobre un bloque recurrente."""

    block_id: int
    external_provider: str | None = None
    external_series_id: str | None = None
    external_event_id: str | None = None
    external_sync_status: str | None = None
    external_sync_metadata: dict[str, object] = field(default_factory=dict)


class ScheduleRepository(Protocol):
    """Contrato para guardar bloques recurrentes por estudiante."""

    def replace_student_schedule(
        self,
        student_id: int,
        occupation: str,
        timezone: str,
        summary_text: str,
        blocks: list[Any],
        conflicts: list[Any],
        conflicts_accepted: bool,
        schedule_end_date: date | None = None,
    ) -> PersistedScheduleProfile: ...

    def get_current_schedule_profile(
        self,
        *,
        student_id: int,
    ) -> PersistedScheduleProfileRecord | None: ...

    def list_student_schedule_blocks(
        self,
        *,
        student_id: int,
        schedule_profile_id: int | None = None,
        only_current_profile: bool | None = None,
        external_provider: str | None = None,
    ) -> list[PersistedRecurringScheduleBlock]: ...

    def update_block_sync_metadata(
        self,
        *,
        updates: list[RecurringScheduleBlockSyncUpdate],
    ) -> list[PersistedRecurringScheduleBlock]: ...

    def update_schedule_end_date(
        self,
        *,
        schedule_profile_id: int,
        schedule_end_date: date | None,
    ) -> PersistedScheduleProfileRecord: ...


class InMemoryScheduleRepository:
    """Repositorio en memoria para pruebas."""

    def __init__(self) -> None:
        self._profiles: dict[int, dict[str, Any]] = {}
        self._profiles_by_id: dict[int, dict[str, Any]] = {}
        self._blocks_by_id: dict[int, PersistedRecurringScheduleBlock] = {}
        self._next_profile_id = 1
        self._next_block_id = 1

    def replace_student_schedule(
        self,
        student_id: int,
        occupation: str,
        timezone: str,
        summary_text: str,
        blocks: list[Any],
        conflicts: list[Any],
        conflicts_accepted: bool,
        schedule_end_date: date | None = None,
    ) -> PersistedScheduleProfile:
        for profile in self._profiles_by_id.values():
            if profile["student_id"] == student_id and profile["is_current"]:
                profile["is_current"] = False

        profile_id = self._next_profile_id
        self._next_profile_id += 1
        profile_record = {
            "id": profile_id,
            "student_id": student_id,
            "occupation": occupation,
            "timezone": timezone,
            "summary_text": summary_text,
            "blocks": [_model_dump_json(block) for block in blocks],
            "conflicts": [_model_dump_json(conflict) for conflict in conflicts],
            "conflicts_accepted": conflicts_accepted,
            "is_current": True,
            "version_number": sum(1 for profile in self._profiles_by_id.values() if profile["student_id"] == student_id) + 1,
            "has_conflicts": bool(conflicts),
            "confirmed_by_user": True,
            "confirmed_at": None,
            "is_active": True,
            "schedule_end_date": schedule_end_date,
        }
        self._profiles[student_id] = profile_record
        self._profiles_by_id[profile_id] = profile_record

        for raw_block in blocks:
            block = _coerce_struct(raw_block)
            persisted_block = PersistedRecurringScheduleBlock(
                id=self._next_block_id,
                schedule_profile_id=profile_id,
                student_id=student_id,
                source_block_id=str(block.block_id),
                block_type=str(block.block_type),
                title=str(block.title),
                day_of_week=str(block.day_of_week),
                start_time=str(block.start_time),
                end_time=str(block.end_time),
                frequency=str(block.frequency),
                timezone=str(block.timezone),
                source_text=str(block.source_text),
                is_active=bool(block.is_active),
                confirmed_by_user=bool(block.user_confirmed),
                has_conflict=bool(block.has_conflict),
                conflict_accepted=bool(block.conflict_accepted),
                profile_is_current=True,
                schedule_end_date=schedule_end_date,
            )
            self._blocks_by_id[self._next_block_id] = persisted_block
            self._next_block_id += 1
        return PersistedScheduleProfile(
            schedule_profile_id=profile_id,
            block_count=len(blocks),
            schedule_end_date=schedule_end_date,
        )

    def get_current_schedule_profile(
        self,
        *,
        student_id: int,
    ) -> PersistedScheduleProfileRecord | None:
        record = self._profiles.get(student_id)
        if record is None:
            return None
        return _schedule_profile_record_from_payload(record)

    def list_student_schedule_blocks(
        self,
        *,
        student_id: int,
        schedule_profile_id: int | None = None,
        only_current_profile: bool | None = None,
        external_provider: str | None = None,
    ) -> list[PersistedRecurringScheduleBlock]:
        blocks: list[PersistedRecurringScheduleBlock] = []
        for record in self._blocks_by_id.values():
            current_flag = bool(
                self._profiles_by_id.get(record.schedule_profile_id, {}).get(
                    "is_current",
                    record.profile_is_current,
                )
            )
            effective_record = replace(
                record,
                profile_is_current=current_flag,
                schedule_end_date=_coerce_date(
                    self._profiles_by_id.get(record.schedule_profile_id, {}).get(
                        "schedule_end_date"
                    )
                ),
            )
            if record.student_id != student_id:
                continue
            if schedule_profile_id is not None and effective_record.schedule_profile_id != schedule_profile_id:
                continue
            if only_current_profile is not None and effective_record.profile_is_current != only_current_profile:
                continue
            if external_provider is not None and effective_record.external_provider != external_provider:
                continue
            blocks.append(effective_record)
        blocks.sort(key=lambda item: (item.profile_is_current is False, item.day_of_week, item.start_time, item.id))
        return blocks

    def update_block_sync_metadata(
        self,
        *,
        updates: list[RecurringScheduleBlockSyncUpdate],
    ) -> list[PersistedRecurringScheduleBlock]:
        stored: list[PersistedRecurringScheduleBlock] = []
        for update in updates:
            existing = self._blocks_by_id.get(update.block_id)
            if existing is None:
                raise ScheduleRepositoryError(
                    f"No existe recurring_schedule_block id={update.block_id}."
                )
            merged_metadata = dict(existing.external_sync_metadata)
            merged_metadata.update(dict(update.external_sync_metadata))
            persisted = replace(
                existing,
                external_provider=update.external_provider,
                external_series_id=update.external_series_id,
                external_event_id=update.external_event_id,
                external_sync_status=update.external_sync_status,
                external_sync_metadata=merged_metadata,
                profile_is_current=bool(
                    self._profiles_by_id.get(existing.schedule_profile_id, {}).get(
                        "is_current",
                        existing.profile_is_current,
                    )
                ),
            )
            self._blocks_by_id[update.block_id] = persisted
            stored.append(persisted)
        return stored

    def update_schedule_end_date(
        self,
        *,
        schedule_profile_id: int,
        schedule_end_date: date | None,
    ) -> PersistedScheduleProfileRecord:
        profile = self._profiles_by_id.get(schedule_profile_id)
        if profile is None:
            raise ScheduleRepositoryError(
                f"No existe schedule_profile id={schedule_profile_id}."
            )
        profile["schedule_end_date"] = schedule_end_date
        if profile.get("is_current"):
            self._profiles[int(profile["student_id"])] = profile
        for block_id, block in list(self._blocks_by_id.items()):
            if block.schedule_profile_id != schedule_profile_id:
                continue
            self._blocks_by_id[block_id] = replace(
                block,
                schedule_end_date=schedule_end_date,
            )
        return _schedule_profile_record_from_payload(profile)


class PostgresScheduleRepository:
    """Repositorio PostgreSQL de horarios recurrentes."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def replace_student_schedule(
        self,
        student_id: int,
        occupation: str,
        timezone: str,
        summary_text: str,
        blocks: list[Any],
        conflicts: list[Any],
        conflicts_accepted: bool,
        schedule_end_date: date | None = None,
    ) -> PersistedScheduleProfile:
        with self._connect() as conn:
            current_version_row = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) FROM schedule_profiles WHERE student_id = %s",
                (student_id,),
            ).fetchone()
            current_version = (
                current_version_row[0]
                if current_version_row and not isinstance(current_version_row, dict)
                else current_version_row.get("coalesce", 0)
                if current_version_row
                else 0
            )
            conn.execute(
                """
                UPDATE schedule_profiles
                SET is_current = FALSE,
                    updated_at = NOW()
                WHERE student_id = %s
                  AND is_current = TRUE
                """,
                (student_id,),
            )
            profile_row = conn.execute(
                """
                INSERT INTO schedule_profiles (
                    student_id,
                    version_number,
                    occupation,
                    base_timezone,
                    summary_text,
                    has_conflicts,
                    conflicts_accepted,
                    confirmed_by_user,
                    confirmed_at,
                    schedule_end_date,
                    is_current
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), %s, TRUE)
                RETURNING id
                """,
                (
                    student_id,
                    int(current_version) + 1,
                    occupation,
                    timezone,
                    summary_text,
                    bool(conflicts),
                    conflicts_accepted,
                    schedule_end_date,
                ),
            ).fetchone()
            profile_id = profile_row[0] if not isinstance(profile_row, dict) else profile_row["id"]

            block_id_map: dict[str, int] = {}
            for raw_block in blocks:
                block = _coerce_struct(raw_block)
                row = conn.execute(
                    """
                    INSERT INTO recurring_schedule_blocks (
                        schedule_profile_id,
                        source_block_id,
                        block_type,
                        title,
                        day_of_week,
                        start_time,
                        end_time,
                        frequency,
                        timezone,
                        source_text,
                        normalized_payload,
                        confidence,
                        ambiguity_flags,
                        needs_clarification,
                        is_active,
                        confirmed_by_user,
                        has_conflict,
                        conflict_accepted
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        profile_id,
                        block.block_id,
                        block.block_type,
                        block.title,
                        block.day_of_week,
                        block.start_time,
                        block.end_time,
                        block.frequency,
                        block.timezone,
                        block.source_text,
                        json.dumps(_model_dump_json(block)),
                        block.confidence,
                        json.dumps(block.ambiguity_flags),
                        block.needs_clarification,
                        block.is_active,
                        block.user_confirmed,
                        block.has_conflict,
                        block.conflict_accepted,
                    ),
                ).fetchone()
                persisted_block_id = row[0] if not isinstance(row, dict) else row["id"]
                block_id_map[block.block_id] = persisted_block_id

            for raw_conflict in conflicts:
                conflict = _coerce_struct(raw_conflict)
                left_id = block_id_map.get(conflict.left_block_id)
                right_id = block_id_map.get(conflict.right_block_id)
                if left_id is None or right_id is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO schedule_conflicts (
                        schedule_profile_id,
                        left_block_id,
                        right_block_id,
                        day_of_week,
                        overlap_start,
                        overlap_end,
                        user_accepted
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        profile_id,
                        min(left_id, right_id),
                        max(left_id, right_id),
                        conflict.day_of_week,
                        conflict.overlap_start,
                        conflict.overlap_end,
                        conflict.accepted,
                    ),
                )

            conn.commit()
        return PersistedScheduleProfile(
            schedule_profile_id=profile_id,
            block_count=len(blocks),
            schedule_end_date=schedule_end_date,
        )

    def get_current_schedule_profile(
        self,
        *,
        student_id: int,
    ) -> PersistedScheduleProfileRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    student_id,
                    version_number,
                    occupation,
                    base_timezone,
                    summary_text,
                    has_conflicts,
                    conflicts_accepted,
                    confirmed_by_user,
                    confirmed_at,
                    is_current,
                    is_active,
                    schedule_end_date
                FROM schedule_profiles
                WHERE student_id = %s
                  AND is_current = TRUE
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()
        if row is None:
            return None
        return _schedule_profile_from_row(row)

    def list_student_schedule_blocks(
        self,
        *,
        student_id: int,
        schedule_profile_id: int | None = None,
        only_current_profile: bool | None = None,
        external_provider: str | None = None,
    ) -> list[PersistedRecurringScheduleBlock]:
        query = """
            SELECT
                rsb.id,
                rsb.schedule_profile_id,
                sp.student_id,
                rsb.source_block_id,
                rsb.block_type,
                rsb.title,
                rsb.day_of_week,
                rsb.start_time,
                rsb.end_time,
                rsb.frequency,
                rsb.timezone,
                rsb.source_text,
                rsb.is_active,
                rsb.confirmed_by_user,
                rsb.has_conflict,
                rsb.conflict_accepted,
                sp.is_current AS profile_is_current,
                sp.schedule_end_date,
                rsb.external_provider,
                rsb.external_series_id,
                rsb.external_event_id,
                rsb.external_sync_status,
                rsb.external_sync_metadata
            FROM recurring_schedule_blocks AS rsb
            INNER JOIN schedule_profiles AS sp
                ON sp.id = rsb.schedule_profile_id
            WHERE sp.student_id = %s
              AND rsb.is_active = TRUE
        """
        params: list[Any] = [student_id]
        if schedule_profile_id is not None:
            query += " AND rsb.schedule_profile_id = %s"
            params.append(schedule_profile_id)
        if only_current_profile is not None:
            query += " AND sp.is_current = %s"
            params.append(only_current_profile)
        if external_provider is not None:
            query += " AND rsb.external_provider = %s"
            params.append(external_provider)
        query += """
            ORDER BY
                sp.is_current DESC,
                rsb.day_of_week ASC,
                rsb.start_time ASC,
                rsb.id ASC
        """
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_schedule_block_from_row(row) for row in rows]

    def update_block_sync_metadata(
        self,
        *,
        updates: list[RecurringScheduleBlockSyncUpdate],
    ) -> list[PersistedRecurringScheduleBlock]:
        stored: list[PersistedRecurringScheduleBlock] = []
        with self._connect() as conn:
            for update in updates:
                row = conn.execute(
                    """
                    UPDATE recurring_schedule_blocks AS rsb
                    SET external_provider = %s,
                        external_series_id = %s,
                        external_event_id = %s,
                        external_sync_status = %s,
                        external_sync_metadata = %s::jsonb,
                        updated_at = NOW()
                    FROM schedule_profiles AS sp
                    WHERE rsb.id = %s
                      AND sp.id = rsb.schedule_profile_id
                    RETURNING
                        rsb.id,
                        rsb.schedule_profile_id,
                        sp.student_id,
                        rsb.source_block_id,
                        rsb.block_type,
                        rsb.title,
                        rsb.day_of_week,
                        rsb.start_time,
                        rsb.end_time,
                        rsb.frequency,
                        rsb.timezone,
                        rsb.source_text,
                        rsb.is_active,
                        rsb.confirmed_by_user,
                        rsb.has_conflict,
                        rsb.conflict_accepted,
                        sp.is_current AS profile_is_current,
                        sp.schedule_end_date,
                        rsb.external_provider,
                        rsb.external_series_id,
                        rsb.external_event_id,
                        rsb.external_sync_status,
                        rsb.external_sync_metadata
                    """,
                    (
                        update.external_provider,
                        update.external_series_id,
                        update.external_event_id,
                        update.external_sync_status,
                        json.dumps(update.external_sync_metadata),
                        update.block_id,
                    ),
                ).fetchone()
                if row is None:
                    raise ScheduleRepositoryError(
                        f"No existe recurring_schedule_block id={update.block_id}."
                    )
                stored.append(_schedule_block_from_row(row))
            conn.commit()
        return stored

    def update_schedule_end_date(
        self,
        *,
        schedule_profile_id: int,
        schedule_end_date: date | None,
    ) -> PersistedScheduleProfileRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE schedule_profiles
                SET schedule_end_date = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING
                    id,
                    student_id,
                    version_number,
                    occupation,
                    base_timezone,
                    summary_text,
                    has_conflicts,
                    conflicts_accepted,
                    confirmed_by_user,
                    confirmed_at,
                    is_current,
                    is_active,
                    schedule_end_date
                """,
                (schedule_end_date, schedule_profile_id),
            ).fetchone()
            if row is None:
                raise ScheduleRepositoryError(
                    f"No existe schedule_profile id={schedule_profile_id}."
                )
            conn.commit()
        return _schedule_profile_from_row(row)

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - cubre psycopg errors reales
            raise ScheduleRepositoryError(str(exc)) from exc


def build_schedule_repository(database_url: str) -> ScheduleRepository:
    """Construye el repositorio PostgreSQL o falla de forma explícita."""

    return PostgresScheduleRepository(require_database_url(database_url))


def _coerce_struct(item: Any) -> Any:
    if isinstance(item, dict):
        return SimpleNamespace(**item)
    return item


def _model_dump_json(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "__dict__"):
        return dict(vars(item))
    raise TypeError(f"Unsupported schedule payload type: {type(item)!r}")


def _schedule_block_from_row(row: Any) -> PersistedRecurringScheduleBlock:
    return PersistedRecurringScheduleBlock(
        id=int(_row_value(row, "id", 0)),
        schedule_profile_id=int(_row_value(row, "schedule_profile_id", 1)),
        student_id=int(_row_value(row, "student_id", 2)),
        source_block_id=str(_row_value(row, "source_block_id", 3)),
        block_type=str(_row_value(row, "block_type", 4)),
        title=str(_row_value(row, "title", 5)),
        day_of_week=str(_row_value(row, "day_of_week", 6)),
        start_time=_stringify_time(_row_value(row, "start_time", 7)),
        end_time=_stringify_time(_row_value(row, "end_time", 8)),
        frequency=str(_row_value(row, "frequency", 9)),
        timezone=str(_row_value(row, "timezone", 10)),
        source_text=str(_row_value(row, "source_text", 11)),
        is_active=bool(_row_value(row, "is_active", 12)),
        confirmed_by_user=bool(_row_value(row, "confirmed_by_user", 13)),
        has_conflict=bool(_row_value(row, "has_conflict", 14)),
        conflict_accepted=bool(_row_value(row, "conflict_accepted", 15)),
        profile_is_current=bool(_row_value(row, "profile_is_current", 16)),
        schedule_end_date=_coerce_date(_row_value(row, "schedule_end_date", 17)),
        external_provider=_optional_str(_row_value(row, "external_provider", 18)),
        external_series_id=_optional_str(_row_value(row, "external_series_id", 19)),
        external_event_id=_optional_str(_row_value(row, "external_event_id", 20)),
        external_sync_status=_optional_str(_row_value(row, "external_sync_status", 21)),
        external_sync_metadata=_coerce_json_dict(_row_value(row, "external_sync_metadata", 22)),
    )


def _schedule_profile_record_from_payload(
    payload: dict[str, Any],
) -> PersistedScheduleProfileRecord:
    return PersistedScheduleProfileRecord(
        id=int(payload["id"]),
        student_id=int(payload["student_id"]),
        version_number=int(payload.get("version_number", 1)),
        occupation=str(payload.get("occupation") or ""),
        base_timezone=str(
            payload.get("base_timezone")
            or payload.get("timezone")
            or "America/Bogota"
        ),
        summary_text=_optional_str(payload.get("summary_text")),
        has_conflicts=bool(payload.get("has_conflicts", False)),
        conflicts_accepted=bool(payload.get("conflicts_accepted", False)),
        confirmed_by_user=bool(payload.get("confirmed_by_user", True)),
        confirmed_at=payload.get("confirmed_at"),
        is_current=bool(payload.get("is_current", True)),
        is_active=bool(payload.get("is_active", True)),
        schedule_end_date=_coerce_date(payload.get("schedule_end_date")),
    )


def _schedule_profile_from_row(row: Any) -> PersistedScheduleProfileRecord:
    return PersistedScheduleProfileRecord(
        id=int(_row_value(row, "id", 0)),
        student_id=int(_row_value(row, "student_id", 1)),
        version_number=int(_row_value(row, "version_number", 2)),
        occupation=str(_row_value(row, "occupation", 3)),
        base_timezone=str(_row_value(row, "base_timezone", 4)),
        summary_text=_optional_str(_row_value(row, "summary_text", 5)),
        has_conflicts=bool(_row_value(row, "has_conflicts", 6)),
        conflicts_accepted=bool(_row_value(row, "conflicts_accepted", 7)),
        confirmed_by_user=bool(_row_value(row, "confirmed_by_user", 8)),
        confirmed_at=_row_value(row, "confirmed_at", 9),
        is_current=bool(_row_value(row, "is_current", 10)),
        is_active=bool(_row_value(row, "is_active", 11)),
        schedule_end_date=_coerce_date(_row_value(row, "schedule_end_date", 12)),
    )


def _row_value(row: Any, key: str, position: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    return row[position]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _stringify_time(value: Any) -> str:
    if value is None:
        return ""
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _coerce_json_dict(value: Any) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return {}
        try:
            decoded = json.loads(normalized)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return decoded
    return {}


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
