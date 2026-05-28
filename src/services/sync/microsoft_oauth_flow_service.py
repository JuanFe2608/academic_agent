"""Flujo de aplicacion para OAuth Microsoft bloqueante en onboarding."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from bootstrap.settings import database_url_from_env
from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftTokenRecord,
    build_microsoft_oauth_client_from_env,
)
from project_env import load_project_env
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    MicrosoftGraphStateRepository,
    MicrosoftOAuthPendingStateRecord,
    build_microsoft_graph_state_repository,
)

_REQUIRE_MICROSOFT_OAUTH_FLAG = "ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH"
_TRUTHY_VALUES = {"1", "true", "yes", "on", "required", "obligatorio"}
_DEFAULT_PENDING_TTL_MINUTES = 15


@dataclass(frozen=True)
class MicrosoftOAuthFlowStartResult:
    """Resultado de iniciar o resolver el paso OAuth."""

    ok: bool
    already_authorized: bool = False
    authorization_url: str | None = None
    state_token: str | None = None
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MicrosoftOAuthCallbackResult:
    """Resultado de procesar el callback OAuth externo al grafo."""

    ok: bool
    student_id: int | None = None
    error_code: str | None = None
    detail: str | None = None


class MicrosoftOAuthFlowService:
    """Coordina state aleatorio, persistencia pendiente y callback OAuth."""

    def __init__(
        self,
        *,
        state_repository: MicrosoftGraphStateRepository,
        auth_client: MicrosoftOAuthClient,
        pending_ttl_minutes: int = _DEFAULT_PENDING_TTL_MINUTES,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.state_repository = state_repository
        self.auth_client = auth_client
        self.pending_ttl_minutes = max(1, int(pending_ttl_minutes))
        self.now_factory = now_factory or (lambda: datetime.now(timezone.utc))

    def has_connection(self, *, student_id: int) -> bool:
        """Indica si ya existe una conexion OAuth persistida para el estudiante."""

        try:
            return self.auth_client.get_stored_token(student_id=int(student_id)) is not None
        except Exception:
            return False

    def start_authorization(
        self,
        *,
        student_id: int,
        institutional_email: str | None = None,
        force: bool = False,
    ) -> MicrosoftOAuthFlowStartResult:
        """Genera un state no deterministico, lo persiste y devuelve la URL.

        force=True omite la verificación de conexión existente — útil para reconectar
        una cuenta Microsoft cuya autenticación ha expirado.
        """

        student_id = int(student_id)
        if not force and self.has_connection(student_id=student_id):
            return MicrosoftOAuthFlowStartResult(ok=True, already_authorized=True)

        state_token = _generate_state_token(student_id)
        authorization_request = self.auth_client.build_authorization_request(
            student_id=student_id,
            state_token=state_token,
        )
        if not authorization_request.ready:
            return MicrosoftOAuthFlowStartResult(
                ok=False,
                error_code=authorization_request.error_code or "microsoft_oauth_not_ready",
                detail=authorization_request.detail,
            )

        expires_at = self.now_factory() + timedelta(minutes=self.pending_ttl_minutes)
        stored = self.state_repository.upsert_oauth_pending_state(
            record=MicrosoftOAuthPendingStateRecord(
                state_token=state_token,
                student_id=student_id,
                institutional_email=_normalize_email(institutional_email),
                expires_at=expires_at,
                scopes=tuple(authorization_request.scopes),
                authorization_url=authorization_request.authorization_url,
                status="pending",
            )
        )
        return MicrosoftOAuthFlowStartResult(
            ok=True,
            authorization_url=stored.authorization_url,
            state_token=stored.state_token,
            expires_at=stored.expires_at,
            scopes=stored.scopes,
        )

    def complete_authorization(
        self,
        *,
        state_token: str,
        authorization_code: str,
    ) -> MicrosoftOAuthCallbackResult:
        """Valida el state recibido y persiste la conexion Microsoft."""

        normalized_state = str(state_token or "").strip()
        if not normalized_state:
            return MicrosoftOAuthCallbackResult(
                ok=False,
                error_code="missing_oauth_state",
                detail="El callback no incluyo state OAuth.",
            )

        pending = self.state_repository.get_oauth_pending_state(
            state_token=normalized_state
        )
        if pending is None:
            return MicrosoftOAuthCallbackResult(
                ok=False,
                error_code="oauth_state_not_found",
                detail="No encontre un state OAuth pendiente para este callback.",
            )
        if pending.status == "completed":
            return MicrosoftOAuthCallbackResult(
                ok=True,
                student_id=pending.student_id,
            )
        if pending.status != "pending":
            return MicrosoftOAuthCallbackResult(
                ok=False,
                student_id=pending.student_id,
                error_code="oauth_state_not_pending",
                detail="El state OAuth ya no esta pendiente para este callback.",
            )

        if _ensure_aware(pending.expires_at) <= self.now_factory():
            self.state_repository.mark_oauth_pending_state_failed(
                state_token=normalized_state,
                last_error="oauth_state_expired",
            )
            return MicrosoftOAuthCallbackResult(
                ok=False,
                student_id=pending.student_id,
                error_code="oauth_state_expired",
                detail="El enlace de autorizacion ya vencio.",
            )

        exchange = self.auth_client.exchange_authorization_code_without_persisting(
            student_id=pending.student_id,
            authorization_code=authorization_code,
            scopes=pending.scopes,
        )
        if not exchange.ok:
            self.state_repository.mark_oauth_pending_state_failed(
                state_token=normalized_state,
                last_error=exchange.error_code or "microsoft_oauth_exchange_failed",
            )
            return MicrosoftOAuthCallbackResult(
                ok=False,
                student_id=pending.student_id,
                error_code=exchange.error_code or "microsoft_oauth_exchange_failed",
                detail=exchange.detail,
            )

        identity_error = self._validate_authorized_microsoft_identity(
            pending=pending,
            token=exchange.token,
        )
        if identity_error is not None:
            self.state_repository.mark_oauth_pending_state_failed(
                state_token=normalized_state,
                last_error=identity_error.error_code or "microsoft_oauth_identity_error",
            )
            return identity_error

        try:
            if exchange.token is not None:
                self.auth_client.save_token_record(token=exchange.token)
            self.state_repository.mark_oauth_pending_state_completed(
                state_token=normalized_state
            )
        except Exception:
            if exchange.token is not None:
                self.state_repository.delete_connection(student_id=pending.student_id)
            raise
        return MicrosoftOAuthCallbackResult(
            ok=True,
            student_id=pending.student_id,
        )

    def _validate_authorized_microsoft_identity(
        self,
        *,
        pending: MicrosoftOAuthPendingStateRecord,
        token: MicrosoftTokenRecord | None,
    ) -> MicrosoftOAuthCallbackResult | None:
        if token is None:
            return None

        account_identifiers = _account_identifiers_from_token(token)
        expected_email = _normalize_email(pending.institutional_email)
        if expected_email and account_identifiers and expected_email not in account_identifiers:
            return MicrosoftOAuthCallbackResult(
                ok=False,
                student_id=pending.student_id,
                error_code="microsoft_account_mismatch",
                detail=(
                    "La cuenta Microsoft autorizada no coincide con el correo que "
                    "escribiste en el chat. Vuelve a WhatsApp y usa la cuenta correcta "
                    "o corrige el correo."
                ),
            )

        duplicate = self.state_repository.find_connection_by_microsoft_identity(
            microsoft_user_id=token.microsoft_user_id,
            account_identifiers=tuple(account_identifiers),
            exclude_student_id=pending.student_id,
        )
        if duplicate is not None:
            return MicrosoftOAuthCallbackResult(
                ok=False,
                student_id=pending.student_id,
                error_code="microsoft_account_already_connected",
                detail=(
                    "Esa cuenta Microsoft ya esta conectada a otra cuenta de estudiante. "
                    "Vuelve a WhatsApp y escribe otro correo."
                ),
            )
        return None


def is_microsoft_oauth_required() -> bool:
    """Lee el flag operativo que vuelve bloqueante el OAuth Microsoft."""

    raw_value = os.getenv(_REQUIRE_MICROSOFT_OAUTH_FLAG)
    if raw_value is None:
        load_project_env()
        raw_value = os.getenv(_REQUIRE_MICROSOFT_OAUTH_FLAG)
    return str(raw_value or "").strip().lower() in _TRUTHY_VALUES


def build_microsoft_oauth_flow_service(
    *,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
) -> MicrosoftOAuthFlowService:
    """Construye el servicio OAuth con repositorio durable por defecto."""

    effective_repository = state_repository
    if effective_repository is None:
        if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_MICROSOFT_REPO", "").strip() == "1":
            effective_repository = InMemoryMicrosoftGraphStateRepository()
        else:
            effective_repository = build_microsoft_graph_state_repository(
                database_url_from_env()
            )
    effective_client = auth_client or build_microsoft_oauth_client_from_env(
        token_store=MicrosoftGraphStateTokenStore(effective_repository)
    )
    return MicrosoftOAuthFlowService(
        state_repository=effective_repository,
        auth_client=effective_client,
    )


def _generate_state_token(student_id: int) -> str:
    return f"student:{int(student_id)}:microsoft:{secrets.token_urlsafe(32)}"


def _normalize_email(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _account_identifiers_from_token(token: MicrosoftTokenRecord) -> set[str]:
    identifiers: set[str] = set()
    for value in (token.email, token.user_principal_name):
        normalized = _normalize_email(value)
        if normalized:
            identifiers.add(normalized)
    return identifiers


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


__all__ = [
    "MicrosoftOAuthCallbackResult",
    "MicrosoftOAuthFlowService",
    "MicrosoftOAuthFlowStartResult",
    "build_microsoft_oauth_flow_service",
    "is_microsoft_oauth_required",
]
