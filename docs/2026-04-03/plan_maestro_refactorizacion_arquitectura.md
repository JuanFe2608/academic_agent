# Plan Maestro De Refactorizacion Arquitectonica

Fecha: 2026-04-03

Estado: Propuesta maestra para ejecucion

Alcance: Reorganizacion progresiva del codebase para alinear la arquitectura real con una separacion clara entre `agents/`, `services/`, `repositories/`, `schemas/`, `integrations/`, `rag/`, `utils/` y `docs/`, sin romper el comportamiento actual del sistema.

Documento base relacionado:

- `docs/2026-04-01/architecture_audit.md`
- `docs/2026-04-01/refactor_plan.md`
- `docs/2026-04-01/codebase_map.md`

Este documento debe considerarse el plan rector a seguir para la refactorizacion.

## 1. Resumen Ejecutivo

El proyecto no necesita una reescritura total. La base actual ya tiene una direccion valida:

- LangGraph como orquestador principal.
- Separacion parcial `node -> service -> repository`.
- Persistencia PostgreSQL real.
- Suite de pruebas util para refactorizar con seguridad.

El problema no es la ausencia total de arquitectura, sino la mezcla de capas dentro de `src/agents/support/` y el crecimiento de hotspots que hoy concentran demasiadas responsabilidades.

La estrategia recomendada es:

1. No mover carpetas por estetica al inicio.
2. Consolidar fronteras arquitectonicas reales antes de renombrar rutas.
3. Introducir capas nuevas con compatibilidad hacia atras.
4. Migrar imports por fases.
5. Eliminar wrappers temporales solo cuando la nueva capa ya este estable.

La refactorizacion debe preservar:

- el entrypoint actual del grafo;
- el comportamiento de los nodos;
- el estado conversacional;
- la persistencia actual;
- y la suite de pruebas como red de seguridad.

## 2. Contexto Y Restricciones

## 2.1 Objetivo del negocio

El sistema es un agente academico enfocado en:

- onboarding del estudiante;
- captura y validacion de horarios;
- personalizacion del metodo de estudio;
- priorizacion academica;
- planificacion semanal;
- recordatorios, seguimiento y replanificacion;
- integracion con Outlook, Microsoft Graph, WhatsApp y RAG.

## 2.2 Restricciones tecnicas obligatorias

- No romper el flujo actual del agente.
- No cambiar el contrato funcional sin necesidad.
- No reescribir el grafo desde cero.
- No mezclar RAG con persistencia operativa.
- No convertir el refactor en una migracion cosmetica de carpetas.
- Mantener `langgraph.json` funcional durante todo el proceso.

## 2.3 Restricciones operativas

- El repositorio ya contiene 42 archivos de pruebas; deben usarse como red de seguridad.
- El runtime actual apunta a `src/agents/support/agent.py:agent`.
- El proyecto ya tiene persistencia productiva en PostgreSQL y modulos activos de onboarding, scheduling, personalization y planning.

## 3. Diagnostico Consolidado

## 3.1 Hallazgos principales

1. `src/agents/support/tools/db.py` actua como service locator global y composition root informal.
2. `src/agents/support/state.py` mezcla estado conversacional, DTOs compartidos y utilidades de dominio.
3. `src/agents/support/tools/llm.py` mezcla cliente de proveedor, prompting, parsing estructurado, multimodal y manejo de errores.
4. Existen imports cruzados impropios entre dominios, por ejemplo varios modulos importan `RepositoryConfigurationError` desde onboarding.
5. Algunos nodos ya son finos, pero otros siguen mezclando orquestacion conversacional, reglas de negocio y mutacion de estado.
6. Hay hotspots demasiado grandes para sostener el crecimiento futuro, en especial `apply_modifications/node.py`, `state.py`, `tools/llm.py`, `agent.py`, `schedule_review_service.py` y varios repositorios grandes.

## 3.2 Interpretacion arquitectonica

La arquitectura actual es un monolito modular orientado por grafo. Esa base es valida y debe conservarse. Lo que debe cambiar es la distribucion de responsabilidades:

- `agents/` debe orquestar conversacion, fases y estado.
- `services/` debe contener casos de uso y logica de negocio.
- `repositories/` debe concentrar persistencia.
- `integrations/` debe encapsular proveedores externos.
- `schemas/` debe contener modelos reutilizables y contratos estables.
- `utils/` debe quedar reducido a helpers genericos reales.

