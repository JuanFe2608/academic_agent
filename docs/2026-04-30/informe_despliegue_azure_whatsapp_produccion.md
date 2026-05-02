# Informe De Despliegue Azure + WhatsApp

Fecha: 2026-05-01

## 0. Estado De Preparacion

Actualizacion post despliegue, 2026-05-01: el piloto ya fue desplegado en Azure Container Apps y esta siendo probado por WhatsApp. El backend publico quedo en:

```text
https://ca-lara-academic-agent-pilot.greenriver-35e70b6b.canadacentral.azurecontainerapps.io
```

`GET /health` respondio:

```json
{"status":"ok","agent":"ready"}
```

El webhook de WhatsApp fue validado por Meta con HTTP 200 y se probo envio directo con WhatsApp Cloud API usando un System User token permanente. El procedimiento real esta documentado en `docs/2026-05-01/informe_despliegue_real_azure_whatsapp_piloto.md`.

Actualizacion RAG/pgvector: despues del despliegue se habilito la extension `vector` en Azure PostgreSQL Flexible Server, se aplico la migracion RAG y se cargo el corpus de recomendaciones. El estado validado fue: `15` documentos, `468` chunks, `355` relaciones y `468` chunks con embedding.

Decision actual: el proyecto esta desplegado como piloto controlado en Azure con una sola replica. Para produccion abierta con estudiantes reales sigue siendo necesario cerrar validacion end-to-end ampliada, operacion y deuda de pruebas.

La arquitectura principal del MVP ya esta implementada: FastAPI, WhatsApp Cloud API, LangGraph/ReAct, PostgreSQL, OAuth Microsoft, Outlook Calendar, Microsoft To Do, recordatorios, replanificacion controlada, manejo defensivo de audio/links/videos/stickers/emojis y persistencia durable de actividades academicas. Las migraciones recientes ya cubren recordatorios por tipo, vinculo durable actividad academica -> Microsoft To Do y deduplicacion durable de webhooks de WhatsApp.

Condiciones minimas que se siguieron para desplegar el piloto:

1. Usar una sola replica (`min=1`, `max=1`).
2. Confirmar variables reales de Azure, Meta y Microsoft, incluido `WHATSAPP_APP_SECRET`.
3. Usar URL publica estable para WhatsApp y Microsoft, no ngrok.
4. Tener aplicadas las migraciones hasta `0023_processed_webhook_messages.sql`.
5. Dejar identificado el job/scheduler que invocara `POST /tasks/reminders/run`.
6. Usar `WHATSAPP_ACCESS_TOKEN` permanente o system-user token; no usar token temporal de Meta.
7. Restringir documentos/media a alcance controlado o aceptar que Blob Storage queda pendiente.
8. Ejecutar smoke test inicial con health check, webhook y envio WhatsApp.

Bloqueantes antes de produccion abierta:

1. Limpiar o reclasificar formalmente la suite completa: al 2026-05-01 hay 65 fallos en 605 pruebas.
2. Ejecutar y documentar staging end-to-end con WhatsApp real, OAuth real, Calendar, To Do y recordatorios.
3. Implementar Blob Storage o una politica productiva clara para media/documentos.
4. Implementar o deshabilitar explicitamente el analisis de documentos academicos; hoy audio/links/videos/stickers/emojis estan normalizados, pero documentos no tienen flujo robusto de descarga/extraccion/validacion academica.
5. Definir plantillas de WhatsApp para recordatorios fuera de la ventana de 24 horas.
6. Agregar monitoreo, alertas, backups verificados y procedimiento de rollback.

## 1. Objetivo Del Informe

Este informe consolida el estado actual del proyecto antes de desplegarlo en Azure y conectarlo a WhatsApp Cloud API. Cubre:

- despliegue de base de datos;
- despliegue del backend;
- configuracion del webhook permanente de WhatsApp;
- flujo de autenticacion OAuth2 con Microsoft;
- sincronizacion con Outlook Calendar;
- sincronizacion con Microsoft To Do;
- recordatorios y jobs operativos;
- riesgos tecnicos que deben cerrarse antes de produccion.

El alcance sigue el MVP definido para el agente academico: agenda, planificacion de estudio, recordatorios, replanificacion automatica controlada y recomendacion personalizada de metodos de estudio.

## 2. Resumen Ejecutivo

El proyecto esta en estado de candidato para piloto controlado, no de produccion abierta. Ya existe una API FastAPI desplegable, un Dockerfile funcional, integracion con WhatsApp Cloud API, flujo OAuth con Microsoft Graph, clientes reales para Outlook Calendar y Microsoft To Do, persistencia en PostgreSQL y migraciones para estado conversacional, Microsoft Graph, planificacion, recordatorios, actividades academicas, deduplicacion de webhooks y RAG.

