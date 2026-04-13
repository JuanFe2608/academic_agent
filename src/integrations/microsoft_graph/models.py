"""Modelos y contratos compartidos para Microsoft Graph."""

from ._clients_impl import (
    MicrosoftGraphClientError,
    MicrosoftGraphTransport,
    MicrosoftMailClient,
    MicrosoftMailMessage,
    MicrosoftTodoClient,
    MicrosoftTodoTaskList,
    MicrosoftTodoTaskUpsert,
    OutlookCalendarClient,
    OutlookCalendarEventSnapshot,
    OutlookCalendarEventUpsert,
    OutlookEventRecurrence,
    UpsertedMicrosoftTodoTask,
    UpsertedOutlookCalendarEvent,
)

__all__ = [
    "MicrosoftGraphClientError",
    "MicrosoftGraphTransport",
    "MicrosoftMailClient",
    "MicrosoftMailMessage",
    "MicrosoftTodoClient",
    "MicrosoftTodoTaskList",
    "MicrosoftTodoTaskUpsert",
    "OutlookCalendarClient",
    "OutlookCalendarEventSnapshot",
    "OutlookCalendarEventUpsert",
    "OutlookEventRecurrence",
    "UpsertedMicrosoftTodoTask",
    "UpsertedOutlookCalendarEvent",
]