## 4. Arquitectura Objetivo

## 4.1 Estructura objetivo recomendada

```text
src/
  agents/
    support/
      agent.py
      state.py
      nodes/
      prompts/
      flows/

  services/
    onboarding/
    scheduling/
    personalization/
    priorities/
    planning/
    reminders/
    sync/
    study_methods/

  repositories/
    common/
    onboarding/
    scheduling/
    personalization/
    planning/
    reminders/
    microsoft_graph/

  schemas/
    onboarding.py
    scheduling.py
    personalization.py
    priorities.py
    planning.py
    reminders.py
    microsoft_graph.py
    common.py

  integrations/
    ai/
    microsoft_graph/
    whatsapp/
    langgraph/

  rag/
    ingestion/
    retrieval/
    prompting/

  utils/

  bootstrap/
    container.py
    settings.py
```

Notas:

- `bootstrap/` no estaba en la propuesta original del usuario, pero se recomienda como composition root explicito para resolver dependencias sin usar globals dispersos.
- `priorities/` puede seguir como dominio propio aunque luego termine integrado con `planning/`.
- `study_methods/` debe aparecer cuando la recomendacion de metodos deje de ser solo scoring y pase a combinar reglas, contenido y RAG.

## 4.2 Reglas de dependencia objetivo

Regla general:

`agents -> services -> repositories/integrations -> schemas/utils`

Restricciones por capa:

- `agents/` puede importar `services/`, `schemas/` y `utils/`.
- `agents/` no debe importar `repositories/` ni `integrations/` directamente.
- `services/` puede importar `repositories/`, `integrations/`, `schemas/` y `utils/`.
- `repositories/` no debe importar `agents/`.
- `integrations/` no debe importar `agents/`.
- `schemas/` no debe importar `agents/`, `services/`, `repositories/` ni `integrations/`.
- `utils/` no debe contener reglas de negocio especificas de un dominio.

## 4.3 Criterios globales de exito

La refactorizacion se considera exitosa cuando:

- `src/agents/support/` contenga principalmente grafo, nodos, prompts, flujos conversacionales y estado.
- los servicios de negocio vivan fuera de `agents/`.
- los repositorios PostgreSQL e in-memory vivan fuera de `agents/`.
- `tools/` desaparezca o quede reducido a wrappers de compatibilidad temporal.
- `state.py` ya no contenga validadores ni normalizadores de dominio.
- no existan imports cruzados de errores de infraestructura entre dominios.
- la suite de pruebas siga pasando sin regresiones.

## 5. Principios Rectores De La Refactorizacion

1. Refactor evolutivo, no reescritura.
2. Primero extraer responsabilidades, despues mover archivos.
3. Mantener compatibilidad hacia atras mientras existan imports viejos.
4. Cada fase debe ser mergeable por si sola.
5. Cada fase debe dejar el sistema en estado ejecutable.
6. El entrypoint del grafo no debe romperse durante el proceso.
7. La capa conversacional no debe absorber logica de negocio nueva.
8. La logica de negocio no debe depender del estado LangGraph salvo a traves de DTOs.
9. RAG es una capacidad futura, no una excusa para mezclar conocimiento con datos operativos.
10. Todo cambio estructural debe ir acompanado por pruebas o smoke checks equivalentes.

## 6. Estrategia De Migracion

## 6.1 Patron general

La migracion debe seguir siempre este orden:

1. Crear nueva capa o nuevo modulo.
2. Mover o copiar la logica al nuevo modulo.
3. Dejar un wrapper o re-export en la ruta vieja.
4. Cambiar imports consumidores de forma gradual.
5. Ejecutar pruebas.
6. Eliminar wrapper solo cuando no tenga consumidores.

## 6.2 Estrategia de compatibilidad

Durante el refactor se permitiran wrappers temporales en rutas antiguas, por ejemplo:

- `src/agents/support/tools/db.py` delegando a `src/bootstrap/container.py`
- `src/agents/support/state.py` reexportando DTOs movidos a `src/schemas/`
- `src/agents/support/onboarding/repository.py` reexportando implementaciones que ya vivan en `src/repositories/onboarding/`

