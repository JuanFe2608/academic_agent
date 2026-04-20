"""Repositorios para requests y propuestas de replanificacion."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url


class StudyReplanRepositoryError(Exception):
    """Error base del repositorio de replanificacion."""


@dataclass(frozen=True)
class PersistedReplanRequest:
    """Identidad durable de una solicitud de replanificacion."""

    request_id: int
    status: str


@dataclass(frozen=True)
class PersistedReplanProposal:
    """Identidad durable de una propuesta generada."""

    proposal_id: int
    proposal_number: int
    status: str


class StudyReplanRepository(Protocol):
    """Contrato de trazabilidad para replanificacion controlada."""

    def create_request(
        self,
        *,
        student_id: int,
        current_study_plan_profile_id: int,
        trigger_type: str,
        reason_text: str | None,
        request_payload: dict[str, object],
        source_study_plan_event_instance_id: int | None = None,
    ) -> PersistedReplanRequest: ...

    def create_proposal(
        self,
        *,
        replan_request_id: int,
        summary_text: str,
        proposal_payload: dict[str, object],
        impact_payload: dict[str, object],
    ) -> PersistedReplanProposal: ...

    def mark_request_rejected(
        self,
        *,
        replan_request_id: int,
    ) -> None: ...

    def mark_proposal_applied(
        self,
        *,
        replan_request_id: int,
        proposal_number: int,
        resulting_study_plan_profile_id: int,
        supersedes_study_plan_profile_id: int,
    ) -> None: ...


class InMemoryStudyReplanRepository:
    """Repositorio en memoria para pruebas del flujo de replanificacion."""

    def __init__(self) -> None:
        self.requests: dict[int, dict[str, Any]] = {}
        self.proposals: dict[int, dict[str, Any]] = {}
        self.applied_plans: dict[int, dict[str, Any]] = {}
        self._next_request_id = 1
        self._next_proposal_id = 1

    def create_request(
        self,
        *,
        student_id: int,
        current_study_plan_profile_id: int,
        trigger_type: str,
        reason_text: str | None,
        request_payload: dict[str, object],
        source_study_plan_event_instance_id: int | None = None,
    ) -> PersistedReplanRequest:
        request_id = self._next_request_id
        self._next_request_id += 1
        self.requests[request_id] = {
            "id": request_id,
            "student_id": student_id,
            "current_study_plan_profile_id": current_study_plan_profile_id,
            "source_study_plan_event_instance_id": source_study_plan_event_instance_id,
            "trigger_type": trigger_type,
            "status": "pending",
            "reason_text": reason_text,
            "request_payload": dict(request_payload),
        }
        return PersistedReplanRequest(request_id=request_id, status="pending")

    def create_proposal(
        self,
        *,
        replan_request_id: int,
        summary_text: str,
        proposal_payload: dict[str, object],
        impact_payload: dict[str, object],
    ) -> PersistedReplanProposal:
        proposal_number = (
            sum(1 for item in self.proposals.values() if item["replan_request_id"] == replan_request_id)
            + 1
        )
        proposal_id = self._next_proposal_id
        self._next_proposal_id += 1
        self.proposals[proposal_id] = {
            "id": proposal_id,
            "replan_request_id": replan_request_id,
            "proposal_number": proposal_number,
            "status": "generated",
            "summary_text": summary_text,
            "proposal_payload": dict(proposal_payload),
            "impact_payload": dict(impact_payload),
            "resulting_study_plan_profile_id": None,
        }
        request = self.requests.get(replan_request_id)
        if request is not None:
            request["status"] = "proposed"
        return PersistedReplanProposal(
            proposal_id=proposal_id,
            proposal_number=proposal_number,
            status="generated",
        )

    def mark_request_rejected(
        self,
        *,
        replan_request_id: int,
    ) -> None:
        request = self.requests.get(replan_request_id)
        if request is not None:
            request["status"] = "rejected"

    def mark_proposal_applied(
        self,
        *,
        replan_request_id: int,
        proposal_number: int,
        resulting_study_plan_profile_id: int,
        supersedes_study_plan_profile_id: int,
    ) -> None:
        request = self.requests.get(replan_request_id)
        if request is not None:
            request["status"] = "applied"
        for proposal in self.proposals.values():
            if (
                proposal["replan_request_id"] == replan_request_id
                and proposal["proposal_number"] == proposal_number
            ):
                proposal["status"] = "applied"
                proposal["resulting_study_plan_profile_id"] = resulting_study_plan_profile_id
                break
        self.applied_plans[resulting_study_plan_profile_id] = {
            "origin_type": "replan",
            "supersedes_study_plan_profile_id": supersedes_study_plan_profile_id,
            "replan_request_id": replan_request_id,
        }


class PostgresStudyReplanRepository:
    """Repositorio PostgreSQL para trazabilidad de replanificacion."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def create_request(
        self,
        *,
        student_id: int,
        current_study_plan_profile_id: int,
        trigger_type: str,
        reason_text: str | None,
        request_payload: dict[str, object],
        source_study_plan_event_instance_id: int | None = None,
    ) -> PersistedReplanRequest:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    INSERT INTO study_replan_requests (
                        student_id,
                        current_study_plan_profile_id,
                        source_study_plan_event_instance_id,
                        trigger_type,
                        status,
                        reason_text,
                        request_payload
                    ) VALUES (%s, %s, %s, %s, 'pending', %s, %s::jsonb)
                    RETURNING id, status
                    """,
                    (
                        student_id,
                        current_study_plan_profile_id,
                        source_study_plan_event_instance_id,
                        trigger_type,
                        reason_text,
                        json.dumps(request_payload),
                    ),
                ).fetchone()
                conn.commit()
        except (RepositoryConfigurationError, StudyReplanRepositoryError):
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise StudyReplanRepositoryError(str(exc)) from exc

        return PersistedReplanRequest(
            request_id=int(_row_value(row, "id")),
            status=str(_row_value(row, "status", "pending")),
        )

    def create_proposal(
        self,
        *,
        replan_request_id: int,
        summary_text: str,
        proposal_payload: dict[str, object],
        impact_payload: dict[str, object],
    ) -> PersistedReplanProposal:
        try:
            with self._connect() as conn:
                proposal_number_row = conn.execute(
                    """
                    SELECT COALESCE(MAX(proposal_number), 0) + 1 AS next_number
                    FROM study_replan_proposals
                    WHERE replan_request_id = %s
                    """,
                    (replan_request_id,),
                ).fetchone()
                proposal_number = int(_row_value(proposal_number_row, "next_number", 1))
                row = conn.execute(
                    """
                    INSERT INTO study_replan_proposals (
                        replan_request_id,
                        proposal_number,
                        status,
                        summary_text,
                        proposal_payload,
                        impact_payload
                    ) VALUES (%s, %s, 'generated', %s, %s::jsonb, %s::jsonb)
                    RETURNING id, proposal_number, status
                    """,
                    (
                        replan_request_id,
                        proposal_number,
                        summary_text,
                        json.dumps(proposal_payload),
                        json.dumps(impact_payload),
                    ),
                ).fetchone()
                conn.execute(
                    """
                    UPDATE study_replan_requests
                    SET status = 'proposed',
                        updated_at = NOW()
                    WHERE id = %s
                      AND status IN ('pending', 'processing')
                    """,
                    (replan_request_id,),
                )
                conn.commit()
        except (RepositoryConfigurationError, StudyReplanRepositoryError):
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise StudyReplanRepositoryError(str(exc)) from exc

        return PersistedReplanProposal(
            proposal_id=int(_row_value(row, "id")),
            proposal_number=int(_row_value(row, "proposal_number", proposal_number)),
            status=str(_row_value(row, "status", "generated")),
        )

    def mark_request_rejected(
        self,
        *,
        replan_request_id: int,
    ) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE study_replan_requests
                    SET status = 'rejected',
                        resolved_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                      AND status IN ('pending', 'processing', 'proposed')
                    """,
                    (replan_request_id,),
                )
                conn.commit()
        except (RepositoryConfigurationError, StudyReplanRepositoryError):
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise StudyReplanRepositoryError(str(exc)) from exc

    def mark_proposal_applied(
        self,
        *,
        replan_request_id: int,
        proposal_number: int,
        resulting_study_plan_profile_id: int,
        supersedes_study_plan_profile_id: int,
    ) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE study_plan_profiles
                    SET origin_type = 'replan',
                        supersedes_study_plan_profile_id = %s,
                        replan_request_id = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        supersedes_study_plan_profile_id,
                        replan_request_id,
                        resulting_study_plan_profile_id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE study_replan_proposals
                    SET status = 'applied',
                        resulting_study_plan_profile_id = %s,
                        updated_at = NOW()
                    WHERE replan_request_id = %s
                      AND proposal_number = %s
                    """,
                    (
                        resulting_study_plan_profile_id,
                        replan_request_id,
                        proposal_number,
                    ),
                )
                conn.execute(
                    """
                    UPDATE study_replan_proposals
                    SET status = 'discarded',
                        updated_at = NOW()
                    WHERE replan_request_id = %s
                      AND proposal_number <> %s
                      AND status = 'generated'
                    """,
                    (replan_request_id, proposal_number),
                )
                conn.execute(
                    """
                    UPDATE study_replan_requests
                    SET status = 'applied',
                        resolved_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (replan_request_id,),
                )
                conn.commit()
        except (RepositoryConfigurationError, StudyReplanRepositoryError):
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise StudyReplanRepositoryError(str(exc)) from exc

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise StudyReplanRepositoryError(str(exc)) from exc


def build_study_replan_repository(database_url: str) -> StudyReplanRepository:
    """Construye el repositorio PostgreSQL de replanificacion."""

    return PostgresStudyReplanRepository(require_database_url(database_url))


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if key in {"id", "next_number"}:
        return row[0] if len(row) > 0 else default
    if key == "proposal_number":
        return row[1] if len(row) > 1 else default
    if key == "status":
        return row[2] if len(row) > 2 else (row[1] if len(row) > 1 else default)
    return default


__all__ = [
    "InMemoryStudyReplanRepository",
    "PersistedReplanProposal",
    "PersistedReplanRequest",
    "PostgresStudyReplanRepository",
    "StudyReplanRepository",
    "StudyReplanRepositoryError",
    "build_study_replan_repository",
]
