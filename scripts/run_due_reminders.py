"""Worker simple para despachar reminders vencidos desde PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import datetime

from services.reminders import build_reminder_dispatch_runner


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Procesa reminder_dispatches vencidos de forma idempotente."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Cantidad maxima de dispatches a intentar en esta corrida.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Fecha/hora ISO opcional para pruebas operativas. Por defecto usa now UTC.",
    )
    args = parser.parse_args()

    runner = build_reminder_dispatch_runner()
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    result = runner.run_due_dispatches(limit=max(1, int(args.limit)), as_of=as_of)

    if not result.processed:
        print(
            "run_due_reminders failed",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    print(
        "run_due_reminders ok",
        f"leased={result.leased_count}",
        f"sent={result.sent_count}",
        f"failed={result.failed_count}",
        f"retryable={result.retryable_count}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