Los wrappers temporales deben:

- ser delgados;
- no introducir logica nueva;
- incluir comentario de deprecacion;
- tener fecha o fase prevista de eliminacion.

## 6.3 Orden recomendado por dominio

Dentro de cada fase transversal, el orden de migracion recomendado es:

1. Onboarding
2. Scheduling
3. Personalization
4. Priorities
5. Planning
6. Reminders
7. Microsoft sync
8. Canales y RAG

La razon:

- onboarding es el dominio mas simple para validar el nuevo patron;
- scheduling es central y tiene mayor impacto transversal;
- planning, reminders y sync dependen de capas ya estabilizadas;
- RAG y WhatsApp deben entrar cuando las bases arquitectonicas ya esten limpias.

## 6.4 Politica de PRs y rollout

Unidad de ejecucion recomendada:

- una fase no debe convertirse en una sola mega-entrega;
- cada fase debe dividirse en PRs pequenos o medianos;
- cada PR debe tocar una sola frontera arquitectonica dominante.

Reglas practicas:

1. no mezclar movimiento de archivos con cambios funcionales;
2. no tocar mas de un dominio grande por PR salvo en capas comunes;
3. mantener wrappers temporales mientras existan consumidores;
4. ejecutar pruebas del dominio tocado y smoke checks del grafo en cada PR;
5. no renombrar `src/agents/support/agent.py` ni la referencia en `langgraph.json` hasta que el nuevo wiring este completamente estable.

## 7. Fases Del Plan Maestro

## Fase 0 - Baseline, gobierno tecnico y guardrails

Objetivo:

Definir la linea base y las reglas de seguridad antes de mover la arquitectura.

Cambios esperados:

- consolidar este plan como documento rector;
- inventariar modulos viejos y modulos activos;
- definir reglas de importacion permitidas;
- identificar wrappers temporales aceptables;
- dejar preparado un checklist de regresion.

Entregables:

- documento rector aprobado;
- listado de hotspots y prioridades;
- smoke checks de importacion;
- validacion de pruebas actuales;
- criterio de Definition of Done por fase.

Criterios de salida:

- el equipo acepta el plan y el orden de ejecucion;
- existe claridad sobre que se puede mover y que no;
- el estado actual del repo esta estable y versionado.

Riesgos:

- arrancar el refactor sin reglas claras;
- introducir cambios cosmeticos antes de consolidar fronteras.

## Fase 1 - Composition root e infraestructura compartida

Objetivo:

Eliminar el service locator global como punto de acoplamiento principal sin romper los nodos actuales.

Cambios principales:

- crear `src/bootstrap/container.py` como composition root explicito;
- crear `src/bootstrap/settings.py` para resolucion central de configuracion;
- extraer errores compartidos de infraestructura y configuracion;
- hacer que `src/agents/support/tools/db.py` pase a ser wrapper de compatibilidad;
- centralizar la construccion de servicios y repositorios en un solo contenedor.

Modulos candidatos:

- `src/agents/support/tools/db.py`
- `src/agents/support/tools/db_config.py`
- servicios que hoy se construyen desde factories sueltas

Reglas de implementacion:

- no cambiar todavia la firma publica de los nodos;
- mantener getters existentes mientras internamente delegan al container;
- evitar introducir dependency injection complejo por framework; basta con un container claro y explicito.

Entregables:

- container operativo;
- settings centralizados;
- errores de infraestructura compartidos;
- wrappers viejos intactos para compatibilidad.

Criterios de salida:

- ningun nodo rompe por cambio de wiring;
- `tools/db.py` deja de ser el origen real de construccion;
- la aplicacion puede arrancar usando el nuevo composition root.

Riesgos:

- cambiar demasiadas rutas de import al mismo tiempo;
- mezclar este paso con movimiento de archivos de dominio.

## Fase 2 - Separacion entre estado conversacional y schemas reutilizables

Objetivo:

Reducir `state.py` a su responsabilidad propia y mover contratos reutilizables a `schemas/`.

Cambios principales:

- crear `src/schemas/` por dominio;
- mover DTOs reutilizados por servicios y repositorios fuera de `state.py`;
- mantener `AgentState`, `Phase` y ensamblaje de subestados en `agents/support/state.py`;
- mover utilidades de dominio como normalizacion y validacion de eventos fuera de `state.py`;
- dejar re-exports de compatibilidad mientras se migran imports.

Ejemplos de candidatos a mover:

- `Event`
- `SubjectItem`
- `StudyPlanState`
- `PrioritiesState`
- `Constraints`
- estados o DTOs reutilizados por repositorios y servicios

Ejemplos de candidatos a extraer de `state.py`:

- `normalize_time`
- `normalize_day`
- `validate_event`
- `sort_events`

Destino sugerido:

- `src/schemas/scheduling.py`
- `src/schemas/planning.py`
- `src/schemas/personalization.py`
- `src/services/scheduling/validation.py`
- `src/utils/datetime_normalization.py` solo si la utilidad es realmente generica

Entregables:

- `schemas/` operativa;
- `state.py` mas pequeno y enfocado;
- wrappers temporales de compatibilidad.

Criterios de salida:

- `state.py` ya no contiene logica utilitaria de dominio;
- los servicios pueden depender de `schemas/` sin depender del estado LangGraph;
- los tests existentes siguen pasando.

Riesgos:

- mover `AgentState` demasiado pronto;
- fragmentar modelos en exceso sin criterio de consumo real.

## Fase 3 - Repositorios top-level y capa comun de persistencia

Objetivo:

Sacar el acceso a PostgreSQL fuera de `agents/` y normalizar el patron de repositorio.

Cambios principales:

- crear `src/repositories/` por dominio;
- mover implementaciones PostgreSQL e in-memory a su nueva capa;
- introducir `repositories/common/` para configuracion, errores, helpers SQL y transacciones si aplica;
- dejar adaptadores en rutas antiguas mientras migran los imports;
- eliminar imports cruzados impropios de errores de onboarding.

Patron recomendado por repositorio:

```text
repositories/<dominio>/
  contracts.py
  postgres.py
  in_memory.py
  queries.py          # solo si el repositorio ya lo necesita
  mappers.py          # solo si el repositorio ya lo necesita
  exceptions.py
```

No todos los dominios requieren todos esos archivos desde el primer dia. Debe aplicarse con criterio pragmatico.

Repositorios prioritarios:

- onboarding
- scheduling
- personalization
- planning
- reminders
- microsoft_graph state persistence

Entregables:

- repositorios top-level funcionando;
- excepciones de persistencia compartidas;
- desaparicion progresiva de imports `from agents.support.onboarding.repository import RepositoryConfigurationError`.

Criterios de salida:

- `services/` y `agents/` ya no dependen de repositorios dentro de `agents/`;
- la persistencia esta topologicamente separada del grafo;
- existe un patron comun para repositorios grandes.

Riesgos:

- convertir un repositorio simple en una jerarquia exagerada;
- cambiar SQL y arquitectura a la vez.

## Fase 4 - Integraciones externas bien aisladas

Objetivo:

Sacar proveedores externos y runtime adapters fuera de `tools/`.

Cambios principales:

- mover LLM y Azure/OpenAI a `src/integrations/ai/`;
- mover OAuth y clientes HTTP de Microsoft Graph a `src/integrations/microsoft_graph/`;
- mover el checkpointer de LangGraph a `src/integrations/langgraph/` o ubicacion equivalente de runtime adapter;
- separar integracion externa de persistencia local;
- dejar `tools/` solo como capa transitoria o eliminarlo al final.

Distribucion sugerida:

```text
integrations/ai/
  openai_client.py
  azure_openai_client.py
  structured_extraction.py
  multimodal_extraction.py

integrations/microsoft_graph/
  auth_client.py
  calendar_client.py
  todo_client.py
  models.py

integrations/langgraph/
  checkpointer.py
```

Separacion importante:

- clientes Graph y OAuth viven en `integrations/`;
- persistencia de tokens, conexiones y links vive en `repositories/microsoft_graph/`;
- servicios de sincronizacion viven en `services/sync/`.

Entregables:

- integraciones externas separadas de la logica de negocio;
- `tools/llm.py` sustituido por modulos mas pequenos;
- Microsoft Graph desacoplado entre cliente y persistencia.

Criterios de salida:

