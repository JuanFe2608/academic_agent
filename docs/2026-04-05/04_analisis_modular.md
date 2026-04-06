# Analisis Modular Del Proyecto

Fecha: 2026-04-05

Estado: auditoria tecnica en progreso

## 1. Criterios de evaluación modular

Para esta fase se evaluó la modularidad real del repositorio con los siguientes criterios:

1. Responsabilidad única
   Un módulo o archivo debería tener un propósito dominante y entendible.

2. Cohesión interna
   Las funciones y clases dentro del mismo módulo deberían pertenecer al mismo problema.

3. Acoplamiento entre módulos
   Se revisó si las dependencias entre capas son razonables o si atraviesan fronteras innecesarias.

4. Dirección de dependencias
   Se evaluó si la dirección dominante `agents -> services -> repositories/integrations` se mantiene o si hay fugas.

5. Claridad de ubicación
   Se revisó si cada archivo está donde un mantenedor esperaría encontrarlo.

6. Tamaño y densidad de archivos
   Archivos muy grandes o multitarea suelen ocultar más de una responsabilidad y hacen más difícil evolucionar el sistema.

7. Reutilización y duplicación
   Se revisó si hay lógica repetida o patrones copiados que deberían estar abstraídos.

8. Testabilidad y reemplazabilidad
   Se evaluó si la estructura facilita cambiar implementaciones y probar por capas.

9. Limpieza operacional
   Se consideraron scripts, shims y superficies legacy que afectan la mantenibilidad real del proyecto.

## 2. Evaluación por módulo principal

### 2.1 `src/agents/support/`

Responsabilidad actual:

- orquestación conversacional;
- grafo LangGraph;
- routers;
- nodos;
- flujos conversacionales;
- helpers de scheduling/personalización/prioridades.

Evaluación:

- La responsabilidad principal sí tiene sentido: este paquete es el runtime conversacional.
- La separación entre `nodes/` y `flows/` mejoró después del refactor.
- La modularidad interna todavía no está completamente limpia porque parte de la lógica de aplicación vive aquí y no en `src/services/`.

Fortalezas:

- `src/agents/support/nodes/*/node.py` ya son wrappers delgados en varios hotspots.
- `src/agents/support/dependencies.py` evita imports directos de repositorios desde los nodos.
- `src/agents/support/flows/replanning/` muestra un intento claro de subdividir un subflujo complejo.

Problemas:

- [agent.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/agent.py) tiene 626 líneas y mezcla:
  - definición del grafo,
  - routing,
  - lógica de espera,
  - decisiones por fase.
- [schedule_capture_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_capture_service.py) tiene 559 líneas y concentra demasiada lógica de estado, prompts y mutación.
- [schedule_review_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_review_service.py) tiene 677 líneas y mezcla confirmación, corrección, parseo incremental y reconstrucción de estado.
- [persistence_support.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/planning/persistence_support.py) está en capa de agente, pero coordina persistencia, materialización y reminders.
- [state.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/state.py) sigue actuando como bus transversal de muchos subdominios.
- [__init__.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/scheduling/__init__.py) reexporta a la vez modelos de `services.scheduling.models` y helpers de `agents.support.scheduling.*`, mezclando capas en una sola fachada.
- [db.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/tools/db.py) es un shim legacy que mantiene deuda técnica viva.

Dictamen:

- módulo fuerte para MVP;
- modularidad media;
- deuda localizada pero importante en scheduling, routing y planning post-Radar.

### 2.2 `src/services/`

Responsabilidad actual:

- capa principal de aplicación y negocio;
- persistencia coordinada;
- scoring;
- planning;
- tracking;
- sync externo.

Evaluación:

- Es el módulo más sano del proyecto.
- La mayoría de los dominios ya viven donde deberían vivir.
- La separación por subdominio (`onboarding`, `scheduling`, `personalization`, `planning`, `reminders`, `sync`) favorece el crecimiento.

Fortalezas:

- [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/onboarding/service.py) en onboarding está bien alineado con su responsabilidad.
- [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/scheduling/service.py) es delgado y claro.
- [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/personalization/service.py) está bien cohesionado.
- La separación entre [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/reminders/service.py) y [dispatcher.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/reminders/dispatcher.py) es una buena decisión modular.
- [study_plan_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/study_plan_sync_service.py) separa bien sincronización de materias y plan.

Problemas:

- Muchos servicios mezclan lógica de negocio con construcción de infraestructura mediante `build_*service()`.
  Evidencia:
  - [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/onboarding/service.py)
  - [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/scheduling/service.py)
  - [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/personalization/service.py)
  - [persistence_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/persistence_service.py)
  - [materialization_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/materialization_service.py)
  - [tracking_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/tracking_service.py)
  - [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/reminders/service.py)
  - [outlook_calendar_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/outlook_calendar_sync_service.py)
  - [microsoft_todo_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/microsoft_todo_sync_service.py)
- [study_planning_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/study_planning_service.py) tiene 523 líneas. Sigue siendo coherente, pero ya es un archivo de alta densidad.
- [tracking_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/tracking_service.py) tiene 526 líneas y repite mucho patrón transaccional por tipo de cambio de sesión.
- [outlook_calendar_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/outlook_calendar_sync_service.py) y [microsoft_todo_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/microsoft_todo_sync_service.py) duplican gran parte del esqueleto de sync.

Dictamen:

- módulo bien orientado;
- suficiente para crecer;
- necesita más separación entre lógica de aplicación y builders de infraestructura.

### 2.3 `src/repositories/`

Responsabilidad actual:

- persistencia durable;
- contratos `Protocol`;
- implementaciones `InMemory` y `Postgres`.

Evaluación:

- En general está bien organizado.
- La estrategia `Protocol + InMemory + Postgres` mejora testabilidad y evolución.
- La separación por dominio es correcta.

Fortalezas:

- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/onboarding/repository.py) está bien modelado.
- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/scheduling/repository.py) es claro y consistente.
- [state_repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/microsoft_graph/state_repository.py) concentra bien el estado durable de conexiones y links.

Problemas:

- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/planning/repository.py) importa `validate_event` desde `services.scheduling.validation`, lo que rompe la dirección ideal de dependencias.
- En planning hay doble validación:
  - [persistence_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/persistence_service.py) valida eventos;
  - [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/planning/repository.py) vuelve a validarlos.
- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/planning/repository.py) tiene 483 líneas y combina dos subpersistencias distintas:
  - priorities snapshot
  - study plan snapshot

Dictamen:

- buen módulo de persistencia;
- problema puntual serio en planning;
- no se observan ciclos duros de importación, pero sí una fuga de capa.

### 2.4 `src/integrations/`

Responsabilidad actual:

- adaptadores externos de AI, Microsoft Graph y LangGraph.

Evaluación:

- `integrations/ai/` y `integrations/langgraph/` están razonablemente limpios.
- `integrations/microsoft_graph/` tiene la mayor deuda modular dentro de infraestructura.

Fortalezas:

- [checkpointer.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/langgraph/checkpointer.py) está bien ubicado y es cohesivo.
- [_clients_impl.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/_clients_impl.py) define bien contratos y clientes desacoplados.
- [structured_extraction.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/ai/structured_extraction.py) es una frontera clara.

Problemas:

- [auth_client.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/auth_client.py) tiene 737 líneas y mezcla:
  - config OAuth,
  - DTOs,
  - transporte HTTP,
  - token store protocol,
  - adapter a repositorio,
  - cliente OAuth,
  - carga de entorno.
- [auth_client.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/auth_client.py) depende directamente de [state_repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/microsoft_graph/state_repository.py), lo que reduce pureza de la frontera.
- `whatsapp/` existe solo como placeholder y no aporta modularidad funcional todavía.

Dictamen:

- módulo correcto a nivel de intención;
- limpieza buena en AI y LangGraph;
- deuda alta en OAuth Microsoft.

### 2.5 `src/bootstrap/`

Responsabilidad actual:

- composition root;
- settings de runtime;
- errores de bootstrap.

Evaluación:

- módulo bien ubicado y útil para el refactor.
- resuelve de forma explícita el wiring del sistema.

Fortalezas:

