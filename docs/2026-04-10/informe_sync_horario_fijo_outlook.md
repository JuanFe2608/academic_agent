# Integracion Del Horario Fijo Confirmado Con Outlook

Fecha: 2026-04-10

Estado: implementado y verificado

## 1. Objetivo

Conectar el flujo de confirmación del horario fijo del agente con Outlook Calendar para que, cuando el estudiante confirme:

```text
✅ ¿Entendí bien tu horario?
1. Sí, está correcto
2. No, quiero corregir algo
```

el horario:

- se persista primero en PostgreSQL como fuente de verdad;
- pida una fecha límite antes de sincronizar;
- luego se sincronice a Outlook Calendar como eventos recurrentes semanales con fin explícito;
- permita renovar el mismo horario cuando esa fecha venza;
- y no rompa el flujo existente de onboarding, scheduling y personalización.

## 2. Alcance Del Cambio

La implementación cubre únicamente el horario fijo recurrente del estudiante:

- bloques académicos;
- bloques laborales;
- bloques extracurriculares confirmados que ya formen parte del horario fijo.

No cubre en este cambio:

- Google Calendar;
- sincronización de WhatsApp;
- envío push automático fuera del turno conversacional del agente;
- materialización del plan de estudio en este flujo;
- UI nueva.

## 3. Problema Inicial

Antes del cambio, el flujo hacía esto:

1. capturaba el horario fijo;
2. construía el borrador;
3. pedía confirmación final;
4. persistía el horario en PostgreSQL.

El problema era que, después de la confirmación del estudiante, el sistema no proyectaba ese horario fijo al calendario externo aunque:

- ya existía integración real con Microsoft OAuth;
- ya existía cliente real para Microsoft Graph;
- la base relacional ya tenía columnas preparadas para guardar metadatos externos del horario recurrente.

En otras palabras:

- el dominio de scheduling ya tenía fuente de verdad;
- Outlook ya tenía infraestructura;
- faltaba el caso de uso que uniera ambas piezas sin contaminar la capa conversacional.

## 4. Resumen De La Solucion

Se implementó un subflujo nuevo entre la confirmación, la persistencia del horario y el resto del pipeline:

1. El estudiante confirma que el horario está correcto.
2. El agente pide una fecha límite del horario fijo.
3. `persist_schedule` guarda el horario confirmado en PostgreSQL con esa fecha límite.
4. El grafo cambia a una fase intermedia: `schedule_sync`.
5. Un nodo nuevo `sync_fixed_schedule` ejecuta la sincronización real hacia Outlook con una recurrencia semanal `hasta fecha`.
6. Si la fecha límite expira y el estudiante vuelve a interactuar con el agente, se activa un subflujo de renovación.
7. Si la sincronización sale bien, el flujo continúa a `sync` y desde ahí sigue igual.
8. Si la sincronización falla, el horario queda guardado de todas formas en base de datos y el agente informa que falló solo Outlook.

Esto preserva una regla importante del proyecto:

- PostgreSQL sigue siendo la fuente de verdad del estado operativo;
- Outlook es una proyección externa derivada.

## 5. Diseno Arquitectonico

### 5.1 Principio Aplicado

Se respetó la regla del repositorio:

`agents -> services -> repositories/integrations -> schemas`

Por eso la implementación quedó separada así:

- `agents/`
  - enruta y orquesta el paso conversacional.
- `services/sync/`
  - contiene el caso de uso de sincronización del horario fijo hacia Outlook.
- `repositories/scheduling/`
  - expone lectura y actualización de los bloques persistidos del horario fijo.
- `integrations/microsoft_graph/`
  - serializa y envía el payload real a Microsoft Graph.

### 5.2 Por Que No Se Metio La Logica En El Nodo

No se puso la lógica de Outlook directamente en el nodo porque eso rompería la arquitectura:

- el nodo no debe conocer persistencia concreta ni protocolos HTTP;
- el nodo debe delegar a un servicio;
- el servicio debe orquestar repositorio + OAuth + cliente Graph.

### 5.3 Por Que No Se Reutilizo El Sync Del Plan De Estudio

Ya existía `OutlookCalendarSyncService`, pero estaba orientado a:

- instancias materializadas del plan de estudio;
- eventos fechados;
- links en la tabla `outlook_calendar_event_links`.

El horario fijo necesita otra semántica:

