# Informe De Prueba Local OAuth Microsoft Para Estudiante

Fecha: 2026-04-30

## Conclusión

Sí, el proyecto ya tiene el bloque necesario para probar localmente que un estudiante autorice al agente a usar Microsoft Graph para calendario y tareas.

Al inicio de la revisión no hacía falta implementar todo el flujo desde cero, pero sí apareció un bloqueo interno que impedía generar el link OAuth en el onboarding normal: el sistema pedía `email_verified=True` antes de iniciar OAuth, aunque OAuth es precisamente el paso que confirma la conexión Microsoft.

Ese bloqueo ya fue corregido. Con la corrección, el agente puede crear una identidad mínima sin marcar el correo como verificado, generar el link OAuth y marcar el perfil conversacional como verificado/autorizado después de que exista conexión Microsoft.

Con el `.env` revisado inicialmente, la prueba conversacional real no iba a funcionar correctamente porque:

- `ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH` está en `false`.
- `MICROSOFT_REDIRECT_URI` apunta a `http://localhost:8000/auth/microsoft/callback`.
- La ruta real implementada en FastAPI es `http://localhost:8000/oauth/callback`.

Por lo tanto, la base técnica está lista, pero antes de probar hay que ajustar esas variables.

## Corrección Aplicada

Se corrigió el bloqueo circular del onboarding OAuth:

- `OnboardingService.persist_verified_identity()` ya no exige `email_verified=True` para preparar la identidad mínima previa al OAuth.
- `PostgresOnboardingRepository.upsert_verified_student_identity()` ya no marca automáticamente `email_verified=TRUE` antes del consentimiento Microsoft.
- El correo queda no verificado durante el estado `pending`.
- `collect_profile` pausa la captura justo después de recibir el correo cuando OAuth es obligatorio, para evitar que pida semestre antes de enviar el link.
- Cuando el agente detecta conexión Microsoft existente, el nodo `request_microsoft_oauth` marca el perfil conversacional como autorizado y continúa.
- La validación de correo ahora acepta dominios configurados, por ejemplo `@ucatolica.edu.co`, y cuentas Microsoft personales como `@outlook.com`, `@hotmail.com` o `@live.com`.
- La API ahora acepta dos callbacks equivalentes: `/oauth/callback` y `/auth/microsoft/callback`. La segunda ruta queda como alias para configuraciones locales o de Azure que ya estaban registradas con esa URL.

Esto aplica tanto para LangGraph Debugger como para WhatsApp, porque ambos caminos usan el mismo grafo y el mismo nodo `request_microsoft_oauth`.

## Corrección De Imágenes En Debugger Y WhatsApp

También se ajustó el manejo de imágenes del flujo:

- Con `MEDIA_INLINE_PREVIEW=true`, la imagen de bienvenida y la imagen renderizada del horario se entregan como `data:image/...` para que LangGraph Debugger/LangSmith puedan mostrarlas.
- Para WhatsApp, si el agente produce una imagen inline, el canal la materializa primero como archivo local antes de subirla a WhatsApp Cloud API.
- Sin `MEDIA_INLINE_PREVIEW`, el flujo conserva rutas locales de archivo, que WhatsApp sube como media normal.

Esto evita que una configuración útil para debug local rompa el envío real por WhatsApp.

## Estado Detectado Al Inicio De La Revisión

Variables Microsoft y base de datos:

- `MS_CLIENT_ID`: configurada.
- `MS_CLIENT_SECRET`: configurada.
- `MS_TENANT_ID`: configurada.
- `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`: configuradas.
- `ACADEMIC_AGENT_DATABASE_URL`: configurada.

Variables que deben corregirse para la prueba:

```env
ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=false
MICROSOFT_REDIRECT_URI=http://localhost:8000/auth/microsoft/callback
```

Valores recomendados para prueba local:

```env
ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=true
MICROSOFT_REDIRECT_URI=http://localhost:8000/oauth/callback
```

## Qué Bloque Se Activa

El flag operativo es:

```env
ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=true
```

Cuando está activo, el grafo detiene el onboarding en la fase `microsoft_oauth` después de tener los datos mínimos del estudiante:

- nombre completo;
- código estudiantil;
- edad;
- correo institucional.

En ese punto, el nodo `request_microsoft_oauth` genera un enlace de autorización Microsoft y no deja continuar hasta que exista una conexión persistida en `microsoft_graph_connections`.

## Redirect Correcto

La API expone el callback OAuth principal en:

```text
GET /oauth/callback
```

También se mantiene un alias compatible:

```text
GET /auth/microsoft/callback
```

Para una prueba local con el servidor en el puerto `8000`, se puede usar cualquiera de estas dos rutas, siempre que el valor coincida exactamente entre `.env` y Microsoft Entra.

Opción recomendada nueva:

```env
MICROSOFT_REDIRECT_URI=http://localhost:8000/oauth/callback
```

Opción compatible con la app registrada anteriormente:

```env
MICROSOFT_REDIRECT_URI=http://localhost:8000/auth/microsoft/callback
```

La misma URL exacta debe estar registrada en Microsoft Entra ID en la aplicación usada por `MS_CLIENT_ID`.

Si Microsoft Entra no acepta `localhost` para la configuración actual de la app, usar un túnel público y registrar esa URL, por ejemplo:

```env
MICROSOFT_REDIRECT_URI=https://<tunel-publico>/oauth/callback
```

## Permisos Necesarios

El cliente OAuth pide por defecto estos scopes:

```text
offline_access
openid
profile
User.Read
Calendars.ReadWrite
Tasks.ReadWrite
Mail.Send
```

Para probar autorización de calendario, el permiso clave es:

```text
Calendars.ReadWrite
```

Si se quiere reducir la prueba solo a calendario, se puede fijar explícitamente:

```env
MICROSOFT_GRAPH_SCOPES="offline_access openid profile User.Read Calendars.ReadWrite"
```

Si también se van a probar tareas y recordatorios en Microsoft To Do, mantener:

```env
MICROSOFT_GRAPH_SCOPES="offline_access openid profile User.Read Calendars.ReadWrite Tasks.ReadWrite"
```

`Mail.Send` solo es necesario si se va a probar envío de correos vía Microsoft Graph.

## Prerrequisitos De Base De Datos

La prueba necesita persistencia real en PostgreSQL. No activar:

```env
ACADEMIC_AGENT_USE_IN_MEMORY_MICROSOFT_REPO=1
```

Deben existir las tablas de Microsoft Graph y OAuth pendiente. Las migraciones relevantes son:

- `migrations/0013_microsoft_graph_connections_and_sync.sql`
- `migrations/0014_grant_microsoft_graph_permissions.sql`
- `migrations/0017_microsoft_oauth_onboarding_gate.sql`
- `migrations/0018_grant_microsoft_oauth_pending_permissions.sql`

Si la base ya tiene estas migraciones aplicadas, no hay que repetirlas.

## Prueba Recomendada: Flujo Conversacional Real

Esta es la prueba que realmente valida que el estudiante autoriza y el agente continúa.

1. Ajustar `.env`:

```env
ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=true
MICROSOFT_REDIRECT_URI=http://localhost:8000/oauth/callback
```

2. Confirmar en Microsoft Entra que existe exactamente este redirect:

```text
http://localhost:8000/oauth/callback
```

3. Iniciar el servidor local:

```bash
uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

4. Iniciar una conversación de prueba con un estudiante nuevo o sin conexión Microsoft previa.

5. Completar los datos mínimos del perfil.

6. Validar que Lara envía un enlace de Microsoft para autorizar calendario y tareas.

7. Abrir el enlace, iniciar sesión y aceptar permisos.

8. Confirmar que el navegador muestra la página de éxito del callback.

9. Volver al chat y escribir:

```text
listo
```

10. El agente debe detectar la conexión persistida y continuar el onboarding.

Para WhatsApp, el flujo esperado es el mismo:

1. El estudiante completa los datos mínimos por WhatsApp.
2. Lara envía el link de Microsoft por WhatsApp.
3. El estudiante abre el link y autoriza.
4. Microsoft vuelve al backend en `/oauth/callback`.
5. El estudiante regresa a WhatsApp y escribe `listo`.
6. Lara continúa con la captura de datos restantes.

## Validaciones Después Del Callback

Revisar conexión Microsoft:

```bash
uv run python scripts/check_student_microsoft_connection.py --student-id <ID_ESTUDIANTE>
```

Resultado esperado:

- `connection_status: ok`
- `calendar_id: __default__` o un `calendar_id` específico
- scopes con `Calendars.ReadWrite`
- `has_refresh_token: true`

También se puede revisar en base de datos:

```sql
SELECT student_id, email, user_principal_name, expires_at, scopes_json
FROM microsoft_graph_connections
WHERE student_id = <ID_ESTUDIANTE>;
```

## Prueba Manual Por Scripts

Existe una prueba alternativa por terminal:

```bash
uv run python scripts/microsoft_oauth_authorize.py --student-id <ID_ESTUDIANTE>
```

Luego abrir la URL generada, autorizar y canjear el callback completo:

```bash
uv run python scripts/microsoft_oauth_exchange_code.py \
  --student-id <ID_ESTUDIANTE> \
  --callback-url 'http://localhost:8000/oauth/callback?code=...&state=...'
```

Esta prueba sirve para validar credenciales, permisos y persistencia de token, pero no valida completamente el bloqueo conversacional porque `microsoft_oauth_authorize.py` no registra el `state` pendiente en `microsoft_oauth_pending_states`.

Para validar el flujo real del agente, usar la prueba conversacional.

## Riesgos De Prueba

- Si el redirect en `.env` y Microsoft Entra no coinciden exactamente, Microsoft rechazará el canje del `code`.
- Si el flag queda en `false`, el agente no bloqueará el onboarding para pedir autorización.
- Si el redirect configurado en `.env` no coincide con Azure, Microsoft rechazará la autorización antes de volver al backend.
- Si la cuenta Microsoft pertenece a un tenant con restricciones, puede requerir consentimiento de administrador.
- Si el estudiante ya tiene conexión en `microsoft_graph_connections`, el agente puede saltar el bloque porque ya lo considera autorizado.

## Veredicto Operativo

El sistema está listo para probar localmente el consentimiento Microsoft del estudiante, siempre que antes se corrija:

```env
ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=true
MICROSOFT_REDIRECT_URI=http://localhost:8000/oauth/callback
```

Después de eso, la prueba debe hacerse preferiblemente desde el flujo conversacional, no solo con scripts, para confirmar que el bloqueo `microsoft_oauth` se activa y se libera correctamente.

Después de la corrección aplicada, el link debe generarse aunque `student_profile.email_verified` esté en `false`, siempre que ya existan:

- `full_name`
- `student_code`
- `age`
- `institutional_email`
