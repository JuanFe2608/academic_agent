"""Adapters externos para Microsoft Graph."""

from .auth_client import (
    DEFAULT_MICROSOFT_SCOPES,
    InMemoryMicrosoftTokenStore,
    MicrosoftAuthorizationRequest,
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
    MicrosoftOAuthTransport,
    MicrosoftOAuthTransportError,
    MicrosoftTokenOperationResult,
    MicrosoftTokenRecord,
    MicrosoftTokenStore,
    UrllibMicrosoftOAuthTransport,
    build_microsoft_oauth_client_from_env,
)
from .calendar_client import DisabledOutlookCalendarClient, GraphOutlookCalendarClient
from .mail_client import DisabledMicrosoftMailClient, GraphMicrosoftMailClient
from .models import (
    MicrosoftGraphClientError,
    MicrosoftGraphTransport,
    MicrosoftMailClient,
    MicrosoftMailMessage,
    MicrosoftTodoClient,
    MicrosoftTodoTaskList,
    MicrosoftTodoTaskUpsert,
    OutlookCalendarClient,
    OutlookCalendarEventUpsert,
    UpsertedMicrosoftTodoTask,
    UpsertedOutlookCalendarEvent,
)
from .todo_client import DisabledMicrosoftTodoClient, GraphMicrosoftTodoClient
from .transport import UrllibMicrosoftGraphTransport

__all__ = [
    "DEFAULT_MICROSOFT_SCOPES",
    "InMemoryMicrosoftTokenStore",
    "MicrosoftAuthorizationRequest",
    "MicrosoftGraphClientError",
    "MicrosoftGraphStateTokenStore",
    "MicrosoftGraphTransport",
    "MicrosoftMailClient",
    "MicrosoftMailMessage",
    "MicrosoftOAuthClient",
    "MicrosoftOAuthConfig",
    "MicrosoftOAuthTransport",
    "MicrosoftOAuthTransportError",
    "MicrosoftTodoClient",
    "MicrosoftTodoTaskList",
    "MicrosoftTodoTaskUpsert",
    "MicrosoftTokenOperationResult",
    "MicrosoftTokenRecord",
    "MicrosoftTokenStore",
    "OutlookCalendarClient",
    "OutlookCalendarEventUpsert",
    "UpsertedMicrosoftTodoTask",
    "UpsertedOutlookCalendarEvent",
    "UrllibMicrosoftOAuthTransport",
    "UrllibMicrosoftGraphTransport",
    "DisabledOutlookCalendarClient",
    "GraphOutlookCalendarClient",
    "DisabledMicrosoftTodoClient",
    "GraphMicrosoftTodoClient",
    "DisabledMicrosoftMailClient",
    "GraphMicrosoftMailClient",
    "build_microsoft_oauth_client_from_env",
]
