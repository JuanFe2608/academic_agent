# Baseline Y Guardrails De Refactorizacion

Fecha de baseline: 2026-04-03

Estado: activo para fases 0 y 1

Documento rector: `docs/plan_maestro_refactorizacion_arquitectura.md`

## 1. Alcance Del Baseline

Este documento convierte la fase 0 del plan maestro en una linea base operativa y verificable para el repositorio actual.

Su objetivo es fijar:

- los modulos realmente activos del runtime;
- la direccion objetivo de separacion por capas;
- los hotspots priorizados;
- las reglas de dependencia permitidas durante el refactor;
- los wrappers temporales aceptados;
- el checklist minimo de regresion;
- y la Definition of Done para las fases 0 y 1.

## 1.1 Direccion Arquitectonica Objetivo

La evolucion del repositorio debe tender a esta separacion de responsabilidades:

- `agents/`: nodos LangGraph, orquestacion conversacional y estado conversacional
- `services/`: logica de negocio y casos de uso
- `repositories/`: persistencia PostgreSQL y queries
- `schemas/`: modelos Pydantic, DTOs y contratos reutilizables
- `integrations/`: proveedores externos y adaptadores de runtime
- `rag/`: ingestion, retrieval, embeddings y prompting grounded
- `utils/`: helpers compartidos reales
- `docs/`: documentacion tecnica

Excepcion deliberada:

- `bootstrap/` se acepta como package auxiliar para el composition root y settings compartidos, sin competir con `services/`, `repositories/` o `integrations/`.

## 2. Baseline Tecnica Actual

Entrypoints y runtime activos:

- runtime LangGraph: `langgraph.json`
- grafo principal: `src/agents/support/agent.py:agent`
- checkpointer activo: `src/agents/support/tools/langgraph_checkpointer.py:create_checkpointer`

Dominios productivos activos:

- onboarding
- scheduling
- personalization
- priorities
- planning
- reminders
- sync Microsoft

Infraestructura activa hoy:

- PostgreSQL como persistencia operativa
- `src/agents/support/tools/db.py` como service locator legado
- `src/agents/support/tools/db_config.py` como resolucion heredada de conexion
- `src/agents/support/tools/langgraph_checkpointer.py` para persistencia de threads

Evidencia de seguridad actual:

- 43 archivos de prueba en `tests/`
- migraciones SQL versionadas en `migrations/`

## 3. Inventario Operativo

Modulos que deben conservar compatibilidad durante fases 0 y 1:

- `src/agents/support/agent.py`
- `src/agents/support/state.py`
- `src/agents/support/tools/db.py`
- `src/agents/support/tools/db_config.py`
- `src/agents/support/tools/langgraph_checkpointer.py`
- getters `get_*` y setters `set_*` consumidos por nodos y pruebas

Modulos de soporte o legado que no son entrypoint del runtime:

- `main.py`
- `prueba1.py`
- `README.md`
- `INDICATIONS.md`
- `scripts/simulate_support_flow.py`

Interpretacion operativa:

- estos archivos no deben condicionar la arquitectura objetivo;
- cualquier limpieza sobre ellos queda fuera del camino critico de fases 0 y 1;
- el refactor debe priorizar wiring e infraestructura compartida antes de limpiar PoCs o placeholders.

## 4. Hotspots Priorizados

Prioridad alta:

| Archivo | Tamano aprox. | Riesgo dominante |
| --- | ---: | --- |
| `src/agents/support/nodes/apply_modifications/node.py` | 2503 lineas | mezcla de conversacion, reglas y mutacion de estado |
| `src/agents/support/tools/llm.py` | 575 lineas | mezcla de proveedor, prompting y parsing |
| `src/agents/support/agent.py` | 626 lineas | crecimiento del routing y wiring central |
| `src/agents/support/state.py` | 514 lineas | mezcla de estado y utilidades de dominio |
| `src/agents/support/scheduling/schedule_review_service.py` | 677 lineas | hotspot funcional del dominio scheduling |
| `src/agents/support/reminders_repository.py` | 681 lineas | repositorio grande y sensible a persistencia |
| `src/agents/support/planning/repository.py` | 483 lineas | persistencia transaccional relevante |

Prioridad media:

- `src/agents/support/onboarding/repository.py`
- `src/agents/support/planning/tracking_repository.py`
- `src/agents/support/tools/microsoft_graph_state_repository.py`
- `src/agents/support/tools/microsoft_graph_sync_repository.py`

Orden recomendado de intervencion temprana:

1. `tools/db.py` y `db_config.py`
2. errores compartidos de infraestructura
3. `state.py`
4. repositorios top-level
5. integraciones externas y `tools/llm.py`

## 5. Reglas De Dependencia Vigentes

Regla objetivo de referencia:

`agents -> services -> repositories/integrations -> schemas/utils`

Guardrails aplicables desde ya:

- `src/agents/support/nodes/` no debe importar repositorios directamente.
- Excepcion temporal permitida: captura de errores de onboarding en `send_email_verification` y `verify_email_code`.
- `src/agents/support/tools/db.py` y `src/agents/support/tools/db_config.py` quedan congelados como wrappers de compatibilidad; no deben absorber logica nueva.
- La resolucion de configuracion compartida debe vivir en `src/bootstrap/settings.py`.
- Los errores compartidos de infraestructura deben vivir fuera de onboarding.
- No se puede renombrar `src/agents/support/agent.py` ni cambiar `langgraph.json` en fases 0 y 1.
- No se pueden mezclar en el mismo PR movimientos cosmeticos de carpetas con cambios funcionales.

## 6. Wrappers Temporales Aceptados

Wrappers aprobados para esta etapa:

- `src/agents/support/tools/db.py` delegando a `src/bootstrap/container.py`
- `src/agents/support/tools/db_config.py` delegando a `src/bootstrap/settings.py`
- `src/agents/support/onboarding/repository.py` reexportando `RepositoryConfigurationError` desde infraestructura compartida
- `src/agents/support/tools/langgraph_checkpointer.py` manteniendo su API publica mientras delega la resolucion de settings

Reglas para wrappers:

- deben ser delgados;
- no agregan reglas de negocio;
- deben declarar que son temporales;
- su eliminacion queda diferida hasta que los consumidores migren.

## 7. Checklist De Regresion

Checklist minimo por PR de arquitectura:

1. Verificar que `langgraph.json` siga apuntando a `./src/agents/support/agent.py:agent`.
2. Ejecutar smoke checks de importacion del grafo y del container.
3. Ejecutar pruebas del wiring tocado.
4. Ejecutar pruebas de los dominios afectados por el cambio.
5. Confirmar que getters y setters heredados siguen siendo compatibles con las pruebas existentes.
6. Confirmar que los wrappers no contienen logica adicional.
7. Confirmar que no aparecieron nuevos imports directos desde nodos hacia repositorios.

## 8. Definition Of Done

Definition of Done de fase 0:

- existe documento baseline con hotspots y guardrails;
- el runtime actual esta identificado;
- hay smoke checks versionados;
- el criterio de compatibilidad temporal esta documentado.

Definition of Done de fase 1:

- existe `src/bootstrap/container.py`;
- existe `src/bootstrap/settings.py`;
- existe modulo compartido de errores de infraestructura;
- `src/agents/support/tools/db.py` es wrapper y ya no es el origen real del wiring;
- la resolucion compartida de configuracion sale de `db_config.py`;
- los getters y setters heredados siguen pasando pruebas;
- el grafo mantiene el mismo entrypoint.
