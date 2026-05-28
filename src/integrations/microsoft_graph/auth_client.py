"""OAuth real para Microsoft Graph con persistencia desacoplada."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from repositories.microsoft_graph.state_repository import (
    MicrosoftGraphConnectionRecord,
    MicrosoftGraphStateRepository,
)
from project_env import load_project_env

_PERMANENT_TOKEN_FAILURE_CODES = frozenset({
    "invalid_grant",
    "interaction_required",
    "unauthorized_client",
    "consent_required",
})

DEFAULT_MICROSOFT_SCOPES = (
    "offline_access",
    "openid",
    "profile",
    "User.Read",
    "Calendars.ReadWrite",
    "Tasks.ReadWrite",
    "Mail.Send",
)
_DEFAULT_AUTHORITY_BASE_URL = "https://login.microsoftonline.com"
_DEFAULT_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_PROFILE_SELECT_FIELDS = "id,userPrincipalName,mail,displayName"


@dataclass(frozen=True)
class MicrosoftOAuthConfig:
    """Configuración mínima para OAuth con Microsoft Graph."""

    client_id: str = ""
    tenant_id: str = "common"
    client_secret: str | None = None
    redirect_uri: str = ""
    scopes: tuple[str, ...] = DEFAULT_MICROSOFT_SCOPES
    authority_base_url: str = _DEFAULT_AUTHORITY_BASE_URL
    graph_base_url: str = _DEFAULT_GRAPH_BASE_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.redirect_uri and self.tenant_id)

    @property
    def authority(self) -> str:
        base = self.authority_base_url.rstrip("/")
        tenant = self.tenant_id.strip() or "common"
        return f"{base}/{tenant}"

    @property
    def token_endpoint(self) -> str:
        return f"{self.authority}/oauth2/v2.0/token"

    @property
    def profile_endpoint(self) -> str:
        base = self.graph_base_url.rstrip("/")
        return f"{base}/me?$select={_PROFILE_SELECT_FIELDS}"


@dataclass(frozen=True)
class MicrosoftAuthorizationRequest:
    """Resultado de preparar una URL de autorización OAuth."""

    ready: bool
    authorization_url: str | None = None
    state: str | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MicrosoftTokenRecord:
    """Token OAuth almacenado para un estudiante."""

    student_id: int
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: tuple[str, ...]
    token_type: str = "Bearer"
    tenant_id: str = "common"
    microsoft_user_id: str | None = None
    user_principal_name: str | None = None
    email: str | None = None
    display_name: str | None = None
    calendar_id: str | None = None
    todo_task_list_id: str | None = None
    auth_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MicrosoftTokenOperationResult:
    """Resultado de operaciones de intercambio/refresh de tokens."""

    ok: bool
    token: MicrosoftTokenRecord | None = None
    error_code: str | None = None
    detail: str | None = None


class MicrosoftTokenStore(Protocol):
    """Contrato para persistencia de tokens Microsoft."""

    def get_token(self, *, student_id: int) -> MicrosoftTokenRecord | None: ...

    def save_token(self, *, token: MicrosoftTokenRecord) -> None: ...

    def delete_token(self, *, student_id: int) -> None: ...


class MicrosoftOAuthTransport(Protocol):
    """Transporte HTTP inyectable para OAuth y perfil base."""

    def post_form(self, *, url: str, form_data: dict[str, str]) -> dict[str, Any]: ...

    def get_json(self, *, url: str, access_token: str) -> dict[str, Any]: ...


class MicrosoftOAuthTransportError(Exception):
    """Falla de transporte o de respuesta del endpoint OAuth."""

    def __init__(self, *, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.error_code = error_code
        self.detail = detail


class InMemoryMicrosoftTokenStore:
    """Store simple para pruebas y desarrollo local."""

    def __init__(self) -> None:
        self._tokens: dict[int, MicrosoftTokenRecord] = {}

    def get_token(self, *, student_id: int) -> MicrosoftTokenRecord | None:
        return self._tokens.get(student_id)

    def save_token(self, *, token: MicrosoftTokenRecord) -> None:
        self._tokens[token.student_id] = token

    def delete_token(self, *, student_id: int) -> None:
        self._tokens.pop(student_id, None)


class MicrosoftGraphStateTokenStore:
    """Adapter entre MicrosoftOAuthClient y el repositorio durable PostgreSQL."""

    def __init__(self, repository: MicrosoftGraphStateRepository) -> None:
        self.repository = repository

    def get_token(self, *, student_id: int) -> MicrosoftTokenRecord | None:
        record = self.repository.get_connection(student_id=student_id)
        if record is None:
            return None
        return _token_from_connection(record)

    def save_token(self, *, token: MicrosoftTokenRecord) -> None:
        existing = self.repository.get_connection(student_id=token.student_id)
        merged_metadata = dict(existing.auth_metadata) if existing else {}
        merged_metadata.update(dict(token.auth_metadata))
        self.repository.upsert_connection(
            record=MicrosoftGraphConnectionRecord(
                id=existing.id if existing else None,
                student_id=token.student_id,
                tenant_id=token.tenant_id or (existing.tenant_id if existing else "common"),
                access_token=token.access_token,
                refresh_token=token.refresh_token or (existing.refresh_token if existing else None),
                expires_at=token.expires_at,
                scopes=tuple(token.scopes),
                token_type=token.token_type or (existing.token_type if existing else "Bearer"),
                calendar_id=token.calendar_id if token.calendar_id is not None else (existing.calendar_id if existing else None),
                todo_task_list_id=(
                    token.todo_task_list_id
                    if token.todo_task_list_id is not None
                    else (existing.todo_task_list_id if existing else None)
                ),
                microsoft_user_id=(
                    token.microsoft_user_id
                    if token.microsoft_user_id is not None
                    else (existing.microsoft_user_id if existing else None)
                ),
                user_principal_name=(
                    token.user_principal_name
                    if token.user_principal_name is not None
                    else (existing.user_principal_name if existing else None)
                ),
                email=token.email if token.email is not None else (existing.email if existing else None),
                display_name=(
                    token.display_name
                    if token.display_name is not None
                    else (existing.display_name if existing else None)
                ),
                auth_metadata=merged_metadata,
            )
        )

    def delete_token(self, *, student_id: int) -> None:
        self.repository.delete_connection(student_id=student_id)


class UrllibMicrosoftOAuthTransport:
    """Transporte OAuth basado en urllib para no agregar dependencias."""

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def post_form(self, *, url: str, form_data: dict[str, str]) -> dict[str, Any]:
        encoded = urlencode(form_data).encode("utf-8")
        request = Request(
            url=url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._load_json(request)

    def get_json(self, *, url: str, access_token: str) -> dict[str, Any]:
        request = Request(
            url=url,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        return self._load_json(request)

    def _load_json(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:  # pragma: no cover
            raise _transport_error_from_http_error(exc) from exc
        except URLError as exc:  # pragma: no cover
            raise MicrosoftOAuthTransportError(
                error_code="microsoft_oauth_network_error",
                detail=str(exc.reason or exc),
            ) from exc

        if not payload.strip():
            return {}
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise MicrosoftOAuthTransportError(
                error_code="microsoft_oauth_invalid_json",
                detail=f"Respuesta no es JSON válido: {payload[:200]}",
            ) from exc
        if not isinstance(data, dict):
            raise MicrosoftOAuthTransportError(
                error_code="microsoft_oauth_invalid_payload",
                detail="Microsoft devolvió un payload JSON inesperado.",
            )
        return data


class MicrosoftOAuthClient:
    """Cliente de alto nivel para OAuth + refresh + perfil base."""

    def __init__(
        self,
        *,
        config: MicrosoftOAuthConfig,
        token_store: MicrosoftTokenStore | None = None,
        transport: MicrosoftOAuthTransport | None = None,
        refresh_skew_seconds: int = 120,
    ) -> None:
        self.config = config
        self.token_store = token_store or InMemoryMicrosoftTokenStore()
        self.transport = transport or UrllibMicrosoftOAuthTransport()
        self.refresh_skew_seconds = max(0, int(refresh_skew_seconds))

    def build_authorization_request(
        self,
        *,
        student_id: int,
        state_token: str | None = None,
        scopes: tuple[str, ...] | None = None,
        redirect_uri: str | None = None,
    ) -> MicrosoftAuthorizationRequest:
        if not self.config.is_configured:
            return MicrosoftAuthorizationRequest(
                ready=False,
                error_code="microsoft_oauth_not_configured",
                detail=(
                    "Faltan MICROSOFT_CLIENT_ID/MS_CLIENT_ID, "
                    "MICROSOFT_TENANT_ID/MS_TENANT_ID o "
                    "MICROSOFT_REDIRECT_URI/MS_REDIRECT_URI en el entorno."
                ),
            )

        effective_scopes = tuple(scopes or self.config.scopes)
        effective_state = state_token or f"student:{student_id}:microsoft"
        effective_redirect_uri = redirect_uri or self.config.redirect_uri
        params = urlencode(
            {
                "client_id": self.config.client_id,
                "response_type": "code",
                "redirect_uri": effective_redirect_uri,
                "response_mode": "query",
                "scope": " ".join(effective_scopes),
                "state": effective_state,
            }
        )
        url = f"{self.config.authority}/oauth2/v2.0/authorize?{params}"
        return MicrosoftAuthorizationRequest(
            ready=True,
            authorization_url=url,
            state=effective_state,
            scopes=effective_scopes,
        )

    def get_stored_token(self, *, student_id: int) -> MicrosoftTokenRecord | None:
        return self.token_store.get_token(student_id=student_id)

    def get_valid_access_token(
        self,
        *,
        student_id: int,
    ) -> MicrosoftTokenOperationResult:
        stored = self.token_store.get_token(student_id=student_id)
        if stored is None:
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code="microsoft_token_not_found",
                detail="No encontré una conexión Microsoft almacenada para este estudiante.",
            )
        if _token_is_usable(
            stored,
            now=datetime.now(timezone.utc),
            refresh_skew_seconds=self.refresh_skew_seconds,
        ):
            return MicrosoftTokenOperationResult(ok=True, token=stored)
        return self.refresh_access_token(student_id=student_id)

    def save_manual_token(
        self,
        *,
        student_id: int,
        access_token: str,
        refresh_token: str | None = None,
        expires_in_seconds: int | None = None,
        scopes: tuple[str, ...] | None = None,
        token_type: str = "Bearer",
        tenant_id: str | None = None,
        microsoft_user_id: str | None = None,
        user_principal_name: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        calendar_id: str | None = None,
        todo_task_list_id: str | None = None,
        auth_metadata: dict[str, object] | None = None,
    ) -> MicrosoftTokenRecord:
        expires_at = None
        if expires_in_seconds is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        record = MicrosoftTokenRecord(
            student_id=student_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=tuple(scopes or self.config.scopes),
            token_type=token_type or "Bearer",
            tenant_id=(tenant_id or self.config.tenant_id or "common"),
            microsoft_user_id=microsoft_user_id,
            user_principal_name=user_principal_name,
            email=email,
            display_name=display_name,
            calendar_id=calendar_id,
            todo_task_list_id=todo_task_list_id,
            auth_metadata=dict(auth_metadata or {}),
        )
        self.token_store.save_token(token=record)
        return record

    def exchange_authorization_code(
        self,
        *,
        student_id: int,
        authorization_code: str,
        scopes: tuple[str, ...] | None = None,
    ) -> MicrosoftTokenOperationResult:
        result = self.exchange_authorization_code_without_persisting(
            student_id=student_id,
            authorization_code=authorization_code,
            scopes=scopes,
        )
        if result.ok and result.token is not None:
            self.save_token_record(token=result.token)
        return result

    def exchange_authorization_code_without_persisting(
        self,
        *,
        student_id: int,
        authorization_code: str,
        scopes: tuple[str, ...] | None = None,
    ) -> MicrosoftTokenOperationResult:
        """Intercambia un code OAuth y construye el token sin persistirlo."""

        if not self.config.is_configured:
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code="microsoft_oauth_not_configured",
                detail="La configuración de Microsoft OAuth no está completa.",
            )
        if not str(authorization_code).strip():
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code="missing_authorization_code",
                detail="Debes suministrar un authorization_code no vacío.",
            )

        effective_scopes = tuple(scopes or self.config.scopes)
        try:
            token_payload = self.transport.post_form(
                url=self.config.token_endpoint,
                form_data=_token_form_payload(
                    client_id=self.config.client_id,
                    client_secret=self.config.client_secret,
                    redirect_uri=self.config.redirect_uri,
                    scopes=effective_scopes,
                    grant_type="authorization_code",
                    authorization_code=authorization_code.strip(),
                ),
            )
        except MicrosoftOAuthTransportError as exc:
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code=exc.error_code,
                detail=exc.detail,
            )

        return self._token_from_payload(
            student_id=student_id,
            token_payload=token_payload,
            fallback_scopes=effective_scopes,
            include_profile=True,
        )

    def save_token_record(self, *, token: MicrosoftTokenRecord) -> None:
        """Persiste un token ya validado en el store configurado."""

        self.token_store.save_token(token=token)

    def refresh_access_token(
        self,
        *,
        student_id: int,
    ) -> MicrosoftTokenOperationResult:
        stored = self.token_store.get_token(student_id=student_id)
        if stored is None:
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code="microsoft_token_not_found",
                detail="No encontré un token Microsoft almacenado para este estudiante.",
            )
        if _token_is_usable(
            stored,
            now=datetime.now(timezone.utc),
            refresh_skew_seconds=self.refresh_skew_seconds,
        ):
            return MicrosoftTokenOperationResult(ok=True, token=stored)
        if not stored.refresh_token:
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code="missing_refresh_token",
                detail="El token almacenado no tiene refresh_token.",
            )

        try:
            token_payload = self.transport.post_form(
                url=self.config.token_endpoint,
                form_data=_token_form_payload(
                    client_id=self.config.client_id,
                    client_secret=self.config.client_secret,
                    redirect_uri=self.config.redirect_uri,
                    scopes=stored.scopes or self.config.scopes,
                    grant_type="refresh_token",
                    refresh_token=stored.refresh_token,
                ),
            )
        except MicrosoftOAuthTransportError as exc:
            if exc.error_code in _PERMANENT_TOKEN_FAILURE_CODES:
                # Refresh token is permanently invalid — clear auth credentials so
                # subsequent calls return missing_refresh_token immediately (no HTTP
                # retries against Microsoft) while preserving calendar_id / todo IDs.
                self._clear_stored_auth_credentials(student_id=student_id, stored=stored)
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code=exc.error_code,
                detail=exc.detail,
            )

        refreshed = self._token_from_payload(
            student_id=student_id,
            token_payload=token_payload,
            fallback_scopes=stored.scopes or self.config.scopes,
            existing_token=stored,
            include_profile=False,
        )
        if not refreshed.ok or refreshed.token is None:
            return refreshed
        self.save_token_record(token=refreshed.token)
        return MicrosoftTokenOperationResult(ok=True, token=refreshed.token)

    def _token_from_payload(
        self,
        *,
        student_id: int,
        token_payload: dict[str, Any],
        fallback_scopes: tuple[str, ...],
        existing_token: MicrosoftTokenRecord | None = None,
        include_profile: bool,
    ) -> MicrosoftTokenOperationResult:
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            return MicrosoftTokenOperationResult(
                ok=False,
                error_code=str(token_payload.get("error") or "microsoft_oauth_invalid_response"),
                detail=str(
                    token_payload.get("error_description")
                    or "Microsoft no devolvió access_token."
                ),
            )

        refresh_token = str(token_payload.get("refresh_token") or "").strip() or None
        if refresh_token is None and existing_token is not None:
            refresh_token = existing_token.refresh_token

        profile_data: dict[str, Any] = {}
        profile_error: str | None = None
        if include_profile:
            try:
                profile_data = self.transport.get_json(
                    url=self.config.profile_endpoint,
                    access_token=access_token,
                )
            except MicrosoftOAuthTransportError as exc:
                profile_error = f"{exc.error_code}: {exc.detail}"

        token = MicrosoftTokenRecord(
            student_id=student_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=_expires_at_from_payload(token_payload),
            scopes=_scopes_from_payload(token_payload, fallback_scopes),
            token_type=str(token_payload.get("token_type") or "Bearer"),
            tenant_id=(existing_token.tenant_id if existing_token else self.config.tenant_id or "common"),
            microsoft_user_id=_optional_str(profile_data.get("id")) or (existing_token.microsoft_user_id if existing_token else None),
            user_principal_name=(
                _optional_str(profile_data.get("userPrincipalName"))
                or (existing_token.user_principal_name if existing_token else None)
            ),
            email=_optional_str(profile_data.get("mail")) or (existing_token.email if existing_token else None),
            display_name=_optional_str(profile_data.get("displayName")) or (existing_token.display_name if existing_token else None),
            calendar_id=existing_token.calendar_id if existing_token else None,
            todo_task_list_id=existing_token.todo_task_list_id if existing_token else None,
            auth_metadata=_build_auth_metadata(
                token_payload=token_payload,
                profile_error=profile_error,
                existing_metadata=existing_token.auth_metadata if existing_token else None,
            ),
        )
        return MicrosoftTokenOperationResult(ok=True, token=token)


    def _clear_stored_auth_credentials(
        self,
        *,
        student_id: int,
        stored: MicrosoftTokenRecord,
    ) -> None:
        """Clears auth tokens while preserving calendar/todo IDs for after re-auth."""

        cleared = MicrosoftTokenRecord(
            student_id=stored.student_id,
            access_token="",
            refresh_token=None,
            expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            scopes=stored.scopes,
            token_type=stored.token_type,
            tenant_id=stored.tenant_id,
            microsoft_user_id=stored.microsoft_user_id,
            user_principal_name=stored.user_principal_name,
            email=stored.email,
            display_name=stored.display_name,
            calendar_id=stored.calendar_id,
            todo_task_list_id=stored.todo_task_list_id,
            auth_metadata={
                **stored.auth_metadata,
                "invalidated_at": datetime.now(timezone.utc).isoformat(),
                "invalidation_reason": "permanent_refresh_failure",
            },
        )
        try:
            self.token_store.save_token(token=cleared)
        except Exception:
            pass


def build_microsoft_oauth_client_from_env(
    *,
    token_store: MicrosoftTokenStore | None = None,
    transport: MicrosoftOAuthTransport | None = None,
) -> MicrosoftOAuthClient:
    """Construye el cliente OAuth desde variables de entorno."""

    client_id = _env_value("MICROSOFT_CLIENT_ID", "MS_CLIENT_ID")
    tenant_id = _env_value("MICROSOFT_TENANT_ID", "MS_TENANT_ID")
    client_secret = _env_value("MICROSOFT_CLIENT_SECRET", "MS_CLIENT_SECRET")
    redirect_uri = _env_value("MICROSOFT_REDIRECT_URI", "MS_REDIRECT_URI")
    raw_scopes = _env_value("MICROSOFT_GRAPH_SCOPES", "MS_GRAPH_SCOPES")
    authority_base_url = _env_value(
        "MICROSOFT_AUTHORITY_BASE_URL",
        "MS_AUTHORITY_BASE_URL",
    )
    graph_base_url = _env_value(
        "MICROSOFT_GRAPH_BASE_URL",
        "MS_GRAPH_BASE_URL",
    )

    if not (
        client_id
        and tenant_id
        and client_secret
        and redirect_uri
        and raw_scopes
        and authority_base_url
        and graph_base_url
    ):
        load_project_env()
        client_id = client_id or _env_value("MICROSOFT_CLIENT_ID", "MS_CLIENT_ID")
        tenant_id = tenant_id or _env_value("MICROSOFT_TENANT_ID", "MS_TENANT_ID")
        client_secret = client_secret or _env_value(
            "MICROSOFT_CLIENT_SECRET",
            "MS_CLIENT_SECRET",
        )
        redirect_uri = redirect_uri or _env_value(
            "MICROSOFT_REDIRECT_URI",
            "MS_REDIRECT_URI",
        )
        raw_scopes = raw_scopes or _env_value(
            "MICROSOFT_GRAPH_SCOPES",
            "MS_GRAPH_SCOPES",
        )
        authority_base_url = authority_base_url or _env_value(
            "MICROSOFT_AUTHORITY_BASE_URL",
            "MS_AUTHORITY_BASE_URL",
        )
        graph_base_url = graph_base_url or _env_value(
            "MICROSOFT_GRAPH_BASE_URL",
            "MS_GRAPH_BASE_URL",
        )

    scopes = _parse_scopes(raw_scopes) if raw_scopes else DEFAULT_MICROSOFT_SCOPES
    config = MicrosoftOAuthConfig(
        client_id=client_id,
        tenant_id=tenant_id or "common",
        client_secret=client_secret or None,
        redirect_uri=redirect_uri,
        scopes=scopes,
        authority_base_url=authority_base_url or _DEFAULT_AUTHORITY_BASE_URL,
        graph_base_url=graph_base_url or _DEFAULT_GRAPH_BASE_URL,
    )
    return MicrosoftOAuthClient(
        config=config,
        token_store=token_store,
        transport=transport,
    )


def _token_from_connection(record: MicrosoftGraphConnectionRecord) -> MicrosoftTokenRecord:
    return MicrosoftTokenRecord(
        student_id=record.student_id,
        access_token=record.access_token,
        refresh_token=record.refresh_token,
        expires_at=record.expires_at,
        scopes=tuple(record.scopes),
        token_type=record.token_type,
        tenant_id=record.tenant_id,
        microsoft_user_id=record.microsoft_user_id,
        user_principal_name=record.user_principal_name,
        email=record.email,
        display_name=record.display_name,
        calendar_id=record.calendar_id,
        todo_task_list_id=record.todo_task_list_id,
        auth_metadata=dict(record.auth_metadata),
    )


def _token_form_payload(
    *,
    client_id: str,
    client_secret: str | None,
    redirect_uri: str,
    scopes: tuple[str, ...],
    grant_type: str,
    authorization_code: str | None = None,
    refresh_token: str | None = None,
) -> dict[str, str]:
    payload = {
        "client_id": client_id,
        "grant_type": grant_type,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
    }
    if authorization_code:
        payload["code"] = authorization_code
    if refresh_token:
        payload["refresh_token"] = refresh_token
    if client_secret:
        payload["client_secret"] = client_secret
    return payload


def _parse_scopes(raw_value: str) -> tuple[str, ...]:
    normalized = raw_value.replace(",", " ")
    parts = tuple(scope.strip() for scope in normalized.split() if scope.strip())
    return parts or DEFAULT_MICROSOFT_SCOPES


def _env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _scopes_from_payload(
    token_payload: dict[str, Any],
    fallback_scopes: tuple[str, ...],
) -> tuple[str, ...]:
    raw_scope = str(token_payload.get("scope") or "").strip()
    return _parse_scopes(raw_scope) if raw_scope else tuple(fallback_scopes)


def _expires_at_from_payload(token_payload: dict[str, Any]) -> datetime | None:
    expires_in = token_payload.get("expires_in")
    if expires_in is None:
        return None
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _token_is_usable(
    token: MicrosoftTokenRecord,
    *,
    now: datetime,
    refresh_skew_seconds: int,
) -> bool:
    if token.expires_at is None:
        return True
    threshold = token.expires_at - timedelta(seconds=refresh_skew_seconds)
    return threshold > now


def _build_auth_metadata(
    *,
    token_payload: dict[str, Any],
    profile_error: str | None,
    existing_metadata: dict[str, object] | None,
) -> dict[str, object]:
    metadata = dict(existing_metadata or {})
    metadata["last_token_scope"] = str(token_payload.get("scope") or "")
    metadata["last_token_refresh"] = datetime.now(timezone.utc).isoformat()
    if profile_error:
        metadata["last_profile_error"] = profile_error
    else:
        metadata.pop("last_profile_error", None)
    return metadata


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _transport_error_from_http_error(exc: HTTPError) -> MicrosoftOAuthTransportError:
    body = exc.read().decode("utf-8", errors="replace")
    if body.strip():
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    error_code = str(payload.get("error") or f"microsoft_oauth_http_{exc.code}")
    detail = str(
        payload.get("error_description")
        or payload.get("message")
        or body
        or exc.reason
        or exc
    )
    return MicrosoftOAuthTransportError(error_code=error_code, detail=detail)