- [container.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/bootstrap/container.py) centraliza composición.
- [settings.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/bootstrap/settings.py) resuelve configuración compartida de manera limpia.

Problemas:

- [container.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/bootstrap/container.py) funciona como service locator controlado a través de `agents.support.dependencies`.
- La composición no está completamente aislada, porque muchos servicios también mantienen sus propios `build_*`.

Dictamen:

- módulo sano;
- deuda baja;
- útil para seguir creciendo.

### 2.6 `src/schemas/`

Responsabilidad actual:

- contratos reutilizables;
- DTOs transversales.

Evaluación:

- es uno de los mejores módulos del proyecto.
- la salida de DTOs fuera de `agents.support.state` fue una mejora real del refactor.

Fortalezas:

- [onboarding.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/schemas/onboarding.py)
- [scheduling.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/schemas/scheduling.py)
- [planning.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/schemas/planning.py)

Problemas:

- pocos.
- la mayor debilidad no está en `schemas`, sino en que `AgentState` sigue agregando demasiados subestados al mismo tiempo.

Dictamen:

- módulo fuerte;
- alta cohesión;
- bajo acoplamiento.

### 2.7 `scripts/`

Responsabilidad actual:

- entrypoints operativos manuales para tareas administrativas o simulaciones.

Evaluación:

- es el módulo más débil fuera del runtime principal.
- está claramente en transición y no refleja completamente la arquitectura actual.

Problemas:

- [run_due_reminders.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/run_due_reminders.py) importa `agents.support.reminders_dispatcher`, ruta legacy.
- [backfill_study_plan_instances.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/backfill_study_plan_instances.py) importa:
  - `agents.support.planning.materialization_service`
  - `agents.support.state import Event, StudyPlanState`
  - `agents.support.tools.db_config`
- [microsoft_oauth_exchange_code.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/microsoft_oauth_exchange_code.py) importa rutas legacy de `agents.support.tools.*`.
- [simulate_support_flow.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/simulate_support_flow.py) monta un flujo manual por nodos, no por el grafo real, y usa piezas no centrales del runtime actual.

Dictamen:

- modularidad baja;
- deuda operativa alta;
- no rompe el core, pero sí daña la consistencia del proyecto.

### 2.8 `tests/`

Responsabilidad actual:

- pruebas unitarias y guardrails de arquitectura.

Evaluación:

- módulo muy valioso para sostener la modularidad conseguida por el refactor.

Fortalezas:

- [test_refactor_guardrails.py](/home/jfjaramillo12/TESIS/academic_agentAI/tests/test_refactor_guardrails.py) protege límites estructurales.
- Hay pruebas por dominio:
  - scheduling
  - personalization
  - priorities
  - planning
  - reminders
  - integrations Microsoft

Dictamen:

- módulo fuerte;
- favorece mantenimiento.

## 3. Qué responsabilidad tiene cada módulo

| Módulo | Responsabilidad principal | Evaluación breve |
| --- | --- | --- |
| `src/agents/support` | Runtime conversacional, grafo, nodos y subflujos | Bueno para MVP, con deuda de transición |
| `src/services` | Aplicación y lógica de negocio | Es la capa más sólida |
| `src/repositories` | Persistencia durable y contratos | Bien estructurado, salvo planning |
| `src/integrations` | Adaptadores a proveedores externos | Correcto, con deuda alta en OAuth Microsoft |
| `src/bootstrap` | Wiring y configuración | Limpio y útil |
| `src/schemas` | Contratos y DTOs compartidos | Muy bien resuelto |
| `scripts` | Operación manual/CLI | Inconsistente y parcialmente legacy |
| `tests` | Validación funcional y guardrails | Aporta orden real al proyecto |

## 4. Qué archivos parecen bien ubicados

- [container.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/bootstrap/container.py)
  Composition root claro.
- [settings.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/bootstrap/settings.py)
  Configuración transversal centralizada.
- [checkpointer.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/langgraph/checkpointer.py)
  Infraestructura propia del runtime bien aislada.
- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/onboarding/repository.py)
  Contrato y persistencia bien agrupados.
- [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/personalization/service.py)
  Lógica del dominio bien situada.
