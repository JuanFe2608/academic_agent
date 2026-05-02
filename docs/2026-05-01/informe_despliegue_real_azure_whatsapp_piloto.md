# Informe De Despliegue Real Azure + WhatsApp - Piloto Lara

Fecha: 2026-05-01

## 1. Resumen Ejecutivo

El agente academico Lara quedo desplegado en Azure Container Apps y conectado a WhatsApp Cloud API para una prueba piloto. El backend esta publico y responde correctamente en `/health`:

```text
https://ca-lara-academic-agent-pilot.greenriver-35e70b6b.canadacentral.azurecontainerapps.io/health
```

Respuesta validada:

```json
{"status":"ok","agent":"ready"}
```

El webhook de WhatsApp tambien quedo configurado y validado por Meta mediante `GET /webhook`. Ademas, se probo envio directo por WhatsApp Cloud API hacia el numero de prueba configurado.

El despliegue tuvo una desviacion importante frente al plan inicial: Azure for Students permitio usar Azure Container Registry y Azure Container Apps, pero bloqueo la construccion remota con ACR Tasks. Por eso la imagen Docker se construyo localmente en WSL Ubuntu y se subio manualmente al registry con `docker push`.

## 2. Resultado Final Del Piloto

Recursos y estado final:

| Componente | Estado |
| --- | --- |
| Cloud Shell | Funcional sin storage persistente |
| PostgreSQL Flexible Server | Creado en Canada Central |
| Base de datos | `academic_agent` creada y migrada |
| Migraciones | Aplicadas correctamente |
| RAG / pgvector | Extension habilitada, schema migrado y corpus cargado |
| Azure Container Registry | Creado y usado para almacenar imagen |
| Construccion de imagen | Realizada con Docker local en WSL |
| Azure Container Apps | Backend desplegado y publico |
| WhatsApp Cloud API | Webhook configurado y prueba de envio OK |
| Token WhatsApp | System User token permanente |
| Health check | `{"status":"ok","agent":"ready"}` |

URL publica del backend:

```text
https://ca-lara-academic-agent-pilot.greenriver-35e70b6b.canadacentral.azurecontainerapps.io
```

Endpoints principales:

```text
GET  /health
GET  /webhook
POST /webhook
GET  /oauth/callback
POST /tasks/reminders/run
```

## 3. Consideraciones De Seguridad

Durante el despliegue se usaron credenciales reales de Azure, PostgreSQL, Meta/WhatsApp y Microsoft. En este informe no se documentan valores secretos.

Datos que no deben quedar versionados ni publicados:

- `ACADEMIC_AGENT_DATABASE_URL`
- password de PostgreSQL
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_APP_SECRET`
- `WHATSAPP_VERIFY_TOKEN`
- `MS_CLIENT_SECRET`
- `ACADEMIC_AGENT_REMINDER_WORKER_TOKEN`
- numeros personales completos de WhatsApp

El numero de prueba usado fue un numero personal, pero debe tratarse como dato sensible. Para documentacion se debe escribir enmascarado, por ejemplo:

```text
57318****206
```

Si algun secreto se pego en chats, logs, capturas o documentos compartidos, se recomienda rotarlo antes de ampliar la prueba.

## 4. Flujo Real Ejecutado

### 4.1 Cloud Shell

Se intento iniciar Cloud Shell con almacenamiento persistente, pero la cuenta institucional con suscripcion Azure for Students tuvo restricciones de region o permisos.

La solucion fue usar Cloud Shell con la opcion:

```text
No storage account required
```

Esto dejo Cloud Shell funcional, pero efimero. La terminal mostro una advertencia indicando que los archivos y cambios locales no persisten entre sesiones.

Validaciones realizadas:

```bash
az version
az account show
az account list --output table
```

Resultado:

- Azure CLI disponible.
- Suscripcion activa: Azure for Students.
- Usuario autenticado con cuenta institucional.

Implicacion: Cloud Shell sirvio para ejecutar comandos de Azure y validaciones, pero no como ubicacion permanente del proyecto.

### 4.2 PostgreSQL En Azure

Se intento crear PostgreSQL Flexible Server en varias regiones. Algunas fallaron por restricciones de Azure for Students.

La region que funciono fue:

```text
Canada Central
```

Servidor creado:

```text
pg-academic-agent-pilot.postgres.database.azure.com
```

Resource Group:

```text
rg-academic-agent-pilot
```

Base usada:

```text
academic_agent
```

Se valido conexion con `psql` usando SSL:

```bash
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "SELECT version();"
```

Luego se aplicaron migraciones SQL desde el repositorio.

Validacion de tablas:

```bash
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "\dt"
```

Tablas principales creadas:

```text
academic_activities
academic_programs
email_verification_challenges
langgraph_checkpoint_writes
langgraph_thread_checkpoints
microsoft_graph_connections
microsoft_oauth_pending_states
microsoft_todo_task_links
outlook_calendar_event_links
processed_webhook_messages
recurring_schedule_blocks
reminder_dispatches
reminder_policies
schedule_conflicts
schedule_profiles
students
study_personalization_answers
study_personalization_profiles
study_personalization_scores
study_plan_event_instances
study_plan_events
study_plan_profiles
study_priority_profiles
study_priority_subjects
study_replan_proposals
study_replan_requests
study_session_checkins
```

Conclusion: la base quedo lista para persistencia operacional, checkpoints de LangGraph, OAuth Microsoft, planificacion, recordatorios, To Do y deduplicacion de webhooks.

### 4.2.1 RAG / pgvector

Despues de validar las tablas operacionales, se reviso si la base vectorial habia quedado migrada.

Validaciones iniciales:

```bash
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "\dn"
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "\dt rag.*"
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

