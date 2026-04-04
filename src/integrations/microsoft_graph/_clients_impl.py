"""Clientes Microsoft Graph desacoplados del dominio del agente."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

_DEFAULT_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class MicrosoftGraphClientError(Exception):
    """Error base de los adapters Microsoft Graph."""

    def __init__(self, *, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.error_code = error_code
        self.detail = detail


@dataclass(frozen=True)
class OutlookCalendarEventUpsert:
    """Evento listo para sincronizar con Outlook Calendar."""

    external_key: str
    subject: str
    body_preview: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    categories: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, object] = field(default_factory=dict)
    existing_external_event_id: str | None = None
    existing_change_key: str | None = None


@dataclass(frozen=True)
class UpsertedOutlookCalendarEvent:
    """Resultado mínimo de un upsert de evento."""

    external_key: str
    external_event_id: str
    external_change_key: str | None = None


@dataclass(frozen=True)
class MicrosoftTodoTaskUpsert:
    """Tarea lista para sincronizar con Microsoft To Do."""

    external_key: str
    title: str
    body_preview: str
    due_at: datetime | None
    metadata: dict[str, object] = field(default_factory=dict)
    existing_external_task_id: str | None = None


@dataclass(frozen=True)
class UpsertedMicrosoftTodoTask:
    """Resultado mínimo de un upsert de tarea."""

    external_key: str
    external_task_id: str


@dataclass(frozen=True)
class MicrosoftTodoTaskList:
    """Resumen de una lista disponible en Microsoft To Do."""

    id: str
    display_name: str | None = None
    wellknown_list_name: str | None = None


@dataclass(frozen=True)
class MicrosoftMailMessage:
    """Correo listo para envío vía Microsoft Graph."""

    subject: str
    body_text: str
    to_recipients: tuple[str, ...]
    metadata: dict[str, object] = field(default_factory=dict)


class MicrosoftGraphTransport(Protocol):
    """Transporte HTTP inyectable para Microsoft Graph."""

    def request_json(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def request_no_content(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, Any] | None = None,
    ) -> None: ...


class OutlookCalendarClient(Protocol):
    """Contrato para sincronización de eventos en Outlook Calendar."""

    def upsert_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        events: list[OutlookCalendarEventUpsert],
    ) -> list[UpsertedOutlookCalendarEvent]: ...

    def delete_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        external_event_ids: list[str],
    ) -> list[str]: ...


class MicrosoftTodoClient(Protocol):
    """Contrato para sincronización con Microsoft To Do."""

    def list_task_lists(
        self,
        *,
        access_token: str,
    ) -> list[MicrosoftTodoTaskList]: ...

    def upsert_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        tasks: list[MicrosoftTodoTaskUpsert],
    ) -> list[UpsertedMicrosoftTodoTask]: ...

    def delete_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        external_task_ids: list[str],
    ) -> list[str]: ...


class MicrosoftMailClient(Protocol):
    """Contrato para envío de correo por Graph."""

    def send_message(self, *, access_token: str, message: MicrosoftMailMessage) -> str: ...


class DisabledOutlookCalendarClient:
    """Cliente placeholder que falla explícitamente hasta tener Graph real."""

    def upsert_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        events: list[OutlookCalendarEventUpsert],
    ) -> list[UpsertedOutlookCalendarEvent]:
        raise MicrosoftGraphClientError(
            error_code="outlook_client_not_configured",
            detail="OutlookCalendarClient no configurado. Falta adapter real de Microsoft Graph.",
        )

    def delete_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        external_event_ids: list[str],
    ) -> list[str]:
        raise MicrosoftGraphClientError(
            error_code="outlook_client_not_configured",
            detail="OutlookCalendarClient no configurado. Falta adapter real de Microsoft Graph.",
        )


class DisabledMicrosoftTodoClient:
    """Cliente placeholder para To Do mientras no exista adapter real."""

    def list_task_lists(
        self,
        *,
        access_token: str,
    ) -> list[MicrosoftTodoTaskList]:
        raise MicrosoftGraphClientError(
            error_code="todo_client_not_configured",
            detail="MicrosoftTodoClient no configurado. Falta adapter real de Microsoft Graph.",
        )

    def upsert_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        tasks: list[MicrosoftTodoTaskUpsert],
    ) -> list[UpsertedMicrosoftTodoTask]:
        raise MicrosoftGraphClientError(
            error_code="todo_client_not_configured",
            detail="MicrosoftTodoClient no configurado. Falta adapter real de Microsoft Graph.",
        )

    def delete_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        external_task_ids: list[str],
    ) -> list[str]:
        raise MicrosoftGraphClientError(
            error_code="todo_client_not_configured",
            detail="MicrosoftTodoClient no configurado. Falta adapter real de Microsoft Graph.",
        )


class DisabledMicrosoftMailClient:
    """Cliente placeholder para email por Graph mientras no exista adapter real."""

    def send_message(self, *, access_token: str, message: MicrosoftMailMessage) -> str:
        raise MicrosoftGraphClientError(
            error_code="mail_client_not_configured",
            detail="MicrosoftMailClient no configurado. Falta adapter real de Microsoft Graph.",
        )


class UrllibMicrosoftGraphTransport:
    """Transporte Microsoft Graph con urllib para evitar dependencias extra."""

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def request_json(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_bytes = None
        headers = {"Authorization": f"Bearer {access_token}"}
        if json_payload is not None:
            payload_bytes = json.dumps(json_payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url=url, data=payload_bytes, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:  # pragma: no cover
            raise _graph_error_from_http_error(exc) from exc
        except URLError as exc:  # pragma: no cover
            raise MicrosoftGraphClientError(
                error_code="microsoft_graph_network_error",
                detail=str(exc.reason or exc),
            ) from exc

        if not body.strip():
            return {}
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise MicrosoftGraphClientError(
                error_code="microsoft_graph_invalid_payload",
                detail="Microsoft Graph devolvió un payload JSON inesperado.",
            )
        return decoded

    def request_no_content(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, Any] | None = None,
    ) -> None:
        payload_bytes = None
        headers = {"Authorization": f"Bearer {access_token}"}
        if json_payload is not None:
            payload_bytes = json.dumps(json_payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url=url, data=payload_bytes, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()
        except HTTPError as exc:  # pragma: no cover
            raise _graph_error_from_http_error(exc) from exc
        except URLError as exc:  # pragma: no cover
            raise MicrosoftGraphClientError(
                error_code="microsoft_graph_network_error",
                detail=str(exc.reason or exc),
            ) from exc


class GraphOutlookCalendarClient:
    """Adapter real para Outlook Calendar sobre Microsoft Graph."""

    def __init__(
        self,
        *,
        graph_base_url: str = _DEFAULT_GRAPH_BASE_URL,
        transport: MicrosoftGraphTransport | None = None,
    ) -> None:
        self.graph_base_url = graph_base_url.rstrip("/")
        self.transport = transport or UrllibMicrosoftGraphTransport()

    def upsert_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        events: list[OutlookCalendarEventUpsert],
    ) -> list[UpsertedOutlookCalendarEvent]:
        results: list[UpsertedOutlookCalendarEvent] = []
        for event in events:
            if event.existing_external_event_id:
                response = self.transport.request_json(
                    method="PATCH",
                    url=f"{self.graph_base_url}/me/events/{quote(event.existing_external_event_id, safe='')}",
                    access_token=access_token,
                    json_payload=_outlook_event_payload(event),
                )
            else:
                response = self.transport.request_json(
                    method="POST",
                    url=_calendar_events_collection_url(
                        graph_base_url=self.graph_base_url,
                        calendar_id=calendar_id,
                    ),
                    access_token=access_token,
                    json_payload=_outlook_event_payload(event, include_transaction_id=True),
                )
            event_id = str(response.get("id") or event.existing_external_event_id or "").strip()
            if not event_id:
                raise MicrosoftGraphClientError(
                    error_code="outlook_event_missing_id",
                    detail=f"Microsoft Graph no devolvió id para external_key={event.external_key}.",
                )
            results.append(
                UpsertedOutlookCalendarEvent(
                    external_key=event.external_key,
                    external_event_id=event_id,
                    external_change_key=_optional_str(response.get("changeKey")),
                )
            )
        return results

    def delete_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        external_event_ids: list[str],
    ) -> list[str]:
        deleted: list[str] = []
        for external_event_id in external_event_ids:
            self.transport.request_no_content(
                method="DELETE",
                url=f"{self.graph_base_url}/me/events/{quote(external_event_id, safe='')}",
                access_token=access_token,
            )
            deleted.append(external_event_id)
        return deleted


class GraphMicrosoftTodoClient:
    """Adapter real para Microsoft To Do sobre Microsoft Graph."""

    def __init__(
        self,
        *,
        graph_base_url: str = _DEFAULT_GRAPH_BASE_URL,
        transport: MicrosoftGraphTransport | None = None,
    ) -> None:
        self.graph_base_url = graph_base_url.rstrip("/")
        self.transport = transport or UrllibMicrosoftGraphTransport()

    def list_task_lists(
        self,
        *,
        access_token: str,
    ) -> list[MicrosoftTodoTaskList]:
        response = self.transport.request_json(
            method="GET",
            url=f"{self.graph_base_url}/me/todo/lists",
            access_token=access_token,
        )
        raw_lists = response.get("value")
        if not isinstance(raw_lists, list):
            raise MicrosoftGraphClientError(
                error_code="microsoft_todo_lists_invalid_payload",
                detail="Microsoft Graph devolvió una colección de listas inválida.",
            )

        task_lists: list[MicrosoftTodoTaskList] = []
        for raw in raw_lists:
            if not isinstance(raw, dict):
                continue
            list_id = _optional_str(raw.get("id"))
            if not list_id:
                continue
            task_lists.append(
                MicrosoftTodoTaskList(
                    id=list_id,
                    display_name=_optional_str(raw.get("displayName")),
                    wellknown_list_name=_optional_str(raw.get("wellknownListName")),
                )
            )
        return task_lists

    def upsert_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        tasks: list[MicrosoftTodoTaskUpsert],
    ) -> list[UpsertedMicrosoftTodoTask]:
        if not str(task_list_id).strip():
            raise MicrosoftGraphClientError(
                error_code="missing_task_list_id",
                detail="Debes suministrar un task_list_id para sincronizar Microsoft To Do.",
            )

        results: list[UpsertedMicrosoftTodoTask] = []
        list_id = quote(task_list_id, safe="")
        for task in tasks:
            if task.existing_external_task_id:
                response = self.transport.request_json(
                    method="PATCH",
                    url=(
                        f"{self.graph_base_url}/me/todo/lists/{list_id}/tasks/"
                        f"{quote(task.existing_external_task_id, safe='')}"
                    ),
                    access_token=access_token,
                    json_payload=_todo_task_payload(task),
                )
            else:
                response = self.transport.request_json(
                    method="POST",
                    url=f"{self.graph_base_url}/me/todo/lists/{list_id}/tasks",
                    access_token=access_token,
                    json_payload=_todo_task_payload(task),
                )
            task_id = str(response.get("id") or task.existing_external_task_id or "").strip()
            if not task_id:
                raise MicrosoftGraphClientError(
                    error_code="microsoft_todo_missing_id",
                    detail=f"Microsoft Graph no devolvió id para external_key={task.external_key}.",
                )
            results.append(
                UpsertedMicrosoftTodoTask(
                    external_key=task.external_key,
                    external_task_id=task_id,
                )
            )
        return results

    def delete_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        external_task_ids: list[str],
    ) -> list[str]:
        if not str(task_list_id).strip():
            raise MicrosoftGraphClientError(
                error_code="missing_task_list_id",
                detail="Debes suministrar un task_list_id para sincronizar Microsoft To Do.",
            )
        deleted: list[str] = []
        list_id = quote(task_list_id, safe="")
        for external_task_id in external_task_ids:
            self.transport.request_no_content(
                method="DELETE",
                url=(
                    f"{self.graph_base_url}/me/todo/lists/{list_id}/tasks/"
                    f"{quote(external_task_id, safe='')}"
                ),
                access_token=access_token,
            )
            deleted.append(external_task_id)
        return deleted


class GraphMicrosoftMailClient:
    """Adapter real para `sendMail` vía Microsoft Graph."""

    def __init__(
        self,
        *,
        graph_base_url: str = _DEFAULT_GRAPH_BASE_URL,
        transport: MicrosoftGraphTransport | None = None,
    ) -> None:
        self.graph_base_url = graph_base_url.rstrip("/")
        self.transport = transport or UrllibMicrosoftGraphTransport()

    def send_message(self, *, access_token: str, message: MicrosoftMailMessage) -> str:
        if not message.to_recipients:
            raise MicrosoftGraphClientError(
                error_code="missing_mail_recipients",
                detail="MicrosoftMailMessage requiere al menos un destinatario.",
            )
        self.transport.request_no_content(
            method="POST",
            url=f"{self.graph_base_url}/me/sendMail",
            access_token=access_token,
            json_payload={
                "message": {
                    "subject": message.subject,
                    "body": {
                        "contentType": "Text",
                        "content": message.body_text,
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": recipient}}
                        for recipient in message.to_recipients
                    ],
                },
                "saveToSentItems": True,
            },
        )
        provider_id = _optional_str(message.metadata.get("provider_message_id"))
        if provider_id:
            return provider_id
        dispatch_id = _optional_str(message.metadata.get("dispatch_id"))
        return dispatch_id or "microsoft_graph_sendmail"


def _calendar_events_collection_url(*, graph_base_url: str, calendar_id: str | None) -> str:
    if str(calendar_id or "").strip():
        return f"{graph_base_url}/me/calendars/{quote(str(calendar_id), safe='')}/events"
    return f"{graph_base_url}/me/calendar/events"


def _outlook_event_payload(
    event: OutlookCalendarEventUpsert,
    *,
    include_transaction_id: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subject": event.subject,
        "body": {
            "contentType": "Text",
            "content": event.body_preview,
        },
        "start": _graph_datetime_payload(event.starts_at),
        "end": _graph_datetime_payload(event.ends_at),
        "categories": list(event.categories),
    }
    if include_transaction_id:
        payload["transactionId"] = event.external_key[:255]
    return payload


def _todo_task_payload(task: MicrosoftTodoTaskUpsert) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": task.title,
        "body": {
            "content": task.body_preview,
            "contentType": "text",
        },
    }
    if task.due_at is not None:
        payload["dueDateTime"] = _graph_datetime_payload(task.due_at)
    return payload


def _graph_datetime_payload(value: datetime) -> dict[str, str]:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    utc_value = normalized.astimezone(timezone.utc).replace(microsecond=0)
    return {
        "dateTime": utc_value.isoformat().replace("+00:00", "Z"),
        "timeZone": "UTC",
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _graph_error_from_http_error(exc: HTTPError) -> MicrosoftGraphClientError:
    body = exc.read().decode("utf-8", errors="replace")
    payload: dict[str, Any] = {}
    if body.strip():
        try:
            decoded = json.loads(body)
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            payload = {}
    inner_error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    error_code = str(
        (inner_error or {}).get("code")
        or payload.get("code")
        or f"microsoft_graph_http_{exc.code}"
    )
    detail = str(
        (inner_error or {}).get("message")
        or payload.get("message")
        or body
        or exc.reason
        or exc
    )
    return MicrosoftGraphClientError(error_code=error_code, detail=detail)
