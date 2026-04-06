# Reglas de Arquitectura

Fecha: 2026-04-03

## Capas

- `src/agents/support/`
  Responsabilidad: grafo LangGraph, nodos, prompts, flujos conversacionales y ensamblaje del estado.
- `src/services/`
  Responsabilidad: casos de uso, lógica de negocio y coordinación de repositorios/integraciones.
- `src/repositories/`
  Responsabilidad: persistencia durable o in-memory.
- `src/integrations/`
  Responsabilidad: clientes y adaptadores de proveedores externos.
- `src/schemas/`
  Responsabilidad: contratos estables, DTOs y modelos compartidos.
- `src/bootstrap/`
  Responsabilidad: wiring explícito, settings y composition root.
- `src/utils/`
  Responsabilidad: helpers genéricos sin conocimiento de dominio.

## Regla de dependencia

`agents -> services -> repositories/integrations -> schemas/utils`

## Reglas operativas

- `agents/` puede importar `services/`, `schemas/`, `utils/` y wrappers de compatibilidad ya curados.
- `agents/` no debe importar `repositories/` ni `integrations/` directamente.
- `services/` puede importar `repositories/`, `integrations/`, `schemas/` y `utils/`.
- `services/` no debe importar `agents/`.
- `repositories/` no debe importar `agents/` ni `services/`.
- `integrations/` no debe importar `agents/`.
- `schemas/` no debe importar `agents/`, `services/`, `repositories/` ni `integrations/`.

## Convenciones específicas del repo

- `src/agents/support/tools/` es una zona congelada.
  Solo puede contener shims mínimos de compatibilidad explícita.
- No se deben crear módulos nuevos en `tools/`.
- `src/agents/support/state.py` conserva ensamblaje del estado y re-exports puntuales.
  No debe recuperar parsing, validadores o lógica de dominio movida a `services/` o `schemas/`.
- No deben reintroducirse wrappers de repositorio o servicios dentro de `agents/`.
- El único shim legacy permitido debe justificarse como compatibilidad transitoria explícita.

## Ubicación de responsabilidades frecuentes

- Parsing y normalización de horarios: `src/services/scheduling/`.
- Matching y heurísticas de actividades: `src/services/scheduling/`.
- Renderizado y preview conversacional del horario: `src/agents/support/scheduling/`.
- Sync Microsoft: `src/services/sync/` + `src/integrations/microsoft_graph/`.
- Flujos conversacionales de replanificación: `src/agents/support/flows/replanning/`.
- Persistencia de onboarding, planning y reminders: `src/repositories/*`.

## Capacidades futuras

- RAG debe construirse bajo `src/rag/ingestion/`, `src/rag/retrieval/` y `src/rag/prompting/`.
- WhatsApp debe entrar por `src/integrations/whatsapp/` y consumirse desde `services/`, no desde `agents/`.

## Enforcement

Las reglas se validan automáticamente en [tests/test_refactor_guardrails.py](/home/jfjaramillo12/TESIS/academic_agentAI/tests/test_refactor_guardrails.py).
