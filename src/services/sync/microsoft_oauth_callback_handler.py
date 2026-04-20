"""Handler framework-agnostic para callbacks OAuth Microsoft."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from services.sync.microsoft_oauth_flow_service import (
    MicrosoftOAuthFlowService,
    build_microsoft_oauth_flow_service,
)


@dataclass(frozen=True)
class MicrosoftOAuthCallbackHandlerResult:
    """Respuesta simple para adaptadores HTTP o jobs de callback."""

    ok: bool
    status_code: int
    message: str
    student_id: int | None = None
    error_code: str | None = None


def handle_microsoft_oauth_callback(
    query_params: Mapping[str, object],
    *,
    flow_service: MicrosoftOAuthFlowService | None = None,
) -> MicrosoftOAuthCallbackHandlerResult:
    """Procesa `state` y `code` de Microsoft sin acoplarse a un framework web."""

    provider_error = _param(query_params, "error")
    if provider_error:
        return MicrosoftOAuthCallbackHandlerResult(
            ok=False,
            status_code=400,
            message=_param(query_params, "error_description")
            or "Microsoft rechazo la autorizacion.",
            error_code=provider_error,
        )

    state_token = _param(query_params, "state")
    authorization_code = _param(query_params, "code")
    if not state_token or not authorization_code:
        return MicrosoftOAuthCallbackHandlerResult(
            ok=False,
            status_code=400,
            message="El callback debe incluir state y code.",
            error_code="missing_oauth_callback_params",
        )

    service = flow_service or build_microsoft_oauth_flow_service()
    result = service.complete_authorization(
        state_token=state_token,
        authorization_code=authorization_code,
    )
    if not result.ok:
        return MicrosoftOAuthCallbackHandlerResult(
            ok=False,
            status_code=400,
            message=result.detail or "No pude completar la autorizacion Microsoft.",
            student_id=result.student_id,
            error_code=result.error_code,
        )

    return MicrosoftOAuthCallbackHandlerResult(
        ok=True,
        status_code=200,
        message="Autorizacion Microsoft completada.",
        student_id=result.student_id,
    )


def _param(query_params: Mapping[str, object], key: str) -> str:
    value = query_params.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


__all__ = [
    "MicrosoftOAuthCallbackHandlerResult",
    "handle_microsoft_oauth_callback",
]