- bloques recurrentes semanales;
- series semanales en Outlook;
- persistencia del link externo directamente sobre `recurring_schedule_blocks`.

Por eso se creó un servicio nuevo específico para horario fijo.

## 6. Flujo Tecnico Detallado

### 6.1 Confirmacion Del Estudiante

Cuando el estudiante responde que el horario está correcto:

- el flujo de revisión marca los bloques como confirmados;
- pide una fecha límite para el horario fijo;
- y solo después de esa fecha pasa a `schedule_persist`.

La fecha aceptada se puede escribir como:

- `YYYY-MM-DD`
- `DD/MM/YYYY`

### 6.2 Persistencia Canonica En PostgreSQL

El nodo `persist_schedule`:

- toma `persisted_student_id`;
- toma los bloques confirmados del estado;
- persiste un nuevo `schedule_profile`;
- persiste `schedule_end_date` en ese `schedule_profile`;
- persiste sus `recurring_schedule_blocks`;
- marca versiones previas como `is_current = false`.

Después de eso, ya existe:

- un `schedule_profile_id` nuevo;
- una versión actual del horario;
- los bloques semanales guardados como fuente de verdad.

### 6.3 Fase Intermedia De Sync

En vez de saltar directo a `sync`, ahora el grafo entra a:

- `schedule_sync`

Esa fase existe para hacer explícito que:

- el horario ya fue guardado;
- ahora se intenta su proyección a Outlook.

### 6.4 Servicio De Sincronizacion

El servicio `OutlookFixedScheduleSyncService` hace lo siguiente:

1. valida `student_id`;
2. valida `schedule_profile_id`;
3. revisa que exista conexión Microsoft en `microsoft_graph_connections`;
4. obtiene o refresca el token OAuth;
5. lee los bloques persistidos del estudiante desde `recurring_schedule_blocks`;
6. separa:
   - bloques actuales del `schedule_profile_id` confirmado;
   - bloques viejos ya sincronizados que pertenecen a versiones anteriores;
7. convierte los bloques actuales en payloads recurrentes semanales de Outlook;
8. si el perfil tiene `schedule_end_date`, genera una recurrencia semanal con `range.type = endDate`;
9. si el perfil no tiene fecha límite, mantiene compatibilidad con `range.type = noEnd`;
10. crea o actualiza las series en Outlook;
11. elimina en Outlook las series antiguas de perfiles anteriores para no duplicar eventos;
12. persiste los IDs externos y metadatos de sync de vuelta en `recurring_schedule_blocks`.

### 6.5 Proyeccion A Microsoft Graph

Cada bloque recurrente se convierte en un `OutlookCalendarEventUpsert` con:

- `subject`
- `body`
- `start`
- `end`
- `categories`
- `recurrence`
- `transactionId`

La recurrencia usa:

- patrón semanal;
- timezone local del bloque;
- `range.type = endDate` cuando existe `schedule_end_date`;
- `range.type = noEnd` para datos antiguos sin fecha límite.

### 6.6 Renovacion Del Horario Vencido

Cuando el `schedule_end_date` ya pasó, el agente detecta que el horario actual expiró al inicio del siguiente turno conversacional y abre un subflujo nuevo:

fase: `schedule_renewal`

El mensaje mejorado quedó así:

```text
⏰ Tu horario fijo llegó a su fecha límite en Outlook.
Fecha límite anterior: 30/06/2026

¿Quieres seguir manteniendo estas actividades?
(Escribe el número de la opción que quieres elegir)
1. ✅ Sí, mantener el mismo horario
2. ❌ No, prefiero cambiarlo
```

Si el estudiante elige `1`:

- el agente pide una nueva fecha límite;
- actualiza el `schedule_profile` actual;
- vuelve a sincronizar Outlook con la nueva fecha.

Si el estudiante elige `2`:

- pregunta si quiere organizar un horario nuevo ahora o luego;
- si responde `ahora`, reinicia la captura del horario fijo;
- si responde `luego`, cierra la conversación sin borrar el histórico.

### 6.7 Continuidad Del Flujo

Cuando el sync termina:

- si sale bien, el agente responde que también quedó guardado en Outlook;
- si falla, el agente responde que el horario quedó guardado en el sistema pero no en Outlook.

En ambos casos, el flujo sigue a `sync`, por lo que no bloquea el resto del onboarding.

## 7. Archivos Principales Del Cambio

