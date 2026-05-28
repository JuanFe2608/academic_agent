#!/usr/bin/env python3

"""Detección de sesiones de estudio movidas o eliminadas en Outlook Calendar.

Cron sugerido (cada 15 minutos):
  */15 * * * * cd /ruta/proyecto && PYTHONPATH=src python scripts/reconcile_study_sessions.py --student-id <id> >> logs/reconcile.log 2>&1
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bootstrap.settings import database_url_from_env
from repositories.planning.reconciliation_repository import build_reconciliation_repository
from services.channels import WhatsAppChannelService, ChannelOutboundMessage
from services.planning.study_session_reconciliation_service import (
    StudySessionDrift,
    build_study_session_reconciliation_service,
)

try:
    from integrations.whatsapp.cloud_client import WhatsAppCloudClient
except ImportError:
    WhatsAppCloudClient = None  # type: ignore[assignment,misc]


_WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS_ES = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio",
              "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def main() -> int:
    args = _build_parser().parse_args()
    student_id = args.student_id
    lookahead_days = args.lookahead_days

    reconciliation_service = build_study_session_reconciliation_service()
    database_url = database_url_from_env()
    reconciliation_repo = build_reconciliation_repository(database_url)

    drifts = reconciliation_service.reconcile_for_student(
        student_id=student_id,
        lookahead_days=lookahead_days,
    )

    if not drifts:
        print(
            "reconcile_study_sessions ok",
            f"student_id={student_id}",
            "drifts=0",
            f"timestamp={datetime.utcnow().isoformat()}Z",
        )
        return 0

    pending = reconciliation_repo.list_pending_for_student(str(student_id))
    already_tracked: set[tuple[str, str]] = {
        (str(p["instance_id"]), str(p["drift_kind"]))
        for p in pending
        if p.get("resolved_at") is None
    }

    whatsapp_service = _build_whatsapp_service()
    whatsapp_recipient_id = _resolve_recipient(student_id)

    notified = 0
    skipped = 0
    for drift in drifts:
        key = (drift.instance_id, drift.kind)
        if key in already_tracked:
            skipped += 1
            continue

        rec_id = reconciliation_repo.upsert_pending(
            student_id=str(student_id),
            instance_id=drift.instance_id,
            outlook_event_id=drift.outlook_event_id,
            drift_kind=drift.kind,
            session_title=drift.session_title,
            original_start=drift.original_start,
            original_end=drift.original_end,
            new_start=drift.new_start,
            new_end=drift.new_end,
        )
        if rec_id is None:
            skipped += 1
            continue

        if whatsapp_service and whatsapp_recipient_id:
            message = _format_drift_message(drift)
            try:
                whatsapp_service.send_outbound(
                    ChannelOutboundMessage(
                        channel="whatsapp",
                        recipient_id=whatsapp_recipient_id,
                        kind="text",
                        text=message,
                    )
                )
                notified += 1
            except Exception as exc:
                print(
                    "reconcile_study_sessions whatsapp_error",
                    f"student_id={student_id}",
                    f"instance_id={drift.instance_id}",
                    f"error={exc}",
                )
        else:
            notified += 1

    print(
        "reconcile_study_sessions ok",
        f"student_id={student_id}",
        f"drifts={len(drifts)}",
        f"notified={notified}",
        f"skipped={skipped}",
        f"timestamp={datetime.utcnow().isoformat()}Z",
    )
    return 0


def _format_drift_message(drift: StudySessionDrift) -> str:
    title = f"*{drift.session_title}*" if drift.session_title else "la sesión"
    if drift.kind == "deleted":
        orig_label = _format_dt_spanish(drift.original_start)
        return (
            f"Noté que eliminaste la sesión de {title} del {orig_label}. "
            "¿La borro también de tu plan? Responde *sí* o *no*."
        )
    new_label = _format_dt_spanish(drift.new_start) if drift.new_start else "una nueva hora"
    return (
        f"Noté que moviste {title} en Outlook al {new_label}. "
        "¿Actualizo tu plan aquí también? Responde *sí* o *no*."
    )


def _format_dt_spanish(dt: datetime | None) -> str:
    if dt is None:
        return "fecha desconocida"
    try:
        weekday = _WEEKDAYS_ES[dt.weekday()]
        month = _MONTHS_ES[dt.month]
        return f"{weekday} {dt.day} de {month} a las {dt.strftime('%H:%M')}"
    except Exception:
        return dt.isoformat()


def _build_whatsapp_service() -> WhatsAppChannelService | None:
    if WhatsAppCloudClient is None:
        return None
    try:
        return WhatsAppChannelService(WhatsAppCloudClient.from_env())
    except Exception:
        return None


def _resolve_recipient(student_id: int) -> str | None:
    import os
    raw = os.getenv("ACADEMIC_AGENT_WHATSAPP_RECIPIENTS", "").strip()
    if not raw:
        return os.getenv("ACADEMIC_AGENT_DEFAULT_WHATSAPP_RECIPIENT_ID", "").strip() or None
    for pair in raw.split(","):
        parts = pair.strip().split(":", 1)
        if len(parts) == 2 and parts[0].strip() == str(student_id):
            return parts[1].strip()
    return os.getenv("ACADEMIC_AGENT_DEFAULT_WHATSAPP_RECIPIENT_ID", "").strip() or None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detecta sesiones de estudio movidas o eliminadas en Outlook Calendar.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--lookahead-days", type=int, default=14)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
