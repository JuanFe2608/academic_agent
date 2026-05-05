"""Worker programado para despachar solo reminders WhatsApp vencidos."""

from __future__ import annotations

from datetime import datetime

from services.reminders import build_reminder_dispatch_runner


def main() -> int:
    runner = build_reminder_dispatch_runner()
    result = runner.run_due_dispatches(
        limit=500,
        as_of=None,
        channels={"whatsapp"},
    )

    if not result.processed:
        print(
            "run_due_whatsapp_reminders failed",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    all_failed = result.leased_count > 0 and result.sent_count == 0

    print(
        "run_due_whatsapp_reminders all_failed" if all_failed else "run_due_whatsapp_reminders ok",
        f"timestamp={datetime.utcnow().isoformat()}Z",
        f"leased={result.leased_count}",
        f"sent={result.sent_count}",
        f"failed={result.failed_count}",
        f"retryable={result.retryable_count}",
        f"channels={result.channel_counts or {}}",
        f"dispatch_types={result.dispatch_type_counts or {}}",
    )
    return 1 if all_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
