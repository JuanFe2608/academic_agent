# Informe De La Arquitectura Actual Del Agente

Fecha: 2026-04-03

Documento rector analizado: `docs/plan_maestro_refactorizacion_arquitectura.md`

## 1. Resumen ejecutivo

La arquitectura actual del proyecto ya no corresponde al estado inicial mezclado dentro de `src/agents/support/`. Después del refactor, el sistema quedó principalmente como un **monolito modular orientado por grafo** con una **arquitectura por capas** y un **composition root explícito**.

En términos prácticos, hoy el proyecto usa esta combinación:

- **LangGraph como orquestador principal** del flujo conversacional;
- **arquitectura por capas** para separar conversación, negocio, persistencia e integraciones;
- **monolito modular** porque todo sigue desplegándose como una sola aplicación, pero con dominios y capas diferenciadas;
- **compatibilidad transicional controlada** mediante wrappers puntuales para no romper el runtime ni las pruebas.

Conclusión corta:

- **sí se llegó en gran medida a la arquitectura objetivo del plan**;
- **no se llegó al 100% de limpieza estructural física**, porque todavía existen wrappers legacy controlados y algunos elementos del target quedaron como placeholders o no aplican todavía.

## 2. Qué arquitectura usa hoy el agente

La arquitectura real actual puede describirse como:

### 2.1 Monolito modular orientado por grafo

El entrypoint sigue siendo el grafo LangGraph en:

- `src/agents/support/agent.py`

Ese grafo orquesta nodos y decide transiciones de fase (`profile`, `schedules`, `extras`, `validate`, `study_profile`, `study_plan`, etc.). Por eso, el sistema **no es hexagonal puro**, ni microservicios, ni un backend CRUD tradicional. El centro operativo sigue siendo un **state machine conversacional**.

### 2.2 Arquitectura por capas

La distribución real de responsabilidades hoy es:

- `agents/`
  Orquestación conversacional, grafo, nodos, flujos y ensamblaje del estado.
- `services/`
  Casos de uso y lógica de negocio reutilizable.
- `repositories/`
  Persistencia PostgreSQL e in-memory.
- `integrations/`
  Adaptadores de proveedores externos.
- `schemas/`
  Contratos y modelos reutilizables.
- `bootstrap/`
  Wiring explícito mediante container.

### 2.3 Composition root explícito

El proyecto ya tiene un `container` dedicado en:

- `src/bootstrap/container.py`

Esto corrige uno de los principales problemas originales: el wiring ya no vive disperso de forma informal dentro de `tools/db.py`, aunque ese archivo todavía existe como wrapper de compatibilidad.

## 3. Cómo quedó organizada la arquitectura

## 3.1 Capa conversacional

La capa `agents/` quedó enfocada principalmente en conversación:

- `src/agents/support/agent.py`
- `src/agents/support/state.py`
- `src/agents/support/nodes/`
- `src/agents/support/flows/`

Aquí se conservan:

- el grafo;
- el `AgentState`;
- la lógica de routing conversacional;
- los nodos LangGraph;
- los flujos multi-turno especializados.

Esto sí está alineado con el plan maestro.

## 3.2 Capa de negocio

La lógica de negocio ya vive top-level en:

- `src/services/onboarding/`
- `src/services/personalization/`
- `src/services/priorities/`
- `src/services/planning/`
- `src/services/reminders/`
- `src/services/scheduling/`
- `src/services/sync/`

Esto representa uno de los cambios estructurales más importantes del refactor, porque la lógica dejó de colgar directamente de `agents/support/*`.

## 3.3 Capa de persistencia

La persistencia ya está concentrada en:

- `src/repositories/common/`
- `src/repositories/onboarding/`
- `src/repositories/personalization/`
- `src/repositories/planning/`
- `src/repositories/reminders/`
- `src/repositories/scheduling/`
- `src/repositories/microsoft_graph/`

Esto también coincide con la arquitectura objetivo.