- [service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/reminders/service.py)
  Buena separación respecto al dispatcher.
- [dispatcher.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/reminders/dispatcher.py)
  Operación runtime diferida bien separada de políticas.
- [onboarding.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/schemas/onboarding.py)
- [scheduling.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/schemas/scheduling.py)
- [planning.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/schemas/planning.py)
- [test_refactor_guardrails.py](/home/jfjaramillo12/TESIS/academic_agentAI/tests/test_refactor_guardrails.py)
  Excelente pieza de sostenimiento arquitectónico.

## 5. Qué archivos parecen mal ubicados

- [persistence_support.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/planning/persistence_support.py)
  Está en `agents`, pero hace trabajo claramente de capa de aplicación/persistencia.
- [__init__.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/scheduling/__init__.py)
  Mezcla API pública de agente y modelos del dominio de servicios.
- [db.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/tools/db.py)
  Ubicación y propósito puramente legacy.
- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/planning/repository.py)
  La lógica de validación no debería venir desde `services`.
- [auth_client.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/auth_client.py)
  Ubicación válida a nivel de capa, pero demasiado concentrado para un solo archivo.
- [run_due_reminders.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/run_due_reminders.py)
- [backfill_study_plan_instances.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/backfill_study_plan_instances.py)
- [microsoft_oauth_exchange_code.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/microsoft_oauth_exchange_code.py)
  Operación montada sobre rutas legacy o ya removidas.

## 6. Dónde hay mezcla de responsabilidades

### 6.1 Grafo y routing en un solo archivo

Evidencia:

- [agent.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/agent.py)

Mezcla:

- composición del grafo;
- lógica de routing por fase;
- espera por turno;
- decisión de feature flags.

### 6.2 Scheduling conversacional demasiado concentrado

Evidencia:

- [schedule_capture_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_capture_service.py)
- [schedule_review_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_review_service.py)

Mezcla:

- parsing de entrada;
- control de estado;
- reglas de negocio;
- prompts;
- mutación de subestado.

### 6.3 Persistencia de planning en capa del agente

Evidencia:

- [persistence_support.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/planning/persistence_support.py)

Mezcla:

- persistencia de snapshot;
- materialización;
- sync de reminders;
- manejo de errores;
- composición de updates del grafo.

### 6.4 Nodo de persistencia del Radar con demasiadas responsabilidades

Evidencia:

- [node.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/nodes/persist_study_profile/node.py)

Mezcla:

- persistencia del perfil;
- sincronización de materias;
- generación del primer plan;
- decisión de si pasar a prioridades;
- formateo de respuesta al usuario.

### 6.5 OAuth Microsoft demasiado cargado

Evidencia:

- [auth_client.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/auth_client.py)

Mezcla:

- config;
- transporte;
- DTOs;
- adapter a repositorio;
- cliente;
- carga de entorno.

## 7. Dónde hay duplicación o lógica repetida

### 7.1 Sync Outlook y To Do

Evidencia:

- [outlook_calendar_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/outlook_calendar_sync_service.py)
- [microsoft_todo_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/microsoft_todo_sync_service.py)

Duplicación observada:

- cargar conexión;
- pedir token válido;
- listar instancias;
- resolver links existentes;
- upsert/delete externos;
- persistir links;
- devolver mapa sincronizado.

Evaluación:

- duplicación media-alta;
- misma plantilla con distinto proveedor objetivo.

### 7.2 Validación de eventos de planning

Evidencia:

- [persistence_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/persistence_service.py)
- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/planning/repository.py)

Duplicación observada:

- ambos validan `study_plan.plan_events` con `validate_event`.

### 7.3 Builders repetidos dentro de cada servicio

Evidencia distribuida:

- `build_onboarding_service`
- `build_schedule_service`
- `build_personalization_service`
- `build_study_planning_persistence_service`
- `build_study_plan_materialization_service`
- `build_study_session_tracking_service`
- `build_study_plan_reminders_service`
- `build_outlook_calendar_sync_service`
- `build_microsoft_todo_sync_service`

Evaluación:

- duplicación intencional y pragmática;
- no es crítica, pero sí dispersa la composición.

