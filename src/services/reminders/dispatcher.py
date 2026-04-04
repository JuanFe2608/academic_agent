"""Worker idempotente para despachar reminders vencidos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    build_microsoft_oauth_client_from_env,
)
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


@dataclass(frozen=True)
class ReminderSendResult:
    """Resultado de intentar enviar un despacho a un canal."""

    sent: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class RunDueRemindersResult:
    """Resumen operativo del worker de reminders."""

    processed: bool
    leased_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    error_code: str | None = None
    detail: str | None = None


class ReminderChannelSender(Protocol):
    """Contrato mínimo para adaptadores de canal."""

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult: ...


class InAppReminderSender:
    """Canal local mínimo: marca el dispatch como enviado."""

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult:
        return ReminderSendResult(
            sent=True,
            provider_message_id=f"in_app:{dispatch.id}",
        )


class UnsupportedReminderSender:
    """Fallback explícito para canales no implementados todavía."""

    def __init__(self, channel: str) -> None:
        self.channel = channel

    def send(self, dispatch: LeasedReminderDispatch) -> ReminderSendResult:
        return ReminderSendResult(
            sent=False,
            error_code=f"unsupported_channel:{self.channel}",
            detail=(
                "El canal aun no tiene adaptador de entrega. "
                "Debes conectar un sender externo para usarlo."
            ),
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


class ReminderDispatchRunner:
    """Leasing + envío + actualización durable de dispatches."""

    def __init__(
        self,
        repository: RemindersRepository,
        *,
        in_app_sender: ReminderChannelSender | None = None,
        email_sender: ReminderChannelSender | None = None,
        whatsapp_sender: ReminderChannelSender | None = None,
    ) -> None:
        self.repository = repository
        self.senders = {
            "in_app": in_app_sender or InAppReminderSender(),
            "email": email_sender or UnsupportedReminderSender("email"),
            "whatsapp": whatsapp_sender or UnsupportedReminderSender("whatsapp"),
        }

    def run_due_dispatches(
        self,
        *,
        as_of: datetime | None = None,
        limit: int = 50,
    ) -> RunDueRemindersResult:
        effective_as_of = as_of or datetime.now(timezone.utc)
        try:
            leased = self.repository.lease_due_dispatches(
                as_of=effective_as_of,
                limit=max(1, int(limit)),
            )
        except (RemindersRepositoryError, RepositoryConfigurationError) as exc:
            return RunDueRemindersResult(
                processed=False,
                error_code="reminder_dispatch_lease_error",
                detail=str(exc),
            )

        sent_count = 0
        failed_count = 0
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
                else:
                    self.repository.mark_dispatch_failed(
                        dispatch_id=dispatch.id,
                        failure_reason=result.error_code or "reminder_dispatch_failed",
                    )
                    failed_count += 1
            except (RemindersRepositoryError, RepositoryConfigurationError) as exc:
                return RunDueRemindersResult(
                    processed=False,
                    leased_count=len(leased),
                    sent_count=sent_count,
                    failed_count=failed_count,
                    error_code="reminder_dispatch_update_error",
                    detail=str(exc),
                )

        return RunDueRemindersResult(
            processed=True,
            leased_count=len(leased),
            sent_count=sent_count,
            failed_count=failed_count,
        )


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
    )


def _email_subject(dispatch: LeasedReminderDispatch) -> str:
    title = str(dispatch.payload.get("title") or "Sesion de estudio")
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
