# Priorities Phase 2 Report

## Objetivo

La Fase 2 activa el primer subflujo conversacional real de `priorities` y conecta el dominio de materias priorizadas con `study_plan` sin reescribir el grafo completo.

## Decisión de integración

Para no romper el flujo actual por defecto, la integración quedó detrás del flag:

- `ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE=1`

Con el flag apagado, el comportamiento previo se conserva.
Con el flag encendido, después de `persist_study_profile` el agente pasa a `priorities` si detecta que faltan urgencia o carga semanal explícitas.

## Arquitectura resultante

### Dominio `priorities`

Se añadieron componentes específicos:

- `config.py` para activar/desactivar el módulo
- `parser.py` para parseo determinista de materias manuales
- `formatter.py` para prompts y mensajes
- `priority_capture_service.py` para la lógica conversacional del subflujo

### Dominio `planning`

Se añadió `study_plan_sync_service.py` para consolidar:

- catálogo final de materias (`subjects`)
- regeneración de `study_plan`

Con esto, `persist_study_profile` y el nuevo nodo `build_study_plan` comparten la misma lógica de sincronización.

## Nodos nuevos

- `collect_priorities`
- `build_study_plan`

Ambos siguen el patrón de nodo fino:

- leer estado
- delegar al servicio
- devolver el update final

## Flujo activo con flag encendido

1. `persist_study_profile`
2. `collect_priorities`
3. `build_study_plan`
4. `end`

## Compatibilidad preservada

- el flujo sigue igual cuando el flag está apagado
- no se cambió el nombre público del grafo existente
- `persist_study_profile` sigue sembrando `subjects` y `study_plan` para compatibilidad
- si el usuario responde `omitir`, el agente termina sin bloquear el flujo

## Estado del agente tras esta fase

La arquitectura ya quedó mejor organizada en lo esencial:

- `scheduling` define bloques fijos
- `personalization` define técnica base
- `priorities` define materias reales y su peso
- `planning` ubica sesiones en la semana

Siguen pendientes hotspots estructurales como:

- `agent.py` todavía concentra demasiado routing
- `tools/db.py` sigue siendo un service locator global
- `apply_modifications` continúa como nodo legado grande

## Próximo paso recomendado

La siguiente fase natural es dejar de depender solo de `SubjectItem` y abrir un modelo más rico para trabajo académico, por ejemplo:

- tareas
- entregas
- exámenes
- fechas límite
- objetivos semanales

Eso permitiría pasar de una priorización estática de materias a una priorización real basada en carga y urgencia operativa.
