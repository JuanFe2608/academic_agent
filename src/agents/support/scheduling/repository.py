"""Repositorios para persistencia de horarios recurrentes."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from agents.support.onboarding.repository import RepositoryConfigurationError

from .models import (
    ScheduleConflict,
    WeeklyScheduleBlock,
    ensure_schedule_conflict,
    ensure_weekly_block,
)


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
        blocks: list[WeeklyScheduleBlock],
        conflicts: list[ScheduleConflict],
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
        blocks: list[WeeklyScheduleBlock],
        conflicts: list[ScheduleConflict],
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
            "blocks": [block.model_dump() for block in blocks],
            "conflicts": [conflict.model_dump() for conflict in conflicts],
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
        blocks: list[WeeklyScheduleBlock],
        conflicts: list[ScheduleConflict],
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
                block = ensure_weekly_block(raw_block)
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
                        json.dumps(block.model_dump(mode="json")),
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
                conflict = ensure_schedule_conflict(raw_conflict)
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
        psycopg, dict_row = _load_psycopg()
        try:
            with psycopg.connect(
                self.database_url,
                row_factory=dict_row,
            ) as conn:
                yield conn
        except ImportError as exc:
            raise RepositoryConfigurationError(
                "psycopg no esta instalado; no pude conectar PostgreSQL."
            ) from exc
        except Exception as exc:  # pragma: no cover - cubre psycopg errors reales
            raise ScheduleRepositoryError(str(exc)) from exc


def build_schedule_repository(database_url: str) -> ScheduleRepository:
    """Construye el repositorio PostgreSQL o falla de forma explícita."""

    if not database_url:
        raise RepositoryConfigurationError(
            "ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGPORT/PGDATABASE/PGUSER no estan configurados."
        )
    return PostgresScheduleRepository(database_url)


def _load_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RepositoryConfigurationError(
            "psycopg no esta disponible en el entorno actual."
        ) from exc
    return psycopg, dict_row