## 3.4 Capa de integraciones

Las integraciones externas reales quedaron separadas en:

- `src/integrations/ai/`
- `src/integrations/langgraph/`
- `src/integrations/microsoft_graph/`
- `src/integrations/whatsapp/`

Importante:

- `ai`, `langgraph` y `microsoft_graph` ya tienen implementación real;
- `whatsapp` existe hoy como placeholder estructural, no como integración funcional completa.

## 3.5 Contratos y modelos

Los modelos compartidos están centralizados en:

- `src/schemas/common.py`
- `src/schemas/onboarding.py`
- `src/schemas/scheduling.py`
- `src/schemas/personalization.py`
- `src/schemas/planning.py`
- `src/schemas/reminders.py`
- `src/schemas/microsoft_graph.py`

Esto está claramente alineado con el plan.

## 3.6 Capacidades futuras

La estructura objetivo para nuevas capacidades ya existe:

- `src/rag/ingestion/`
- `src/rag/retrieval/`
- `src/rag/prompting/`
- `src/integrations/whatsapp/`

Sin embargo, hoy estas rutas son **preparación estructural**, no dominios funcionales ya completados.

## 4. Comparación contra la arquitectura objetivo del plan maestro

## 4.1 Elementos alcanzados

Se alcanzó claramente:

- separación top-level de `services/`, `repositories/`, `schemas/`, `integrations/`, `bootstrap/` y `rag/`;
- mantenimiento de `agents/` como capa conversacional;
- `bootstrap/container.py` como composition root explícito;
- aislamiento de integraciones externas relevantes;
- guardrails automáticos para reglas de importación;
- hotspots principales adelgazados y movidos a `flows/` o `services/`;
- reducción fuerte de `tools/` como “zona gris”.

## 4.2 Elementos alcanzados parcialmente

Se alcanzó solo de forma parcial:

- `tools/`:
  no desapareció del todo; quedó reducido y congelado como zona curada de compatibilidad.
- `state.py`:
  ya no contiene la mayor parte de DTOs y utilidades de dominio, pero todavía conserva ensamblaje del estado y re-exports transicionales.
- limpieza física del árbol `agents/support/`:
  todavía existen wrappers legacy en onboarding, scheduling, planning, personalization y repositorios.
- pureza total de capas:
  se logró a nivel productivo real, pero no a nivel de desaparición absoluta de rutas legacy.

## 4.3 Elementos no alcanzados completamente

No se alcanzó todavía o no se materializó del todo:

- `src/agents/support/prompts/`
  El plan objetivo lo proponía como carpeta explícita, pero la estructura final no consolidó un directorio top-level `prompts/`; los prompts siguen distribuidos por dominios/nodos/flujos.
- `src/services/study_methods/`
  No existe como dominio independiente todavía. Esto es coherente con la nota del plan: debía aparecer solo cuando la recomendación de métodos dejara de ser scoring simple y necesitara reglas + contenido + RAG.
- eliminación total de compatibilidad legacy:
  todavía no es recomendable porque algunos wrappers siguen sosteniendo estabilidad y pruebas.

## 4.4 Evaluación final de alineación

Evaluación general:

- **alineación conceptual con la arquitectura objetivo: alta**;
- **alineación estructural real del código: alta**;
- **alineación física perfecta del árbol de carpetas: media-alta, no total**.

En otras palabras:

- **la arquitectura objetivo sí se alcanzó como arquitectura operativa real**;
- **todavía no se completó como limpieza absoluta del codebase**.

## 5. Problemas y fricciones durante la refactorización

## 5.1 Necesidad de conservar compatibilidad hacia atrás

Este fue el principal factor que impidió una limpieza más radical.

Problema:

- romper de una vez todas las rutas legacy habría puesto en riesgo el grafo, el runtime y la suite de pruebas.

Resultado:

