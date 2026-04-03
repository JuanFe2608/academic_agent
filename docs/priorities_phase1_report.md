# Priorities Phase 1 Report

## Objetivo

Esta fase crea el primer dominio explícito de `priorities` para que la planificación semanal no cargue con la responsabilidad de interpretar materias, carga y urgencia.

## Diagnóstico arquitectónico previo

Después de las fases anteriores, la arquitectura quedó **mucho mejor organizada**, pero no completamente cerrada:

- `scheduling` ya tiene servicios de aplicación claros
- `planning` ya existe como dominio propio
- `personalization` ya tiene scoring y persistencia separados

Sin embargo, todavía quedaban tres focos de deuda:

- `src/agents/support/agent.py` sigue siendo un router grande del grafo
- `src/agents/support/tools/db.py` sigue funcionando como service locator global
- `study_planning_service` todavía estaba resolviendo materias y prioridades por su cuenta

## Qué se implementó

Se creó el dominio `src/agents/support/priorities/` con:

- `state_helpers.py` para normalizar `subjects`
- `subject_prioritization_service.py` para resolver materias priorizadas

El servicio nuevo produce dos salidas coherentes:

- `subject_items`: la versión canónica que debe vivir en el estado
- `prioritized_subjects`: la versión enriquecida para consumo de `planning`

## Reglas base del priorizador

El primer priorizador combina de forma determinista:

- prioridad declarada
- dificultad
- urgencia
- carga semanal estimada
- días preferentes derivados del horario académico cuando existen

Si `subjects` ya existe, preserva esa fuente como principal.
Si `subjects` está vacío, genera una base mínima desde `schedule.blocks` académicos.

## Refactor aplicado sobre planning

`src/agents/support/planning/study_planning_service.py` dejó de resolver materias por su cuenta y ahora delega esa responsabilidad al dominio `priorities`.

Con esto se logra la separación correcta:

- `priorities`: decide qué materias pesan más y cuántas sesiones deberían sugerirse
- `planning`: decide dónde ubicar esas sesiones en la semana

## Compatibilidad preservada

- no se cambió el mensaje final del Radar
- no se reescribió el grafo
- no se activó todavía un flujo conversacional nuevo de `priorities`
- `persist_study_profile` ahora normaliza y deja sembrado `subjects` además de `study_plan`

## Resultado arquitectónico

La arquitectura del agente **sí está organizada lo suficiente para seguir creciendo**, pero con una precisión importante:

- está organizada por dominios principales
- está lista para crecer de forma incremental
- pero todavía no está “cerrada” porque el router y algunos nodos legado siguen siendo grandes

En otras palabras: **ya no está desordenada**, pero todavía requiere fases posteriores de consolidación.

## Próximo paso recomendado

La siguiente fase natural es activar el primer subflujo conversacional de `priorities` para capturar del estudiante:

- materias reales
- urgencia de cada una
- carga/tiempo objetivo por semana
- dificultad percibida

Así el plan semanal dejará de depender del fallback derivado desde el horario y empezará a usar prioridades académicas reales capturadas por el agente.
