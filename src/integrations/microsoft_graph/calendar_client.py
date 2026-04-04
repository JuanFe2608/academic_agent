"""Cliente de Outlook Calendar sobre Microsoft Graph."""

from ._clients_impl import DisabledOutlookCalendarClient, GraphOutlookCalendarClient

__all__ = [
    "DisabledOutlookCalendarClient",
    "GraphOutlookCalendarClient",
]