- se dejaron wrappers de compatibilidad en varios módulos de `agents/support/*`;
- `src/agents/support/tools/db.py` sigue existiendo como wrapper hacia `bootstrap.container`;
- varios wrappers de repositorio siguen presentes mientras terminan de migrar consumidores.

Esto no es un fallo del refactor; es el costo de haber hecho un refactor evolutivo en vez de una reescritura.

## 5.2 Hotspots demasiado grandes

Varios hotspots no podían moverse “de una sola vez” sin riesgo:

- `apply_modifications`
- parsing de horarios
- flujos de scheduling
- algunos servicios de planning

La refactorización tuvo que hacerse por fases:

- primero desacoplar;
- luego mover;
- después partir internamente;
- finalmente proteger con pruebas y guardrails.

Esto obligó a mantener durante un tiempo módulos mixtos o wrappers temporales.

## 5.3 Colisión entre arquitectura objetivo y estructura histórica

El árbol antiguo dentro de `src/agents/support/` no se podía borrar de inmediato porque concentraba:

- imports heredados;
- puntos de entrada del grafo;
- contratos usados por nodos;
- dependencias de pruebas.

Por eso, la nueva arquitectura quedó primero como **origen real**, mientras la antigua quedó como **fachada de compatibilidad** en varios puntos.

## 5.4 Riesgo documental y numeración histórica

Durante la refactorización también hubo una fricción de documentación:

- algunos reportes históricos por dominio (`scheduling_phase4_report.md`, `study_planning_phase5_report.md`) no usan la misma numeración que el plan maestro de arquitectura.

Esto podía inducir a confundir “fase funcional” con “fase de refactor arquitectónico”.

La documentación nueva reduce ese problema, pero el riesgo histórico no desaparece completamente mientras esos documentos sigan coexistiendo.

## 5.5 Objetivo de pureza versus realidad del producto

El plan maestro apuntaba a una arquitectura más limpia y autoexplicativa. Sin embargo, la necesidad de:

- no romper el entrypoint;
- no romper el estado conversacional;
- no romper la persistencia;
- no romper las pruebas;

impidió aplicar una limpieza total inmediata.

Eso deja una conclusión importante:

- el refactor fue exitoso desde la perspectiva arquitectónica;
- pero sigue siendo un refactor **transicionalmente conservador**, no una reestructuración destructiva.

## 6. Estado actual de la calidad arquitectónica

Hoy la calidad arquitectónica es mejor que al inicio por cinco razones concretas:

1. El wiring ya está centralizado en `bootstrap/`.
2. La lógica de negocio ya no vive mayoritariamente en `agents/`.
3. Las integraciones externas ya no viven mezcladas con la conversación.
4. Los contratos compartidos ya están en `schemas/`.
5. Existen pruebas de guardrail para evitar recaídas.

El cambio más relevante no es solo el árbol de carpetas, sino que **las fronteras arquitectónicas ahora son verificables**.

## 7. Conclusión final

La nueva arquitectura del agente quedó como un:

**monolito modular orientado por grafo, con arquitectura por capas y composition root explícito**.

Síntesis final:

- **sí se alcanzó la arquitectura objetivo del plan en lo esencial**;
- **no se alcanzó todavía una eliminación total de compatibilidad legacy**;
- **la arquitectura real ya opera según las capas objetivo**;
- **lo que queda pendiente es sobre todo deuda de transición y limpieza final**, no una falla de diseño base.

## 8. Recomendación técnica

Si se quiere cerrar la refactorización con criterio de “arquitectura final” y no solo “arquitectura operativa”, los siguientes pasos naturales serían:

1. seguir reduciendo wrappers legacy que ya no tengan consumidores;
2. decidir si `prompts/` merece consolidarse como carpeta real o si la organización por dominio es suficiente;
3. evaluar si `AgentState` debe seguir exponiendo tantos re-exports de compatibilidad;
4. crear `services/study_methods/` solo cuando el producto realmente abra esa capacidad;
5. limpiar artefactos residuales del árbol antiguo que ya no aporten compatibilidad real.
