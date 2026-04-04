"""Cliente de correo sobre Microsoft Graph."""

from ._clients_impl import DisabledMicrosoftMailClient, GraphMicrosoftMailClient

__all__ = [
    "DisabledMicrosoftMailClient",
    "GraphMicrosoftMailClient",
]
