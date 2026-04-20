"""Servidor FastAPI: punto de entrada HTTP del agente Lara."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from integrations.whatsapp import (
    extract_inbound_messages,
    verify_webhook_challenge,
)
from services.sync.microsoft_oauth_callback_handler import handle_microsoft_oauth_callback

logger = logging.getLogger(__name__)

_runner: "AgentRunner | None" = None  # type: ignore[name-defined]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa y limpia recursos compartidos del agente."""
    global _runner
    from api.agent_runner import AgentRunner

    logger.info("Iniciando AgentRunner...")
    try:
        _runner = AgentRunner.from_env()
        logger.info("AgentRunner listo.")
    except Exception:
        logger.exception("Error al inicializar AgentRunner.")
        _runner = None

    yield

    _runner = None
    logger.info("AgentRunner detenido.")


app = FastAPI(
    title="Lara Academic Agent",
    description="Asistente académica conversacional via WhatsApp.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Probe de disponibilidad para Azure y balanceadores."""
    return {"status": "ok", "agent": "ready" if _runner is not None else "initializing"}


# ---------------------------------------------------------------------------
# WhatsApp webhook
# ---------------------------------------------------------------------------


@app.get("/webhook", tags=["whatsapp"])
def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    """Verificacion del webhook GET de WhatsApp Cloud API."""
    expected_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=500, detail="WHATSAPP_VERIFY_TOKEN no configurado.")

    challenge = verify_webhook_challenge(
        mode=hub_mode,
        verify_token=hub_verify_token,
        challenge=hub_challenge,
        expected_verify_token=expected_token,
    )
    if challenge is None:
        raise HTTPException(status_code=403, detail="Token de verificacion invalido.")

    return Response(content=challenge, media_type="text/plain")


@app.post("/webhook", tags=["whatsapp"])
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Recibe mensajes entrantes de WhatsApp y los despacha al agente."""
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        return {"status": "ok"}  # Payload invalido — responder 200 para evitar reintentos

    if _runner is None:
        logger.warning("Mensaje recibido pero el AgentRunner no esta listo.")
        return {"status": "ok"}

    messages = extract_inbound_messages(body)
    for msg in messages:
        if msg.text or msg.media:
            background_tasks.add_task(_runner.process_message, msg)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Microsoft OAuth callback
# ---------------------------------------------------------------------------


@app.get("/oauth/callback", tags=["microsoft"])
async def microsoft_oauth_callback(request: Request) -> HTMLResponse:
    """Completa el flujo OAuth de Microsoft y notifica al estudiante."""
    params = dict(request.query_params)
    result = handle_microsoft_oauth_callback(params)

    if not result.ok:
        logger.warning("OAuth callback fallido: %s", result.message)
        html = _oauth_result_page(
            success=False,
            message="No pude completar la conexion con tu cuenta Microsoft. Intenta de nuevo.",
        )
        return HTMLResponse(content=html, status_code=400)

    html = _oauth_result_page(
        success=True,
        message=(
            "✅ Tu cuenta Microsoft fue conectada correctamente. "
            "Vuelve a WhatsApp para continuar con Lara."
        ),
    )
    return HTMLResponse(content=html, status_code=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _oauth_result_page(*, success: bool, message: str) -> str:
    icon = "✅" if success else "❌"
    color = "#2ecc71" if success else "#e74c3c"
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lara — Conexion Microsoft</title>
  <style>
    body {{ font-family: sans-serif; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0;
           background: #f5f6fa; }}
    .card {{ background: white; padding: 2rem 2.5rem; border-radius: 12px;
             box-shadow: 0 4px 20px rgba(0,0,0,.1); text-align: center;
             max-width: 420px; }}
    .icon {{ font-size: 3rem; }}
    h2 {{ color: {color}; margin: .5rem 0 1rem; }}
    p {{ color: #555; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h2>{"Listo" if success else "Ocurrio un error"}</h2>
    <p>{message}</p>
  </div>
</body>
</html>"""


__all__ = ["app"]
