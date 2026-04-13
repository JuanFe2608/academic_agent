# Checklist De Prueba Del Horario Fijo En Outlook

Fecha: 2026-04-10

## 1. Preparación

- Aplicar la migración `migrations/0015_schedule_profile_end_dates.sql`.
- Tener variables OAuth de Microsoft configuradas.
- Tener un estudiante ya persistido en PostgreSQL.

## 2. Conectar Outlook

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run python scripts/microsoft_oauth_authorize.py --student-id 1
```

- Abrir la URL.
- Autorizar Microsoft.
- Copiar la URL completa del callback.

```bash
uv run python scripts/microsoft_oauth_exchange_code.py --student-id 1 --callback-url 'http://localhost:8000/auth/microsoft/callback?code=...&state=student:1:microsoft'
```

## 3. Verificar Conexión Microsoft

```bash
uv run python scripts/check_student_microsoft_connection.py --student-id 1
```

Validar:

- `connection_status: ok`
- `calendar_id` presente o `__default__`

## 4. Confirmar Horario En El Flujo

- Llegar al mensaje:

```text
✅ ¿Entendí bien tu horario?
1. Sí, está correcto
2. No, quiero corregir algo
```

- Responder `1`.
- Cuando pida la fecha límite, responder por ejemplo:

```text
2026-06-30
```

## 5. Validar Persistencia Interna

```bash
uv run python scripts/check_student_fixed_schedule.py --student-id 1
```

Validar:

- existe `schedule_profile_id` actual
- `schedule_end_date` tiene la fecha enviada
- `block_count` es mayor que `0`

## 6. Validar Sync Outlook

```bash
uv run python scripts/check_student_fixed_schedule_sync.py --student-id 1
```

Validar:

- `active_synced_blocks` es mayor que `0`
- `external_provider = outlook`
- `external_sync_status = active`

## 7. Forzar Sync Manual Si Hace Falta

```bash
uv run python scripts/sync_outlook_fixed_schedule.py --student-id 1
```

## 8. Probar Cambio Manual En Outlook

- Editar un evento del horario fijo directamente en Outlook.
- Cambiar por ejemplo el título o la hora.

## 9. Ejecutar Reconciliación

```bash
uv run python scripts/reconcile_outlook_fixed_schedule.py --student-id 1
```

Validar:

- `drifted > 0` si hubo cambios manuales
- `missing > 0` si borraste un evento en Outlook

## 10. Reparar Outlook Desde La BD

- Si la reconciliación encontró `drifted` o `missing`, ejecutar:

```bash
uv run python scripts/repair_outlook_fixed_schedule.py --student-id 1
```

Validar:

- `repair_outlook_fixed_schedule ok`
- `restored > 0` si el evento fue editado manualmente
- `recreated > 0` si el evento fue borrado en Outlook
- luego volver a correr:

```bash
uv run python scripts/check_student_fixed_schedule_sync.py --student-id 1
```

Validar:

- los bloques reparados vuelven a `external_sync_status = active`

## 11. Probar Reparación Desde El Flujo Del Agente

- Ejecutar primero la reconciliación para marcar drift en BD.
- Escribirle de nuevo al agente.
- Validar que aparezca el mensaje:

```text
🛠️ Detecté cambios manuales en tu horario fijo de Outlook.
```

- Probar la opción `1` para restaurar Outlook desde el horario oficial del asistente.
- Probar la opción `2` en otro caso controlado para iniciar un horario fijo nuevo.
- Probar la opción `3` para dejar la reparación pendiente.

## 12. Verificar Renovación Cuando Venza

- Esperar a que la fecha límite pase o usar un caso de prueba controlado.
- Escribirle de nuevo al agente.
- Validar que aparezca el mensaje de renovación del horario fijo.
- Probar:
  - mantener el mismo horario con una nueva fecha
  - o iniciar un horario nuevo