### 7.4 Patrón de detección de input + armado de update

Evidencia distribuida:

- muchos nodos de `src/agents/support/nodes/*`
- varios flows en `src/agents/support/flows/*`

Evaluación:

- repetición moderada;
- parte de esta repetición es aceptable por claridad de cada turno.

## 8. Dónde hay acoplamiento excesivo

### 8.1 `AgentState` como bus global

Evidencia:

- [state.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/state.py)

Impacto:

- aumenta acoplamiento semántico entre onboarding, scheduling, planning, personalization, reminders y replanificación;
- cualquier cambio en el contrato del estado toca muchas piezas a la vez.

### 8.2 `dependencies.py` + `AppContainer`

Evidencia:

- [dependencies.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/dependencies.py)
- [container.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/bootstrap/container.py)

Impacto:

- es un acoplamiento pragmático aceptable para MVP;
- pero reduce explicitud de dependencias en cada flujo.

### 8.3 Fuga `repository -> service`

Evidencia:

- [repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/planning/repository.py)

Impacto:

- rompe el límite más importante de persistencia;
- aumenta riesgo de acoplamiento conceptual aunque no haya ciclo duro de importación.

### 8.4 Fuga `integration -> repository`

Evidencia:

- [auth_client.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/auth_client.py)

Impacto:

- la integración OAuth conoce detalles del repositorio durable;
- la frontera de adapter queda menos limpia.

### 8.5 Scripts atados a rutas legacy

Evidencia:

- [run_due_reminders.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/run_due_reminders.py)
- [backfill_study_plan_instances.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/backfill_study_plan_instances.py)
- [microsoft_oauth_exchange_code.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/microsoft_oauth_exchange_code.py)

Impacto:

- acoplamiento operativo a APIs viejas;
- reduce confianza en automatización CLI.

### 8.6 ¿Hay dependencias circulares?

Conclusión observada:

- No se detectaron ciclos de importación críticos en el core auditado.
- El problema dominante no es circularidad dura, sino:
  - fugas de dirección de dependencia;
  - fachadas mixtas;
  - archivos demasiado centrales.

## 9. Dónde hay oportunidad de simplificación

- Separar [agent.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/agent.py) en:
  - construcción del grafo;
  - routers;
  - helpers de espera.
- Mover la cadena `persist snapshot -> materialize -> sync reminders` fuera de [persistence_support.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/planning/persistence_support.py) hacia un servicio de aplicación de planning.
- Reducir la superficie pública mixta de [__init__.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/scheduling/__init__.py).
- Partir [auth_client.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/auth_client.py) en submódulos:
  - config,
  - transport,
  - token store adapter,
  - client.
- Extraer una plantilla común para los servicios de sync Microsoft.
- Corregir o retirar los scripts que apuntan a rutas legacy.
- Considerar trasladar `build_*service()` al composition root a mediano plazo.

## 10. Conclusión: si la modularidad actual es suficiente o no para el crecimiento del proyecto

Conclusión ejecutiva:

- Sí, la modularidad actual es suficiente para seguir creciendo en el corto plazo como MVP.
- No, no es todavía suficiente para crecer cómodamente hacia más integraciones, más canales y replanificación compleja sin limpiar algunas zonas.

Juicio técnico:

- El refactor reciente sí dejó una base buena.
- El proyecto ya no parece un monolito desordenado.
- La modularidad fuerte está en:
  - `services`
  - `repositories`
  - `schemas`
  - `bootstrap`
- La modularidad débil está en:
  - `agents/support` en zonas de scheduling y planning
  - `integrations/microsoft_graph/auth_client.py`
  - `scripts/`

Dictamen final:

`la modularidad actual es buena para un MVP y claramente mejor que antes, pero aún tiene deuda estructural localizada que conviene resolver antes de ampliar integraciones, canales y replanificación en producción`

## 11. Tabla de hallazgos modulares

