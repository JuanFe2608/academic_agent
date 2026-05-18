"""Servidor FastAPI: punto de entrada HTTP del agente Lara."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from integrations.whatsapp import (
    extract_inbound_messages,
    verify_webhook_challenge,
)
from services.sync.microsoft_oauth_callback_handler import handle_microsoft_oauth_callback

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from api.agent_runner import AgentRunner

_runner: "AgentRunner | None" = None  # type: ignore[name-defined]

limiter = Limiter(key_func=get_remote_address)


def _check_startup_config() -> None:
    """Registra advertencias tempranas sobre variables de entorno criticas."""
    redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "").strip()
    if not redirect_uri:
        logger.warning(
            "MICROSOFT_REDIRECT_URI no configurado: el flujo OAuth de Microsoft fallara."
        )
    elif redirect_uri.startswith("http://localhost") or redirect_uri.startswith("http://127."):
        logger.warning(
            "MICROSOFT_REDIRECT_URI apunta a localhost (%s). "
            "En staging/produccion debe ser https://<dominio>/oauth/callback "
            "y estar registrado en Microsoft Entra.",
            redirect_uri,
        )
    elif not redirect_uri.startswith("https://"):
        logger.warning(
            "MICROSOFT_REDIRECT_URI no usa HTTPS (%s). "
            "Microsoft Entra rechaza URIs de redireccion HTTP en produccion.",
            redirect_uri,
        )
    else:
        logger.info("MICROSOFT_REDIRECT_URI configurado: %s", redirect_uri)

    if not os.getenv("WHATSAPP_APP_SECRET", "").strip():
        logger.warning(
            "WHATSAPP_APP_SECRET no configurado: el webhook POST no valida la firma "
            "X-Hub-Signature-256. Configurar antes de exponer el endpoint publicamente."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa y limpia recursos compartidos del agente."""
    global _runner
    from api.agent_runner import AgentRunner

    _check_startup_config()

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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: este backend no tiene frontend web; se deniega todo origen cross-origin por defecto.
# Para habilitar un origen especifico en el futuro, configurar ACADEMIC_AGENT_CORS_ORIGINS
# con una lista separada por comas (ej: https://mi-admin.com).
_cors_origins = [
    o.strip()
    for o in os.getenv("ACADEMIC_AGENT_CORS_ORIGINS", "").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _verify_whatsapp_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Valida la firma HMAC-SHA256 del webhook de Meta/WhatsApp.

    Meta incluye el header 'X-Hub-Signature-256: sha256=<hex>' calculado como
    HMAC-SHA256(app_secret, raw_body). Se usa compare_digest para evitar
    ataques de timing.
    """
    if not signature_header.startswith("sha256="):
        return False
    expected_hex = signature_header[len("sha256="):]
    computed_hex = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_hex, expected_hex)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Probe de disponibilidad para Azure y balanceadores."""
    return {"status": "ok"}


@app.post("/tasks/reminders/run", tags=["infra"])
@limiter.limit("10/minute")
async def run_due_reminders(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    """Ejecuta un ciclo del worker de recordatorios para Azure Scheduler/Functions."""

    expected_token = os.getenv("ACADEMIC_AGENT_REMINDER_WORKER_TOKEN", "").strip()
    if not expected_token:
        logger.error("Reminder worker rechazado: ACADEMIC_AGENT_REMINDER_WORKER_TOKEN no configurado.")
        raise HTTPException(status_code=503, detail="Worker de recordatorios no configurado.")

    provided_token = (request.headers.get("x-reminder-worker-token") or "").strip()
    if not hmac.compare_digest(provided_token, expected_token):
        logger.warning("Reminder worker rechazado: token ausente o invalido.")
        raise HTTPException(status_code=403, detail="Token de worker invalido.")

    from services.reminders import build_reminder_dispatch_runner

    result = build_reminder_dispatch_runner().run_due_dispatches(limit=limit)
    if not result.processed:
        logger.error(
            "Reminder worker fallo: error_code=%s detail=%s leased_count=%s "
            "sent_count=%s failed_count=%s retryable_count=%s channels=%s dispatch_types=%s",
            result.error_code,
            result.detail,
            result.leased_count,
            result.sent_count,
            result.failed_count,
            result.retryable_count,
            result.channel_counts or {},
            result.dispatch_type_counts or {},
        )
        raise HTTPException(
            status_code=500,
            detail="No se pudieron procesar recordatorios.",
        )
    logger.info(
        "Reminder worker ejecutado: leased_count=%s sent_count=%s failed_count=%s "
        "retryable_count=%s channels=%s dispatch_types=%s",
        result.leased_count,
        result.sent_count,
        result.failed_count,
        result.retryable_count,
        result.channel_counts or {},
        result.dispatch_type_counts or {},
    )
    return {
        "status": "ok",
        "leased_count": result.leased_count,
        "sent_count": result.sent_count,
        "failed_count": result.failed_count,
        "retryable_count": result.retryable_count,
        "channels": result.channel_counts or {},
        "dispatch_types": result.dispatch_type_counts or {},
    }


# ---------------------------------------------------------------------------
# Legal
# ---------------------------------------------------------------------------


@app.get("/legal/habeas-data", tags=["legal"])
def habeas_data_policy() -> HTMLResponse:
    """Pagina publica de autorizacion para tratamiento de datos personales."""
    return HTMLResponse(content=_habeas_data_policy_page(), status_code=200)


# ---------------------------------------------------------------------------
# WhatsApp webhook
# ---------------------------------------------------------------------------


@app.get("/webhook", tags=["whatsapp"])
@limiter.limit("10/minute")
def verify_webhook(
    request: Request,
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
@limiter.limit("120/minute")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Recibe mensajes entrantes de WhatsApp y los despacha al agente."""
    raw_body = await request.body()

    app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if not app_secret:
        logger.error(
            "Webhook POST rechazado: WHATSAPP_APP_SECRET no configurado. "
            "Configurar la variable de entorno antes de exponer el endpoint publicamente."
        )
        raise HTTPException(status_code=503, detail="Webhook no disponible: configuracion incompleta.")

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_whatsapp_signature(raw_body, signature, app_secret):
        logger.warning("Webhook POST rechazado: firma X-Hub-Signature-256 invalida.")
        raise HTTPException(status_code=403, detail="Firma de webhook invalida.")

    body: dict[str, Any] = {}
    try:
        body = json.loads(raw_body)
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
@app.get("/auth/microsoft/callback", tags=["microsoft"], include_in_schema=False)
@limiter.limit("10/minute")
async def microsoft_oauth_callback(request: Request) -> HTMLResponse:
    """Completa el flujo OAuth de Microsoft y notifica al estudiante."""
    params = dict(request.query_params)
    result = handle_microsoft_oauth_callback(params)

    if not result.ok:
        logger.warning("OAuth callback fallido: %s", result.message)
        html = _oauth_result_page(
            success=False,
            message=result.message
            or "No pude completar la conexion con tu cuenta Microsoft. Intenta de nuevo.",
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
    safe_message = html.escape(message)
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
    <p>{safe_message}</p>
  </div>
</body>
</html>"""


def _habeas_data_policy_page() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lara AI - Tratamiento de datos personales</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f7fb;
      --paper: #ffffff;
      --ink: #172033;
      --muted: #5b6475;
      --line: #dbe3ef;
      --accent: #1166cc;
      --accent-soft: #e8f1ff;
      --ok-soft: #e9f8ef;
      --warn-soft: #fff5dc;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.62;
    }
    main {
      width: min(960px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }
    .hero {
      padding: 32px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
      box-shadow: 0 16px 36px rgba(23, 32, 51, 0.08);
    }
    .eyebrow {
      margin: 0 0 8px;
      color: var(--accent);
      font-weight: 700;
      letter-spacing: 0;
      text-transform: uppercase;
      font-size: 0.78rem;
    }
    h1 {
      margin: 0;
      font-size: clamp(1.8rem, 4vw, 3rem);
      line-height: 1.08;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 1.05rem;
      max-width: 760px;
    }
    .meta {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 24px;
    }
    .meta div, section {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
    }
    .meta div {
      padding: 14px 16px;
    }
    .meta strong {
      display: block;
      margin-bottom: 4px;
      color: var(--ink);
    }
    .meta span, .meta a {
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    section {
      margin-top: 16px;
      padding: 24px;
    }
    h2 {
      display: flex;
      gap: 10px;
      align-items: center;
      margin: 0 0 14px;
      font-size: 1.24rem;
      line-height: 1.25;
      letter-spacing: 0;
    }
    h3 {
      margin: 18px 0 8px;
      font-size: 1rem;
      letter-spacing: 0;
    }
    p { margin: 0 0 12px; }
    ul {
      margin: 0;
      padding-left: 1.2rem;
    }
    li + li { margin-top: 6px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .panel {
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfdff;
    }
    .notice {
      padding: 16px;
      border-radius: 8px;
      background: var(--warn-soft);
      border: 1px solid #f2d38a;
    }
    .ok {
      padding: 16px;
      border-radius: 8px;
      background: var(--ok-soft);
      border: 1px solid #b8e5c6;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 3px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.82rem;
      font-weight: 700;
    }
    a {
      color: var(--accent);
      font-weight: 700;
    }
    footer {
      color: var(--muted);
      font-size: 0.92rem;
      padding: 24px 4px 0;
      text-align: center;
    }
    @media (max-width: 720px) {
      main { width: min(100% - 24px, 960px); padding-top: 16px; }
      .hero, section { padding: 20px; }
      .meta, .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <header class="hero">
      <p class="eyebrow">Proyecto Lara AI - Agente Academico Inteligente</p>
      <h1>📄 Autorizacion para el tratamiento de datos personales</h1>
      <p class="subtitle">
        Informacion para estudiantes sobre la recoleccion, uso, almacenamiento y proteccion
        de datos personales dentro del piloto academico Lara AI.
      </p>
      <div class="meta" aria-label="Informacion principal">
        <div>
          <strong>🏛️ Institucion</strong>
          <span>Universidad Catolica de Colombia</span>
        </div>
        <div>
          <strong>👤 Responsable</strong>
          <span>Juan Felipe Jaramillo R.<br>Laura Marcela Gutierrez P.</span>
        </div>
        <div>
          <strong>📩 Contacto</strong>
          <a href="mailto:jfjaramillo12@ucatolica.edu.co">jfjaramillo12@ucatolica.edu.co</a>
        </div>
      </div>
    </header>

    <section>
      <h2>⚖️ Marco normativo</h2>
      <p>
        Esta autorizacion se presenta conforme al regimen colombiano de proteccion
        de datos personales, en especial la Ley 1581 de 2012, el Decreto 1377 de
        2013, el Decreto 1074 de 2015 y las normas que los modifiquen, complementen
        o sustituyan. En virtud de este marco, el titular recibe informacion clara
        sobre las finalidades, datos tratados, derechos, canales de atencion y
        condiciones bajo las cuales Lara AI realiza el tratamiento de informacion
        personal dentro del proyecto academico.
      </p>
    </section>

    <section>
      <h2>🎯 Finalidades del tratamiento</h2>
      <div class="grid">
        <div class="panel">
          <h3>Finalidades principales</h3>
          <ul>
            <li>Gestionar el registro y perfil del estudiante dentro de Lara AI.</li>
            <li>Recolectar, almacenar y procesar informacion academica necesaria para el asistente.</li>
            <li>Apoyar la gestion del tiempo academico, planificacion de actividades y organizacion de tareas.</li>
            <li>Recomendar metodos de estudio personalizados segun el perfil y los habitos del estudiante.</li>
            <li>Generar recordatorios y notificaciones sobre actividades, eventos y planificacion diaria o semanal.</li>
          </ul>
        </div>
        <div class="panel">
          <h3>Integraciones autorizadas</h3>
          <ul>
            <li>WhatsApp como interfaz conversacional.</li>
            <li>Microsoft Outlook y Microsoft Graph API.</li>
            <li>Microsoft To Do, cuando sea necesario para proyectar tareas o recordatorios academicos.</li>
            <li>Servicios Microsoft conectados voluntariamente por el estudiante mediante OAuth.</li>
          </ul>
        </div>
        <div class="panel">
          <h3>Finalidades tecnicas y academicas</h3>
          <ul>
            <li>Realizar seguimiento tecnico del funcionamiento del sistema.</li>
            <li>Registrar logs para diagnostico de errores, rendimiento y seguridad.</li>
            <li>Realizar analisis estadisticos o investigativos con fines academicos.</li>
            <li>Evaluar el desempeno del sistema en el contexto del trabajo de grado.</li>
          </ul>
        </div>
        <div class="panel">
          <h3>Finalidades legales y administrativas</h3>
          <ul>
            <li>Cumplir obligaciones legales y regulatorias aplicables.</li>
            <li>Garantizar la seguridad de la informacion.</li>
            <li>Prevenir accesos no autorizados o usos indebidos del sistema.</li>
          </ul>
        </div>
      </div>
    </section>

    <section>
      <h2>🗂️ Datos personales recolectados</h2>
      <div class="grid">
        <div class="panel">
          <h3>Datos de identificacion</h3>
          <ul>
            <li>Nombre completo.</li>
            <li>Correo electronico institucional.</li>
            <li>Programa academico.</li>
            <li>Semestre academico.</li>
          </ul>
        </div>
        <div class="panel">
          <h3>Datos academicos</h3>
          <ul>
            <li>Materias cursadas, horarios, tareas, entregas y evaluaciones programadas.</li>
            <li>Actividades academicas y preferencias de estudio.</li>
            <li>Metodos de aprendizaje utilizados.</li>
          </ul>
        </div>
        <div class="panel">
          <h3>Interaccion con el sistema</h3>
          <ul>
            <li>Mensajes enviados al asistente.</li>
            <li>Historial de planificacion academica.</li>
            <li>Uso del sistema y configuracion del perfil academico.</li>
          </ul>
        </div>
        <div class="panel">
          <h3>Datos tecnicos</h3>
          <ul>
            <li>Registros de uso e identificadores tecnicos.</li>
            <li>Informacion necesaria para autenticacion.</li>
            <li>Tokens de acceso a servicios Microsoft autorizados voluntariamente por el estudiante.</li>
          </ul>
        </div>
      </div>
      <p class="notice">
        ⚠️ Lara AI no recolecta datos sensibles como informacion medica, datos biometricos,
        informacion financiera o datos sobre salud mental, salvo autorizacion expresa y especifica.
      </p>
    </section>

    <section>
      <h2>☁️ Servicios tecnologicos</h2>
      <p>
        El tratamiento de datos podra realizarse mediante plataformas como Microsoft Azure,
        OpenAI o Azure OpenAI, WhatsApp Cloud API, Microsoft Graph API y bases de datos
        PostgreSQL.
      </p>
      <p>
        Estas plataformas podran almacenar informacion en servidores ubicados dentro o fuera
        del territorio colombiano, cumpliendo estandares de seguridad internacionales.
      </p>
    </section>

    <section>
      <h2>🛡️ Derechos del titular</h2>
      <ul>
        <li>Conocer, actualizar y rectificar sus datos personales.</li>
        <li>Solicitar prueba de la autorizacion otorgada.</li>
        <li>Ser informado sobre el uso dado a sus datos personales.</li>
        <li>Presentar consultas y reclamos ante el responsable del tratamiento.</li>
        <li>Revocar la autorizacion y solicitar la supresion de sus datos personales.</li>
        <li>Acceder en forma gratuita a sus datos personales.</li>
        <li>Presentar quejas ante la Superintendencia de Industria y Comercio cuando considere vulnerados sus derechos.</li>
      </ul>
    </section>

    <section>
      <h2>📬 Canal para ejercer derechos</h2>
      <p>
        El titular podra ejercer sus derechos mediante solicitud escrita enviada al correo
        <a href="mailto:jfjaramillo12@ucatolica.edu.co">jfjaramillo12@ucatolica.edu.co</a>.
      </p>
      <p>La solicitud debe incluir nombre del titular, identificacion, descripcion clara de la solicitud y datos de contacto.</p>
    </section>

    <section>
      <h2>🔐 Seguridad de la informacion</h2>
      <p>
        Lara AI implementa medidas tecnicas, administrativas y organizativas para proteger
        la informacion personal contra perdida, acceso no autorizado, alteracion, uso indebido
        o divulgacion no autorizada.
      </p>
      <div class="ok">
        <span class="badge">Medidas aplicadas</span>
        <ul>
          <li>Validacion del webhook de WhatsApp mediante firma HMAC-SHA256 en el header X-Hub-Signature-256, cuando el secreto de aplicacion esta configurado.</li>
          <li>Verificacion del endpoint GET del webhook mediante token de verificacion.</li>
          <li>Uso de OAuth de Microsoft con token state aleatorio, vencimiento temporal y validacion del callback antes de persistir la conexion.</li>
          <li>Proteccion del worker de recordatorios mediante token de acceso configurado por entorno.</li>
          <li>Deduplicacion durable de mensajes entrantes de WhatsApp en PostgreSQL para evitar reprocesamientos por reintentos del proveedor.</li>
          <li>Separacion de secretos y credenciales mediante variables de entorno, sin exponerlos en el codigo fuente.</li>
          <li>Persistencia operativa en PostgreSQL para perfiles, planificacion, recordatorios, conexiones Microsoft y checkpoints del agente.</li>
        </ul>
      </div>
    </section>

    <section>
      <h2>⏳ Vigencia, transferencia y transmision</h2>
      <p>
        Los datos personales seran tratados durante el tiempo necesario para cumplir las finalidades
        descritas, ejecutar el proyecto academico y realizar analisis posteriores del trabajo de grado.
      </p>
      <p>
        Una vez finalizado el proyecto, los datos podran ser eliminados, anonimizados o conservados
        unicamente cuando exista obligacion legal.
      </p>
      <p>
        El titular autoriza que sus datos puedan ser transmitidos o transferidos a plataformas
        tecnologicas autorizadas, servicios necesarios para el funcionamiento del sistema y entidades
        academicas relacionadas con el proyecto, siempre bajo condiciones de seguridad y confidencialidad.
      </p>
    </section>

    <section>
      <h2>📌 Principios y caracter voluntario</h2>
      <p>
        El tratamiento se realizara conforme a los principios de legalidad, finalidad, libertad,
        veracidad, transparencia, acceso restringido, seguridad y confidencialidad.
      </p>
      <p>
        El suministro de datos personales es voluntario. Sin embargo, algunos datos son necesarios
        para el funcionamiento de Lara AI y la prestacion del servicio.
      </p>
    </section>

    <section>
      <h2>✅ Autorizacion del titular</h2>
      <p>
        Al aceptar desde WhatsApp, el estudiante declara que ha leido y comprendido esta autorizacion
        para el tratamiento de datos personales.
      </p>
      <p>
        El estudiante autoriza de manera previa, expresa e informada al Proyecto Lara AI - Universidad
        Catolica de Colombia para tratar sus datos personales conforme a las finalidades descritas.
      </p>
      <p>
        Esta autorizacion se otorga de manera voluntaria y podra ser revocada en cualquier momento,
        siempre que no exista obligacion legal o contractual que impida la eliminacion de la informacion.
      </p>
    </section>

    <footer>
      Version habeas-data-v1 · Proyecto academico Lara AI · Universidad Catolica de Colombia
    </footer>
  </main>
</body>
</html>"""


__all__ = ["app"]
