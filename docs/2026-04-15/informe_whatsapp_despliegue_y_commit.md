# Informe: WhatsApp Cloud API, despliegue y commit seguro

Fecha: 2026-04-15

## 1. Credenciales actuales y qué falta

Credenciales disponibles:

- `WHATSAPP_PHONE_NUMBER_ID`: identifica el número de WhatsApp Business que envía mensajes por Cloud API.
- `WHATSAPP_BUSINESS_ACCOUNT_ID`: identifica la WABA. Sirve para administración, plantillas, métricas y configuración del negocio.
- `WHATSAPP_ACCESS_TOKEN`: autentica llamadas hacia Graph API. Debe enviarse como `Authorization: Bearer ...`, no en query string.

Para el flujo robusto del proyecto, aún falta definir o confirmar:

- `WHATSAPP_WEBHOOK_VERIFY_TOKEN`: valor secreto elegido por nosotros para que Meta valide el endpoint webhook durante la configuración inicial. No lo entrega Meta; se crea y se guarda como secreto.
- URL pública HTTPS del webhook: por ejemplo `https://dominio.com/webhooks/whatsapp`. Meta enviará ahí mensajes entrantes, estados de entrega y eventos.
- `WHATSAPP_APP_SECRET`: secreto de la app de Meta. Es necesario para validar firmas `X-Hub-Signature-256` en webhooks y rechazar payloads falsificados.
- Token permanente o de larga duración para producción: el token temporal de pruebas no debe usarse en despliegue.
- Permisos del token: como mínimo `whatsapp_business_messaging` para enviar/recibir mensajes. Para administrar WABA, plantillas o números también puede requerirse `whatsapp_business_management` y, según operación, `business_management`.
- `WHATSAPP_GRAPH_API_VERSION`: fijar versión explícita, por ejemplo `v20.0` o la versión vigente probada. No depender de defaults.
- Almacenamiento persistente para medios: `ACADEMIC_AGENT_MEDIA_DIR` debe apuntar a un volumen persistente o a una capa reemplazable por object storage. No debe ser un directorio efímero del contenedor.
- Plantillas aprobadas: necesarias para iniciar conversaciones o enviar recordatorios fuera de la ventana de atención permitida por WhatsApp.

## 2. Consideraciones funcionales

WhatsApp no es un chat local como LangGraph Studio. En Studio se pueden ver rutas locales si el navegador y el proceso comparten máquina, pero WhatsApp solo acepta medios accesibles para Meta: o se suben a Cloud API y se envían por `media_id`, o se envían como URL pública.

La solución implementada separa estos casos:

- Entrada del estudiante: el webhook trae un `media_id`; el servicio descarga la imagen/documento desde WhatsApp, lo guarda como artefacto local controlado y lo transforma en un mensaje humano con referencia local. El agente no persiste base64 pesado.
- Salida del agente: si el agente produce una imagen local, el canal de WhatsApp la sube primero a Cloud API y luego envía el `media_id`. Si ya existe una URL pública, se puede enviar como link.
- Persistencia LangGraph: los mensajes y checkpoints deben guardar referencias livianas a medios, no strings base64. Esto evita que `.langgraph_api`, checkpoints y LangSmith Studio crezcan hasta provocar lentitud u Out of Memory.

## 3. Arquitectura aplicada en el proyecto

Capas relevantes:

- `src/schemas/channels.py`: contratos neutrales de canal (`ChannelInboundMessage`, `ChannelOutboundMessage`, medios y resultados).
- `src/integrations/whatsapp/`: cliente Cloud API, modelos de error/respuesta y mapeo de webhooks.
- `src/services/channels/whatsapp_service.py`: orquesta subida, descarga, conversión de mensajes y adaptación entre WhatsApp y LangGraph.
- `src/utils/media_artifacts.py` y `src/utils/message_sanitizer.py`: materializan imágenes base64 en archivos y limpian mensajes antes de persistirlos.
- `src/integrations/langgraph/checkpointer.py`: sanitiza checkpoints antes de serializarlos.

Con esta separación, el agente académico no depende directamente de WhatsApp. El canal adapta entrada/salida y el grafo sigue trabajando con mensajes y estado normalizados.

## 4. Seguridad y secretos

No se debe commitear:

- `.env`, `.env.*` reales, tokens, secrets, certificados privados o llaves.
- `.codex`, porque es estado/configuración local de la herramienta.
- `.langgraph_api`, `.langgraph_api.bak*` y `.langgraph_media`, porque son persistencia local, checkpoints, cachés y medios posiblemente sensibles.
- Capturas, imágenes temporales, backups, dumps de base de datos o logs con datos de estudiantes.

Recomendaciones para producción:

- Guardar credenciales en el secret manager del entorno de despliegue, no en archivos versionados.
- Validar el `verify_token` en el challenge GET del webhook.
- Validar la firma del webhook con `WHATSAPP_APP_SECRET` antes de procesar mensajes.
- Rotar el access token si se expuso localmente o en logs.
- Registrar logs sin tokens, sin payloads completos de medios y sin PII innecesaria.

