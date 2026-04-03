"""Servicio de aplicación para políticas y despachos de recordatorios."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from agents.support.onboarding.repository import RepositoryConfigurationError
from agents.support.planning.instances_repository import StudyPlanInstancesRepository
from agents.support.reminders_repository import (
    InMemoryRemindersRepository,
    PersistedReminderPolicy,
    ReminderDispatchSeed,
    ReminderPolicySpec,
    ReminderSchedulableInstance,
    RemindersRepository,
    RemindersRepositoryError,
    build_reminders_repository,
)
from agents.support.reminders_state_helpers import ensure_reminders_state
from agents.support.state import RemindersState
from agents.support.tools.db_config import database_url_from_env

DEFAULT_REMINDER_CHANNELS = ("in_app",)
_SUPPORTED_CHANNELS = {"in_app", "email", "whatsapp"}
_DEFAULT_QUIET_HOURS = {"start": "22:00", "end": "06:00"}
_DEFERRED_REMINDER_TYPES = {"missed_session"}
_DEFAULT_POLICY_BLUEPRINTS: tuple[dict[str, object], ...] = (
    {
        "reminder_type": "pre_session",
        "lead_minutes": 60,
        "followup_minutes": None,
        "metadata_json": {"timing": "before_start", "origin": "default"},
    },
    {
        "reminder_type": "pre_session",
        "lead_minutes": 10,
        "followup_minutes": None,
        "metadata_json": {"timing": "before_start", "origin": "default"},
    },
    {
        "reminder_type": "followup",
        "lead_minutes": 15,
        "followup_minutes": 15,
        "metadata_json": {"timing": "after_end", "origin": "default"},
    },
    {
        "reminder_type": "missed_session",
        "lead_minutes": 30,
        "followup_minutes": None,
        "metadata_json": {
            "timing": "after_end",
            "origin": "default",
            "requires_tracking": True,
        },
    },
)


@dataclass(frozen=True)
class SyncStudyPlanRemindersResult:
    """Resultado público del sync de reminders para un plan materializado."""

    synced: bool
    persisted_policy_ids: list[int] = field(default_factory=list)
    policy_count: int = 0
    schedulable_instance_count: int = 0
    created_dispatch_count: int = 0
    canceled_dispatch_count: int = 0
    synced_at: str | None = None
    error_code: str | None = None
    detail: str | None = None


class StudyPlanRemindersService:
    """Orquesta políticas default y cola durable de recordatorios."""

    def __init__(
        self,
        repository: RemindersRepository,
        *,
        default_channels: Iterable[str] = DEFAULT_REMINDER_CHANNELS,
    ) -> None:
        normalized_channels = tuple(
            channel for channel in dict.fromkeys(default_channels) if channel in _SUPPORTED_CHANNELS
        )
        self.repository = repository
        self.default_channels = normalized_channels or DEFAULT_REMINDER_CHANNELS

    def sync_reminders_for_study_plan(
        self,
        *,
        student_id: int | None,
        study_plan_profile_id: int | None,
        reminders_state: RemindersState | dict | None,
        timezone: str,
    ) -> SyncStudyPlanRemindersResult:
        if not student_id:
            return SyncStudyPlanRemindersResult(
                synced=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar recordatorios.",
            )
        if not study_plan_profile_id:
            return SyncStudyPlanRemindersResult(
                synced=False,
                error_code="missing_study_plan_profile_id",
                detail="No encontré el plan persistido para sincronizar recordatorios.",
            )

        normalized = ensure_reminders_state(reminders_state)
        try:
            zone = ZoneInfo(str(timezone or "America/Bogota"))
        except Exception as exc:
            return SyncStudyPlanRemindersResult(
                synced=False,
                error_code="invalid_timezone",
                detail=str(exc),
            )

        sync_now = datetime.now(zone)
        try:
            persisted_policies = self.repository.upsert_policies(
                student_id=student_id,
                policies=_build_policy_specs(
                    normalized,
                    timezone=str(zone),
                    default_channels=self.default_channels,
                    study_plan_profile_id=study_plan_profile_id,
                ),
            )
            canceled_dispatch_count = self.repository.cancel_dispatches_for_superseded_instances(
                student_id=student_id
            )
            if not normalized.enabled:
                return _success_result(
                    persisted_policies=persisted_policies,
                    schedulable_instance_count=0,
                    created_dispatch_count=0,
                    canceled_dispatch_count=canceled_dispatch_count,
                    synced_at=sync_now.isoformat(),
                )

            instances = self.repository.list_schedulable_instances(
                student_id=student_id,
                study_plan_profile_id=study_plan_profile_id,
            )
            dispatches = _build_dispatches(
                persisted_policies=persisted_policies,
                instances=instances,
                sync_now=sync_now,
            )
            created_dispatch_count = self.repository.sync_dispatches(dispatches=dispatches)
        except (RemindersRepositoryError, RepositoryConfigurationError) as exc:
            return SyncStudyPlanRemindersResult(
                synced=False,
                error_code="study_plan_reminders_sync_error",
                detail=str(exc),
            )

        return _success_result(
            persisted_policies=persisted_policies,
            schedulable_instance_count=len(instances),
            created_dispatch_count=created_dispatch_count,
            canceled_dispatch_count=canceled_dispatch_count,
            synced_at=sync_now.isoformat(),
        )


def build_study_plan_reminders_service(
    *,
    instances_repository: StudyPlanInstancesRepository | Any | None = None,
) -> StudyPlanRemindersService:
    """Construye el servicio de reminders según el entorno."""

    default_channels = _default_channels_from_env()
    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_REMINDERS_REPO", "").strip() == "1":
        repository = InMemoryRemindersRepository(instances_repository=instances_repository)
    else:
        repository = build_reminders_repository(database_url_from_env())
    return StudyPlanRemindersService(
        repository=repository,
        default_channels=default_channels,
    )


def _success_result(
    *,
    persisted_policies: list[PersistedReminderPolicy],
    schedulable_instance_count: int,
    created_dispatch_count: int,
    canceled_dispatch_count: int,
    synced_at: str,
) -> SyncStudyPlanRemindersResult:
    return SyncStudyPlanRemindersResult(
        synced=True,
        persisted_policy_ids=[policy.id for policy in persisted_policies],
        policy_count=len(persisted_policies),
        schedulable_instance_count=schedulable_instance_count,
        created_dispatch_count=created_dispatch_count,
        canceled_dispatch_count=canceled_dispatch_count,
        synced_at=synced_at,
    )


def _build_policy_specs(
    reminders_state: RemindersState,
    *,
    timezone: str,
    default_channels: tuple[str, ...],
    study_plan_profile_id: int,
) -> list[ReminderPolicySpec]:
    channels = _normalize_channels(
        reminders_state.policy.get("channels"),
        default_channels=default_channels,
    )
    quiet_hours = _normalize_quiet_hours(reminders_state.policy.get("quiet_hours"))
    blueprints = _normalize_policy_blueprints(reminders_state.policy.get("rules"))

    specs: list[ReminderPolicySpec] = []
    for channel in channels:
        for blueprint in blueprints:
            metadata_json = dict(blueprint.get("metadata_json") or {})
            metadata_json.setdefault("study_plan_profile_id", study_plan_profile_id)
            specs.append(
                ReminderPolicySpec(
                    channel=channel,
                    reminder_type=str(blueprint["reminder_type"]),
                    lead_minutes=int(blueprint["lead_minutes"]),
                    followup_minutes=(
                        int(blueprint["followup_minutes"])
                        if blueprint.get("followup_minutes") is not None
                        else None
                    ),
                    quiet_hours=quiet_hours,
                    enabled=bool(blueprint.get("enabled", True) and reminders_state.enabled),
                    timezone=timezone,
                    metadata_json=metadata_json,
                )
            )
    return specs


def _normalize_channels(
    raw_channels: object,
    *,
    default_channels: tuple[str, ...],
) -> tuple[str, ...]:
    if isinstance(raw_channels, str):
        candidates = [raw_channels]
    elif isinstance(raw_channels, (list, tuple, set)):
        candidates = [str(item) for item in raw_channels]
    else:
        candidates = list(default_channels)

    normalized = tuple(
        channel
        for channel in dict.fromkeys(candidate.strip() for candidate in candidates if candidate)
        if channel in _SUPPORTED_CHANNELS
    )
    return normalized or default_channels


def _normalize_quiet_hours(raw_quiet_hours: object) -> dict[str, object]:
    if not isinstance(raw_quiet_hours, dict):
        return dict(_DEFAULT_QUIET_HOURS)

    start = str(raw_quiet_hours.get("start") or _DEFAULT_QUIET_HOURS["start"]).strip()
    end = str(raw_quiet_hours.get("end") or _DEFAULT_QUIET_HOURS["end"]).strip()
    return {"start": start, "end": end}


def _normalize_policy_blueprints(raw_rules: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_rules, list):
        return tuple(dict(item) for item in _DEFAULT_POLICY_BLUEPRINTS)

    normalized: list[dict[str, object]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        reminder_type = str(raw_rule.get("reminder_type") or "").strip()
        if reminder_type not in {"pre_session", "followup", "missed_session"}:
            continue
        try:
            lead_minutes = max(0, int(raw_rule.get("lead_minutes", 0)))
        except (TypeError, ValueError):
            continue
        followup_minutes = raw_rule.get("followup_minutes")
        if followup_minutes is not None:
            try:
                followup_minutes = max(0, int(followup_minutes))
            except (TypeError, ValueError):
                followup_minutes = None
        normalized.append(
            {
                "reminder_type": reminder_type,
                "lead_minutes": lead_minutes,
                "followup_minutes": followup_minutes,
                "enabled": bool(raw_rule.get("enabled", True)),
                "metadata_json": dict(raw_rule.get("metadata_json") or {}),
            }
        )

    if not normalized:
        return tuple(dict(item) for item in _DEFAULT_POLICY_BLUEPRINTS)
    return tuple(normalized)


def _build_dispatches(
    *,
    persisted_policies: list[PersistedReminderPolicy],
    instances: list[ReminderSchedulableInstance],
    sync_now: datetime,
) -> list[ReminderDispatchSeed]:
    dispatches: list[ReminderDispatchSeed] = []
    for instance in instances:
        if instance.ends_at <= sync_now:
            continue
        for policy in persisted_policies:
            if not policy.enabled:
                continue
            if policy.reminder_type in _DEFERRED_REMINDER_TYPES:
                continue
            scheduled_for = _scheduled_for_instance(
                policy=policy,
                instance=instance,
            )
            if scheduled_for is None:
                continue
            dispatches.append(
                ReminderDispatchSeed(
                    student_id=instance.student_id,
                    reminder_policy_id=policy.id,
                    study_plan_event_instance_id=instance.id,
                    dispatch_type=_dispatch_type(policy),
                    channel=policy.channel,
                    scheduled_for=scheduled_for,
                    payload={
                        "instance_id": instance.id,
                        "study_plan_profile_id": instance.study_plan_profile_id,
                        "source_instance_key": instance.source_instance_key,
                        "title": instance.title,
                        "timezone": instance.timezone,
                        "starts_at": instance.starts_at.isoformat(),
                        "ends_at": instance.ends_at.isoformat(),
                        "channel": policy.channel,
                        "reminder_type": policy.reminder_type,
                        "lead_minutes": policy.lead_minutes,
                    },
                )
            )
    return dispatches


def _scheduled_for_instance(
    *,
    policy: PersistedReminderPolicy,
    instance: ReminderSchedulableInstance,
) -> datetime | None:
    if policy.reminder_type == "pre_session":
        return instance.starts_at - timedelta(minutes=policy.lead_minutes)
    if policy.reminder_type == "followup":
        offset = policy.followup_minutes if policy.followup_minutes is not None else policy.lead_minutes
        return instance.ends_at + timedelta(minutes=offset)
    return None


def _dispatch_type(policy: PersistedReminderPolicy) -> str:
    if policy.reminder_type == "followup":
        offset = policy.followup_minutes if policy.followup_minutes is not None else policy.lead_minutes
        return f"followup_{offset}m"
    return f"{policy.reminder_type}_{policy.lead_minutes}m"


def _default_channels_from_env() -> tuple[str, ...]:
    raw_value = os.getenv("ACADEMIC_AGENT_REMINDER_CHANNELS", "").strip()
    if not raw_value:
        return DEFAULT_REMINDER_CHANNELS
    parts = tuple(
        channel.strip()
        for channel in raw_value.split(",")
        if channel.strip() in _SUPPORTED_CHANNELS
    )
    return parts or DEFAULT_REMINDER_CHANNELS