Resultado inicial:

- solo existia el schema `public`;
- no existian relaciones `rag.*`;
- la extension `vector` no estaba habilitada.

Por tanto, la parte operacional de la base si estaba migrada, pero RAG/pgvector todavia no.

Para resolverlo, se ajustaron permisos/configuracion del recurso PostgreSQL Flexible Server:

```text
pg-academic-agent-pilot
```

Luego se habilito la extension `vector` y se aplico la migracion RAG:

```bash
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql "$ACADEMIC_AGENT_DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0016_rag_study_recommendations.sql
```

Despues se sincronizo el corpus de recomendaciones de estudio y se generaron embeddings:

```bash
python scripts/dev/build_rag_corpus.py --sync-db --embed-changed
```

Resultado de la ingesta:

```text
RAG corpus build
- documents: 15
- chunks: 468
- relations: 355
- issues: 0
- db_sync: completed
- ingestion_run_id: 1
- run_id: study_recommendations.f678a2bbcf32b0ab19de77c8

- embed_changed: completed
- requested_chunks: 468
- embedded_chunks: 468
- updated_chunks: 468
- skipped_chunks: 0
```

Validacion final:

```bash
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "
SELECT 'rag.documents' AS table_name, COUNT(*) FROM rag.documents
UNION ALL
SELECT 'rag.chunks', COUNT(*) FROM rag.chunks
UNION ALL
SELECT 'rag.relations', COUNT(*) FROM rag.relations
UNION ALL
SELECT 'rag.chunks_with_embedding', COUNT(*) FROM rag.chunks WHERE embedding IS NOT NULL;
"
```

Resultado:

```text
        table_name         | count
---------------------------+-------
 rag.documents             |    15
 rag.chunks                |   468
 rag.relations             |   355
 rag.chunks_with_embedding |   468
```

Conclusion: la base vectorial quedo migrada y cargada correctamente. El agente ya puede usar recuperacion RAG/vectorial para recomendaciones personalizadas de metodos de estudio.

### 4.3 WhatsApp Cloud API

Se ajusto la configuracion en Meta:

1. Se creo o ajusto un System User.
2. Se asignaron permisos a la app.
3. Se asignaron permisos a la cuenta de WhatsApp.
4. Se genero un token permanente.
5. Se evito usar el token temporal de 24 horas.
6. Se configuro el numero de prueba con el numero personal autorizado.
7. Se configuro el webhook del backend en Meta.

El uso de System User token fue clave porque el token temporal del panel de Meta vence y dejaria al backend sin capacidad de enviar mensajes.

Variables relevantes:

```text
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_BUSINESS_ACCOUNT_ID
WHATSAPP_ACCESS_TOKEN
WHATSAPP_VERIFY_TOKEN
WHATSAPP_APP_SECRET
WHATSAPP_GRAPH_API_VERSION
WHATSAPP_GRAPH_BASE_URL
```

Validacion del webhook:

```bash
curl -i "https://<backend>/webhook?hub.mode=subscribe&hub.verify_token=<VERIFY_TOKEN>&hub.challenge=12345"
```

Resultado esperado y observado:

```text
HTTP/2 200
content-type: text/plain; charset=utf-8

12345
```

Prueba de envio directo por Graph API:

```bash
curl -i -X POST "https://graph.facebook.com/v25.0/<PHONE_NUMBER_ID>/messages" \
  -H "Authorization: Bearer $WHATSAPP_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "<NUMERO_PRUEBA>",
    "type": "text",
    "text": {
      "body": "Mensaje de prueba directo"
    }
  }'
```

Resultado observado:

```text
HTTP/2 200
```

La respuesta incluyo `contacts`, `wa_id` y un `messages.id` tipo `wamid...`, lo cual confirma que WhatsApp Cloud API acepto el envio.

### 4.4 Azure Container Apps

Se creo el Container Apps Environment.