Cambios relevantes ya incorporados:

- `migrations/0021_activity_reminder_policy_types.sql`: agrega tipos de recordatorio `daily_agenda`, `activity_due` y `activity_overdue`.
- `migrations/0022_academic_activity_todo_task_id.sql`: agrega `todo_task_id` a `academic_activities`, con constraint e indice parcial.
- `migrations/0023_processed_webhook_messages.sql`: agrega deduplicacion durable de mensajes webhook de WhatsApp.
- Validacion HMAC `X-Hub-Signature-256` en `POST /webhook` usando `WHATSAPP_APP_SECRET`.
- Persistencia ReAct de actividades modificadas antes de sincronizar recordatorios.
- Sincronizacion de actividades academicas con Microsoft To Do usando `todo_task_id` como vinculo durable.
- `sync_tasks_to_todo` ya ve actividades creadas/modificadas en el mismo ciclo ReAct mediante acumulador de actualizaciones del turno.
- Normalizacion defensiva de entradas WhatsApp: audio se transcribe con Azure OpenAI; links/videos/stickers/emojis se manejan sin romper el grafo.
- Endpoint operativo `POST /tasks/reminders/run` para disparar recordatorios vencidos desde un scheduler externo.
- `Dockerfile` incluye `scripts/` operativos y excluye `scripts/dev/`, por lo que jobs administrativos basicos pueden existir dentro de la imagen si se decide usarlos.

Antes de abrirlo a los 3 estudiantes del piloto hay ajustes operativos obligatorios:

1. Configurar `MICROSOFT_REDIRECT_URI` para que apunte al callback real del ambiente: `https://<dominio>/oauth/callback`.
2. Registrar exactamente esa URL en Microsoft Entra.
3. Configurar WhatsApp con una URL publica estable, no temporal: `https://<dominio>/webhook`.
4. Usar un token permanente o system-user token de Meta, no un token temporal.
5. Configurar `WHATSAPP_APP_SECRET` para activar la validacion de firma del webhook.
6. Configurar un scheduler/job para `POST /tasks/reminders/run`, agenda diaria y tracking de sesiones vencidas.
7. No escalar a multiples replicas durante el piloto, aunque la deduplicacion de mensajes ya sea durable.
8. Ejecutar pruebas end-to-end en staging con WhatsApp real, Microsoft OAuth real, Calendar y To Do.

## 3. Estado Actual Del Backend

### 3.1 API HTTP

El backend ya expone los endpoints necesarios en `src/api/app.py`:

- `GET /health`: health check para Azure.
- `POST /tasks/reminders/run`: ejecucion protegida de un ciclo de recordatorios vencidos.
- `GET /webhook`: validacion inicial del webhook de Meta mediante `WHATSAPP_VERIFY_TOKEN`.
- `POST /webhook`: recepcion de mensajes entrantes de WhatsApp.
- `GET /oauth/callback`: callback OAuth de Microsoft Graph.

El endpoint de WhatsApp procesa mensajes con `BackgroundTasks`, extrae mensajes entrantes mediante el mapper de WhatsApp y delega en `AgentRunner`.

Estado: funcional para MVP, staging y piloto controlado.

Riesgo: la validacion de firma depende de configurar `WHATSAPP_APP_SECRET`. Si la variable queda vacia, el endpoint registra advertencia y opera sin validacion; eso no debe ocurrir en un ambiente publico.

### 3.2 Docker

El `Dockerfile` usa Python 3.11, instala dependencias con `uv`, copia `src`, `knowledge_base`, `assets` y `main.py`, expone el puerto `8000` y arranca:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Esto encaja bien con Azure Container Apps configurando target port `8000`.

Estado: listo para construir imagen y desplegar. La imagen copia `scripts/` pero excluye `scripts/dev/`, `tests/`, `docs/` y `migrations/`.

Riesgo: el comando fija el puerto `8000`. En Azure Container Apps esta bien si el target port es `8000`. En Azure App Service podria requerir ajuste adicional.

### 3.3 WhatsApp

Existe cliente real para WhatsApp Cloud API en `src/integrations/whatsapp/client.py`. Toma credenciales desde:

- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_GRAPH_API_VERSION`
- `WHATSAPP_GRAPH_BASE_URL`

El servicio de canal `src/services/channels/whatsapp_service.py` puede enviar texto, imagenes y documentos. Si la imagen es local, la sube primero a WhatsApp Cloud API.

Ademas, el canal ahora tiene normalizacion defensiva antes de LangGraph:

- audio: se descarga y se transcribe con Azure OpenAI antes de invocar el agente;
- links: se rechazan con mensaje amigable, sin invocar ReAct;
- videos: se rechazan con mensaje amigable, sin invocar ReAct;
- stickers: se responden como contexto no accionable;
- emojis de confirmacion: se convierten a `si`/`no`;
- otros emojis: reciben respuesta contextual.

Pendiente: documentos academicos. El canal puede representar documentos, pero no hay todavia un flujo productivo completo para descargar, extraer texto, validar que el contenido este dentro del alcance academico y pasarlo al agente de forma segura.

Estado: funcional para integracion real.

Riesgos:

- si `WHATSAPP_APP_SECRET` no se configura, la firma del webhook no se valida;
- la deduplicacion de mensajes de WhatsApp ya puede ser PostgreSQL, pero tiene fallback in-memory si la DB no inicializa;
- con multiples replicas aun conviene introducir cola o validar mas carga/concurrencia antes de escalar;
- los medios locales no son persistentes si el contenedor se reinicia.

### 3.4 OAuth Microsoft

El flujo de OAuth esta implementado:

- `request_microsoft_oauth` genera y envia link de autenticacion al estudiante durante onboarding si `ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=1`.
- `MicrosoftOAuthFlowService` crea `state`, lo persiste y valida el callback.
- `GET /oauth/callback` intercambia el codigo por tokens y muestra una pagina HTML de resultado.
- Los tokens quedan en `microsoft_graph_connections`.

Scopes configurados por defecto:

- `offline_access`
- `openid`
- `profile`
- `User.Read`
- `Calendars.ReadWrite`
- `Tasks.ReadWrite`
- `Mail.Send`

Estado: implementado.

Riesgo critico: `MICROSOFT_REDIRECT_URI` debe coincidir exactamente con la URL registrada en Microsoft Entra. La ruta canonica de la API es `/oauth/callback`; tambien existe un alias legacy `/auth/microsoft/callback`, pero no debe usarse como ruta principal nueva. En el ambiente del piloto debe quedar:

```text
MICROSOFT_REDIRECT_URI=https://<dominio>/oauth/callback
```

La misma URL exacta debe estar registrada en Microsoft Entra.

### 3.5 Outlook Calendar

Existe cliente real `GraphOutlookCalendarClient` y servicio `OutlookCalendarSyncService`. El sistema puede crear, actualizar y eliminar eventos de Outlook, con links durables para evitar duplicados.

Tambien existe sincronizacion de horario fijo mediante `OutlookFixedScheduleSyncService`.

Estado: implementado.

Riesgo funcional: la herramienta directa `sync_plan_to_calendar()` en `academic_agent/tools.py` llama al sync, pero no siempre materializa instancias antes. El flujo conversacional mas robusto de sincronizacion de sesiones si contempla preview, confirmacion y materializacion. Antes de produccion se debe probar el camino real que usara el estudiante.

### 3.6 Microsoft To Do

Existe cliente real `GraphMicrosoftTodoClient` y servicio `MicrosoftTodoSyncService`. El sistema puede crear, actualizar y eliminar tareas en Microsoft To Do.

La proyeccion actual cubre:

- sesiones perdidas u omitidas;
- actividades academicas pendientes;
- links durables en base de datos para evitar duplicados.

Estado: implementado.

Actualizacion 2026-05-01: la migracion `0022_academic_activity_todo_task_id.sql` agrega `todo_task_id` en `academic_activities`. El repositorio `activity_repository.py` ya inserta, lista, retorna y preserva este campo con `COALESCE(EXCLUDED.todo_task_id, academic_activities.todo_task_id)`, evitando perder el vinculo cuando se editan otros campos de la actividad. Esto corrige el riesgo de que el vinculo con To Do viviera solo en el checkpoint de LangGraph.

Riesgo funcional: igual que Calendar, debe validarse el flujo conversacional final desde WhatsApp, no solo los servicios unitarios. El gap de mismo turno entre `add_academic_activity` y `sync_tasks_to_todo` ya fue corregido con acumulador de actualizaciones del ciclo ReAct y esta cubierto por pruebas focalizadas.

### 3.7 Recordatorios

El proyecto tiene servicios para crear politicas de recordatorio y despachar recordatorios pendientes.

Puntos importantes:

- `StudyPlanRemindersService` crea recordatorios persistentes.
- `ReminderDispatchRunner` despacha recordatorios vencidos.
- `scripts/run_due_reminders.py` ejecuta el dispatcher.
- `scripts/mark_missed_sessions.py` puede marcar sesiones vencidas.
- los tipos de recordatorio soportan agenda diaria (`daily_agenda`), actividad proxima (`activity_due`) y actividad vencida (`activity_overdue`).

Estado: implementado a nivel de servicio y con endpoint HTTP operativo para scheduler externo.

Riesgos:

- el backend web no ejecuta estos jobs por si solo;
- en Azure se necesita un Container Apps Job, Azure Function, Logic App o scheduler que invoque `POST /tasks/reminders/run`;
- el endpoint debe protegerse con `ACADEMIC_AGENT_REMINDER_WORKER_TOKEN`;
- si se usan scripts en vez del endpoint HTTP, validar el comando final dentro de la imagen; `scripts/` se copia, pero `scripts/dev/` queda excluido;
- WhatsApp fuera de la ventana de 24 horas requiere plantillas aprobadas por Meta.

Implicacion practica: Lara puede enviar recordatorios y mensajes proactivos solo si el scheduler externo esta activo. Sin ese scheduler, las politicas y dispatches pueden existir en base de datos, pero no se procesan automaticamente.

## 4. Base De Datos

El proyecto usa PostgreSQL para:

- estudiantes;
- onboarding;
- horarios recurrentes;
- actividades academicas;
- planificacion de estudio;
- tracking de sesiones;
- recordatorios;
- conexiones Microsoft Graph;
- links de Outlook Calendar;
- links de Microsoft To Do;
- checkpoints y writes de LangGraph;
- RAG con `pgvector`.

Variables soportadas:

- `ACADEMIC_AGENT_DATABASE_URL`
- `LANGGRAPH_CHECKPOINTER_DATABASE_URL`
- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `PGPASSWORD`

Recomendacion para MVP:

- usar Azure Database for PostgreSQL Flexible Server;
- crear una base para staging y otra para produccion;
- usar `ACADEMIC_AGENT_DATABASE_URL` y `LANGGRAPH_CHECKPOINTER_DATABASE_URL`;
- iniciar usando la misma base para datos operacionales y checkpointing;
- separar mas adelante si el volumen lo exige.

### 4.1 Migraciones

Las migraciones estan en `migrations/`. Hay que aplicarlas en orden controlado.

Punto importante: existen dos archivos con prefijo `0014`. No es un problema si se aplica manualmente en un orden documentado, pero no conviene depender solo del orden alfabetico sin revisarlo.

Si se activa RAG, antes de `0016_rag_study_recommendations.sql` debe habilitarse la extension `vector` en PostgreSQL.

Migraciones recientes obligatorias para este estado del MVP:

- `0021_activity_reminder_policy_types.sql`: actualiza el constraint de `reminder_policies.reminder_type` para soportar recordatorios diarios, de vencimiento de actividad y de actividad vencida.
- `0022_academic_activity_todo_task_id.sql`: agrega `todo_task_id` a `academic_activities`, constraint de longitud e indice parcial para busquedas eficientes.
- `0023_processed_webhook_messages.sql`: crea `processed_webhook_messages` para deduplicar de forma durable los `message_id` recibidos por webhook.

Estado reportado al 2026-05-01: las migraciones correspondientes ya fueron aplicadas en el ambiente preparado para pruebas. En cualquier nuevo ambiente se debe aplicar hasta `0023`.

Comando operativo para aplicar la ultima migracion en un ambiente nuevo:

```bash
psql "$DATABASE_URL" -f migrations/0023_processed_webhook_messages.sql
```

Nota: `migrations/` esta excluido de la imagen Docker por `.dockerignore`. Las migraciones deben aplicarse desde el repositorio, desde CI/CD o desde una tarea administrativa separada, no desde el contenedor runtime actual.

Orden operativo recomendado:

1. Crear base vacia.
2. Habilitar extensiones necesarias, especialmente `vector` si RAG estara activo.
3. Aplicar migraciones SQL.
4. Validar tablas principales.
5. Cargar corpus RAG si aplica.
6. Probar conexion desde el contenedor.

## 5. Plan Paso A Paso De Despliegue

### Paso 1. Cerrar Configuracion Del Piloto

Definir:

- dominio estable de Azure Container Apps para el piloto;
- ambiente `staging` o `pilot`;
- nombre de base de datos del ambiente;
- estrategia de secretos;
- numero de WhatsApp de prueba o final;
- tenant Microsoft que usaran los 3 estudiantes;
- responsable de revisar logs y responder incidentes durante la prueba.

No usar ngrok ni URLs temporales. WhatsApp y Microsoft deben apuntar a un dominio estable porque ambos validan URLs y callbacks.

### Paso 2. Crear Recursos En Azure

Recursos recomendados:

- Resource Group.
- Azure Container Registry.
- Azure Container Apps Environment.
- Azure Database for PostgreSQL Flexible Server.
- Azure Key Vault.
- Log Analytics Workspace.
- Application Insights.
- Storage Account para media.
- Opcional: Azure Service Bus si se quiere desacoplar webhook y procesamiento.

Para MVP se puede iniciar sin Service Bus, pero con una sola replica.

### Paso 3. Preparar PostgreSQL Flexible Server

1. Crear PostgreSQL Flexible Server.
2. Crear base `academic_agent_staging`.
3. Crear base `academic_agent_prod`.
4. Configurar firewall o acceso privado.
5. Habilitar SSL.
6. Habilitar `vector` si RAG estara activo.
7. Aplicar migraciones hasta `0023`.
8. Validar que existan las tablas de:
   - estudiantes;
   - LangGraph checkpoints;
   - Microsoft Graph connections;
   - planificacion;
   - recordatorios;
   - `processed_webhook_messages`;
   - RAG si aplica.

### Paso 4. Construir Y Publicar Imagen

Construir la imagen con el `Dockerfile` actual y publicarla en Azure Container Registry.

La imagen debe correr el backend en puerto `8000`.

Plan inicial:

```bash
az acr build \
  --registry <ACR_NAME> \
  --image academic-agent:<tag> \
  .
