"""Servicios del dominio de recordatorios."""

from .dispatcher import (
    GraphEmailReminderSender,
    ReminderDispatchRunner,
    ReminderRecipientResolver,
    ReminderSendResult,
    RunDueRemindersResult,
    WhatsAppReminderSender,
    build_reminder_dispatch_runner,
    default_whatsapp_recipient_resolver,
    render_whatsapp_reminder_message,
)
from .service import (
    StudyPlanRemindersService,
    SyncStudyPlanRemindersResult,
    build_study_plan_reminders_service,
)
from .state_helpers import (
    ensure_reminders_state,
    reminders_state_to_update,
    update_reminders_state,
)

__all__ = [
    "GraphEmailReminderSender",
    "ReminderDispatchRunner",
    "ReminderRecipientResolver",
    "ReminderSendResult",
    "RunDueRemindersResult",
    "StudyPlanRemindersService",
    "SyncStudyPlanRemindersResult",
    "WhatsAppReminderSender",
    "build_reminder_dispatch_runner",
    "build_study_plan_reminders_service",
    "default_whatsapp_recipient_resolver",
    "ensure_reminders_state",
    "render_whatsapp_reminder_message",
    "reminders_state_to_update",
    "update_reminders_state",
]
