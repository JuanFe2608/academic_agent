"""Servicio de aplicación para políticas y despachos de recordatorios."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from repositories.planning.instances_repository import StudyPlanInstancesRepository
from repositories.reminders.repository import (
    InMemoryRemindersRepository,
    PersistedReminderPolicy,
    ReminderDispatchSeed,
    ReminderPolicySpec,
    ReminderSchedulableInstance,
    RemindersRepository,
    RemindersRepositoryError,
    build_reminders_repository,
)
from schemas.reminders import RemindersState
from schemas.planning import AcademicActivity
from services.planning.academic_activity_service import coerce_academic_activities
from services.reminders.state_helpers import ensure_reminders_state

DEFAULT_REMINDER_CHANNELS = ("in_app",)
_SUPPORTED_CHANNELS = {"in_app", "email", "whatsapp"}
_SUPPORTED_REMINDER_TYPES = {
    "pre_session",
    "followup",
    "missed_session",
    "daily_agenda",
    "activity_due",
    "activity_overdue",
}
_DEFAULT_QUIET_HOURS = {"start": "22:00", "end": "06:00"}
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
_DEFAULT_ACTIVITY_POLICY_BLUEPRINTS: tuple[dict[str, object], ...] = (
    {
        "reminder_type": "daily_agenda",
        "lead_minutes": 0,
        "followup_minutes": None,
        "metadata_json": {"timing": "same_day", "origin": "default"},
    },
    {
        "reminder_type": "activity_due",
        "lead_minutes": 180,
        "followup_minutes": None,
        "metadata_json": {"timing": "before_due", "origin": "default"},
    },
    {
        "reminder_type": "activity_due",
        "lead_minutes": 60,
        "followup_minutes": None,
        "metadata_json": {"timing": "before_due", "origin": "default"},
    },
    {
        "reminder_type": "activity_due",
        "lead_minutes": 15,
        "followup_minutes": None,
        "metadata_json": {"timing": "before_due", "origin": "default"},
    },
    {
        "reminder_type": "activity_overdue",
        "lead_minutes": 15,
        "followup_minutes": None,
        "metadata_json": {"timing": "after_due", "origin": "default"},
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

    def sync_reminders_for_academic_activities(
        self,
        *,
        student_id: int | None,
        activities: list,
        reminders_state: RemindersState | dict | None,
        timezone: str,
        whatsapp_recipient_id: str | None = None,
    ) -> SyncStudyPlanRemindersResult:
        """Sincroniza agenda diaria, avisos previos y seguimiento de vencidos.

        Las actividades completadas o eliminadas no generan recordatorios y además
        cancelan dispatches futuros que hayan quedado pendientes.
        """

        if not student_id:
            return SyncStudyPlanRemindersResult(
                synced=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar recordatorios.",
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
        pending_activities = [
            activity
            for activity in coerce_academic_activities(activities)
            if activity.status == "pending" and activity.due_date
        ]

        try:
            persisted_policies = self.repository.upsert_policies(
                student_id=student_id,
                policies=_build_activity_policy_specs(
                    normalized,
                    timezone=str(zone),
                    default_channels=self.default_channels,
                ),
            )
            dispatches = (
                _build_activity_dispatches(
                    persisted_policies=persisted_policies,
                    activities=pending_activities,
                    timezone=str(zone),
                    sync_now=sync_now,
                    whatsapp_recipient_id=whatsapp_recipient_id,
                )
                if normalized.enabled
                else []
            )
            valid_source_keys = {
                str(dispatch.payload.get("reminder_source") or "")
                for dispatch in dispatches
                if str(dispatch.payload.get("reminder_source") or "").strip()
            }
            canceled_dispatch_count = self.repository.cancel_stale_activity_dispatches(
                student_id=student_id,
                valid_source_keys=valid_source_keys,
            )
            created_dispatch_count = (
                self.repository.sync_dispatches(dispatches=dispatches)
                if normalized.enabled
                else 0
            )
        except (RemindersRepositoryError, RepositoryConfigurationError) as exc:
            return SyncStudyPlanRemindersResult(
                synced=False,
                error_code="academic_activity_reminders_sync_error",
                detail=str(exc),
            )

        return _success_result(
            persisted_policies=persisted_policies,
            schedulable_instance_count=len(pending_activities),
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


def _build_activity_policy_specs(
    reminders_state: RemindersState,
    *,
    timezone: str,
    default_channels: tuple[str, ...],
) -> list[ReminderPolicySpec]:
    channels = _normalize_channels(
        reminders_state.policy.get("channels"),
        default_channels=default_channels,
    )
    quiet_hours = _normalize_quiet_hours(reminders_state.policy.get("quiet_hours"))
    blueprints = _normalize_policy_blueprints(
        reminders_state.policy.get("activity_rules"),
        default_blueprints=_DEFAULT_ACTIVITY_POLICY_BLUEPRINTS,
        allowed_types={"daily_agenda", "activity_due", "activity_overdue"},
    )

    specs: list[ReminderPolicySpec] = []
    for channel in channels:
        for blueprint in blueprints:
            metadata_json = dict(blueprint.get("metadata_json") or {})
            metadata_json.setdefault("domain", "academic_activity")
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


def _normalize_policy_blueprints(
    raw_rules: object,
    *,
    default_blueprints: tuple[dict[str, object], ...] = _DEFAULT_POLICY_BLUEPRINTS,
    allowed_types: set[str] | None = None,
) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_rules, list):
        return tuple(dict(item) for item in default_blueprints)

    allowed = allowed_types or _SUPPORTED_REMINDER_TYPES
    normalized: list[dict[str, object]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        reminder_type = str(raw_rule.get("reminder_type") or "").strip()
        if reminder_type not in allowed:
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
        return tuple(dict(item) for item in default_blueprints)
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


def _build_activity_dispatches(
    *,
    persisted_policies: list[PersistedReminderPolicy],
    activities: list[AcademicActivity],
    timezone: str,
    sync_now: datetime,
    whatsapp_recipient_id: str | None,
) -> list[ReminderDispatchSeed]:
    policies = [policy for policy in persisted_policies if policy.enabled]
    due_policies = [policy for policy in policies if policy.reminder_type == "activity_due"]
    overdue_policies = [policy for policy in policies if policy.reminder_type == "activity_overdue"]
    agenda_policies = [policy for policy in policies if policy.reminder_type == "daily_agenda"]

    dispatches: list[ReminderDispatchSeed] = []
    agenda_by_date: dict[date, list[dict[str, object]]] = {}

    for activity in activities:
        due_at = _activity_due_at(activity, timezone=timezone)
        if due_at is None:
            continue
        agenda_by_date.setdefault(due_at.date(), []).append(
            _activity_payload(activity, due_at=due_at)
        )

        if due_at > sync_now:
            for policy in due_policies:
                scheduled_for = due_at - timedelta(minutes=policy.lead_minutes)
                if scheduled_for < sync_now:
                    continue
                source_key = _activity_source_key(
                    activity.activity_id,
                    "due",
                    policy.lead_minutes,
                    scheduled_for,
                )
                dispatches.append(
                    _activity_dispatch_seed(
                        policy=policy,
                        activity=activity,
                        scheduled_for=scheduled_for,
                        due_at=due_at,
                        source_key=source_key,
                        kind="activity_due",
                        timezone=timezone,
                        whatsapp_recipient_id=whatsapp_recipient_id,
                    )
                )

        for policy in overdue_policies:
            scheduled_for = due_at + timedelta(minutes=policy.lead_minutes)
            source_key = _activity_source_key(
                activity.activity_id,
                "overdue",
                policy.lead_minutes,
                scheduled_for,
            )
            dispatches.append(
                _activity_dispatch_seed(
                    policy=policy,
                    activity=activity,
                    scheduled_for=scheduled_for,
                    due_at=due_at,
                    source_key=source_key,
                    kind="activity_overdue",
                    timezone=timezone,
                    whatsapp_recipient_id=whatsapp_recipient_id,
                )
            )

    for agenda_date, agenda_items in sorted(agenda_by_date.items()):
        scheduled_for = _daily_agenda_at(agenda_date, timezone=timezone)
        source_key = f"agenda:{agenda_date.isoformat()}:{scheduled_for.isoformat()}"
        for policy in agenda_policies:
            dispatches.append(
                ReminderDispatchSeed(
                    student_id=policy.student_id,
                    reminder_policy_id=policy.id,
                    study_plan_event_instance_id=None,
                    dispatch_type=f"daily_agenda_{agenda_date.isoformat()}",
                    channel=policy.channel,
                    scheduled_for=scheduled_for,
                    payload={
                        "reminder_domain": "academic_activity",
                        "reminder_source": source_key,
                        "kind": "daily_agenda",
                        "title": "Agenda academica de hoy",
                        "agenda_date": agenda_date.isoformat(),
                        "timezone": timezone,
                        "starts_at": scheduled_for.isoformat(),
                        "channel": policy.channel,
                        "reminder_type": policy.reminder_type,
                        "lead_minutes": policy.lead_minutes,
                        "activities": sorted(
                            agenda_items,
                            key=lambda item: str(item.get("due_at") or ""),
                        ),
                        **_whatsapp_payload(whatsapp_recipient_id),
                    },
                )
            )

    return dispatches


def _activity_dispatch_seed(
    *,
    policy: PersistedReminderPolicy,
    activity: AcademicActivity,
    scheduled_for: datetime,
    due_at: datetime,
    source_key: str,
    kind: str,
    timezone: str,
    whatsapp_recipient_id: str | None,
) -> ReminderDispatchSeed:
    return ReminderDispatchSeed(
        student_id=policy.student_id,
        reminder_policy_id=policy.id,
        study_plan_event_instance_id=None,
        dispatch_type=f"{kind}_{policy.lead_minutes}m_{activity.activity_id[:12]}",
        channel=policy.channel,
        scheduled_for=scheduled_for,
        payload={
            "reminder_domain": "academic_activity",
            "reminder_source": source_key,
            "kind": kind,
            "activity_id": activity.activity_id,
            "activity_type": activity.activity_type,
            "subject_name": activity.subject_name,
            "title": _activity_title(activity),
            "timezone": timezone,
            "starts_at": due_at.isoformat(),
            "due_at": due_at.isoformat(),
            "channel": policy.channel,
            "reminder_type": policy.reminder_type,
            "lead_minutes": policy.lead_minutes,
            **_whatsapp_payload(whatsapp_recipient_id),
        },
    )


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
    if policy.reminder_type == "missed_session":
        return instance.ends_at + timedelta(minutes=policy.lead_minutes)
    return None


def _dispatch_type(policy: PersistedReminderPolicy) -> str:
    if policy.reminder_type == "followup":
        offset = policy.followup_minutes if policy.followup_minutes is not None else policy.lead_minutes
        return f"followup_{offset}m"
    return f"{policy.reminder_type}_{policy.lead_minutes}m"


def _activity_due_at(activity: AcademicActivity, *, timezone: str) -> datetime | None:
    try:
        due_date = date.fromisoformat(str(activity.due_date or "")[:10])
    except ValueError:
        return None
    due_time = _parse_time(activity.due_time) or _default_activity_due_time()
    zone = ZoneInfo(timezone)
    return datetime.combine(due_date, due_time, tzinfo=zone)


def _daily_agenda_at(agenda_date: date, *, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    return datetime.combine(agenda_date, _daily_agenda_time(), tzinfo=zone)


def _activity_payload(activity: AcademicActivity, *, due_at: datetime) -> dict[str, object]:
    return {
        "activity_id": activity.activity_id,
        "activity_type": activity.activity_type,
        "subject_name": activity.subject_name,
        "title": _activity_title(activity),
        "due_at": due_at.isoformat(),
        "priority_level": activity.priority_level,
    }


def _activity_title(activity: AcademicActivity) -> str:
    title = str(activity.activity_title or "").strip()
    if title:
        return title
    label = str(activity.activity_type or "actividad").replace("_", " ")
    subject = str(activity.subject_name or "").strip()
    return f"{label.capitalize()} de {subject}".strip()


def _activity_source_key(
    activity_id: str,
    kind: str,
    lead_minutes: int,
    scheduled_for: datetime,
) -> str:
    return f"activity:{activity_id}:{kind}:{lead_minutes}:{scheduled_for.isoformat()}"


def _whatsapp_payload(recipient_id: str | None) -> dict[str, object]:
    recipient = str(recipient_id or "").strip()
    return {"whatsapp_recipient_id": recipient} if recipient else {}


def _parse_time(value: object) -> time | None:
    if isinstance(value, time):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return time.fromisoformat(text[:5])
    except ValueError:
        return None


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