| Módulo/archivo | Responsabilidad actual | Problema detectado | Severidad | Recomendación |
| --- | --- | --- | --- | --- |
| [src/agents/support/flows/planning/persistence_support.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/planning/persistence_support.py) | Persistir snapshot desde el update del grafo | Mezcla agente, persistencia, materialización y reminders | Alta | Llevar esta cadena a un servicio de aplicación de planning |
| [src/agents/support/state.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/state.py) | Estado global del runtime | `AgentState` concentra demasiados subdominios | Alta | Reducir acoplamiento por subestados o contratos más acotados |
| [src/agents/support/agent.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/agent.py) | Grafo y routing principal | Archivo demasiado grande y multitarea | Alta | Separar build del grafo, routers y helpers |
| [src/integrations/microsoft_graph/auth_client.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/integrations/microsoft_graph/auth_client.py) | OAuth Microsoft | Archivo sobrecargado y dependiente del repositorio | Alta | Partir en submódulos y reducir dependencia directa de repositorio |
| [scripts/backfill_study_plan_instances.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/backfill_study_plan_instances.py) | Backfill operativo | Usa imports legacy ya no alineados con la arquitectura | Alta | Reescribir sobre APIs actuales o retirarlo |
| [scripts/run_due_reminders.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/run_due_reminders.py) | Worker CLI de reminders | Importa ruta legacy `agents.support.reminders_dispatcher` | Alta | Actualizar imports a `services.reminders.dispatcher` |
| [scripts/microsoft_oauth_exchange_code.py](/home/jfjaramillo12/TESIS/academic_agentAI/scripts/microsoft_oauth_exchange_code.py) | CLI OAuth Microsoft | Usa wrappers legacy inexistentes o transicionales | Alta | Reapuntarlo a `bootstrap/settings` y repositorios actuales |
| [src/repositories/planning/repository.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/repositories/planning/repository.py) | Persistencia de snapshot académico | Depende de `services.scheduling.validation` y duplica validación | Alta | Mover validación antes del repositorio y dejar persistencia pura |
| [src/agents/support/scheduling/__init__.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/scheduling/__init__.py) | Fachada pública del dominio de horario | Mezcla símbolos de `agents` y `services` | Media | Limitar su superficie o dividir fachadas por capa |
| [src/agents/support/flows/scheduling/schedule_review_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_review_service.py) | Revisión y corrección del horario | Archivo muy denso, con demasiadas ramas y mutaciones | Media | Extraer submódulos por etapa de revisión |
| [src/agents/support/flows/scheduling/schedule_capture_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_capture_service.py) | Captura conversacional del horario | Estado, prompts y reglas muy concentrados | Media | Separar captura de ocupación, secciones y pendientes |
| [src/services/sync/outlook_calendar_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/outlook_calendar_sync_service.py) | Sync Outlook | Duplica patrón estructural de sync Microsoft | Media | Extraer base común de sync/links/tokens |
| [src/services/sync/microsoft_todo_sync_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/sync/microsoft_todo_sync_service.py) | Sync To Do | Duplica patrón estructural de sync Microsoft | Media | Extraer base común de sync/links/tokens |
| [src/services/planning/study_planning_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/study_planning_service.py) | Generación del plan semanal | Archivo grande y algorítmicamente denso | Media | Separar scoring, ventanas y asignación |
| [src/services/planning/tracking_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/planning/tracking_service.py) | Tracking de sesiones | Mucha lógica repetida por transición de estado | Media | Extraer motor común de mutaciones/transiciones |
| [src/agents/support/tools/db.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/tools/db.py) | Shim de compatibilidad | Deuda legacy visible | Baja | Eliminarlo cuando ya no existan consumidores |
| [src/services/onboarding/service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/onboarding/service.py) | Servicio de onboarding | Mezcla negocio con builder de infraestructura | Baja | Dejar builders solo en bootstrap a mediano plazo |
| [src/services/personalization/service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/personalization/service.py) | Servicio de Radar | Mezcla negocio con builder de infraestructura | Baja | Mismo criterio: concentrar composición en bootstrap |
| [tests/test_refactor_guardrails.py](/home/jfjaramillo12/TESIS/academic_agentAI/tests/test_refactor_guardrails.py) | Guardrails de arquitectura | Sin problema; es una fortaleza | Baja | Mantenerlo y extenderlo a scripts si siguen siendo importantes |