### Grafo y nodos

- `src/agents/support/agent.py`
- `src/agents/support/state.py`
- `src/agents/support/nodes/persist_schedule/node.py`
- `src/agents/support/nodes/sync_fixed_schedule/node.py`
- `src/agents/support/nodes/renew_fixed_schedule/node.py`
- `src/agents/support/flows/scheduling/fixed_schedule_renewal_service.py`
- `src/agents/support/nodes/repair_fixed_schedule/node.py`
- `src/agents/support/flows/scheduling/fixed_schedule_repair_service.py`

### Servicios

- `src/services/scheduling/end_date_support.py`
- `src/services/scheduling/service.py`
- `src/services/sync/fixed_schedule_outlook_projection.py`
- `src/services/sync/outlook_fixed_schedule_sync_service.py`
- `src/services/sync/outlook_fixed_schedule_reconciliation_service.py`
- `src/services/sync/outlook_fixed_schedule_repair_service.py`
- `src/services/sync/__init__.py`

### Repositorios

- `src/repositories/scheduling/repository.py`

### Migraciones

- `migrations/0015_schedule_profile_end_dates.sql`

### Integracion Microsoft Graph

- `src/integrations/microsoft_graph/_clients_impl.py`
- `src/integrations/microsoft_graph/models.py`
- `src/integrations/microsoft_graph/__init__.py`

### Wiring

- `src/bootstrap/container.py`
- `src/agents/support/dependencies.py`

### Scripts operativos

- `scripts/microsoft_oauth_authorize.py`
- `scripts/microsoft_oauth_exchange_code.py`
- `scripts/sync_outlook_fixed_schedule.py`
- `scripts/reconcile_outlook_fixed_schedule.py`
- `scripts/repair_outlook_fixed_schedule.py`

### Pruebas

- `tests/test_schedule_persistence.py`
- `tests/test_personalization_flow.py`
- `tests/test_outlook_fixed_schedule_sync_service.py`
- `tests/test_outlook_fixed_schedule_reconciliation_service.py`
- `tests/test_outlook_fixed_schedule_repair_service.py`
- `tests/test_fixed_schedule_repair_flow.py`
- `tests/test_microsoft_graph_calendar_client.py`

## 8. Datos Y Valores Necesarios Para Que Funcione

Para que el horario fijo se sincronice a Outlook hacen falta estos datos:

### 8.1 Datos del estudiante

- `student_profile.persisted_student_id`

Sin ese valor, no se puede asociar ni la persistencia ni la conexión OAuth.

### 8.2 Datos del horario persistido

- `schedule.persisted_profile_id`
- bloques guardados en `recurring_schedule_blocks`

Cada bloque debe tener al menos:

- `source_block_id`
- `title`
- `day_of_week`
- `start_time`
- `end_time`
- `timezone`

Y el perfil horario actual debe tener:

- `schedule_end_date` para la nueva modalidad con vencimiento;
- o `NULL` si es un perfil viejo que todavía no se ha renovado.

### 8.3 Conexion Microsoft

Debe existir una fila en `microsoft_graph_connections` para ese estudiante con:

- `access_token`
- `refresh_token` si aplica
- `expires_at`
- scopes con `Calendars.ReadWrite`

### 8.4 Calendar ID

`calendar_id` es opcional:

- si existe en la conexión Microsoft, se usa ese;
- si no existe, Outlook usa el calendario principal de la cuenta (`__default__` a nivel lógico interno).

## 9. Persistencia Relacional Del Sync

Se reutilizó el diseño ya previsto por la base:

tabla: `recurring_schedule_blocks`

columnas usadas para el sync:

- `external_provider`
- `external_series_id`
- `external_event_id`
- `external_sync_status`
- `external_sync_metadata`

Esto permite:

- saber si un bloque ya fue sincronizado;
- saber a qué evento/serie externa corresponde;
- marcar sync activo o eliminado;
- guardar metadatos útiles como:
  - `calendar_id`
  - `series_start_date`
  - `schedule_end_date`
  - `external_change_key`
  - `synced_at`

Además, `schedule_profiles` ahora guarda la fecha límite canónica:

- `schedule_end_date`

## 10. Comportamiento Importante Ante Nuevas Versiones Del Horario

Si el estudiante vuelve a confirmar un horario nuevo:

1. se crea un `schedule_profile` nuevo;
2. el perfil anterior deja de ser `is_current`;
3. el sync del nuevo perfil detecta bloques antiguos sincronizados con Outlook;
4. elimina esas series anteriores de Outlook;
5. crea o actualiza las series del perfil nuevo.

Esto evita:

- duplicados en el calendario;
- basura histórica visible al estudiante;
- confusión entre horarios viejos y horarios actuales.

## 11. Como Probarlo Desde Terminal

## 11.1 Requisito de ejecucion

La forma recomendada es usar `uv run` con caché en `/tmp`:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
```

Si no usas `uv run`, debes tener un entorno virtual activo con las dependencias del proyecto.

## 11.2 Paso 1: Generar la URL OAuth de Microsoft

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/microsoft_oauth_authorize.py --student-id 1
```

Salida esperada:

- imprime `microsoft_oauth_authorize ok`
- imprime `state=...`
- imprime `url=...`

Debes abrir esa URL en el navegador.

## 11.3 Paso 2: Autorizar la cuenta y canjear el callback completo

Después de autorizar en Microsoft, copia la URL completa de redirección y úsala así:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/microsoft_oauth_exchange_code.py --student-id 1 --callback-url 'http://localhost:8000/auth/microsoft/callback?code=...&state=student:1:microsoft'
```

Notas importantes:

- usar comillas simples `'...'`;
- pegar la URL completa en una sola línea;
- no extraer el `code` manualmente;
- no escapar `?`, `=`, `&`, `!` ni `*` dentro de comillas simples.

Salida exitosa esperada:

```text
microsoft_oauth_exchange_code ok student_id=1 email=... calendar_id=__default__ todo_task_list_id=n/a
```

Eso significa que la conexión Microsoft quedó persistida.

## 11.4 Paso 3: Confirmar el horario con fecha límite en el flujo

Después de responder:

```text
✅ ¿Entendí bien tu horario?
1. Sí, está correcto
2. No, quiero corregir algo
```

el agente ahora debe pedir algo así:

```text
📅 Antes de guardarlo en Outlook, necesito la fecha límite de este horario fijo.
Escríbela en uno de estos formatos:
1. YYYY-MM-DD
2. DD/MM/YYYY
Ejemplo: 2026-06-30
```

Si respondes con una fecha válida:

- el horario se persiste con `schedule_end_date`;
- Outlook recibe la recurrencia semanal con fin;
- el mensaje de éxito indica hasta qué fecha se agendó.

## 11.5 Paso 4: Forzar manualmente el sync del horario fijo

Si el estudiante ya tiene horario fijo confirmado y persistido:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/sync_outlook_fixed_schedule.py --student-id 1
```

Salida exitosa esperada:

```text
sync_outlook_fixed_schedule ok schedule_profile_id=... upserted=... deleted=... active_links=...
```

### Variantes utiles

Con `schedule_profile_id` explícito:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/sync_outlook_fixed_schedule.py --student-id 1 --schedule-profile-id 23
```

Con `calendar_id` explícito:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/sync_outlook_fixed_schedule.py --student-id 1 --calendar-id TU_CALENDAR_ID
```

## 11.6 Paso 5: Reconciliar contra Outlook para detectar cambios manuales

Si sospechas que alguien movió, editó o borró eventos directamente en Outlook:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/reconcile_outlook_fixed_schedule.py --student-id 1
```

Salida esperada:

```text
reconcile_outlook_fixed_schedule ok schedule_profile_id=... inspected=... aligned=... drifted=... missing=... unsynced=... errors=...
finding block_id=... status=drifted event_id=... drift_fields=subject,end detail=...
```

Interpretación:

- `aligned`
  - el bloque sigue alineado con PostgreSQL.
- `drifted`
  - Outlook fue modificado manualmente o la versión externa cambió respecto al último sync.
- `missing`
  - el evento ya no existe o fue cancelado en Outlook.
- `unsynced`
  - el bloque actual no tiene link activo hacia Outlook.

La reconciliación no modifica la fuente de verdad interna.

Lo que sí hace:

- consulta Outlook por cada `external_event_id` del horario actual;
- compara contra la proyección esperada del bloque interno;
- persiste el resultado de la reconciliación en `external_sync_status` y `external_sync_metadata`.

## 11.7 Paso 6: Reparar Outlook desde el horario oficial interno

Si la reconciliación deja bloques en estado `drifted` o `missing`, se puede restaurar Outlook usando PostgreSQL como fuente de verdad:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/repair_outlook_fixed_schedule.py --student-id 1
```

