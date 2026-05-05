"""Limpia reminders viejos in_app y prepara dispatches WhatsApp futuros.

Uso seguro:
    python scripts/operate_reminders_whatsapp_migration.py --dry-run
    python scripts/operate_reminders_whatsapp_migration.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bootstrap.settings import database_url_from_env  # noqa: E402

_SCRIPT_ID = "scripts/operate_reminders_whatsapp_migration.py"
_QUIET_HOURS_JSON = json.dumps({"start": "22:00", "end": "06:00"})


@dataclass(frozen=True)
class CandidateStudent:
    student_id: int
    has_future_instances: bool
    has_future_activities: bool


def main() -> int:
    args = _build_parser().parse_args()
    if args.apply and args.dry_run:
        print("--apply y --dry-run son mutuamente excluyentes.", file=sys.stderr)
        return 2
    dry_run = not args.apply

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        print(f"psycopg no esta disponible: {exc}", file=sys.stderr)
        return 1

    database_url = database_url_from_env()
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        summary = _operate(conn, args=args, dry_run=dry_run)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _operate(conn: Any, *, args: argparse.Namespace, dry_run: bool) -> dict[str, Any]:
    cutoff_hours = max(1, int(args.older_than_hours))
    reason = f"stale_in_app_cleanup_older_than_{cutoff_hours}h"
    student_ids = _normalize_student_ids(args.student_id)
    candidate_students = _candidate_students(conn, student_ids=student_ids)
    recipient_map = _recipient_map_for_candidates(candidate_students)
    eligible_ids = sorted(recipient_map)
    missing_ids = sorted(
        student.student_id
        for student in candidate_students
        if student.student_id not in recipient_map
    )

    _create_temp_recipients(conn, recipient_map)
    cleanup = _cancel_stale_in_app(
        conn,
        cutoff_hours=cutoff_hours,
        reason=reason,
        enabled=not args.migrate_only,
    )
    migration = _migrate_whatsapp(
        conn,
        enabled=not args.cleanup_only and bool(eligible_ids),
    )

    return {
        "mode": "dry_run" if dry_run else "apply",
        "cleanup_policy": {
            "channel": "in_app",
            "statuses": ["pending"],
            "older_than_hours": cutoff_hours,
            "reason": reason,
        },
        "candidate_student_count": len(candidate_students),
        "eligible_whatsapp_student_count": len(eligible_ids),
        "missing_whatsapp_recipient_student_ids": missing_ids,
        "cleanup": cleanup,
        "migration": migration,
    }


def _candidate_students(conn: Any, *, student_ids: list[int] | None) -> list[CandidateStudent]:
    where = ""
    params: list[Any] = [_default_activity_due_time()]
    if student_ids:
        where = "WHERE s.id = ANY(%s)"
        params.append(student_ids)

    rows = conn.execute(
        f"""
        SELECT
            s.id AS student_id,
            EXISTS (
                SELECT 1
                FROM study_plan_profiles AS spp
                JOIN study_plan_event_instances AS spei
                    ON spei.study_plan_profile_id = spp.id
                   AND spei.student_id = spp.student_id
                WHERE spp.student_id = s.id
                  AND spp.is_current = TRUE
                  AND spei.status = 'scheduled'
                  AND spei.ends_at > NOW()
            ) AS has_future_instances,
            EXISTS (
                SELECT 1
                FROM academic_activities AS aa
                WHERE aa.student_id = s.id
                  AND aa.status = 'pending'
                  AND aa.due_date IS NOT NULL
                  AND ((aa.due_date + COALESCE(aa.due_time, %s)) AT TIME ZONE 'America/Bogota') > NOW()
            ) AS has_future_activities
        FROM students AS s
        {where}
        ORDER BY s.id
        """,
        tuple(params),
    ).fetchall()
    return [
        CandidateStudent(
            student_id=int(row["student_id"]),
            has_future_instances=bool(row["has_future_instances"]),
            has_future_activities=bool(row["has_future_activities"]),
        )
        for row in rows
        if row["has_future_instances"] or row["has_future_activities"]
    ]


def _recipient_map_for_candidates(candidates: list[CandidateStudent]) -> dict[int, str]:
    configured = _recipient_mapping_from_env()
    default_recipient = os.getenv("ACADEMIC_AGENT_DEFAULT_WHATSAPP_RECIPIENT_ID", "").strip()
    result: dict[int, str] = {}
    for candidate in candidates:
        recipient = configured.get(str(candidate.student_id)) or default_recipient
        if recipient:
            result[candidate.student_id] = recipient
    return result


def _recipient_mapping_from_env() -> dict[str, str]:
    raw_value = os.getenv("ACADEMIC_AGENT_WHATSAPP_RECIPIENTS", "").strip()
    if not raw_value:
        return {}
    if raw_value.startswith("{"):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            str(key).strip(): str(value).strip()
            for key, value in parsed.items()
            if str(key).strip() and str(value).strip()
        }

    mapping: dict[str, str] = {}
    for item in raw_value.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip()
        if key and value:
            mapping[key] = value
    return mapping


def _create_temp_recipients(conn: Any, recipient_map: dict[int, str]) -> None:
    conn.execute(
        """
        CREATE TEMP TABLE tmp_whatsapp_reminder_recipients (
            student_id BIGINT PRIMARY KEY,
            recipient_id TEXT NOT NULL
        ) ON COMMIT DROP
        """
    )
    if not recipient_map:
        return
    rows = [(student_id, recipient_id) for student_id, recipient_id in recipient_map.items()]
    conn.executemany(
        """
        INSERT INTO tmp_whatsapp_reminder_recipients (student_id, recipient_id)
        VALUES (%s, %s)
        """,
        rows,
    )


def _cancel_stale_in_app(
    conn: Any,
    *,
    cutoff_hours: int,
    reason: str,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "canceled_count": 0, "by_dispatch_type": {}}

    rows = conn.execute(
        """
        WITH candidates AS (
            SELECT id
            FROM reminder_dispatches
            WHERE channel = 'in_app'
              AND status = 'pending'
              AND scheduled_for < NOW() - (%s * INTERVAL '1 hour')
        ),
        updated AS (
            UPDATE reminder_dispatches AS rd
            SET
                status = 'canceled',
                failure_reason = %s,
                next_attempt_at = NULL,
                payload = jsonb_set(
                    rd.payload,
                    '{maintenance}',
                    COALESCE(rd.payload->'maintenance', '{}'::jsonb)
                    || jsonb_build_object(
                        'canceled_by', %s::text,
                        'canceled_at', NOW(),
                        'cancellation_reason', %s::text,
                        'older_than_hours', %s::integer
                    ),
                    TRUE
                )
            FROM candidates
            WHERE rd.id = candidates.id
            RETURNING rd.dispatch_type
        )
        SELECT dispatch_type, COUNT(*) AS total
        FROM updated
        GROUP BY dispatch_type
        ORDER BY dispatch_type
        """,
        (cutoff_hours, reason, _SCRIPT_ID, reason, cutoff_hours),
    ).fetchall()
    by_type = {str(row["dispatch_type"]): int(row["total"]) for row in rows}
    return {
        "enabled": True,
        "canceled_count": sum(by_type.values()),
        "by_dispatch_type": by_type,
    }


def _migrate_whatsapp(conn: Any, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "upserted_policy_count": 0,
            "created_study_dispatch_count": 0,
            "created_activity_dispatch_count": 0,
            "created_daily_agenda_dispatch_count": 0,
        }

    policy_count = _upsert_whatsapp_policies(conn)
    study_count = _create_study_plan_dispatches(conn)
    activity_count = _create_activity_dispatches(conn)
    agenda_count = _create_daily_agenda_dispatches(conn)
    return {
        "enabled": True,
        "upserted_policy_count": policy_count,
        "created_study_dispatch_count": study_count,
        "created_activity_dispatch_count": activity_count,
        "created_daily_agenda_dispatch_count": agenda_count,
    }


def _upsert_whatsapp_policies(conn: Any) -> int:
    rows = conn.execute(
        """
        WITH desired(reminder_type, lead_minutes, followup_minutes, metadata_json) AS (
            VALUES
                ('pre_session', 60, NULL, '{"timing":"before_start","origin":"whatsapp_migration"}'::jsonb),
                ('pre_session', 10, NULL, '{"timing":"before_start","origin":"whatsapp_migration"}'::jsonb),
                ('followup', 15, 15, '{"timing":"after_end","origin":"whatsapp_migration"}'::jsonb),
                ('missed_session', 30, NULL, '{"timing":"after_end","origin":"whatsapp_migration","requires_tracking":true}'::jsonb),
                ('daily_agenda', 0, NULL, '{"timing":"same_day","origin":"whatsapp_migration","domain":"academic_activity"}'::jsonb),
                ('activity_due', 180, NULL, '{"timing":"before_due","origin":"whatsapp_migration","domain":"academic_activity"}'::jsonb),
                ('activity_due', 60, NULL, '{"timing":"before_due","origin":"whatsapp_migration","domain":"academic_activity"}'::jsonb),
                ('activity_due', 15, NULL, '{"timing":"before_due","origin":"whatsapp_migration","domain":"academic_activity"}'::jsonb),
                ('activity_overdue', 15, NULL, '{"timing":"after_due","origin":"whatsapp_migration","domain":"academic_activity"}'::jsonb)
        ),
        upserted AS (
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
            )
            SELECT
                recipients.student_id,
                'whatsapp',
                desired.reminder_type,
                desired.lead_minutes,
                desired.followup_minutes::integer,
                %s::jsonb,
                TRUE,
                'America/Bogota',
                desired.metadata_json
            FROM tmp_whatsapp_reminder_recipients AS recipients
            CROSS JOIN desired
            ON CONFLICT (student_id, channel, reminder_type, lead_minutes)
            DO UPDATE SET
                followup_minutes = EXCLUDED.followup_minutes,
                quiet_hours = EXCLUDED.quiet_hours,
                enabled = TRUE,
                timezone = EXCLUDED.timezone,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = NOW()
            RETURNING id
        )
        SELECT COUNT(*) AS total FROM upserted
        """,
        (_QUIET_HOURS_JSON,),
    ).fetchone()
    return int(rows["total"])


def _create_study_plan_dispatches(conn: Any) -> int:
    row = conn.execute(
        """
        WITH candidate AS (
            SELECT
                spei.student_id,
                rp.id AS reminder_policy_id,
                spei.id AS study_plan_event_instance_id,
                CASE
                    WHEN rp.reminder_type = 'pre_session'
                        THEN spei.starts_at - (rp.lead_minutes * INTERVAL '1 minute')
                    WHEN rp.reminder_type = 'followup'
                        THEN spei.ends_at + (COALESCE(rp.followup_minutes, rp.lead_minutes) * INTERVAL '1 minute')
                    WHEN rp.reminder_type = 'missed_session'
                        THEN spei.ends_at + (rp.lead_minutes * INTERVAL '1 minute')
                END AS scheduled_for,
                CASE
                    WHEN rp.reminder_type = 'followup'
                        THEN 'followup_' || COALESCE(rp.followup_minutes, rp.lead_minutes)::text || 'm'
                    ELSE rp.reminder_type || '_' || rp.lead_minutes::text || 'm'
                END AS dispatch_type,
                jsonb_build_object(
                    'instance_id', spei.id,
                    'study_plan_profile_id', spei.study_plan_profile_id,
                    'source_instance_key', spei.source_instance_key,
                    'title', COALESCE(
                        spei.instance_payload->'event'->>'titulo',
                        spei.instance_payload->>'title',
                        'Sesion de estudio'
                    ),
                    'timezone', spei.timezone,
                    'starts_at', spei.starts_at,
                    'ends_at', spei.ends_at,
                    'channel', 'whatsapp',
                    'reminder_type', rp.reminder_type,
                    'lead_minutes', rp.lead_minutes,
                    'whatsapp_recipient_id', recipients.recipient_id
                ) AS payload
            FROM tmp_whatsapp_reminder_recipients AS recipients
            JOIN study_plan_profiles AS spp
                ON spp.student_id = recipients.student_id
               AND spp.is_current = TRUE
            JOIN study_plan_event_instances AS spei
                ON spei.student_id = spp.student_id
               AND spei.study_plan_profile_id = spp.id
            JOIN reminder_policies AS rp
                ON rp.student_id = recipients.student_id
               AND rp.channel = 'whatsapp'
               AND rp.enabled = TRUE
               AND rp.reminder_type IN ('pre_session', 'followup', 'missed_session')
            WHERE spei.status = 'scheduled'
              AND spei.ends_at > NOW()
        ),
        inserted AS (
            INSERT INTO reminder_dispatches (
                student_id,
                reminder_policy_id,
                study_plan_event_instance_id,
                dispatch_type,
                channel,
                scheduled_for,
                status,
                payload
            )
            SELECT
                student_id,
                reminder_policy_id,
                study_plan_event_instance_id,
                dispatch_type,
                'whatsapp',
                scheduled_for,
                'pending',
                payload
            FROM candidate
            WHERE scheduled_for > NOW()
            ON CONFLICT DO NOTHING
            RETURNING id
        )
        SELECT COUNT(*) AS total FROM inserted
        """
    ).fetchone()
    return int(row["total"])


def _create_activity_dispatches(conn: Any) -> int:
    row = conn.execute(
        """
        WITH activities AS (
            SELECT
                aa.*,
                ((aa.due_date + COALESCE(aa.due_time, %s)) AT TIME ZONE 'America/Bogota') AS due_at
            FROM academic_activities AS aa
            JOIN tmp_whatsapp_reminder_recipients AS recipients
                ON recipients.student_id = aa.student_id
            WHERE aa.status = 'pending'
              AND aa.due_date IS NOT NULL
        ),
        candidate AS (
            SELECT
                activities.student_id,
                rp.id AS reminder_policy_id,
                NULL::bigint AS study_plan_event_instance_id,
                CASE
                    WHEN rp.reminder_type = 'activity_due'
                        THEN activities.due_at - (rp.lead_minutes * INTERVAL '1 minute')
                    ELSE activities.due_at + (rp.lead_minutes * INTERVAL '1 minute')
                END AS scheduled_for,
                rp.reminder_type || '_' || rp.lead_minutes::text || 'm_' || left(activities.activity_uid, 12) AS dispatch_type,
                jsonb_build_object(
                    'reminder_domain', 'academic_activity',
                    'reminder_source', 'activity:' || activities.activity_uid || ':' || rp.reminder_type || ':' || rp.lead_minutes::text,
                    'kind', rp.reminder_type,
                    'activity_id', activities.activity_uid,
                    'activity_type', activities.activity_type,
                    'subject_name', activities.subject_name,
                    'title', COALESCE(activities.activity_title, activities.activity_type || ' de ' || activities.subject_name),
                    'timezone', 'America/Bogota',
                    'starts_at', activities.due_at,
                    'due_at', activities.due_at,
                    'channel', 'whatsapp',
                    'reminder_type', rp.reminder_type,
                    'lead_minutes', rp.lead_minutes,
                    'whatsapp_recipient_id', recipients.recipient_id
                ) AS payload
            FROM activities
            JOIN tmp_whatsapp_reminder_recipients AS recipients
                ON recipients.student_id = activities.student_id
            JOIN reminder_policies AS rp
                ON rp.student_id = activities.student_id
               AND rp.channel = 'whatsapp'
               AND rp.enabled = TRUE
               AND rp.reminder_type IN ('activity_due', 'activity_overdue')
            WHERE activities.due_at > NOW()
        ),
        inserted AS (
            INSERT INTO reminder_dispatches (
                student_id,
                reminder_policy_id,
                study_plan_event_instance_id,
                dispatch_type,
                channel,
                scheduled_for,
                status,
                payload
            )
            SELECT
                student_id,
                reminder_policy_id,
                study_plan_event_instance_id,
                dispatch_type,
                'whatsapp',
                scheduled_for,
                'pending',
                payload
            FROM candidate
            WHERE scheduled_for > NOW()
            ON CONFLICT DO NOTHING
            RETURNING id
        )
        SELECT COUNT(*) AS total FROM inserted
        """,
        (_default_activity_due_time(),),
    ).fetchone()
    return int(row["total"])


def _create_daily_agenda_dispatches(conn: Any) -> int:
    row = conn.execute(
        """
        WITH activities AS (
            SELECT
                aa.*,
                recipients.recipient_id,
                ((aa.due_date + COALESCE(aa.due_time, %s)) AT TIME ZONE 'America/Bogota') AS due_at
            FROM academic_activities AS aa
            JOIN tmp_whatsapp_reminder_recipients AS recipients
                ON recipients.student_id = aa.student_id
            WHERE aa.status = 'pending'
              AND aa.due_date IS NOT NULL
        ),
        agenda AS (
            SELECT
                activities.student_id,
                activities.due_date AS agenda_date,
                ((activities.due_date + %s) AT TIME ZONE 'America/Bogota') AS scheduled_for,
                activities.recipient_id,
                jsonb_agg(
                    jsonb_build_object(
                        'activity_id', activities.activity_uid,
                        'activity_type', activities.activity_type,
                        'subject_name', activities.subject_name,
                        'title', COALESCE(activities.activity_title, activities.activity_type || ' de ' || activities.subject_name),
                        'due_at', activities.due_at,
                        'priority_level', activities.priority_level
                    )
                    ORDER BY activities.due_at
                ) AS agenda_items
            FROM activities
            WHERE activities.due_at > NOW()
            GROUP BY activities.student_id, activities.due_date, activities.recipient_id
        ),
        candidate AS (
            SELECT
                agenda.student_id,
                rp.id AS reminder_policy_id,
                'daily_agenda_' || agenda.agenda_date::text AS dispatch_type,
                agenda.scheduled_for,
                jsonb_build_object(
                    'reminder_domain', 'academic_activity',
                    'reminder_source', 'agenda:' || agenda.agenda_date::text || ':' || agenda.scheduled_for::text,
                    'kind', 'daily_agenda',
                    'title', 'Agenda academica de hoy',
                    'agenda_date', agenda.agenda_date,
                    'timezone', 'America/Bogota',
                    'starts_at', agenda.scheduled_for,
                    'channel', 'whatsapp',
                    'reminder_type', 'daily_agenda',
                    'lead_minutes', rp.lead_minutes,
                    'activities', agenda.agenda_items,
                    'whatsapp_recipient_id', agenda.recipient_id
                ) AS payload
            FROM agenda
            JOIN reminder_policies AS rp
                ON rp.student_id = agenda.student_id
               AND rp.channel = 'whatsapp'
               AND rp.enabled = TRUE
               AND rp.reminder_type = 'daily_agenda'
            WHERE agenda.scheduled_for > NOW()
        ),
        inserted AS (
            INSERT INTO reminder_dispatches (
                student_id,
                reminder_policy_id,
                study_plan_event_instance_id,
                dispatch_type,
                channel,
                scheduled_for,
                status,
                payload
            )
            SELECT
                student_id,
                reminder_policy_id,
                NULL,
                dispatch_type,
                'whatsapp',
                scheduled_for,
                'pending',
                payload
            FROM candidate
            ON CONFLICT DO NOTHING
            RETURNING id
        )
        SELECT COUNT(*) AS total FROM inserted
        """,
        (_default_activity_due_time(), _daily_agenda_time()),
    ).fetchone()
    return int(row["total"])


def _default_activity_due_time() -> time:
    return _env_time("ACADEMIC_AGENT_ACTIVITY_DEFAULT_DUE_TIME", time(23, 59))


def _daily_agenda_time() -> time:
    return _env_time("ACADEMIC_AGENT_DAILY_AGENDA_TIME", time(6, 0))


def _env_time(name: str, default: time) -> time:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return time.fromisoformat(raw_value[:5])
    except ValueError:
        return default


def _normalize_student_ids(raw_values: list[int] | None) -> list[int] | None:
    if not raw_values:
        return None
    return sorted({int(value) for value in raw_values if int(value) > 0})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cancela dispatches in_app obsoletos y migra recordatorios futuros "
            "a WhatsApp para estudiantes con destinatario resoluble."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Calcula cambios y hace rollback.")
    mode.add_argument("--apply", action="store_true", help="Aplica cambios en la base.")
    parser.add_argument(
        "--older-than-hours",
        type=int,
        default=24,
        help="Antiguedad minima de dispatches in_app pendientes a cancelar.",
    )
    parser.add_argument(
        "--student-id",
        action="append",
        type=int,
        default=None,
        help="Limita la migracion a un estudiante. Se puede repetir.",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--cleanup-only", action="store_true")
    scope.add_argument("--migrate-only", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