```

Resultado real en Azure for Students: ACR Tasks fue bloqueado por la suscripcion con un error de permisos. Por tanto, la ruta usada para el despliegue piloto fue construir localmente con Docker en WSL Ubuntu y subir la imagen manualmente a ACR:

```bash
docker build -t laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001 .
docker push laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001
```

Esta ruta evita depender de ACR Tasks. Para futuras correcciones del piloto se debe repetir el mismo patron con un tag nuevo, por ejemplo `pilot-002`, y luego actualizar la Container App.

Validaciones:

- la imagen arranca;
- `/health` responde;
- el contenedor tiene acceso a variables de entorno;
- el contenedor puede conectar a PostgreSQL;
- el contenedor puede llamar a Azure OpenAI;
- el contenedor puede llamar a Meta Graph API;
- el contenedor puede llamar a Microsoft Graph.

### Paso 5. Crear Azure Container App

Configuracion inicial recomendada para piloto:

- Ingress externo habilitado.
- Target port: `8000`.
- Min replicas: `1`.
- Max replicas: `1`.
- CPU y memoria segun carga de LangGraph y modelo.
- Secrets desde Key Vault o secretos de Container Apps.
- Logs conectados a Log Analytics.

Razon para una sola replica: aunque la deduplicacion de webhooks ya es durable en PostgreSQL, todavia hay estado operacional auxiliar, media local, procesamiento en background y falta de pruebas de carga/concurrencia. Escalar debe quedar para despues del piloto.

### Paso 6. Configurar Variables De Entorno

Variables minimas:

```text
ACADEMIC_AGENT_DATABASE_URL=postgresql://...
LANGGRAPH_CHECKPOINTER_DATABASE_URL=postgresql://...

AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_DEPLOYMENT_NAME=...
AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS=...
OPENAI_API_VERSION=...

AZURE_OPENAI_API_KEY_TRANSCRIBE=...
AZURE_OPENAI_ENDPOINT_TRANSCRIBE=...
AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE=...
OPENAI_API_VERSION_TRANSCRIBE=...

WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_BUSINESS_ACCOUNT_ID=...
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_APP_SECRET=...
WHATSAPP_GRAPH_API_VERSION=v20.0
WHATSAPP_GRAPH_BASE_URL=https://graph.facebook.com

MS_CLIENT_ID=...
MS_CLIENT_SECRET=...
MS_TENANT_ID=...
MICROSOFT_REDIRECT_URI=https://<dominio>/oauth/callback

ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=1
ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION=1
ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS=1
ACADEMIC_AGENT_REMINDER_CHANNELS=whatsapp
ACADEMIC_AGENT_REMINDER_WORKER_TOKEN=...
```

Variables recomendadas adicionales:

```text
LOG_LEVEL=INFO
ACADEMIC_AGENT_MEDIA_DIR=/app/.langgraph_media
ACADEMIC_AGENT_REMINDER_DISPATCH_MAX_ATTEMPTS=3
ACADEMIC_AGENT_REMINDER_RETRY_DELAY_MINUTES=10
MEDIA_INLINE_PREVIEW=false
```
`WHATSAPP_APP_SECRET` es obligatorio en un endpoint publico. Si no se configura, el webhook POST no valida `X-Hub-Signature-256`.

`WHATSAPP_ACCESS_TOKEN` debe ser un token permanente o system-user token administrado desde Meta Business. No usar el token temporal del panel de Meta Developers porque vence y dejaria al agente sin capacidad de responder o enviar recordatorios. Para el piloto, guardar el token como secreto de Azure, no en `.env` versionado, y rotarlo si se uso durante pruebas manuales.

### Paso 7. Configurar Microsoft Entra

1. Ir a App registrations.
2. Registrar o abrir la aplicacion existente.
3. Configurar Redirect URI web:

```text
https://<dominio>/oauth/callback
```

4. Confirmar que coincide exactamente con `MICROSOFT_REDIRECT_URI`.
5. Configurar permisos delegados:
   - `User.Read`
   - `Calendars.ReadWrite`
   - `Tasks.ReadWrite`
   - `offline_access`
   - `openid`
   - `profile`
   - `Mail.Send` si se usara correo.
6. Revisar si el tenant requiere admin consent.
7. Probar con un estudiante real o cuenta de prueba institucional.

Flujo esperado:

1. Estudiante escribe por WhatsApp.
2. Lara completa onboarding minimo.
3. Lara envia link de autenticacion Microsoft.
4. Estudiante abre el link.
5. Microsoft redirige a `/oauth/callback`.
6. El backend guarda tokens.
7. Estudiante vuelve a WhatsApp y continua.

### Paso 8. Configurar WhatsApp Cloud API

1. En Meta Developers, configurar callback URL:

```text
https://<dominio>/webhook
```

2. Configurar verify token igual a `WHATSAPP_VERIFY_TOKEN`.
3. Suscribir eventos de `messages`.
4. Usar `WHATSAPP_ACCESS_TOKEN` permanente o system-user token, almacenado como secreto.
5. Probar verificacion GET.
6. Probar envio de mensaje entrante con firma valida.
7. Probar que una firma invalida devuelve `403`.
8. Probar respuesta del agente.
9. Probar envio de audio e imagen si el flujo lo requiere.
10. Probar reintento/duplicado de webhook y confirmar que no duplica acciones criticas.
11. Validar que el token no sea temporal revisando su origen en Meta Business y ejecutando una prueba de envio despues de reiniciar el contenedor.

Resultado real del piloto:

- se configuro un System User en Meta;
- se asignaron permisos a la app y a la cuenta de WhatsApp;
- se genero un token permanente;
- se evito el token temporal de 24 horas;
- se configuro el numero de prueba;
- `GET /webhook` respondio HTTP 200;
- el envio directo por Graph API respondio HTTP 200 y retorno un `messages.id`.

### Paso 9. Configurar Jobs De Recordatorios

Crear uno o mas jobs/schedulers externos. El backend no tiene un loop interno que despierte solo; Azure debe invocarlo periodicamente.

Jobs minimos para el piloto:

- dispatch de recordatorios vencidos: invocar `POST /tasks/reminders/run`.
- tracking de sesiones vencidas: ejecutar `scripts/mark_missed_sessions.py` o entrypoint equivalente.

Jobs recomendados si se activa agenda diaria:

- agenda diaria temprano en la manana: generar/despachar recordatorios `daily_agenda` para materias, sesiones y actividades pendientes del dia.
- mantenimiento de deduplicacion: limpiar `processed_webhook_messages` antiguos si se quiere controlar crecimiento de tabla.

Para recordatorios, el camino recomendado en el estado actual es invocar el endpoint HTTP protegido:

```text
POST https://<dominio>/tasks/reminders/run?limit=50
Header: x-reminder-worker-token: <ACADEMIC_AGENT_REMINDER_WORKER_TOKEN>
```

Frecuencia sugerida para piloto:

- recordatorios vencidos: cada 5 o 10 minutos.
- agenda diaria: una vez al dia, por ejemplo 06:30 America/Bogota.
- sesiones vencidas: cada 15 o 30 minutos.

Esto evita acoplar el scheduler al comando interno de la imagen runtime.

Estado actual: el `Dockerfile` copia `scripts/`, mientras `.dockerignore` excluye `scripts/dev/`. Por tanto, los scripts operativos como `scripts/run_due_reminders.py` y `scripts/mark_missed_sessions.py` pueden estar en la imagen. Aun asi, para el piloto el camino mas simple es invocar el endpoint HTTP protegido desde un scheduler externo.

Para sesiones vencidas, usar `scripts/mark_missed_sessions.py` desde un Container Apps Job o mover el entrypoint a `src/` si se quiere una interfaz mas estable.

Mensaje "buenos dias": el informe considera este caso como agenda diaria. Para que funcione en piloto, debe existir un job que dispare el flujo `daily_agenda` y el canal WhatsApp debe poder enviar el mensaje. Si el mensaje se envia fuera de la ventana de 24 horas de WhatsApp, puede requerir plantilla aprobada por Meta.

### Paso 10. Configurar Media Persistente

La carpeta local de media sirve para desarrollo, pero en Container Apps no debe asumirse persistente.

Para produccion:

- guardar imagenes y documentos en Azure Blob Storage;
- guardar en el estado solo referencias livianas;
- definir politica de retencion;
- no guardar base64 en checkpoints.

Para el piloto de 3 estudiantes se puede probar con disco local si se documenta la limitacion: reinicios del contenedor pueden perder archivos locales. Para produccion real con documentos/imagenes de estudiantes, Blob Storage debe entrar antes de escalar o antes de asumir persistencia de media.

### Paso 11. Pruebas End-To-End En Staging

Checklist minimo:

1. `GET /health` responde OK.
2. Meta valida `GET /webhook`.
3. WhatsApp envia mensaje y el backend responde.
4. WhatsApp reintenta un mensaje y no genera doble accion critica.
5. Onboarding pide datos minimos.
6. Lara envia link OAuth Microsoft.
7. El link abre Microsoft.
8. El callback `/oauth/callback` se ejecuta correctamente.
9. Se crea registro en `microsoft_graph_connections`.
10. Lara puede continuar despues del OAuth.
11. Se crea horario fijo y aparece en Outlook Calendar.
12. Se crea actividad academica y aparece en Microsoft To Do si el flujo lo permite.
13. Se genera plan semanal de estudio.
14. Las sesiones se materializan.
15. Las sesiones se sincronizan a Outlook.
16. Un recordatorio se crea en DB.
17. El job de recordatorios lo despacha.
18. La agenda diaria genera o despacha un mensaje de buenos dias con materias/sesiones/pendientes del dia, si se activa este job.
19. Una sesion perdida se marca como `missed`.
20. La replanificacion controlada no duplica eventos ni tareas.
21. Logs no exponen tokens, correos completos, telefonos ni payloads sensibles.

### Paso 12. Promocion A Produccion Abierta

Antes de produccion:

- congelar version de imagen;
- aplicar migraciones hasta `0023` en produccion;
- revisar backups de PostgreSQL;
- configurar alertas;
- configurar dominio estable;
- validar TLS;
- registrar redirect URI final en Microsoft;
- configurar webhook final en Meta;
- rotar tokens si fueron usados en pruebas;
- ejecutar smoke test con un usuario controlado;
- habilitar usuarios reales gradualmente.

## 6. Riesgos Bloqueantes Y Mitigacion

| Riesgo | Impacto | Mitigacion |
| --- | --- | --- |
| Redirect URI incorrecto | OAuth falla en produccion | Usar `https://<dominio>/oauth/callback` en env y Microsoft Entra |
| Token temporal de WhatsApp | La API dejara de responder cuando venza el token | Usar token permanente o system-user token en secretos de Azure |
| `WHATSAPP_APP_SECRET` no configurado | Endpoint publico sin validacion de firma | Configurar secret real y probar firma invalida `403` |
| Fallback de deduplicacion in-memory | Duplicados si PostgreSQL no inicializa | Confirmar logs: "Deduplicacion de webhooks: PostgreSQL activo" |
| Media local en contenedor | Perdida de archivos al reiniciar | Migrar a Azure Blob Storage |
| Jobs no desplegados | No salen recordatorios ni tracking vencido | Crear Container Apps Jobs |
| Scripts operativos no programados | Jobs existen pero no se ejecutan solos | Usar endpoint HTTP protegido o Container Apps Job |
| WhatsApp fuera de ventana 24h | Recordatorios libres pueden fallar | Crear plantillas aprobadas por Meta |
| Sync Calendar sin materializacion previa | Puede no crear sesiones esperadas | Usar flujo de sync con materializacion y confirmacion |
| Tests no estan 100% limpios | Riesgo de regresion antes de release | Corregir tests o confirmar cambio esperado |

