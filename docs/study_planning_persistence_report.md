# Persistencia de subjects, priorities y study_plan

## Objetivo

Persistir de forma relacional y versionada el catálogo académico derivado (`subjects`), el estado operativo de priorización (`priorities`) y el plan semanal inicial (`study_plan`) sin romper el flujo actual del agente.

## Tablas nuevas

- `study_priority_profiles`
  - Snapshot versionado del subestado `priorities` por estudiante.
  - Referencia opcional a `schedule_profiles` y `study_personalization_profiles`.
- `study_priority_subjects`
  - Materias del snapshot con `priority`, `difficulty`, `urgency`, `weekly_load_min` y `origin`.
- `study_plan_profiles`
  - Snapshot versionado del `study_plan`, incluyendo `rules` y `result_payload`.
  - Referencia al snapshot de prioridades usado para construir el plan.
- `study_plan_events`
  - Eventos individuales del plan semanal propuesto.

## Punto de integración en el flujo

- `persist_study_profile`
  - Persiste el snapshot inicial después de guardar el Radar.
  - Si `priorities` debe abrirse, el snapshot queda con estado `collecting`.
- `collect_priorities`
  - Persiste el snapshot cuando el usuario omite el refinamiento (`skipped`) o deja lista la base para recalcular (`study_plan`).
- `build_study_plan`
  - Persiste el snapshot final tras recalcular el plan semanal.

## Compatibilidad preservada

- Si la configuración de base de datos no está disponible, el flujo visible no se rompe.
- La persistencia nueva se ejecuta detrás de una capa de compatibilidad (`planning/persistence_support.py`).
- Los mensajes y fases visibles del agente se mantienen iguales.

## Nuevos campos de estado

- `PrioritiesState`
  - `persisted_profile_id`
  - `version_number`
  - `persistence_error`
- `StudyPlanState`
  - `persisted_profile_id`
  - `version_number`
  - `persistence_error`

## Archivos principales

- `migrations/0007_study_planning_profiles.sql`
- `migrations/0008_grant_study_planning_permissions.sql`
- `src/agents/support/planning/repository.py`
- `src/agents/support/planning/persistence_service.py`
- `src/agents/support/planning/persistence_support.py`
- `tests/test_study_planning_persistence.py`

## Verificación en PostgreSQL

Una vez aplicadas las migraciones, en DBeaver puedes validar con consultas como:

```sql
select * from study_priority_profiles order by created_at desc;
select * from study_priority_subjects order by priority_profile_id desc, position asc;
select * from study_plan_profiles order by created_at desc;
select * from study_plan_events order by study_plan_profile_id desc, position asc;
```

## Pendiente operativo

Para que esta persistencia funcione en un entorno real, debes aplicar las migraciones nuevas antes de ejecutar el agente contra PostgreSQL.
