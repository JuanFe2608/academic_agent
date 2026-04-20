# Fase 16 - Sincronizacion De Sesiones Con Outlook Calendar

## Objetivo

Permitir que Lara sincronice sesiones materializadas del plan de estudio con Outlook Calendar sin tocar servicios externos antes de la confirmacion del estudiante.

## Logica aplicada

1. El router detecta solicitudes como `Sincroniza mis sesiones de estudio con Outlook`.
2. El nodo `sync_study_calendar` materializa instancias del plan de forma idempotente si el plan ya esta persistido.
3. `OutlookCalendarSyncService.preview_student_calendar_sync` calcula impacto local sin llamar a Microsoft Graph:
   - eventos a crear;
   - eventos a actualizar;
   - eventos a eliminar.
4. Lara pide confirmacion antes de llamar a Outlook.
5. Si el estudiante responde `no`, no se llama a Microsoft Graph.
6. Si responde `si`, se ejecuta `sync_student_calendar`.
7. Los external ids quedan guardados en `outlook_calendar_event_links`.
8. Reintentos usan `source_instance_key`, por lo que actualizan el evento existente y no duplican calendario.
9. Si hay instancias `superseded` o `canceled` con link externo, se eliminan en Outlook y se marca el link como `deleted`.
10. Si falta OAuth o conexion Microsoft, Lara responde con un mensaje no tecnico y conserva el plan local.

## Alcance

Esta fase deja operativo el sync de sesiones dinamicas del plan. Las actividades puntuales con fecha/hora pueden proyectarse despues sobre el mismo servicio, pero requieren definir una politica clara para actividades sin hora exacta y su llave externa. El criterio de cierre del plan se cubre con sesiones materializadas y replanificacion.

## Archivos principales

- `src/services/sync/outlook_calendar_sync_service.py`
- `src/services/sync/study_calendar_sync_intent.py`
- `src/agents/support/flows/sync/study_calendar_sync.py`
- `src/agents/support/nodes/sync_study_calendar/node.py`
- `src/services/conversation/input_classifier.py`
- `src/services/conversation/router.py`
- `src/agents/support/agent.py`
- `tests/test_study_calendar_sync_flow.py`
- `tests/test_outlook_calendar_sync_service.py`

## Requisitos de base de datos

No se agrego una migracion nueva. La fase usa tablas ya creadas por:

- `migrations/0009_study_plan_instances_and_tracking.sql`
- `migrations/0013_microsoft_graph_connections_and_sync.sql`

## Pruebas

```bash
uv run --with pytest python -m pytest \
  tests/test_study_calendar_sync_flow.py \
  tests/test_outlook_calendar_sync_service.py \
  tests/test_conversation_router.py \
  tests/test_agent_wait_routing.py
```