## 7. Resultados De Verificacion Local

Se reviso la configuracion y se ejecutaron pruebas locales el 2026-05-01.

Resultado relevante:

- Pruebas focalizadas de la ruta critica de despliegue: `33 passed`.
  - firma HMAC webhook;
  - deduplicacion durable de webhooks;
  - visibilidad de estado en el mismo ciclo ReAct;
  - Microsoft To Do;
  - OAuth routes.
- Suite completa actual: `540 passed, 65 failed` sobre `605` pruebas.

Comando focalizado ejecutado:

```bash
uv run --with pytest python -m pytest \
  tests/test_webhook_signature.py \
  tests/test_webhook_dedup.py \
  tests/test_react_cycle_state_visibility.py \
  tests/test_microsoft_todo_service.py \
  tests/test_api_oauth_routes.py
```

Categorias principales de fallos de la suite completa:

- tests antiguos esperando `events` como campo derivado legacy;
- expectativas de router con nombres de intent/domain anteriores;
- tests que esperan mensajes de texto plano, pero ahora hay contenido multimodal `text + image_url`;
- flujos de planificacion que esperaban `phase=end` y ahora conservan `phase=running`;
- guardrails/refactor tests desalineados con la arquitectura actual;
- dos tests de WhatsApp esperan `input_image`, mientras el formato actual usa `image_url`.
- tests que esperan scripts antiguos en `scripts/`, aunque algunos pasaron a `scripts/dev/`.