- ningun modulo de negocio importa directamente `tools/llm.py`;
- `tools/` deja de ser un cajon de sastre;
- las integraciones externas tienen fronteras claras.

Riesgos:

- mover a la vez cliente, parsing y prompts;
- confundir servicios de sync con clientes de proveedor.

## Fase 5 - Normalizacion de la capa `services/`

Objetivo:

Consolidar `services/` como la capa de negocio y casos de uso del sistema.

Cambios principales:

- mover logica de negocio fuera de `agents/support/<dominio>/` hacia `src/services/<dominio>/`;
- mantener en `agents/` solo orquestacion conversacional, prompts y manejo de estado;
- reubicar servicios de sync de Outlook y To Do en `services/sync/`;
- consolidar nomenclatura y convenciones de servicios.

Principio de clasificacion:

- si depende de `phase`, prompts, mensajes del usuario o `awaiting_user_input`, pertenece a `agents/`;
- si implementa una regla de negocio o un caso de uso reutilizable, pertenece a `services/`;
- si solo hace SQL, pertenece a `repositories/`;
- si habla con un proveedor externo, pertenece a `integrations/`.

Ejemplos de destino esperado:

- onboarding persist/verify -> `services/onboarding/`
- parsing, normalizacion, conflictos y draft scheduling -> `services/scheduling/`
- scoring y recomendacion base -> `services/personalization/`
- priorizacion, plan semanal, materializacion, tracking y replan -> `services/planning/`
- politicas y dispatch de reminders -> `services/reminders/`
- sync Outlook y Microsoft To Do -> `services/sync/`

Entregables:

- servicios top-level por dominio;
- responsabilidad de negocio claramente separada;
- modulos de `agents/support/*` reducidos o convertidos en wrappers.

Criterios de salida:

- la logica reutilizable ya no vive dentro de `agents/`;
- se puede razonar por dominio sin entrar al grafo;
- los servicios ya no importan errores de otros dominios solo para configuracion.

Riesgos:

- mover a `services/` piezas que en realidad son conversacionales;
- mezclar recomendaciones futuras de RAG con servicios operativos actuales.

## Fase 6 - Limpieza de la capa `agents/`

Objetivo:

Dejar `agents/` alineado con su responsabilidad real: orquestacion conversacional y estado.

Cambios principales:

- convertir nodos en coordinadores finos;
- agrupar prompts y formateadores de respuesta en paquetes de agente;
- mover handlers conversacionales hoy mal ubicados en `scheduling/`, `priorities/` o `planning/` hacia `agents/support/flows/`;
- hacer explicita la frontera entre nodo LangGraph y flujo conversacional reusable.

Destino recomendado dentro de agents:

```text
agents/support/
  agent.py
  state.py
  nodes/
  prompts/
  flows/
  routing/
```

Ejemplos de candidatos a `agents/support/flows/`:

- `schedule_capture_service.py`
- `schedule_review_service.py`
- `priority_capture_service.py`
- ayudantes conversacionales que manipulan fases y mensajes

Hotspots prioritarios:

- `apply_modifications/node.py`
- `collect_profile/node.py`
- `collect_extracurricular_details/node.py`
- `agent.py` si sigue creciendo en routing

Entregables:

- nodos pequenos y consistentes;
- prompts centralizados por dominio;
- flujos conversacionales fuera de modulos de negocio puros.

Criterios de salida:

- los nodos ya no concentran reglas de negocio complejas;
- `agents/` deja claro que su trabajo es conversar y enrutar;
- los flujos pueden probarse sin reconstruir todo el grafo.

Riesgos:

- intentar adelgazar todos los nodos en una sola tanda;
- tocar `agent.py` y hot paths de routing sin cobertura suficiente.

## Fase 7 - Descomposicion de hotspots y eliminacion de legado

Objetivo:

Reducir archivos gigantes, decidir el destino de codigo no conectado y remover compatibilidad que ya no aporte.

Cambios principales:

- dividir archivos gigantes en modulos mas pequenos orientados por responsabilidad;
- decidir si modulos no conectados al grafo se integran, se archivan o se eliminan;
- retirar wrappers de compatibilidad ya agotados;
- eliminar `tools/` si ya no tiene razon de existir.

Hotspots a intervenir tarde, no al inicio:

- `apply_modifications/node.py`
- `generate_tentative_extracurricular/node.py`
- `tools/schedule_parser.py`
- `tools/llm.py` si aun existiera como wrapper

Regla de priorizacion:

- primero limpiar el camino productivo activo;
- despues tratar modulos experimentales o legado.

Entregables:

- hotspots partidos en modulos mantenibles;
- codigo legado identificado y tratado;
- wrappers temporales removidos.

Criterios de salida:

- el repo ya no depende de modulos de compatibilidad vieja;
- los archivos mas grandes ya no concentran responsabilidades heterogeneas;
- el mapa de paquetes se acerca de forma real a la arquitectura objetivo.

Riesgos:

- hacer esta fase antes de estabilizar las nuevas capas;
- eliminar wrappers demasiado pronto.

## Fase 8 - Enforcement arquitectonico, documentacion final y apertura a nuevas capacidades

Objetivo:

Evitar regresiones arquitectonicas y preparar el terreno para nuevas capacidades.

Cambios principales:

- agregar pruebas de frontera de capas;
- actualizar `README.md` y documentacion tecnica;
- documentar import rules y ubicacion de cada responsabilidad;
- crear estructura vacia o ADRs para `rag/` y `integrations/whatsapp/` si se decide abrir esas lineas.

Pruebas de arquitectura recomendadas:

- `agents/` no importa `repositories/` ni `integrations/` directamente;
- `schemas/` no importa nada de capas superiores;
- `tools/` no debe reaparecer como zona gris;
- `state.py` no vuelve a absorber utilidades de dominio.

Entregables:

- documentacion consolidada;
- reglas de importacion automatizadas o validadas por tests;
- estructura preparada para RAG y canales futuros.

Criterios de salida:

- la nueva arquitectura es autoexplicativa;
- el equipo tiene reglas claras para no recaer;
- las siguientes funcionalidades ya pueden construirse en la capa correcta.

Riesgos:

- dejar la arquitectura sin mecanismos de enforcement;
- abrir RAG o WhatsApp antes de estabilizar la base.

## 8. Secuencia Operativa Recomendada

Secuencia obligatoria:

1. Fase 0
2. Fase 1
3. Fase 2
4. Fase 3
5. Fase 4
6. Fase 5
7. Fase 6
8. Fase 7
9. Fase 8

Secuencia por dominio dentro de cada fase:

1. onboarding
2. scheduling
3. personalization
4. priorities
5. planning
6. reminders
7. sync Microsoft
8. RAG y canales

Razon de la secuencia:

- onboarding permite validar rapidamente el patron;
- scheduling es el dominio mas transversal;
- planning y reminders dependen de scheduling y personalization;
- sync y canales deben montarse sobre una arquitectura ya limpia.

## 9. Mapa De Migracion Actual -> Objetivo

| Actual                                                            | Objetivo                                                      | Estrategia                                         |
| ----------------------------------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| `src/agents/support/agent.py`                                     | `src/agents/support/agent.py`                                 | Se conserva, pero mas fino y con wiring explicito  |
| `src/agents/support/state.py`                                     | `src/agents/support/state.py` + `src/schemas/*`               | Extraer DTOs y utilidades, mantener compatibilidad |
| `src/agents/support/tools/db.py`                                  | `src/bootstrap/container.py`                                  | Convertir `tools/db.py` en wrapper temporal        |
| `src/agents/support/tools/db_config.py`                           | `src/bootstrap/settings.py` o `repositories/common/config.py` | Centralizar configuracion                          |
| `src/agents/support/onboarding/service.py`                        | `src/services/onboarding/`                                    | Mover sin romper imports actuales                  |
| `src/agents/support/onboarding/repository.py`                     | `src/repositories/onboarding/`                                | Wrapper temporal en la ruta vieja                  |
| `src/agents/support/scheduling/service.py` y servicios de dominio | `src/services/scheduling/`                                    | Separar negocio de flujos conversacionales         |
| `src/agents/support/scheduling/schedule_capture_service.py`       | `src/agents/support/flows/scheduling/`                        | Clasificar como orquestacion conversacional        |
| `src/agents/support/planning/*service.py`                         | `src/services/planning/`                                      | Reorganizar por casos de uso                       |
| `src/agents/support/reminders_service.py`                         | `src/services/reminders/`                                     | Mantener contrato funcional                        |
| `src/agents/support/tools/llm.py`                                 | `src/integrations/ai/`                                        | Separar cliente, prompting y parsing               |
| `src/auth/microsoft_auth.py`                                      | `src/integrations/microsoft_graph/auth_client.py`             | Mover adaptador de OAuth                           |
| `src/agents/support/tools/microsoft_graph_clients.py`             | `src/integrations/microsoft_graph/`                           | Clientes HTTP y contratos externos                 |
| `src/agents/support/tools/microsoft_graph_state_repository.py`    | `src/repositories/microsoft_graph/`                           | Persistencia local de tokens y links               |
| `src/agents/support/tools/calendar_outlook.py`                    | `src/services/sync/outlook_calendar_sync_service.py`          | Servicio de sincronizacion + clientes inyectados   |
| `src/agents/support/tools/microsoft_todo.py`                      | `src/services/sync/microsoft_todo_sync_service.py`            | Servicio de sincronizacion + clientes inyectados   |
| `src/agents/support/tools/langgraph_checkpointer.py`              | `src/integrations/langgraph/checkpointer.py`                  | Runtime adapter con wrapper temporal               |