Salida esperada:

```text
repair_outlook_fixed_schedule ok schedule_profile_id=... repairable=... restored=... recreated=... skipped=... events=...
```

Funcionamiento:

- para `drifted`, el servicio vuelve a proyectar el bloque oficial y actualiza la serie existente en Outlook;
- para `missing`, el servicio limpia el link externo viejo, crea una serie nueva en Outlook y guarda el nuevo `external_event_id`;
- el servicio solo repara los bloques marcados como `drifted` o `missing`;
- por defecto ejecuta reconciliación antes de reparar para no actuar sobre estados obsoletos.

Si ya ejecutaste reconciliación y quieres reparar exactamente lo que está marcado en BD:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/repair_outlook_fixed_schedule.py --student-id 1 --skip-reconcile
```

En el flujo conversacional, si el estudiante escribe de nuevo y el horario actual tiene bloques `drifted` o `missing`, el agente pregunta:

```text
🛠️ Detecté cambios manuales en tu horario fijo de Outlook.
Eventos editados: X. Eventos eliminados: Y.

Tu horario oficial sigue guardado en el asistente. ¿Qué quieres hacer?
(Escribe el número de la opción que quieres elegir)
1. ✅ Restaurar Outlook con el horario oficial del asistente
2. 🗓️ Organizar un horario fijo nuevo
3. ⏳ Revisarlo después
```

Esta decisión mantiene la arquitectura limpia:

- la reconciliación detecta y persiste el drift;
- la reparación restaura Outlook desde la fuente interna;
- el agente solo decide con el estudiante qué acción ejecutar.

## 11.8 Si el script falla

Casos comunes:

- `current_schedule_profile_not_found`
  - el estudiante aún no tiene horario fijo confirmado en base de datos.
- `microsoft_connection_not_found`
  - falta completar OAuth para ese `student_id`.
- `microsoft_oauth_error`
  - token expirado sin refresh válido o problema en el exchange/refresh.
- errores `microsoft_graph_*`
  - Outlook rechazó la operación o hubo un problema de red/configuración.

## 12. Como Probarlo Desde El Flujo Del Agente

## 12.1 Precondiciones

Antes de entrar al flujo conversacional:

1. el estudiante debe existir en la base;
2. el estudiante debe tener conexión Microsoft válida;
3. el entorno debe tener configuradas las variables OAuth de Microsoft;
4. la cuenta de Outlook debe permitir escritura en calendario.

## 12.2 Secuencia funcional

La prueba end-to-end es:

1. completar onboarding del estudiante;
2. capturar el horario fijo;
3. llegar al mensaje:

```text
✅ ¿Entendí bien tu horario?
1. Sí, está correcto
2. No, quiero corregir algo
```

4. responder `1` o una variante equivalente de confirmación;
5. enviar una fecha límite válida;
6. el agente debe:
   - guardar el horario en PostgreSQL;
   - pasar a `schedule_sync`;
   - sincronizar Outlook;
   - responder algo como:

```text
✅ También guardé tu horario fijo en Outlook hasta el 30/06/2026.
```

## 12.3 Como validar que realmente funciono

Validar en los tres niveles:

### En la conversación

Debe aparecer el mensaje de éxito de Outlook o el mensaje de fallo parcial.

### En Outlook

Abrir el calendario de la cuenta conectada y verificar:

- que aparezcan los bloques recurrentes;
- que sean semanales;
- que el horario corresponda al confirmado;
- que estén en el calendario principal o en el `calendar_id` configurado.

### En la base de datos

Verificar que los bloques actuales tengan datos externos:

```sql
SELECT
    rsb.id,
    rsb.schedule_profile_id,
    sp.schedule_end_date,
    rsb.title,
    rsb.day_of_week,
    rsb.start_time,
    rsb.end_time,
    rsb.external_provider,
    rsb.external_series_id,
    rsb.external_event_id,
    rsb.external_sync_status,
    rsb.external_sync_metadata
FROM recurring_schedule_blocks rsb
JOIN schedule_profiles sp
  ON sp.id = rsb.schedule_profile_id
