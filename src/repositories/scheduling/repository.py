"""Repositorios para persistencia de horarios recurrentes."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
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
    ) -> PersistedScheduleProfile: ...


class InMemoryScheduleRepository:
    """Repositorio en memoria para pruebas."""

    def __init__(self) -> None:
        self._profiles: dict[int, dict[str, Any]] = {}
        self._next_profile_id = 1

    def replace_student_schedule(
        self,
        student_id: int,
        occupation: str,
        timezone: str,
        summary_text: str,
        blocks: list[Any],
        conflicts: list[Any],
        conflicts_accepted: bool,
    ) -> PersistedScheduleProfile:
        profile_id = self._next_profile_id
        self._next_profile_id += 1
        self._profiles[student_id] = {
            "id": profile_id,
            "student_id": student_id,
            "occupation": occupation,
            "timezone": timezone,
            "summary_text": summary_text,
            "blocks": [_model_dump_json(block) for block in blocks],
            "conflicts": [_model_dump_json(conflict) for conflict in conflicts],
            "conflicts_accepted": conflicts_accepted,
        }
        return PersistedScheduleProfile(
            schedule_profile_id=profile_id,
            block_count=len(blocks),
        )


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
                    is_current
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), TRUE)
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
        )

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
