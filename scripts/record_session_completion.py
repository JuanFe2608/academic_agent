"""Registra eventos de tracking sobre una instancia de estudio."""

from __future__ import annotations

import argparse

from agents.support.planning.tracking_service import build_study_session_tracking_service


def main() -> int:
    args = _build_parser().parse_args()
    service = build_study_session_tracking_service()

    if args.action == "start":
        result = service.start_session(
            student_id=args.student_id,
            study_plan_event_instance_id=args.instance_id,
            actor_type=args.actor_type,
            reported_at=args.reported_at,
            actual_start_at=args.actual_start_at,
            notes=args.notes,
        )
    elif args.action == "complete":
        result = service.complete_session(
            student_id=args.student_id,
            study_plan_event_instance_id=args.instance_id,
            actor_type=args.actor_type,
            reported_at=args.reported_at,
            actual_start_at=args.actual_start_at,
            actual_end_at=args.actual_end_at,
            completion_pct=args.completion_pct,
            comprehension_score=args.comprehension_score,
            energy_score=args.energy_score,
            notes=args.notes,
        )
    elif args.action == "skip":
        result = service.skip_session(
            student_id=args.student_id,
            study_plan_event_instance_id=args.instance_id,
            actor_type=args.actor_type,
            reported_at=args.reported_at,
            actual_start_at=args.actual_start_at,
            actual_end_at=args.actual_end_at,
            notes=args.notes,
        )
    elif args.action == "missed":
        result = service.mark_session_missed(
            student_id=args.student_id,
            study_plan_event_instance_id=args.instance_id,
            actor_type=args.actor_type,
            reported_at=args.reported_at,
            notes=args.notes,
        )
    else:
        result = service.record_feedback(
            student_id=args.student_id,
            study_plan_event_instance_id=args.instance_id,
            actor_type=args.actor_type,
            reported_at=args.reported_at,
            completion_pct=args.completion_pct,
            comprehension_score=args.comprehension_score,
            energy_score=args.energy_score,
            notes=args.notes,
        )

    if not result.tracked:
        print(
            "record_session_completion failed",
            f"error={result.error_code}",
            f"detail={result.detail}",
            f"instance_id={result.instance_id}",
        )
        return 1

    print(
        "record_session_completion ok",
        f"instance_id={result.instance_id}",
        f"from={result.previous_status}",
        f"to={result.resulting_status}",
        f"checkin_id={result.checkin_id}",
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Registra start/complete/skip/missed/feedback sobre study_session_checkins.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--instance-id", type=int, required=True)
    parser.add_argument(
        "--action",
        choices=("start", "complete", "skip", "missed", "feedback"),
        required=True,
    )
    parser.add_argument("--actor-type", default="student")
    parser.add_argument("--reported-at", default=None)
    parser.add_argument("--actual-start-at", default=None)
    parser.add_argument("--actual-end-at", default=None)
    parser.add_argument("--completion-pct", type=int, default=None)
    parser.add_argument("--comprehension-score", type=int, default=None)
    parser.add_argument("--energy-score", type=int, default=None)
    parser.add_argument("--notes", default=None)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
