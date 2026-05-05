"""Worker idempotente para despachar reminders vencidos."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

_logger = logging.getLogger(__name__)

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    build_microsoft_oauth_client_from_env,
)
from integrations.whatsapp import WhatsAppClientError, WhatsAppCloudClient
from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from repositories.microsoft_graph.state_repository import (
    MicrosoftGraphStateRepository,
    MicrosoftGraphStateRepositoryError,
    build_microsoft_graph_state_repository,
)
from repositories.reminders.repository import (
    LeasedReminderDispatch,
    RemindersRepository,
    RemindersRepositoryError,
    build_reminders_repository,
)
from integrations.microsoft_graph.mail_client import GraphMicrosoftMailClient
from integrations.microsoft_graph.models import (
    MicrosoftGraphClientError,
    MicrosoftMailClient,
    MicrosoftMailMessage,
)
from schemas.channels import ChannelOutboundMessage
from services.channels import WhatsAppChannelService

_DEFAULT_DISPATCH_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_MINUTES = 15


@dataclass(frozen=True)
class ReminderSendResult:
    """Resultado de intentar enviar un despacho a un canal."""

    sent: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    detail: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class RunDueRemindersResult:
    """Resumen operativo del worker de reminders."""

    processed: bool
    leased_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    retryable_count: int = 0
    channel_counts: dict[str, int] | None = None
    dispatch_type_counts: dict[str, int] | None = None
    error_code: str | None = None
    detail: str | None = None


class ReminderChannelSender(Protocol):
    """Contrato mínimo para adaptadores de canal."""

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult: ...


class ReminderRecipientResolver(Protocol):
    """Resuelve el destinatario externo de un dispatch."""

    def recipient_for(self, dispatch: LeasedReminderDispatch) -> str | None: ...


class InAppReminderSender:
    """Canal local mínimo: marca el dispatch como enviado."""

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult:
        return ReminderSendResult(
            sent=True,
            provider_message_id=f"in_app:{dispatch.id}",
        )


class UnsupportedReminderSender:
    """Fallback explícito para canales no implementados todavía."""

    def __init__(
        self,
        channel: str,
        *,
        error_code: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.channel = channel
        self.error_code = error_code or f"unsupported_channel:{channel}"
        self.detail = detail or (
            "El canal aun no tiene adaptador de entrega. "
            "Debes conectar un sender externo para usarlo."
        )

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult:
        return ReminderSendResult(
            sent=False,
            error_code=self.error_code,
            detail=self.detail,
        )


class GraphEmailReminderSender:
    """Canal email usando tokens OAuth Microsoft persistidos."""

    def __init__(
        self,
        *,
        state_repository: MicrosoftGraphStateRepository,
        oauth_client: MicrosoftOAuthClient,
        mail_client: MicrosoftMailClient | None = None,
    ) -> None:
        self.state_repository = state_repository
        self.oauth_client = oauth_client
        self.mail_client = mail_client or GraphMicrosoftMailClient()

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult:
        try:
            token_result = self.oauth_client.get_valid_access_token(student_id=dispatch.student_id)
            if not token_result.ok or token_result.token is None:
                return ReminderSendResult(
                    sent=False,
                    error_code=token_result.error_code or "microsoft_oauth_error",
                    detail=token_result.detail,
                )

            connection = self.state_repository.get_connection(student_id=dispatch.student_id)
            recipient = self.state_repository.get_student_institutional_email(
                student_id=dispatch.student_id
            ) or (connection.email if connection is not None else None)
            if not recipient:
                return ReminderSendResult(
                    sent=False,
                    error_code="missing_recipient_email",
                    detail="No encontré un correo institucional para enviar el reminder.",
                )

            provider_message_id = self.mail_client.send_message(
                access_token=token_result.token.access_token,
                message=MicrosoftMailMessage(
                    subject=_email_subject(dispatch),
                    body_text=_email_body(dispatch),
                    to_recipients=(recipient,),
                    metadata={"dispatch_id": dispatch.id},
                ),
            )
            return ReminderSendResult(
                sent=True,
                provider_message_id=provider_message_id,
            )
        except (
            MicrosoftGraphClientError,
            MicrosoftGraphStateRepositoryError,
            RepositoryConfigurationError,
        ) as exc:
            return ReminderSendResult(
                sent=False,
                error_code=getattr(exc, "error_code", "microsoft_email_send_error"),
                detail=getattr(exc, "detail", str(exc)),
            )


class PayloadReminderRecipientResolver:
    """Busca el destinatario WhatsApp dentro del payload del dispatch."""

    _PAYLOAD_KEYS = (
        "whatsapp_recipient_id",
        "recipient_id",
        "to",
        "phone_number",
        "conversation_id",
        "sender_id",
    )

    def recipient_for(self, dispatch: LeasedReminderDispatch) -> str | None:
        for key in self._PAYLOAD_KEYS:
            candidate = str(dispatch.payload.get(key) or "").strip()
            if candidate:
                return candidate
        return None


class EnvWhatsAppRecipientResolver:
    """Resuelve destinatarios WhatsApp desde variables de entorno operativas."""

    def __init__(
        self,
        *,
        recipients_by_student_id: Mapping[str, str] | None = None,
        default_recipient_id: str | None = None,
    ) -> None:
        self.recipients_by_student_id = {
            str(key).strip(): str(value).strip()
            for key, value in dict(recipients_by_student_id or {}).items()
            if str(key).strip() and str(value).strip()
        }
        self.default_recipient_id = str(default_recipient_id or "").strip() or None

    @classmethod
    def from_env(cls) -> "EnvWhatsAppRecipientResolver":
        return cls(
            recipients_by_student_id=_recipient_mapping_from_env(),
            default_recipient_id=os.getenv(
                "ACADEMIC_AGENT_DEFAULT_WHATSAPP_RECIPIENT_ID",
                "",
            ),
        )

    def recipient_for(self, dispatch: LeasedReminderDispatch) -> str | None:
        return (
            self.recipients_by_student_id.get(str(dispatch.student_id))
            or self.default_recipient_id
        )


class CompositeReminderRecipientResolver:
    """Prueba resolvers en orden y retorna el primer destinatario disponible."""

    def __init__(self, resolvers: tuple[ReminderRecipientResolver, ...]) -> None:
        self.resolvers = resolvers

    def recipient_for(self, dispatch: LeasedReminderDispatch) -> str | None:
        for resolver in self.resolvers:
            candidate = resolver.recipient_for(dispatch)
            if candidate:
                return candidate
        return None


class WhatsAppReminderSender:
    """Canal WhatsApp para despachar recordatorios académicos reales."""

    def __init__(
        self,
        *,
        channel_service: WhatsAppChannelService,
        recipient_resolver: ReminderRecipientResolver | None = None,
    ) -> None:
        self.channel_service = channel_service
        self.recipient_resolver = recipient_resolver or default_whatsapp_recipient_resolver()

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult:
        recipient_id = self.recipient_resolver.recipient_for(dispatch)
        if not recipient_id:
            return ReminderSendResult(
                sent=False,
                error_code="missing_whatsapp_recipient",
                detail=(
                    "No encontré destinatario WhatsApp para el estudiante. "
                    "Configura ACADEMIC_AGENT_WHATSAPP_RECIPIENTS o incluye "
                    "whatsapp_recipient_id en el payload del dispatch."
                ),
            )

        try:
            result = self.channel_service.send_outbound(
                ChannelOutboundMessage(
                    channel="whatsapp",
                    recipient_id=recipient_id,
                    kind="text",
                    text=render_whatsapp_reminder_message(dispatch),
                )
            )
        except WhatsAppClientError as exc:
            return ReminderSendResult(
                sent=False,
                error_code="whatsapp_send_error",
                detail=str(exc),
                retryable=_is_retryable_whatsapp_error(exc),
            )
        except Exception as exc:  # pragma: no cover - protege el worker operativo
            return ReminderSendResult(
                sent=False,
                error_code="whatsapp_send_unexpected_error",
                detail=str(exc),
                retryable=True,
            )

        if result.status != "sent":
            return ReminderSendResult(
                sent=False,
                error_code="whatsapp_send_failed",
                detail=result.detail,
                retryable=True,
            )

        return ReminderSendResult(
            sent=True,
            provider_message_id=result.provider_message_id,
        )


class ReminderDispatchRunner:
    """Leasing + envío + actualización durable de dispatches."""

    def __init__(
        self,
        repository: RemindersRepository,
        *,
        in_app_sender: ReminderChannelSender | None = None,
        email_sender: ReminderChannelSender | None = None,
        whatsapp_sender: ReminderChannelSender | None = None,
        max_attempts: int = _DEFAULT_DISPATCH_MAX_ATTEMPTS,
        retry_delay_minutes: int = _DEFAULT_RETRY_DELAY_MINUTES,
    ) -> None:
        self.repository = repository
        self.senders = {
            "in_app": in_app_sender or InAppReminderSender(),
            "email": email_sender or UnsupportedReminderSender("email"),
            "whatsapp": whatsapp_sender or UnsupportedReminderSender("whatsapp"),
        }
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay = timedelta(minutes=max(1, int(retry_delay_minutes)))

    def run_due_dispatches(
        self,
        *,
        as_of: datetime | None = None,
        limit: int = 50,
        channels: set[str] | None = None,
    ) -> RunDueRemindersResult:
        effective_as_of = as_of or datetime.now(timezone.utc)
        allowed_channels = {
            str(channel).strip()
            for channel in (channels or set())
            if str(channel).strip()
        } or None
        try:
            leased = self.repository.lease_due_dispatches(
                as_of=effective_as_of,
                limit=max(1, int(limit)),
                channels=allowed_channels,
            )
        except (RemindersRepositoryError, RepositoryConfigurationError) as exc:
            return RunDueRemindersResult(
                processed=False,
                error_code="reminder_dispatch_lease_error",
                detail=str(exc),
            )

        sent_count = 0
        failed_count = 0
        retryable_count = 0
        channel_counts = dict(Counter(dispatch.channel for dispatch in leased))
        dispatch_type_counts = dict(Counter(dispatch.dispatch_type for dispatch in leased))

        _logger.info(
            "reminder_dispatch_batch_start leased=%d as_of=%s channels=%s",
            len(leased),
            effective_as_of.isoformat(),
            ",".join(sorted(allowed_channels)) if allowed_channels else "all",
        )

        for dispatch in leased:
            sender = self.senders.get(dispatch.channel, UnsupportedReminderSender(dispatch.channel))
            result = sender.send(dispatch)
            try:
                if result.sent:
                    self.repository.mark_dispatch_sent(
                        dispatch_id=dispatch.id,
                        sent_at=effective_as_of,
                        provider_message_id=result.provider_message_id,
                    )
                    sent_count += 1
                    _logger.info(
                        "reminder_dispatch_sent dispatch_id=%s student_id=%s channel=%s"
                        " dispatch_type=%s provider_message_id=%s",
                        dispatch.id,
                        dispatch.student_id,
                        dispatch.channel,
                        dispatch.dispatch_type,
                        result.provider_message_id,
                    )
                else:
                    retry_at = self._retry_at_for_failure(
                        dispatch=dispatch,
                        result=result,
                        as_of=effective_as_of,
                    )
                    self.repository.mark_dispatch_failed(
                        dispatch_id=dispatch.id,
                        failure_reason=result.error_code or "reminder_dispatch_failed",
                        retry_at=retry_at,
                    )
                    if retry_at is None:
                        failed_count += 1
                        _logger.warning(
                            "reminder_dispatch_failed dispatch_id=%s student_id=%s channel=%s"
                            " dispatch_type=%s attempt=%s error_code=%s detail=%s",
                            dispatch.id,
                            dispatch.student_id,
                            dispatch.channel,
                            dispatch.dispatch_type,
                            dispatch.attempt_count,
                            result.error_code,
                            result.detail,
                        )
                    else:
                        retryable_count += 1
                        _logger.warning(
                            "reminder_dispatch_retryable dispatch_id=%s student_id=%s channel=%s"
                            " dispatch_type=%s attempt=%s error_code=%s retry_at=%s",
                            dispatch.id,
                            dispatch.student_id,
                            dispatch.channel,
                            dispatch.dispatch_type,
                            dispatch.attempt_count,
                            result.error_code,
                            retry_at.isoformat(),
                        )
            except (RemindersRepositoryError, RepositoryConfigurationError) as exc:
                _logger.error(
                    "reminder_dispatch_update_error dispatch_id=%s student_id=%s channel=%s error=%s",
                    dispatch.id,
                    dispatch.student_id,
                    dispatch.channel,
                    exc,
                )
                return RunDueRemindersResult(
                    processed=False,
                    leased_count=len(leased),
                    sent_count=sent_count,
                    failed_count=failed_count,
                    retryable_count=retryable_count,
                    channel_counts=channel_counts,
                    dispatch_type_counts=dispatch_type_counts,
                    error_code="reminder_dispatch_update_error",
                    detail=str(exc),
                )

        _logger.info(
            "reminder_dispatch_batch_done leased=%d sent=%d failed=%d retryable=%d",
            len(leased),
            sent_count,
            failed_count,
            retryable_count,
        )
        return RunDueRemindersResult(
            processed=True,
            leased_count=len(leased),
            sent_count=sent_count,
            failed_count=failed_count,
            retryable_count=retryable_count,
            channel_counts=channel_counts,
            dispatch_type_counts=dispatch_type_counts,
        )

    def _retry_at_for_failure(
        self,
        *,
        dispatch: LeasedReminderDispatch,
        result: ReminderSendResult,
        as_of: datetime,
    ) -> datetime | None:
        if not result.retryable:
            return None
        next_attempt_count = int(dispatch.attempt_count) + 1
        if next_attempt_count >= self.max_attempts:
            return None
        return as_of + self.retry_delay


def build_reminder_dispatch_runner() -> ReminderDispatchRunner:
    """Construye el runner durable de dispatches según el entorno."""

    state_repository = build_microsoft_graph_state_repository(database_url_from_env())
    oauth_client = build_microsoft_oauth_client_from_env(
        token_store=MicrosoftGraphStateTokenStore(state_repository)
    )
    return ReminderDispatchRunner(
        repository=build_reminders_repository(database_url_from_env()),
        email_sender=GraphEmailReminderSender(
            state_repository=state_repository,
            oauth_client=oauth_client,
        ),
        whatsapp_sender=_build_whatsapp_sender_from_env(),
        max_attempts=_dispatch_max_attempts_from_env(),
        retry_delay_minutes=_dispatch_retry_delay_minutes_from_env(),
    )


def default_whatsapp_recipient_resolver() -> ReminderRecipientResolver:
    """Resolver por defecto: payload primero, configuración operativa después."""

    return CompositeReminderRecipientResolver(
        (
            PayloadReminderRecipientResolver(),
            EnvWhatsAppRecipientResolver.from_env(),
        )
    )


def render_whatsapp_reminder_message(dispatch: LeasedReminderDispatch) -> str:
    """Renderiza un recordatorio académico breve para WhatsApp."""

    title = str(dispatch.payload.get("title") or "Sesion de estudio").strip()
    kind = str(dispatch.payload.get("kind") or "").strip()
    reminder_type = str(dispatch.payload.get("reminder_type") or "").strip()
    starts_at = _format_dispatch_datetime(
        dispatch.payload.get("starts_at"),
        fallback=dispatch.scheduled_for,
        timezone_name=str(dispatch.payload.get("timezone") or "America/Bogota"),
    )
    ends_at = _format_dispatch_datetime(
        dispatch.payload.get("ends_at"),
        fallback=dispatch.scheduled_for,
        timezone_name=str(dispatch.payload.get("timezone") or "America/Bogota"),
    )
    lead_minutes = _int_payload(dispatch.payload.get("lead_minutes"))

    if kind == "daily_agenda" or reminder_type == "daily_agenda":
        return _render_daily_agenda_message(dispatch)

    if kind == "activity_due" or reminder_type == "activity_due":
        lead_text = _lead_text(lead_minutes)
        return "\n".join(
            [
                "Recordatorio de actividad academica",
                f"Actividad: {title}",
                f"Vence: {starts_at}",
                f"Faltan {lead_text}.",
                "Prioriza cerrar esta entrega antes de abrir nuevas tareas.",
            ]
        )

    if kind == "activity_overdue" or reminder_type == "activity_overdue":
        return "\n".join(
            [
                "Seguimiento de actividad vencida",
                f"Actividad: {title}",
                f"Vencio: {starts_at}",
                "¿La completaste?",
                f"Responde \"complete {title}\" para marcarla como completada, o \"dejala pendiente\" para mantenerla.",
            ]
        )

    if reminder_type == "pre_session" or dispatch.dispatch_type.startswith("pre_session"):
        lead_text = _lead_text(lead_minutes)
        return "\n".join(
            [
                "Recordatorio de estudio",
                f"Sesion: {title}",
                f"Inicio: {starts_at}",
                f"Faltan {lead_text}.",
                "Prepara el material y protege este bloque.",
            ]
        )

    if reminder_type == "followup" or dispatch.dispatch_type.startswith("followup"):
        return "\n".join(
            [
                "Seguimiento de estudio",
                f"Sesion: {title}",
                f"Bloque: {starts_at} - {ends_at}",
                "Responde completada, parcial u omitida para actualizar tu avance.",
            ]
        )

    if reminder_type == "missed_session" or dispatch.dispatch_type.startswith("missed_session"):
        return "\n".join(
            [
                "Revision de sesion",
                f"Sesion: {title}",
                f"Terminaba: {ends_at}",
                "No tengo confirmacion de esta sesion.",
                "Responde no pude si necesitas replanificarla.",
            ]
        )

    return "\n".join(
        [
            "Recordatorio academico",
            f"Sesion: {title}",
            f"Fecha: {starts_at}",
        ]
    )


def _render_daily_agenda_message(dispatch: LeasedReminderDispatch) -> str:
    agenda_date = str(dispatch.payload.get("agenda_date") or "").strip()
    activities = [
        item
        for item in list(dispatch.payload.get("activities") or [])
        if isinstance(item, dict)
    ]
    lines = ["Agenda academica de hoy"]
    if agenda_date:
        lines.append(f"Fecha: {agenda_date}")
    if activities:
        lines.append("Tienes pendiente:")
        for item in activities[:6]:
            title = str(item.get("title") or "Actividad").strip()
            subject = str(item.get("subject_name") or "").strip()
            due_at = _format_dispatch_datetime(
                item.get("due_at"),
                fallback=dispatch.scheduled_for,
                timezone_name=str(dispatch.payload.get("timezone") or "America/Bogota"),
            )
            label = title if not subject or subject.lower() in title.lower() else f"{title} ({subject})"
            lines.append(f"- {label}: vence {due_at}")
        extra = len(activities) - 6
        if extra > 0:
            lines.append(f"- Y {extra} pendiente(s) mas.")
    else:
        lines.append("No tengo actividades academicas puntuales para hoy.")
    lines.append("Al terminar una, dime que la completaste para actualizar tu To Do y tus recordatorios.")
    return "\n".join(lines)


def _email_subject(dispatch: LeasedReminderDispatch) -> str:
    title = str(dispatch.payload.get("title") or "Sesion de estudio")
    kind = str(dispatch.payload.get("kind") or dispatch.payload.get("reminder_type") or "")
    if kind in {"daily_agenda", "activity_due", "activity_overdue"}:
        return f"Lara: {title}"
    return f"Recordatorio de estudio: {title}"


def _email_body(dispatch: LeasedReminderDispatch) -> str:
    title = str(dispatch.payload.get("title") or "Sesion de estudio")
    starts_at = str(dispatch.payload.get("starts_at") or dispatch.scheduled_for.isoformat())
    reminder_type = str(dispatch.payload.get("reminder_type") or dispatch.dispatch_type)
    return (
        "Academic Agent detecto un recordatorio pendiente.\n\n"
        f"Sesion: {title}\n"
        f"Programada para: {starts_at}\n"
        f"Tipo de reminder: {reminder_type}\n"
        f"Canal: {dispatch.channel}\n"
        f"Dispatch ID: {dispatch.id}\n"
    )


def _build_whatsapp_sender_from_env() -> ReminderChannelSender:
    try:
        return WhatsAppReminderSender(
            channel_service=WhatsAppChannelService(WhatsAppCloudClient.from_env()),
            recipient_resolver=default_whatsapp_recipient_resolver(),
        )
    except WhatsAppClientError as exc:
        return UnsupportedReminderSender(
            "whatsapp",
            error_code="whatsapp_config_error",
            detail=str(exc),
        )


def _recipient_mapping_from_env() -> dict[str, str]:
    raw_value = os.getenv("ACADEMIC_AGENT_WHATSAPP_RECIPIENTS", "").strip()
    if not raw_value:
        return {}
    if raw_value.startswith("{"):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, Mapping):
            return {}
        return {
            str(key).strip(): str(value).strip()
            for key, value in parsed.items()
            if str(key).strip() and str(value).strip()
        }

    mapping: dict[str, str] = {}
    for item in raw_value.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip()
        if key and value:
            mapping[key] = value
    return mapping


def _dispatch_max_attempts_from_env() -> int:
    raw_value = os.getenv("ACADEMIC_AGENT_REMINDER_DISPATCH_MAX_ATTEMPTS", "").strip()
    if not raw_value:
        return _DEFAULT_DISPATCH_MAX_ATTEMPTS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return _DEFAULT_DISPATCH_MAX_ATTEMPTS


def _dispatch_retry_delay_minutes_from_env() -> int:
    raw_value = os.getenv("ACADEMIC_AGENT_REMINDER_RETRY_DELAY_MINUTES", "").strip()
    if not raw_value:
        return _DEFAULT_RETRY_DELAY_MINUTES
    try:
        return max(1, int(raw_value))
    except ValueError:
        return _DEFAULT_RETRY_DELAY_MINUTES


def _format_dispatch_datetime(
    value: object,
    *,
    fallback: datetime,
    timezone_name: str,
) -> str:
    parsed = _parse_datetime(value) or fallback
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = timezone.utc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    else:
        parsed = parsed.astimezone(zone)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _int_payload(value: object, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _lead_text(minutes: int) -> str:
    if minutes == 1:
        return "1 minuto"
    if minutes and minutes % 60 == 0:
        hours = minutes // 60
        return "1 hora" if hours == 1 else f"{hours} horas"
    return f"{minutes} minutos"


def _is_retryable_whatsapp_error(exc: WhatsAppClientError) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        return True
    return status_code == 408 or status_code == 429 or status_code >= 500
