# Refactor Fase 3

Fecha: 2026-04-03

Estado: completada

Documento rector: `docs/2026-04-03/plan_maestro_refactorizacion_arquitectura.md`

## Objetivo Ejecutado

Sacar la persistencia PostgreSQL e in-memory fuera de `agents/` y normalizar una capa de repositorios top-level en `src/repositories/`, preservando compatibilidad hacia atrás mediante wrappers delgados.

## Cambios Aplicados

Nueva capa top-level de repositorios:

- `src/repositories/common/`
- `src/repositories/onboarding/`
- `src/repositories/personalization/`
- `src/repositories/scheduling/`
- `src/repositories/planning/`
- `src/repositories/reminders/`
- `src/repositories/microsoft_graph/`

Capa común mínima de persistencia:

- `src/repositories/common/errors.py`
- `src/repositories/common/postgres.py`

Repositorios migrados:

- onboarding
- scheduling
- personalization
- planning snapshot persistence
- planning instances persistence
- planning tracking persistence
- reminders
- microsoft graph state persistence
- microsoft graph sync read repository

Compatibilidad temporal preservada:

- `src/agents/support/*/repository.py`
- `src/agents/support/reminders_repository.py`
- `src/agents/support/tools/microsoft_graph_state_repository.py`
- `src/agents/support/tools/microsoft_graph_sync_repository.py`

Estas rutas legacy quedaron como wrappers de compatibilidad y ya no son el origen real de la persistencia.

## Resultado Arquitectónico

Después de esta fase:

- `services/`, `auth/`, `bootstrap/` y el código productivo del agente consumen `repositories.*` como origen real;
- `src/repositories/` ya no depende de `agents/`;
- la capa de repositorios comparte manejo mínimo de configuración y conexión PostgreSQL;
- el acceso a datos quedó topológicamente separado del grafo.

## Guardrails Añadidos

- smoke check para impedir imports productivos hacia módulos legacy de repositorio bajo `agents.support.*`;
- guardrail específico para que los nodos no vuelvan a importar repositorios legacy.

## Siguiente Paso Recomendado

Fase 4:

- mover clientes y adapters externos fuera de `tools/`;
- separar Microsoft Graph cliente HTTP vs persistencia local;
- mover `langgraph_checkpointer` y otros adapters de runtime a `integrations/`.