## 10. Politica De Pruebas Durante La Refactorizacion

Reglas:

- no se acepta una fase sin smoke checks o pruebas equivalentes;
- cada fase debe mantener el repo ejecutable;
- cada movimiento estructural importante debe ir con pruebas de importacion o de regresion del flujo.

Tipos de pruebas recomendadas por fase:

- smoke tests de importacion para rutas reexportadas;
- pruebas de servicio para dominios que se muevan a `services/`;
- pruebas de repositorio para implementaciones PostgreSQL e in-memory;
- pruebas de flujo conversacional para nodos criticos;
- pruebas de arquitectura para enforcement de capas.

Checks minimos por PR:

1. imports clave cargan sin errores;
2. el grafo sigue construyendose;
3. pruebas del dominio tocado siguen en verde;
4. no se introducen imports desde capas superiores hacia inferiores.

## 11. Definicion De Done Del Programa De Refactorizacion

El programa completo se considera terminado cuando se cumplan todas estas condiciones:

1. `agents/` solo contiene grafo, nodos, prompts, flows y estado conversacional.
2. `services/` concentra la logica de negocio y casos de uso.
3. `repositories/` concentra acceso a PostgreSQL y persistencia in-memory.
4. `schemas/` concentra DTOs y contratos reutilizables.
5. `integrations/` concentra proveedores externos y adapters de runtime.
6. `tools/` ya no existe o solo queda vacio y eliminado del uso real.
7. `state.py` ya no contiene utilidades de normalizacion ni validacion de negocio.
8. no existen imports de errores o configuracion cruzados entre dominios.
9. la suite de pruebas y los smoke tests del grafo siguen pasando.
10. la documentacion refleja la nueva arquitectura real y no una arquitectura aspiracional.

## 12. Anti-Patrones Que Este Plan Prohibe

- mover carpetas primero y entender dependencias despues;
- reescribir el grafo cuando el problema real es de fronteras de capa;
- mezclar Graph API, SQL y prompts en un solo modulo nuevo;
- seguir agregando funcionalidades nuevas dentro de `tools/`;
- seguir usando `state.py` como deposito de cualquier tipo reutilizable;
- abrir RAG antes de limpiar primero `agents/`, `services/` e `integrations/`;
- tratar el refactor como una sola mega-branch imposible de revisar.

## 13. Recomendacion Final

La mejor ruta para este proyecto es una refactorizacion por capas y por dominios, con compatibilidad temporal, usando la suite actual de pruebas como red de seguridad y manteniendo el grafo estable durante todo el proceso.

La prioridad numero uno no es renombrar carpetas. La prioridad numero uno es imponer fronteras claras:

- composition root explicito;
- `state.py` reducido;
- `tools/` desarmado;
- repositorios fuera de `agents/`;
- integraciones fuera de la logica de negocio;
- nodos realmente finos.

Si se sigue este orden, el proyecto puede llegar a la arquitectura objetivo sin interrumpir el desarrollo funcional ni perder estabilidad.
