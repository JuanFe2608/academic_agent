# Fase 9 - Actividades academicas puntuales

## Objetivo

Registrar y gestionar actividades no recurrentes: parcial, quiz, tarea, taller, entrega, exposicion, proyecto y estudio pendiente.

## Decision principal

Se creo una entidad separada `AcademicActivity` en lugar de reutilizar `subjects`.

Motivo:

- `subjects` representa materias agregadas para priorizacion semanal.
- Una actividad puntual necesita identidad propia para CRUD, confirmacion, fecha, esfuerzo estimado, estado y persistencia.
- La priorizacion se sigue actualizando como una derivacion cuando la actividad confirmada tiene fecha y tipo compatible.

## Comportamiento implementado

- Crear actividad desde lenguaje natural.
- Captura incremental con `missing_fields_json` cuando falta tipo, materia o fecha.
- Confirmacion obligatoria antes de crear, editar o eliminar.
- Listado de actividades pendientes.
- Edicion por referencia a actividad existente.
- Eliminacion logica con estado `deleted`.
- Persistencia dedicada en `academic_activities`.
- Replanificacion marcada cuando la actividad es urgente/cercana o cuando se edita/elimina.
- Solicitudes de resolver evaluaciones siguen bloqueadas por la politica de alcance.

## Archivos principales

- `src/schemas/planning.py`
- `src/services/planning/academic_activity_service.py`
- `src/services/planning/academic_activity_persistence_service.py`
- `src/repositories/planning/activity_repository.py`
- `src/agents/support/nodes/handle_academic_update/node.py`
- `migrations/0019_academic_activities.sql`

## Validacion

Pruebas focales:

```bash
uv run --with pytest python -m pytest tests/test_academic_activity_service.py tests/test_academic_activity_persistence.py tests/test_academic_update_flow.py tests/test_conversation_router.py tests/test_agent_state_partitioning.py
```

Pruebas completas:

```bash
uv run --with pytest python -m pytest
```

Resultado al implementar la fase:

- `474 passed in 75.65s`
