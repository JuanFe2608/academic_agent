# Informe: ruta recomendada para desplegar el agente con WhatsApp en Azure

Fecha: 2026-04-15

## 1. Respuesta corta

La mejor ruta no es desplegar primero WhatsApp ni subir todo a Meta. WhatsApp solo será el canal externo. Lo que debe desplegarse es el backend del agente académico, su base de datos, su almacenamiento de medios, sus secretos y su observabilidad.

Orden recomendado:

1. Cerrar el comportamiento del agente en local y staging: onboarding, captura de horarios por texto/imagen, planificación, recordatorios, replanificación y límites de alcance.
2. Completar el RAG si sus respuestas van a depender de material académico o recomendaciones justificadas. Si RAG no afecta el flujo crítico inicial, puede entrar como fase controlada, pero no debería lanzarse públicamente con respuestas no verificadas.
3. Endurecer seguridad, persistencia, media e idempotencia.
4. Containerizar el backend.
5. Desplegar en Azure en ambiente de staging.
6. Conectar WhatsApp Cloud API al webhook público de staging.
7. Probar extremo a extremo con número de prueba.
8. Promover a producción con secretos, plantillas, monitoreo y backups.

## 2. Dónde vive cada parte

El agente no se sube a WhatsApp. El agente vive en Azure.

Distribución recomendada:

- Código del agente: imagen Docker en Azure Container Registry.
- Runtime del agente: Azure Container Apps.
- Base de datos operacional: Azure Database for PostgreSQL Flexible Server.
- Checkpoints de LangGraph y estado conversacional: PostgreSQL, usando las tablas y checkpointer del proyecto.
- Medios de estudiantes/agente: Azure Blob Storage o una abstracción equivalente; no `.langgraph_media` local en producción.
- Secretos: Azure Key Vault o secretos administrados de Container Apps integrados con Key Vault.
- Logs, métricas y trazas: Application Insights + Log Analytics.
- Trabajos demorados, retries y desacople de webhooks: Azure Service Bus Queue.
- RAG: `src/rag/` en código; corpus fuente fuera de `src/`; embeddings en PostgreSQL con `pgvector` o en un servicio de búsqueda si el alcance crece.
- WhatsApp: Meta Business Platform mantiene número, WABA, token, plantillas y webhook configurado hacia la URL pública del backend.

## 3. Arquitectura objetivo para este proyecto

La arquitectura actual del repo define la regla:

`agents -> services -> repositories/integrations -> schemas/utils`

La ruta de despliegue debe conservar esa regla:

- `src/agents/support/`: sigue siendo el grafo LangGraph, nodos y estado.
- `src/services/`: casos de uso: scheduling, planning, reminders, channels, RAG orchestration cuando aplique.
- `src/repositories/`: acceso a PostgreSQL.
- `src/integrations/whatsapp/`: cliente y mapeo de WhatsApp Cloud API.
- `src/services/channels/whatsapp_service.py`: adaptación entre WhatsApp y mensajes del agente.
- `src/bootstrap/`: wiring de dependencias y settings.
- `src/rag/`: ingestión, retrieval y prompting grounded, sin mezclar persistencia operacional ni lógica conversacional.

Falta una frontera HTTP de producción. Esa frontera debería exponer:

- `GET /webhooks/whatsapp`: validación inicial de Meta con `hub.challenge` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
- `POST /webhooks/whatsapp`: recepción de mensajes, validación de firma, idempotencia y encolado/procesamiento.
- `GET /health` o `/ok`: health check para Azure.

Esta capa HTTP no debe contener lógica de negocio. Debe llamar a `services/channels/` y al runtime del agente.

## 4. Flujo recomendado en producción

Entrada desde estudiante:

1. Estudiante envía texto, imagen o documento a WhatsApp.
2. Meta envía webhook al backend en Azure.
3. El endpoint valida `verify_token` en configuración y firma `X-Hub-Signature-256` en eventos POST.
4. El backend registra o detecta idempotencia por `message_id`.
5. Si viene media, `WhatsAppChannelService` descarga el archivo mediante Cloud API.
6. El archivo se guarda en almacenamiento persistente, idealmente Blob Storage.
7. El mensaje se transforma en `HumanMessage` con referencia liviana al medio.
8. El grafo procesa el estado con LangGraph.
9. El agente responde con texto o imagen.
10. Si hay imagen local, se sube primero a WhatsApp Cloud API `/media` y se envía después por `/messages`.