## 5. Operación y despliegue

Puntos que deben quedar resueltos antes de salir a producción:

- Webhook público con HTTPS, baja latencia y respuesta rápida. Si el procesamiento del agente tarda, conviene responder a Meta y procesar asíncronamente.
- Idempotencia por `message_id`, porque Meta puede reintentar webhooks.
- Backoff ante rate limits y errores transitorios de Graph API.
- Limpieza/retención de medios en `ACADEMIC_AGENT_MEDIA_DIR`.
- Persistencia compartida si hay más de una instancia del backend. Un archivo local funciona para MVP en una sola instancia, pero para múltiples réplicas conviene migrar medios a object storage.
- Plantillas aprobadas para recordatorios proactivos, reactivación y mensajes fuera de ventana.
- Revisión de límites: throughput por número, límites por par usuario-negocio, calidad del número y límites de plantillas.

## 6. Qué sí debería entrar al commit

Para la solución de imágenes y WhatsApp:

- `.gitignore`
- `docs/2026-04-15/informe_whatsapp_despliegue_y_commit.md`
- `src/schemas/channels.py`
- `src/integrations/whatsapp/README.md`
- `src/integrations/whatsapp/__init__.py`
- `src/integrations/whatsapp/client.py`
- `src/integrations/whatsapp/models.py`
- `src/integrations/whatsapp/message_mapper.py`
- `src/services/channels/__init__.py`
- `src/services/channels/whatsapp_service.py`
- `src/utils/media_artifacts.py`
- `src/utils/message_sanitizer.py`
- `src/agents/support/media/`
- Cambios relacionados con sanitización de medios en `src/agents/support/state.py`, `src/agents/support/nodes/utils.py`, `src/agents/support/nodes/welcome_consent/node.py`, `src/agents/support/scheduling/render.py`, `src/integrations/langgraph/checkpointer.py`, `src/schemas/scheduling.py`, `src/services/scheduling/ai_support.py`, `src/services/scheduling/__init__.py`, `src/agents/support/nodes/request_schedules/node.py` y `src/agents/support/flows/scheduling/schedule_capture_service.py`.
- Pruebas relacionadas: `tests/test_whatsapp_client.py`, `tests/test_whatsapp_channel_service.py`, `tests/test_message_image_utils.py`, `tests/test_schedule_preview.py`, `tests/test_schedule_request_flow.py`, `tests/test_out_of_scope_restart.py` y el ajuste de fecha en `tests/test_outlook_fixed_schedule_sync_service.py`.

No incluir en este commit, salvo que sea otro cambio intencional:

- `tmp/schedule.png`
- `.langgraph_api.bak.20260415083013/`
- `.langgraph_media/`
- `.codex`
- `.env` o cualquier variante real de secretos.
- Cambios no relacionados de prioridades, planificación diaria, migraciones o docs de otras fechas si pertenecen a otra tarea.

## 7. Comando sugerido para staging

Revisar primero:

```bash
git status --short
git diff -- .gitignore src/integrations/whatsapp src/services/channels src/schemas/channels.py src/utils/media_artifacts.py src/utils/message_sanitizer.py
```

Luego stagear por intención:

```bash
git add .gitignore \
  docs/2026-04-15/informe_whatsapp_despliegue_y_commit.md \
  src/schemas/channels.py \
  src/integrations/whatsapp/README.md \
  src/integrations/whatsapp/__init__.py \
  src/integrations/whatsapp/client.py \
  src/integrations/whatsapp/models.py \
  src/integrations/whatsapp/message_mapper.py \
  src/services/channels/__init__.py \
  src/services/channels/whatsapp_service.py \
  src/utils/media_artifacts.py \
  src/utils/message_sanitizer.py \
  src/agents/support/media \
  src/agents/support/state.py \
  src/agents/support/nodes/utils.py \
  src/agents/support/nodes/welcome_consent/node.py \
  src/agents/support/scheduling/render.py \
  src/integrations/langgraph/checkpointer.py \
  src/schemas/scheduling.py \
  src/services/scheduling/ai_support.py \
  src/services/scheduling/__init__.py \
  src/agents/support/nodes/request_schedules/node.py \
  src/agents/support/flows/scheduling/schedule_capture_service.py \
  tests/test_whatsapp_client.py \
  tests/test_whatsapp_channel_service.py \
  tests/test_message_image_utils.py \
  tests/test_schedule_preview.py \
  tests/test_schedule_request_flow.py \
  tests/test_out_of_scope_restart.py \
  tests/test_outlook_fixed_schedule_sync_service.py
```

Antes del commit:

```bash
git diff --cached --check
git diff --cached --name-only
```

## 8. Referencias oficiales

- Meta WhatsApp Cloud API Overview: https://meta-preview.mintlify.io/docs/whatsapp/cloud-api/overview
- Meta WhatsApp Cloud API Media: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
- Meta WhatsApp Cloud API Messages: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
- Meta WhatsApp Cloud API Webhooks: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