El plan inicial era construir la imagen directamente en Azure Container Registry con ACR Tasks, usando un comando del estilo:

```bash
az acr build \
  --registry <ACR_NAME> \
  --image academic-agent:pilot-001 \
  .
```

Pero Azure for Students bloqueo esa operacion con un error del tipo:

```text
ACR Tasks requests ... are not permitted
```

Interpretacion: la suscripcion permitia tener ACR y Container Apps, pero no permitia usar el servicio administrado de build remoto de ACR Tasks.

### 4.5 Construccion Con Docker Local En WSL

Como solucion, se construyo la imagen localmente desde WSL Ubuntu usando Docker.

Desde la raiz del repositorio local:

```bash
docker build -t laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001 .
```

Luego se subio manualmente al registry:

```bash
docker push laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001
```

Esto resolvio el bloqueo de ACR Tasks porque Azure ya no construyo la imagen; solo recibio una imagen ya construida.

### 4.6 Creacion De La Container App

Con la imagen ya subida al registry, se creo la Container App apuntando a:

```text
laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001
```

Configuracion aplicada:

- ingress externo habilitado;
- target port `8000`;
- una sola replica para piloto;
- variables de entorno y secretos cargados;
- conexion a PostgreSQL mediante `ACADEMIC_AGENT_DATABASE_URL`;
- token permanente de WhatsApp;
- secretos Microsoft Graph;
- `WHATSAPP_APP_SECRET` para firma del webhook;
- `ACADEMIC_AGENT_REMINDER_WORKER_TOKEN` para proteger recordatorios.

URL publica resultante:

```text
https://ca-lara-academic-agent-pilot.greenriver-35e70b6b.canadacentral.azurecontainerapps.io
```

Health check:

```bash
curl "https://ca-lara-academic-agent-pilot.greenriver-35e70b6b.canadacentral.azurecontainerapps.io/health"
```

Resultado:

```json
{"status":"ok","agent":"ready"}
```

Conclusion: el backend quedo desplegado, con FastAPI activo y `AgentRunner` inicializado.

## 5. Paso A Paso Reproducible

Esta seccion documenta el proceso que debe seguirse si se necesita repetir el despliegue o crear una nueva revision.

### Paso 1. Preparar Variables Locales

En `.env`, configurar secretos y runtime:

```text
ACADEMIC_AGENT_DATABASE_URL=postgresql://<user>:<password>@<host>/<db>?sslmode=require
LANGGRAPH_CHECKPOINTER_DATABASE_URL=postgresql://<user>:<password>@<host>/<db>?sslmode=require

AZURE_OPENAI_API_KEY=<secret>
AZURE_OPENAI_ENDPOINT=<endpoint>
AZURE_OPENAI_DEPLOYMENT_NAME=<deployment>
AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS=<deployment>
OPENAI_API_VERSION=<version>

WHATSAPP_PHONE_NUMBER_ID=<id>
WHATSAPP_BUSINESS_ACCOUNT_ID=<id>
WHATSAPP_ACCESS_TOKEN=<system-user-token>
WHATSAPP_VERIFY_TOKEN=<verify-token>
WHATSAPP_APP_SECRET=<app-secret>

MS_CLIENT_ID=<client-id>
MS_CLIENT_SECRET=<secret>
MS_TENANT_ID=<tenant-id>
MICROSOFT_REDIRECT_URI=https://<backend>/oauth/callback

ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=1
ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION=1
ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS=1
ACADEMIC_AGENT_REMINDER_CHANNELS=whatsapp
ACADEMIC_AGENT_REMINDER_WORKER_TOKEN=<secret>
```

### Paso 2. Validar Base De Datos

```bash
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "\dt"
```

Verificar que exista:

```text
processed_webhook_messages
langgraph_thread_checkpoints
langgraph_checkpoint_writes
students
academic_activities
reminder_policies
reminder_dispatches
microsoft_graph_connections
```

Validar tambien RAG/vectorial:

```bash
psql "$ACADEMIC_AGENT_DATABASE_URL" -c "
SELECT 'rag.documents' AS table_name, COUNT(*) FROM rag.documents
UNION ALL
SELECT 'rag.chunks', COUNT(*) FROM rag.chunks
UNION ALL
SELECT 'rag.relations', COUNT(*) FROM rag.relations
UNION ALL
SELECT 'rag.chunks_with_embedding', COUNT(*) FROM rag.chunks WHERE embedding IS NOT NULL;
"
```

Resultado esperado del piloto:

```text
rag.documents             | 15
rag.chunks                | 468
rag.relations             | 355
rag.chunks_with_embedding | 468
```

### Paso 3. Login En ACR Desde Docker Local

Si se usa Docker local:

```bash
az acr login --name laraacademicpilot20260501
```

O login manual si Azure CLI no esta disponible en la terminal local:

```bash
docker login laraacademicpilot20260501.azurecr.io
```

### Paso 4. Construir Imagen Local

Desde la raiz del repositorio:

```bash
docker build -t laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001 .
```

Para una nueva revision:

```bash
docker build -t laraacademicpilot20260501.azurecr.io/academic-agent:pilot-002 .
```

### Paso 5. Subir Imagen A ACR

```bash
docker push laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001
```

Para una nueva revision:

```bash
docker push laraacademicpilot20260501.azurecr.io/academic-agent:pilot-002
```

### Paso 6. Actualizar Container App

Para cambiar a una nueva imagen:

```bash
az containerapp update \
  --name ca-lara-academic-agent-pilot \
  --resource-group rg-academic-agent-pilot-ca \
  --image laraacademicpilot20260501.azurecr.io/academic-agent:pilot-002
```

### Paso 7. Validar Health

```bash
curl "https://ca-lara-academic-agent-pilot.greenriver-35e70b6b.canadacentral.azurecontainerapps.io/health"
```

Resultado esperado:

```json
{"status":"ok","agent":"ready"}
```

### Paso 8. Validar Webhook De WhatsApp

```bash
curl -i "https://ca-lara-academic-agent-pilot.greenriver-35e70b6b.canadacentral.azurecontainerapps.io/webhook?hub.mode=subscribe&hub.verify_token=<VERIFY_TOKEN>&hub.challenge=12345"
```

Resultado esperado:

```text
HTTP/2 200

12345
```

### Paso 9. Validar Envio WhatsApp

```bash
curl -i -X POST "https://graph.facebook.com/v25.0/<PHONE_NUMBER_ID>/messages" \
  -H "Authorization: Bearer $WHATSAPP_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "<NUMERO_PRUEBA>",
    "type": "text",
    "text": {
      "body": "Mensaje de prueba directo"
    }
  }'
```

Resultado esperado:

```text
HTTP/2 200
```

### Paso 10. Probar Conversacion Real

Desde el numero autorizado como tester en WhatsApp:

1. Enviar un mensaje inicial al numero de prueba de WhatsApp Cloud API.
2. Confirmar que el webhook recibe el evento.
3. Confirmar que Lara responde.
4. Completar onboarding.
5. Probar OAuth Microsoft.
6. Crear una actividad academica.
7. Probar planificacion o recomendacion de metodo de estudio.

## 6. Como Corregir Y Redesplegar

Para una correccion de codigo:

1. Editar codigo.
2. Ejecutar pruebas focalizadas.
3. Construir nueva imagen con tag nuevo.
4. Subir imagen a ACR.
5. Actualizar Container App.
6. Validar `/health`.
7. Probar WhatsApp.

Ejemplo:

```bash
docker build -t laraacademicpilot20260501.azurecr.io/academic-agent:pilot-002 .
docker push laraacademicpilot20260501.azurecr.io/academic-agent:pilot-002

az containerapp update \
  --name ca-lara-academic-agent-pilot \
  --resource-group rg-academic-agent-pilot-ca \
  --image laraacademicpilot20260501.azurecr.io/academic-agent:pilot-002
```

Rollback:

```bash
az containerapp update \
  --name ca-lara-academic-agent-pilot \
  --resource-group rg-academic-agent-pilot-ca \
  --image laraacademicpilot20260501.azurecr.io/academic-agent:pilot-001
```

## 7. Diferencias Frente Al Plan Inicial

| Punto | Plan inicial | Ejecucion real |
| --- | --- | --- |
| Cloud Shell | Usar Cloud Shell con storage | Se uso Cloud Shell efimero sin storage |
| Region PostgreSQL | Region inicial flexible | Canada Central por restricciones Azure for Students |
| Base de datos | Crear y migrar PostgreSQL | Ejecutado correctamente |
| Build imagen | `az acr build` con ACR Tasks | Bloqueado por Azure for Students |
| Alternativa build | No era el camino principal | Docker local en WSL + `docker push` |
| WhatsApp token | Token permanente recomendado | System User token permanente configurado |
| Webhook | Configurar en Meta | Configurado y validado HTTP 200 |
| Backend | Azure Container Apps | Desplegado y listo |

## 8. Estado Final

El despliegue piloto quedo operativo:

- backend publico en Azure Container Apps;
- `/health` responde `ready`;
- PostgreSQL migrado;
- RAG/pgvector migrado y corpus de recomendaciones cargado;
- webhook de WhatsApp validado;
- envio directo por WhatsApp Cloud API probado;
- token permanente de WhatsApp configurado;
- imagen almacenada en Azure Container Registry;
- ruta de redeploy definida con Docker local y `docker push`.

Este informe documenta el procedimiento real que se siguio para desplegar el agente Lara en Azure bajo las restricciones de Azure for Students.
