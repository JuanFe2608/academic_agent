# Study Planning Phase 5 Report

## Objetivo

La Fase 5 introduce el primer servicio funcional de planificación semanal de estudio sobre la base ya estabilizada de `scheduling` y `study_profile`.

Esta fase **no** reescribe el grafo ni crea todavía un subflujo conversacional completo de planificación. Su propósito es dejar implementada la capacidad de generar un plan semanal inicial, determinista y compatible con el estado actual.

## Qué se implementó

Se creó `src/agents/support/planning/study_planning_service.py` para generar `study_plan.plan_events` a partir de:

- bloques fijos confirmados en `schedule.blocks`
- restricciones de `constraints`
- técnicas priorizadas en `study_profile.top_techniques`
- materias explícitas de `subjects` o derivadas automáticamente del horario académico

También se creó `src/agents/support/planning/state_helpers.py` para normalizar `study_plan`, `constraints`, `study_profile` y `subjects` sin romper el contrato actual del grafo.

## Integración elegida

Para no reescribir el flujo LangGraph en esta etapa, la generación del primer plan semanal se integró en `src/agents/support/nodes/persist_study_profile/node.py`.

Esto permite que, cuando el Radar de estudio termina y se persiste correctamente:

- el mensaje final al usuario siga siendo el mismo,
- la `phase` siga terminando en `end`,
- y el estado ya quede sembrado con un `study_plan` inicial.

## Reglas deterministas base

La versión actual del planificador usa reglas explícitas y predecibles:

- la técnica principal ajusta la duración objetivo de la sesión
- `repeticion_espaciada` fuerza separación mínima entre sesiones del mismo tema
- `interleaving` activa orden round-robin entre materias cuando aplica
- el plan nunca invade bloques fijos ya confirmados
- el plan respeta `max_study_per_day_min`
- si no existen materias explícitas, se derivan desde bloques académicos confirmados

## Antes vs después

### Antes

- el proyecto tenía `study_plan` en el estado, pero sin servicio funcional real
- no existía una forma determinista de convertir horario confirmado + Radar en sesiones de estudio
- `persist_study_profile` cerraba el flujo sin dejar una base útil para planificación posterior

### Después

- existe un servicio funcional y testeado para generar el plan semanal inicial
- el estado `study_plan` ya se usa con datos reales
- el grafo no cambia externamente y la compatibilidad visible se preserva

## Compatibilidad preservada

- no se cambiaron nombres públicos del grafo
- no se añadieron nodos nuevos al `StateGraph`
- no se modificó el mensaje final del Radar de estudio
- si el planificador falla internamente, `persist_study_profile` conserva el comportamiento previo mediante una capa de compatibilidad

## Archivos involucrados

### Nuevos

- `src/agents/support/planning/__init__.py`
- `src/agents/support/planning/state_helpers.py`
- `src/agents/support/planning/study_planning_service.py`
- `tests/test_study_planning_service.py`
- `docs/2026-04-03/study_planning_phase5_report.md`

### Actualizados

- `src/agents/support/nodes/persist_study_profile/node.py`

## Cobertura agregada

Las nuevas pruebas validan:

- derivación de materias desde el horario académico
- respeto del máximo de estudio por día
- separación mínima entre sesiones para `repeticion_espaciada`
- integración segura con `persist_study_profile`

## Limitaciones conscientes de esta fase

Esta fase todavía **no** implementa:

- flujo conversacional de prioridades académicas
- CRUD de materias/tareas
- planificación basada en entregas o fechas límite
- persistencia específica del plan semanal en base de datos
- replanificación automática
- sincronización con Outlook / To Do / WhatsApp

## Resultado arquitectónico

Tras esta fase, la arquitectura queda con una base clara para crecer:

- `scheduling` consolida los bloques fijos confirmados
- `personalization` define la técnica principal del estudiante
- `planning` genera un plan semanal inicial reutilizable y determinista

## Siguiente paso recomendado

La siguiente fase natural es crear el primer módulo de **priorización académica** para dejar de inferir materias solo desde el horario y permitir que el plan semanal considere carga, dificultad, urgencia y objetivos reales del estudiante.
