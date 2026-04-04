# Academic Agent AI

Agente académico orientado a LangGraph para:

- gestión de agenda y horarios;
- planificación de sesiones de estudio;
- recordatorios y seguimiento;
- replanificación ante cambios;
- personalización de método de estudio.

## Arquitectura actual

La refactorización vigente separa responsabilidades así:

- `src/agents/support/`: grafo, nodos, estado conversacional y flujos.
- `src/services/`: casos de uso y lógica de negocio.
- `src/repositories/`: persistencia PostgreSQL e in-memory.
- `src/integrations/`: proveedores externos y adaptadores de runtime.
- `src/schemas/`: contratos y modelos reutilizables.
- `src/bootstrap/`: composition root y settings.
- `src/utils/`: helpers genéricos reales.

Regla principal de dependencia:

`agents -> services -> repositories/integrations -> schemas/utils`

## Dónde va cada cosa nueva

- Si coordina fases, mensajes o `AgentState`, va en `agents/`.
- Si aplica reglas de negocio reutilizables, va en `services/`.
- Si habla con PostgreSQL u otra persistencia durable, va en `repositories/`.
- Si habla con OpenAI, Microsoft Graph, LangGraph u otro proveedor, va en `integrations/`.
- Si es un contrato compartido y estable, va en `schemas/`.
- Si es una utilidad transversal sin conocimiento de dominio, va en `utils/`.

## Reglas importantes

- `agents/` no debe importar `repositories/` ni `integrations/` directamente.
- `schemas/` no debe importar capas superiores.
- `src/agents/support/tools/` quedó congelado como zona curada de compatibilidad; no se deben agregar módulos nuevos allí.
- `src/agents/support/state.py` no debe volver a absorber parsing, validación o utilidades de dominio fuera de sus re-exports permitidos.

Las reglas detalladas y la guía de responsabilidades están en [docs/architecture_rules.md](/home/jfjaramillo12/TESIS/academic_agentAI/docs/architecture_rules.md).

## Capacidades futuras

- `src/rag/` quedó preparado para `ingestion/`, `retrieval/` y `prompting/`.
- `src/integrations/whatsapp/` quedó reservado para el adaptador de canal cuando la base actual esté estabilizada.

## Refactor arquitectónico

El plan rector está en [docs/plan_maestro_refactorizacion_arquitectura.md](/home/jfjaramillo12/TESIS/academic_agentAI/docs/plan_maestro_refactorizacion_arquitectura.md).
Los reportes ejecutados por fase viven en `docs/refactor_phase*.md`.