Interpretacion: los servicios criticos recientes estan cubiertos y pasan, pero la suite completa no esta limpia. Esto no bloquea un piloto controlado de 3 estudiantes si se monitorea de cerca y se acepta el riesgo, pero si bloquea promocion a produccion abierta hasta decidir si esos 65 fallos son cambios esperados que requieren actualizar tests, o regresiones reales que deben corregirse.

## 8. Recomendaciones De Implementacion Antes De Produccion

Prioridad alta antes del piloto:

1. Configurar `MICROSOFT_REDIRECT_URI` real.
2. Registrar callback exacto en Microsoft Entra.
3. Configurar `WHATSAPP_APP_SECRET` y probar firma invalida.
4. Confirmar Azure PostgreSQL con migraciones hasta `0023`.
5. Crear Container App con una replica inicial.
6. Configurar WhatsApp con URL estable.
7. Probar OAuth completo desde WhatsApp.
8. Configurar scheduler para `POST /tasks/reminders/run`, sesiones vencidas y agenda diaria si se usara.
9. Confirmar que `WHATSAPP_ACCESS_TOKEN` es permanente/system-user y no temporal.
10. Ejecutar smoke test end-to-end con una cuenta real antes de invitar a los 3 estudiantes.
11. Documentar limitacion de media/documentos durante el piloto.