Salida desde agente:

1. El agente produce una respuesta.
2. `services/channels/` convierte la respuesta en mensajes de canal.
3. `integrations/whatsapp/` llama a Cloud API.
4. Se registra el resultado, el `message_id` de WhatsApp y errores recuperables.

## 5. Por qué Azure Container Apps es la mejor opción inicial

Para este MVP, Azure Container Apps es la opción más equilibrada:

- Ejecuta contenedores sin administrar servidores.
- Soporta endpoints HTTP públicos con HTTPS.
- Escala por tráfico HTTP, CPU, memoria o eventos.
- Puede ejecutar workers separados para colas o jobs.
- Permite manejar secretos e integrarse con logs.
- Evita la complejidad de AKS al inicio.

Alternativas:

- Azure App Service con contenedor: viable si será una sola API web simple. Menos flexible para separar worker, webhook y jobs.
- AKS: potente, pero excesivo para el MVP; agrega operación de Kubernetes antes de que el producto la necesite.
- VM con Docker: rápida para pruebas, pero peor en mantenimiento, seguridad y escalado.

Recomendación práctica:

- Staging y primera producción: Azure Container Apps.
- Si luego hay alto tráfico, múltiples workers, jobs complejos o requisitos internos fuertes, evaluar AKS.

## 6. Base de datos y migración

La base de datos no debe ir en GitHub ni dentro del contenedor en producción.

Debe ir en Azure Database for PostgreSQL Flexible Server porque el proyecto ya usa PostgreSQL para:

- estudiantes;
- onboarding;
- horarios recurrentes;
- planificación;
- seguimiento;
- recordatorios;
- sync con Microsoft Graph;
- checkpoints y writes de LangGraph;
- futuro RAG con pgvector.

Variables relevantes del proyecto:

- `ACADEMIC_AGENT_DATABASE_URL`
- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `PGPASSWORD`
- `LANGGRAPH_CHECKPOINTER_DATABASE_URL`
- `POSTGRES_URI`

Ruta de migración:

1. Crear PostgreSQL Flexible Server en Azure.
2. Crear base de datos por ambiente: `academic_agent_staging`, `academic_agent_prod`.
3. Ejecutar migraciones `migrations/*.sql`.
4. Configurar `ACADEMIC_AGENT_DATABASE_URL` y `LANGGRAPH_CHECKPOINTER_DATABASE_URL`.
5. Para RAG, habilitar extensión `vector` si se usará pgvector.
6. Si hay datos locales reales que migrar, usar `pg_dump`/`pg_restore`; si no, iniciar producción con migraciones limpias.

Para RAG:

- El corpus fuente no debe vivir mezclado en `src/`.
- Si es corpus pequeño, puede versionarse bajo `knowledge_base/` si no contiene datos sensibles.
- Si contiene material privado o datos de estudiantes, debe vivir en Blob Storage.
- Los embeddings deben generarse por pipeline de ingestión y guardarse en PostgreSQL con `vector`, no en archivos versionados.

## 7. Media: imágenes del estudiante y del agente

La solución local actual evita guardar base64 en checkpoints. Eso resuelve el problema de Out of Memory en LangGraph Studio.

En producción hay que dar el siguiente paso:

- `.langgraph_media` solo sirve como almacenamiento local de desarrollo.
- En Azure, los medios deben ir a Blob Storage o a una capa de almacenamiento persistente.
- El estado del grafo debe guardar referencias livianas: URL interna, blob key, hash, metadata, mime type.
- Para WhatsApp, una imagen saliente local debe subirse a Cloud API y luego enviarse por `media_id`.
- Para una imagen entrante, WhatsApp entrega `media_id`; el backend la descarga y la guarda fuera del checkpoint.

Esto protege:

- memoria del proceso;
- tamaño de checkpoints;
- velocidad de LangGraph;
- privacidad de imágenes;
- capacidad de escalar a más de una instancia.

## 8. Seguridad antes de conectar WhatsApp público

Antes de producción deben estar resueltos:

- No commitear `.env`, tokens, `.codex`, `.langgraph_api*`, `.langgraph_media`, dumps ni imágenes reales.
- Validar webhook GET con `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
- Validar POST con `WHATSAPP_APP_SECRET` y firma `X-Hub-Signature-256`.
- Usar token permanente o de larga duración, no token temporal de prueba.
- Guardar tokens en Key Vault o secretos del runtime, no en código.
- Rotación de `WHATSAPP_ACCESS_TOKEN`, OpenAI/Azure OpenAI keys y Microsoft Graph secrets.
- Redactar logs: no imprimir tokens, payloads completos, imágenes, correos, teléfonos o PII innecesaria.
- Idempotencia por `message_id`, porque Meta puede reenviar webhooks.
- Rate limiting y backoff para Graph API, OpenAI/Azure OpenAI y Microsoft Graph.
- Autorización interna para endpoints que no sean webhook público.
- Políticas de retención de medios y conversaciones.

## 9. RAG: cuándo acabarlo

Si el agente va a recomendar métodos de estudio con base en un corpus institucional, académico o documentado, el RAG debe cerrarse antes de abrir WhatsApp a usuarios reales. WhatsApp hará que el agente sea más accesible, por lo tanto también hará más visibles las respuestas malas o inventadas.

Ruta recomendada para RAG:

1. Definir corpus fuente en `knowledge_base/` o Blob Storage.
2. Implementar `src/rag/ingestion/`: carga, chunking, hash/versionado y embeddings.
3. Implementar `src/rag/retrieval/`: búsqueda por similitud y filtros.
4. Implementar `src/rag/prompting/`: armado de contexto citado y límites de respuesta.
5. Exponer RAG desde `services/`, no desde `integrations/` ni directo desde nodos.
6. Agregar evaluaciones: preguntas frecuentes, casos ambiguos y casos fuera de corpus.
7. Guardar embeddings en PostgreSQL con pgvector o, si crece el alcance, evaluar Azure AI Search.

RAG no debe bloquear pruebas técnicas de webhook. Sí debe bloquear el lanzamiento público si las respuestas principales dependen de ese conocimiento.

## 10. Flujo de ambientes

Ambiente local:

- `.env` local.
- `.langgraph_api` y `.langgraph_media` locales e ignorados.
- PostgreSQL local o remoto de desarrollo.
- LangGraph Studio para depurar.

Ambiente staging:

- Azure Container Apps.
- PostgreSQL Flexible Server staging.
- Blob Storage staging.
- Key Vault staging.
- WhatsApp test number o número controlado.
- Logs y alertas.
- Datos sintéticos o estudiantes de prueba.

Ambiente producción:

- Azure Container Apps producción.
- PostgreSQL Flexible Server producción.
- Blob Storage producción.
- Key Vault producción.
- Número real de WhatsApp Business.
- Plantillas aprobadas.
- Backups, monitoreo, alertas y política de incidentes.

Nunca mezclar datos de staging y producción.

## 11. CI/CD recomendado

Pipeline mínimo:

1. Pull request en GitHub.
2. Ejecutar tests.
3. Revisar que no haya secretos.
4. Construir imagen Docker.
5. Publicar imagen en Azure Container Registry.
6. Desplegar a Container Apps staging.
7. Ejecutar smoke tests: `/health`, migraciones, conexión DB, envío simulado WhatsApp.
8. Promoción manual a producción.

Comandos conceptuales:

```bash
pytest
docker build -t academic-agentai:<sha> .
docker push <acr>.azurecr.io/academic-agentai:<sha>
```

Para producción no usar `docker compose` como runtime final. Docker Compose sirve para desarrollo o pruebas locales.

## 12. Componentes Azure recomendados

MVP robusto:

- Azure Container Apps: backend HTTP y worker.
- Azure Container Registry: imágenes Docker.
- Azure Database for PostgreSQL Flexible Server: datos y checkpoints.
- Azure Blob Storage: imágenes/documentos.
- Azure Key Vault: secretos.
- Application Insights + Log Analytics: observabilidad.
- Azure Service Bus Queue: desacoplar webhooks y procesamiento largo.

Opcional según decisión de runtime:

- Azure Managed Redis: si se despliega LangGraph Agent Server oficial o se requiere pub/sub/streaming/background runs compatible con esa arquitectura.
- Azure OpenAI: si se quiere mantener inferencia dentro del ecosistema Azure.
- Azure AI Search: si RAG crece más allá de pgvector o requiere filtros/búsqueda híbrida más avanzada.

## 13. Punto importante sobre LangGraph Server

Hay dos caminos válidos:

Camino A: backend propio con FastAPI o framework equivalente.

- El endpoint WhatsApp vive en tu API.
- Tu API invoca el grafo compilado.
- PostgreSQL guarda estado/checkpoints vía el checkpointer existente.
- Es el camino más directo para este proyecto si quieres controlar el flujo WhatsApp.

Camino B: LangGraph standalone Agent Server.

- Se construye imagen con LangGraph CLI.
- El server requiere Postgres y Redis para producción standalone.
- El webhook de WhatsApp puede vivir como ruta custom o como servicio separado que llama al Agent Server.
- Es útil si quieres aprovechar más capacidades de LangGraph Platform.

Para este proyecto, la recomendación inicial es Camino A, porque ya existe una arquitectura clara por capas y WhatsApp entra como canal en `services/channels/`. El Camino B puede evaluarse después si necesitas server API estándar de LangGraph, streaming avanzado, jobs nativos o despliegue compatible con LangGraph Platform.

## 14. Orden operativo recomendado

Fase 1: estabilizar agente

- Cerrar flujos principales.
- Asegurar que imagen entrante y saliente no persista base64.
- Ejecutar suite completa.
- Documentar variables de entorno.

Fase 2: cerrar RAG mínimo

- Implementar ingestión y retrieval.
- Guardar embeddings en PostgreSQL con `vector`.
- Agregar pruebas y evaluaciones.
- Definir fallback cuando no haya evidencia suficiente.

Fase 3: preparar frontera HTTP

- Agregar endpoint webhook WhatsApp.
- Validar firma.
- Idempotencia por mensaje.
- Health check.
- Wiring desde `bootstrap`.

Fase 4: preparar Azure

- Crear recursos.
- Configurar secretos.
- Ejecutar migraciones.
- Configurar Blob Storage.
- Desplegar container en staging.

Fase 5: WhatsApp staging

- Configurar webhook en Meta hacia staging.
- Probar texto, imagen, documento, errores y reintentos.
- Verificar latencia y logs.

Fase 6: producción

- Número real.
- Plantillas aprobadas.
- Alertas.
- Backups.
- Política de retención.
- Release controlado.

## 15. Decisión recomendada

La mejor opción para este proyecto es:

1. Terminar el agente y RAG mínimo verificable.
2. Endurecer seguridad y persistencia.
3. Crear una API HTTP de producción que respete la arquitectura actual.
4. Containerizar.
5. Desplegar en Azure Container Apps.
6. Usar Azure PostgreSQL Flexible Server para base de datos y checkpoints.
7. Usar Blob Storage para imágenes/documentos.
8. Usar Key Vault para secretos.
9. Conectar WhatsApp Cloud API al endpoint público.

No subir la base de datos a GitHub. No guardar secretos en el repo. No depender de `.langgraph_api` ni `.langgraph_media` para producción.

## 16. Referencias oficiales consultadas

- Meta WhatsApp Cloud API Overview: https://meta-preview.mintlify.io/docs/whatsapp/cloud-api/overview
- Meta WhatsApp Cloud API Media: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
- Meta WhatsApp Cloud API Messages: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
- Meta WhatsApp Cloud API Webhooks: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
- Azure Container Apps overview: https://learn.microsoft.com/en-us/azure/container-apps/overview
- Azure Database for PostgreSQL Flexible Server overview: https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview
- Azure Key Vault overview: https://learn.microsoft.com/en-us/azure/key-vault/general/overview
- Azure Blob Storage overview: https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-overview
- Azure Container Registry overview: https://learn.microsoft.com/en-us/azure/container-registry/container-registry-intro
- Azure Application Insights overview: https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview
- Azure Service Bus queues/topics/subscriptions: https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-queues-topics-subscriptions
- Azure PostgreSQL pgvector: https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector
- LangGraph standalone server deployment: https://docs.langchain.com/langgraph-platform/deploy-standalone-server
