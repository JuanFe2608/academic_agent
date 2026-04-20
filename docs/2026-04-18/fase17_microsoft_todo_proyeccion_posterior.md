# Fase 17. Microsoft To Do Como Proyeccion Posterior

Fecha: 2026-04-18

## Objetivo

Activar Microsoft To Do como proyeccion externa para pendientes academicos accionables, sin mezclarlo con Outlook Calendar ni crear tareas sin confirmacion conversacional.

## Politica Implementada

Para el MVP, To Do sincroniza solamente sesiones de estudio materializadas que quedaron no resueltas:

- `missed`: sesion perdida, se crea como tarea para reprogramar.
- `skipped`: sesion omitida, se crea como tarea para revisar o retomar.

Cuando una sesion deja de ser accionable, la tarea vinculada se elimina y el link durable queda marcado como `deleted`. Esto evita duplicados por reintentos y mantiene la verdad externa ligada a `microsoft_todo_task_links`.

Actividades sin hora exacta, checklist de proyecto o desglose de talleres quedan como extension posterior sobre esta misma capa. No se activan aqui porque requieren la politica de descomposicion y metodo aplicado de fase 18.

## Cambios Principales

1. `MicrosoftTodoSyncService` ahora tiene preview no destructivo:
   - calcula tareas a crear, actualizar o eliminar;
   - resuelve lista To Do por `task_list_id` persistido o lista default;
   - no llama `upsert_tasks` ni `delete_tasks` durante el preview.
2. Se agrego flujo conversacional `sync_study_todo`:
   - detecta solicitud del usuario;
   - muestra resumen de cambios;
   - pide confirmacion `si/no`;
   - ejecuta sync solo si el estudiante confirma.
3. Se agrego nodo fino en `agents/support/nodes/sync_study_todo`.
4. El router conversacional reconoce solicitudes como:
   - "Sincroniza mis pendientes de estudio con Microsoft To Do".
5. El estado del plan guarda el resultado en:
   - `study_plan.rules.todo_sync`;
   - `study_plan.rules.external_sync_status_by_target.microsoft_todo`.
6. Si falta OAuth, el flujo responde de forma no tecnica y no toca To Do ni el plan local.

## Arquitectura

La implementacion conserva la frontera:

```text
agents/support/nodes -> agents/support/flows -> services/sync -> repositories/integrations
```

El nodo no importa repositorios ni clientes Microsoft. Solo delega en el flujo, y el flujo consume `get_microsoft_todo_sync_service()`.

## Base De Datos

No se agrego migracion nueva. La fase usa tablas existentes:

- `study_plan_event_instances` de la migracion `0009`.
- `microsoft_graph_connections` y `microsoft_todo_task_links` de la migracion `0013`.

## Pruebas

Pruebas focalizadas ejecutadas:

```bash
uv run --with pytest python -m pytest tests/test_microsoft_todo_service.py tests/test_study_todo_sync_flow.py tests/test_conversation_router.py tests/test_input_classification.py tests/test_scope_policy.py
```

Resultado:

```text
34 passed
```

## Criterio De Cierre

- Sesiones `missed` o `skipped` generan tareas en Microsoft To Do tras confirmacion.
- Tareas activas se eliminan cuando ya no corresponden a una sesion accionable.
- Los links durables evitan duplicados por reintento.
- Falta de OAuth bloquea solo la proyeccion externa, no el plan local.