WHERE sp.student_id = 1
ORDER BY sp.version_number DESC, rsb.day_of_week, rsb.start_time;
```

Esperado para bloques sincronizados:

- `schedule_end_date` con la fecha límite confirmada;
- `external_provider = 'outlook'`
- `external_event_id` no nulo
- `external_series_id` no nulo
- `external_sync_status = 'active'`

## 13. Como Saber Si Ya Es Una Integracion Real O Si Sigue Local

Esta funcionalidad ya no quedó solo “local” o solo “mockeada”.

Es integración real con Outlook cuando se cumplen estas condiciones:

- el proyecto corre con dependencias reales;
- hay variables Microsoft OAuth configuradas;
- el estudiante completó OAuth;
- el token quedó persistido;
- el sync sale contra `graph.microsoft.com`.

Lo que sí sigue siendo local es:

- el entorno de ejecución del agente;
- la base PostgreSQL local o del entorno donde corra;
- las pruebas automatizadas, que usan fakes/mocks controlados.

Pero el caso de uso implementado apunta a Microsoft Graph real.

## 14. Pruebas Automatizadas Ejecutadas

Se verificó la feature con:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_schedule_modifications.py tests/test_schedule_persistence.py tests/test_outlook_fixed_schedule_sync_service.py tests/test_fixed_schedule_renewal_flow.py tests/test_agent_wait_routing.py
```

Y además se validó compatibilidad con piezas compartidas:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_outlook_calendar_sync_service.py tests/test_bootstrap_container.py tests/test_refactor_guardrails.py tests/test_agent_state_partitioning.py
```

## 15. Decisiones Tecnicas Clave

### 15.1 Persistir primero, sincronizar después

Motivo:

- evita que Outlook se convierta en fuente de verdad;
- el sistema conserva consistencia interna aunque falle el proveedor externo.

### 15.2 Reusar columnas externas existentes

Motivo:

- evita nuevas tablas innecesarias;
- mantiene trazabilidad directamente sobre cada bloque recurrente.

### 15.3 Servicio dedicado para horario fijo

Motivo:

- el sync del plan de estudio y el sync del horario fijo tienen semánticas distintas;
- separarlos reduce acoplamiento y facilita mantenimiento.

### 15.4 Fase intermedia `schedule_sync`

Motivo:

- hace explícito el paso de integración;
- permite razonar el flujo con claridad;
- evita mezclar persistencia transaccional con integración externa en un solo nodo.

### 15.5 Renovar el mismo perfil en vez de crear otro

Motivo:

- cambiar solo la fecha límite no implica un cambio semántico del horario;
- evita versionar el mismo conjunto de bloques solo por extender vigencia;
- permite reusar el mismo `schedule_profile_id` y resincronizar Outlook limpiamente.

## 16. Riesgos Y Limitaciones Conocidas

- Si el `authorization code` se pega mal o caduca, el exchange OAuth falla.
- Si el estudiante no tiene conexión Microsoft, el sync no ocurre.
- Si cambia el calendario destino (`calendar_id`) después del primer sync, puede requerir resincronización explícita.
- El flujo actual no expone todavía una pantalla o menú dedicado para reconectar Outlook; hoy la operación es principalmente por scripts.
- La renovación hoy se dispara al siguiente turno conversacional del agente; todavía no existe un canal push autónomo dentro del chat.
- La reconciliación actual consulta por `external_event_id` y detecta drift puntual; todavía no usa `delta queries`, webhooks ni sincronización inversa automática hacia PostgreSQL.
- La reparación restaura Outlook desde PostgreSQL; no importa cambios manuales de Outlook hacia el horario interno. Si el cambio manual era intencional, el flujo recomendado es organizar un horario fijo nuevo.

## 17. Conclusión

La feature quedó integrada de forma consistente con la arquitectura del proyecto:

- el horario fijo confirmado se guarda primero en PostgreSQL;
- luego se proyecta a Outlook como recurrencia semanal real;
- la lógica queda encapsulada en servicio, repositorio e integración, no en la capa conversacional;
- y existe soporte operativo por terminal para OAuth y para forzar el sync manual cuando sea necesario.

En términos prácticos, ya es posible:

- conectar la cuenta Microsoft de un estudiante;
- confirmar su horario fijo con fecha límite;
- ver ese horario reflejado en Outlook Calendar hasta esa fecha;
- detectar y reparar cambios manuales hechos en Outlook;
- y renovar el mismo horario desde el agente cuando expire.
