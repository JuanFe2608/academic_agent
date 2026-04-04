# Refactor Arquitectura - Fase 7

Fecha: 2026-04-03

## Objetivo ejecutado

Se intervino el camino productivo activo y se retiró compatibilidad ya agotada:

- `tools/schedule_parser.py` salió del limbo de `tools/` y quedó reubicado en `src/services/scheduling/text_parser/`, además dividido por responsabilidad;
- la generación de eventos extracurriculares salió del nodo hotspot y quedó en `src/services/scheduling/extracurricular_events.py`;
- se removieron wrappers legacy ya sin uso productivo en `auth/`, `agents/support/tools/`, `agents/support/scheduling/`, `agents/support/priorities/` y `agents/support/planning/`.

## Hotspots tratados

- `nodes/generate_tentative_extracurricular/node.py` quedó como wrapper fino;
- `services/scheduling/text_parser/` reemplaza al monolito previo de parseo;
- `flows/replanning/apply_modifications.py` ya consume servicios reales (`services.scheduling.*`) en vez de depender de hotspots legacy.

## Riesgo residual

`src/agents/support/flows/replanning/apply_modifications.py` sigue siendo el archivo más grande del camino de replanificación. En esta fase quedó desacoplado del parser legacy y de la generación extracurricular legacy, pero una partición interna más agresiva conviene hacerla solo con cobertura específica del flujo de replanificación.

## Remoción de legado

Se eliminaron los wrappers ya agotados de:

- `src/auth/microsoft_auth.py`
- `src/agents/support/tools/llm.py`
- `src/agents/support/tools/microsoft_graph_clients.py`
- `src/agents/support/tools/langgraph_checkpointer.py`
- `src/agents/support/tools/calendar_outlook.py`
- `src/agents/support/tools/microsoft_todo.py`
- `src/agents/support/tools/schedule_parser.py`
- `src/agents/support/scheduling/schedule_*_service.py`
- `src/agents/support/priorities/priority_capture_service.py`
- `src/agents/support/planning/persistence_support.py`

## Guardrails

- el repo ya no permite imports productivos desde wrappers conversacionales o de integración legacy;
- se valida que los wrappers removidos no reaparezcan;
- `generate_tentative_extracurricular/node.py` se controla como nodo fino.