Prioridad alta antes de produccion abierta:

1. Limpiar o reclasificar los 65 fallos de la suite completa.
2. Migrar media a Azure Blob Storage.
3. Definir plantillas WhatsApp para recordatorios fuera de 24 horas.
4. Separar worker de webhook usando cola si se escala a multiples replicas.
5. Agregar dashboards, alertas, backups verificados y procedimiento de rollback.

Prioridad posterior:

1. Separar DB operacional y checkpointing si crece el trafico.
2. Agregar pruebas de carga.
3. Automatizar despliegue con GitHub Actions o Azure DevOps.
4. Separar ambientes `staging`, `pilot` y `production` si el piloto crece.

## 9. Arquitectura Recomendada Para MVP En Azure

```text
WhatsApp Cloud API
        |
        v
Azure Container Apps - Backend FastAPI/LangGraph
        |
        +--> Azure Database for PostgreSQL Flexible Server
        |        - datos academicos
        |        - checkpoints LangGraph
        |        - conexiones Microsoft Graph
        |        - links Calendar/To Do
|        - recordatorios
|        - RAG con pgvector cargado
        |
        +--> Azure OpenAI
        |
        +--> Microsoft Graph
        |        - Outlook Calendar
        |        - Microsoft To Do
        |
        +--> Azure Blob Storage
        |        - imagenes
        |        - documentos
        |
        +--> Log Analytics / Application Insights

Azure Container Apps Jobs
        |
        +--> dispatch de recordatorios
        +--> agenda diaria / mensaje de buenos dias
        +--> tracking de sesiones vencidas
```

## 10. Decision Recomendada

La ruta recomendada para siguientes redeploys del piloto es:

1. Hacer cambios en codigo.
2. Ejecutar pruebas focalizadas.
3. Construir imagen localmente con Docker en WSL.
4. Subir imagen a ACR con `docker push`.
5. Actualizar Azure Container App con el nuevo tag.
6. Validar `/health`.
7. Validar webhook y conversacion WhatsApp.
8. Monitorear logs durante la prueba.
9. Limpiar la suite completa o documentar formalmente los cambios esperados de tests antes de produccion abierta.
10. Promover a produccion abierta solo despues de cerrar media, plantillas, monitoreo y smoke test real.
11. Escalar replicas solo despues de validar cola/concurrencia/media.

Conclusion: el piloto ya fue desplegado y esta operativo para pruebas por WhatsApp. Debe considerarse un piloto/staging controlado, con una sola replica y monitoreo manual. Los recordatorios y mensajes de buenos dias dependen de que el scheduler externo este configurado; el token de WhatsApp debe ser permanente o system-user para no vencer diariamente. Para produccion abierta todavia faltan suite limpia o reclasificada, smoke test ampliado documentado, estrategia final de media/documentos, plantillas WhatsApp y operacion basica de monitoreo/rollback.

## 11. Referencias Oficiales

- Azure Container Apps: https://learn.microsoft.com/en-us/azure/container-apps/overview
- Custom domains en Azure Container Apps: https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-certificates
- Azure Container Apps Jobs: https://learn.microsoft.com/en-us/azure/container-apps/jobs
- Azure PostgreSQL Flexible Server: https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview
- pgvector en Azure PostgreSQL: https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgvector
- Microsoft OAuth authorization code flow: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
- Microsoft Graph permissions: https://learn.microsoft.com/en-us/graph/permissions-reference
- WhatsApp Cloud API Webhooks: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
- WhatsApp Cloud API messages: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
