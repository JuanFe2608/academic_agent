"""Materializa instancias para planes de estudio ya persistidos."""

from __future__ import annotations

import argparse
from contextlib import closing

from agents.support.planning.materialization_service import (
    StudyPlanMaterializationService,
    build_study_plan_materialization_service,
)
from agents.support.state import Event, StudyPlanState
from agents.support.tools.db_config import database_url_from_env


def main() -> None:
    args = _build_parser().parse_args()
    service = build_study_plan_materialization_service()
    database_url = database_url_from_env()
    if not database_url:
        raise SystemExit("No encontré la configuración de PostgreSQL en el entorno.")

    psycopg = _load_psycopg()
    query, params = _profiles_query(args.student_id, args.profile_id)

    with closing(psycopg.connect(database_url)) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            profiles = cur.fetchall()

            total_profiles = 0
            total_instances = 0
            total_superseded = 0

            for student_id, study_plan_profile_id, timezone in profiles:
                plan_state = _load_plan_state(
                    cursor=cur,
                    study_plan_profile_id=study_plan_profile_id,
                )
                result = service.materialize_plan_instances(
                    student_id=int(student_id),
                    study_plan_profile_id=int(study_plan_profile_id),
                    study_plan=plan_state,
                    timezone=str(timezone),
                )
                total_profiles += 1
                total_instances += result.materialized_instance_count
                total_superseded += result.superseded_instance_count
                print(
                    f"profile={study_plan_profile_id} student={student_id} "
                    f"materialized={result.materialized_instance_count} "
                    f"superseded={result.superseded_instance_count} "
                    f"status={'ok' if result.materialized else result.error_code}"
                )

    print(
        "summary "
        f"profiles={total_profiles} "
        f"materialized={total_instances} "
        f"superseded={total_superseded}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill de study_plan_event_instances para planes persistidos.",
    )
    parser.add_argument(
        "--student-id",
        type=int,
        default=None,
        help="Restringe el backfill a un estudiante.",
    )
    parser.add_argument(
        "--profile-id",
        type=int,
        default=None,
        help="Restringe el backfill a un study_plan_profile específico.",
    )
    return parser


def _profiles_query(
    student_id: int | None,
    profile_id: int | None,
) -> tuple[str, tuple]:
    filters: list[str] = ["is_current = TRUE"]
    params: list[int] = []

    if student_id is not None:
        filters.append("student_id = %s")
        params.append(student_id)
    if profile_id is not None:
        filters.append("id = %s")
        params.append(profile_id)

    query = f"""
        SELECT student_id, id, timezone
        FROM study_plan_profiles
        WHERE {' AND '.join(filters)}
        ORDER BY student_id, id
    """
    return query, tuple(params)


def _load_plan_state(*, cursor, study_plan_profile_id: int) -> StudyPlanState:
    cursor.execute(
        """
        SELECT
            source_event_id,
            day_label,
            start_time::text,
            end_time::text,
            title,
            event_type,
            category,
            origin,
            priority,
            difficulty,
            timezone
        FROM study_plan_events
        WHERE study_plan_profile_id = %s
        ORDER BY position
        """,
        (study_plan_profile_id,),
    )
    rows = cursor.fetchall()
    events = [
        Event(
            id=str(source_event_id),
            dia=str(day_label),
            inicio=str(start_time)[:5],
            fin=str(end_time)[:5],
            titulo=str(title),
            tipo=str(event_type),
            categoria=str(category),
            origen=str(origin),
            prioridad=str(priority) if priority is not None else None,
            dificultad=int(difficulty) if difficulty is not None else None,
            timezone=str(timezone),
        )
        for (
            source_event_id,
            day_label,
            start_time,
            end_time,
            title,
            event_type,
            category,
            origin,
            priority,
            difficulty,
            timezone,
        ) in rows
    ]
    return StudyPlanState(plan_events=events, rules={})


def _load_psycopg():
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise SystemExit("psycopg no está disponible en el entorno actual.") from exc
    return psycopg


if __name__ == "__main__":
    main()
