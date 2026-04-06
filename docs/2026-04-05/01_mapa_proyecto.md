# Mapa Completo Del Proyecto

Fecha: 2026-04-05

Estado: auditoria tecnica en progreso

## 1. Resumen general del repositorio

El repositorio corresponde a un MVP de agente academico construido en Python 3.11+ sobre LangGraph, con persistencia PostgreSQL y adaptadores para AI y Microsoft Graph. La organizacion actual muestra una refactorizacion arquitectonica reciente y, en general, el proyecto ya se comporta como un monolito modular por capas con agrupacion por dominio.

Hechos observados:

- La configuracion del runtime principal esta en `langgraph.json`, que apunta al grafo `support` en `src/agents/support/agent.py:agent` y al checkpointer en `src/integrations/langgraph/checkpointer.py:create_checkpointer`.
- El codigo fuente principal vive en `src/` y esta separado en `agents/`, `services/`, `repositories/`, `integrations/`, `schemas/`, `bootstrap/`, `rag/` y `utils/`.
- Existen `migrations/` SQL reales, `scripts/` operativos, `tests/` amplios y documentacion historica organizada por fecha en `docs/`.
- Excluyendo caches compilados, el arbol tiene al menos:
  - `src/agents`: 116 archivos
  - `src/services`: 43 archivos
  - `src/repositories`: 19 archivos
  - `src/integrations`: 18 archivos
  - `src/schemas`: 8 archivos
  - `tests`: 46 archivos
  - `scripts`: 10 archivos
  - `migrations`: 24 archivos

Lectura arquitectonica preliminar:

- Para un MVP, la arquitectura actual esta bien encaminada.
- La refactorizacion reciente mejoro claramente la separacion por capas y dejo guardrails automaticos en pruebas.
- El sistema aun no es una arquitectura totalmente limpia ni hexagonal estricta.
- La deuda principal ya no parece ser de desorden total, sino de transicion incompleta en ciertos modulos, scripts y superficies legacy.

## 2. Arbol resumido de carpetas importantes

```text
/
├── README.md
├── pyproject.toml
├── langgraph.json
├── main.py
├── prueba1.py
├── docs/
│   ├── 2026-03-25/
│   ├── 2026-03-30/
│   ├── 2026-04-01/
│   ├── 2026-04-03/
│   └── 2026-04-05/
├── migrations/
│   ├── 0001_onboarding_students.sql
│   ├── ...
│   ├── 0014_grant_microsoft_graph_permissions.sql
│   └── diagnostics/
├── scripts/
│   ├── simulate_support_flow.py
│   ├── sync_outlook_calendar.py
│   ├── sync_microsoft_todo.py
│   ├── run_due_reminders.py
│   ├── record_session_completion.py
│   ├── mark_missed_sessions.py
│   ├── microsoft_oauth_authorize.py
│   ├── microsoft_oauth_exchange_code.py
│   ├── backfill_study_plan_instances.py
│   └── check_image_extraction.py
├── src/
│   ├── project_env.py
│   ├── agents/
│   │   └── support/
│   │       ├── agent.py
│   │       ├── state.py
│   │       ├── dependencies.py
│   │       ├── nodes/
│   │       ├── flows/
│   │       ├── onboarding/
│   │       ├── scheduling/
│   │       ├── personalization/
│   │       ├── priorities/
│   │       ├── planning/
│   │       └── tools/
│   ├── bootstrap/
│   │   ├── container.py
│   │   ├── settings.py
│   │   └── errors.py
│   ├── services/
│   │   ├── onboarding/
│   │   ├── scheduling/
│   │   ├── personalization/
│   │   ├── priorities/
│   │   ├── planning/
│   │   ├── reminders/
│   │   └── sync/
│   ├── repositories/
│   │   ├── common/
│   │   ├── onboarding/
│   │   ├── scheduling/
│   │   ├── personalization/
│   │   ├── planning/
│   │   ├── reminders/
│   │   └── microsoft_graph/
│   ├── integrations/
│   │   ├── ai/
│   │   ├── langgraph/
│   │   ├── microsoft_graph/
│   │   └── whatsapp/
│   ├── schemas/
│   │   ├── common.py
│   │   ├── onboarding.py
│   │   ├── scheduling.py
│   │   ├── personalization.py
│   │   ├── planning.py
│   │   ├── reminders.py
│   │   └── microsoft_graph.py
│   ├── rag/
│   │   ├── README.md
│   │   ├── ingestion/
│   │   ├── retrieval/
│   │   └── prompting/
│   └── utils/
└── tests/
    ├── test_refactor_guardrails.py
    ├── test_onboarding_services.py
    ├── test_schedule_*.py
    ├── test_personalization_*.py
    ├── test_priorities_flow.py
    ├── test_study_plan_*.py
    ├── test_reminder_*.py
    ├── test_outlook_calendar_sync_service.py
    └── test_replanning_apply_modifications.py
```

## 3. Clasificacion del codigo por responsabilidad

### 3.1 Orquestacion del agente

La orquestacion principal vive en `src/agents/support/`.

Piezas clave:

- `src/agents/support/agent.py`
  Define el `StateGraph`, agrega nodos y compila el agente.
- `src/agents/support/state.py`
  Define el contrato global `AgentState`.
- `src/agents/support/nodes/`
  Contiene nodos LangGraph, en su mayoria delgados.
- `src/agents/support/flows/`
  Contiene logica conversacional o de coordinacion por subflujo.
- `src/agents/support/dependencies.py`
  Expone acceso semantico al container para nodos y pruebas.

Observacion:

- La orquestacion esta mayormente bien separada.
- Aun quedan modulos dentro de `flows/` que ya se comportan como servicios de aplicacion, no solo como pegamento conversacional.

### 3.2 Codigo de dominio

El nucleo de negocio esta principalmente en `src/services/`.

Dominios visibles:

- `src/services/onboarding/`
  Verificacion de correo, persistencia del estudiante, configuracion y sender de email.
- `src/services/scheduling/`
  Validacion, parsing textual, matching, generacion de eventos, modelos de horario y persistencia del perfil de horario.
- `src/services/personalization/`
  Cuestionario, scoring, desempate, modelos de radar y persistencia del perfil de estudio.
- `src/services/priorities/`
  Construccion y priorizacion de materias.
- `src/services/planning/`
  Sincronizacion de subjects, generacion del plan semanal, materializacion de instancias, tracking y persistencia academica.
- `src/services/reminders/`
  Politicas de recordatorio y worker de dispatch.
- `src/services/sync/`
  Sincronizacion hacia Outlook Calendar y Microsoft To Do.

Observacion:

- Esta capa ya concentra bastante bien los casos de uso reales del MVP.
- En comparacion con el estado historico descrito en `docs/2026-04-01/` y `docs/2026-04-03/`, la refactorizacion fue efectiva.

### 3.3 Persistencia

La persistencia durable esta en `src/repositories/` y se respalda con `migrations/`.

Modulos principales:

- `src/repositories/onboarding/repository.py`
- `src/repositories/scheduling/repository.py`
- `src/repositories/personalization/repository.py`
- `src/repositories/planning/repository.py`
- `src/repositories/planning/instances_repository.py`
- `src/repositories/planning/tracking_repository.py`
- `src/repositories/reminders/repository.py`
- `src/repositories/microsoft_graph/state_repository.py`
- `src/repositories/microsoft_graph/sync_repository.py`
- `src/repositories/common/postgres.py`

Patron repetido observado:

- `Protocol` para contrato
- implementacion `InMemory*`
- implementacion `Postgres*`
- `build_*repository(...)`

Esto es una señal de orden estructural positiva.

### 3.4 Integracion externa

Las integraciones externas viven en `src/integrations/`.

Submodulos:

- `src/integrations/ai/`
  Wrappers y extraccion estructurada/multimodal sobre Azure OpenAI u OpenAI.
- `src/integrations/microsoft_graph/`
  OAuth, clientes de calendario, mail, To Do, transporte HTTP y modelos de proveedor.
- `src/integrations/langgraph/`
  Checkpointer PostgreSQL para hilos del runtime LangGraph.
- `src/integrations/whatsapp/`
  Placeholder, sin adaptador funcional aun.

Observacion:

- La separacion de integraciones es clara.
- No se detecto carpeta activa para Telegram.
- La ruta estructural mas natural para Telegram seria otra integracion de canal paralela a `whatsapp/`, no una implementacion dentro de `agents/`.

### 3.5 Contratos y esquemas

Los contratos compartidos viven en `src/schemas/`.

Modelos observados:

- `src/schemas/onboarding.py`
  `ConsentState`, `StudentProfile`, `EmailVerificationState`, `OnboardingState`
- `src/schemas/scheduling.py`
  `Event`, `RawInputs`, `ExtracurricularItem`, `PendingScheduleItem`, `SchedulePreview`
- `src/schemas/personalization.py`
  `StudyProfile`
- `src/schemas/planning.py`
  `SubjectItem`, `PrioritiesState`, `StudyPlanState`, `ReplanState`, `Constraints`
- `src/schemas/reminders.py`
  `RemindersState`
- `src/schemas/microsoft_graph.py`
  `CalendarState`
- `src/schemas/common.py`
  `BaseSchemaModel`

Observacion:

- La capa de esquemas esta bien delimitada.
- Los modelos mas ricos y especificos del dominio siguen existiendo dentro de `services/`, lo cual es razonable cuando no son contratos estables del estado global.

### 3.6 Configuracion y entorno

La configuracion observable se reparte entre:

- `pyproject.toml`
  Dependencias y version minima de Python.
- `langgraph.json`
  Entry point del grafo y checkpointer.
- `src/bootstrap/settings.py`
  Resolucion de URLs de base de datos y checkpointer.
- `src/project_env.py`
  Carga perezosa de `.env`.
- `src/bootstrap/container.py`
  Composition root de servicios y adapters.
- `src/bootstrap/errors.py`
  Errores compartidos de infraestructura.
- `src/services/*/config.py`
  Configuracion de dominio.

Observacion:

- No se detecto seccion `[project.scripts]` en `pyproject.toml`.
- El empaquetado existe, pero los puntos de entrada operativos siguen siendo `langgraph.json` y `scripts/*.py`.

### 3.7 Utilidades compartidas

Hay dos tipos de utilidades:

- utilidades globales casi inexistentes en `src/utils/`
- utilidades locales por capa o dominio, por ejemplo:
  - `src/agents/support/nodes/utils.py`
  - `src/agents/support/scheduling/state_helpers.py`
  - `src/services/planning/state_helpers.py`
  - `src/services/priorities/state_helpers.py`
  - `src/services/reminders/state_helpers.py`

Observacion:

- `src/utils/` esta practicamente vacio.
- El proyecto prefiere helpers cercanos al dominio, lo cual es sano.
- La contracara es que hay varios `state_helpers.py` dispersos que exigen leer el arbol con cuidado.

## 4. Explicacion de que hace cada modulo principal

### 4.1 `src/agents/support/`

Es la capa mas importante para el comportamiento visible del agente.

Responsabilidades observadas:

- ensamblaje del `StateGraph` en `src/agents/support/agent.py`
- estado global en `src/agents/support/state.py`
- nodos LangGraph en `src/agents/support/nodes/`
- prompts locales por nodo en `src/agents/support/nodes/*/prompt.py`
- subflujos conversacionales en `src/agents/support/flows/`
- formateadores y ayudas de UX en subcarpetas como `onboarding/`, `scheduling/`, `personalization/`, `planning/`, `priorities/`

Señales concretas:

- `src/agents/support/agent.py` define `build_agent()` y luego `agent = build_agent()`.
- En `src/agents/support/nodes/` hay 22 archivos `node.py` y 14 archivos `prompt.py`.
- Algunos nodos son wrappers minimos, por ejemplo `src/agents/support/nodes/collect_profile/node.py`.
- Parte de la logica aun vive en `flows/`, por ejemplo:
  - `src/agents/support/flows/scheduling/schedule_capture_service.py`
  - `src/agents/support/flows/priorities/priority_capture_service.py`
  - `src/agents/support/flows/planning/persistence_support.py`
  - `src/agents/support/flows/replanning/apply_modifications.py`

Evaluacion:

- La capa ya no esta desordenada como un “mega paquete”.
- Sigue siendo la capa mas pesada del repositorio y conserva deuda de transicion.

### 4.2 `src/services/`

Es la capa de casos de uso.

Patrones observados:

- clases de servicio con dataclasses de resultado
- builders `build_*service()`
- uso de repositorios `InMemory` o `Postgres` segun entorno
- dependencia de `bootstrap.settings.database_url_from_env()` para wiring rapido

Ejemplos:

- `src/services/onboarding/service.py`
  Orquesta verificacion de correo y persistencia del estudiante.
- `src/services/scheduling/service.py`
  Persiste horarios recurrentes.
- `src/services/personalization/service.py`
  Evalua y persiste el perfil de estudio.
- `src/services/priorities/subject_prioritization_service.py`
  Deriva o normaliza materias prioritarias.
- `src/services/planning/study_plan_sync_service.py`
  Sincroniza `subjects` y `study_plan`.
- `src/services/planning/study_planning_service.py`
  Genera el plan semanal inicial.
- `src/services/reminders/service.py`
  Define politicas y despachos.
- `src/services/reminders/dispatcher.py`
  Ejecuta el worker de envio.
- `src/services/sync/outlook_calendar_sync_service.py`
  Sincroniza instancias a Outlook.
- `src/services/sync/microsoft_todo_sync_service.py`
  Sincroniza sesiones accionables a To Do.

Evaluacion:

- Esta capa es coherente con el objetivo del MVP.
- Es, probablemente, la mejora mas clara del refactor reciente.

### 4.3 `src/repositories/`

Es la capa durable de acceso a datos.

Patron dominante:

- contrato `Protocol`
- implementacion en memoria para pruebas
- implementacion PostgreSQL para produccion

Esto aparece en onboarding, scheduling, personalization, planning, reminders y Microsoft Graph.

Evaluacion:

- La capa esta bien organizada y es bastante consistente.
- La principal excepcion observada es `src/repositories/planning/repository.py`, que importa `validate_event` desde `services.scheduling.validation`, lo que rompe un poco la direccion ideal de dependencias.

### 4.4 `src/integrations/`

Concentra proveedores externos y adapters de runtime.

Casos principales:

- `src/integrations/ai/_llm_impl.py`
  Construye clientes Azure/OpenAI y expone utilidades de extraccion estructurada.
- `src/integrations/microsoft_graph/auth_client.py`
  Gestiona OAuth, refresh y bridge con persistencia de tokens.
- `src/integrations/microsoft_graph/_clients_impl.py`
  Implementa clientes reales de Outlook Calendar, To Do y Mail.
- `src/integrations/langgraph/checkpointer.py`
  Implementa persistencia de hilos LangGraph en PostgreSQL.

Evaluacion:

- La estructura es limpia.
- Existe un acoplamiento pragmatico entre `integrations/microsoft_graph/auth_client.py` y `repositories.microsoft_graph.state_repository`, aceptable para un MVP, pero no ideal desde una pureza arquitectonica estricta.

### 4.5 `src/schemas/`

Es una capa transversal, pequena y clara.

Rol observado:

- contratos de estado compartido
- DTOs estables que cruzan varias capas
- base Pydantic comun

Evaluacion:

- Es una de las zonas mas limpias del repositorio.

### 4.6 `migrations/`

Representa el modelo durable del negocio.

Cobertura observada por nombres:

- onboarding y estudiantes
- perfiles de horario recurrente
- persistencia de threads LangGraph
- perfiles de personalizacion
- perfiles y eventos de study plan
- reminders, dispatches y tracking
- replan requests y proposals
- conexiones Microsoft Graph y sync

Evaluacion:

- Hay suficiente profundidad de persistencia para un MVP serio.
- No parece un prototipo efimero sin modelo de datos.

### 4.7 `scripts/`

Son entrypoints operativos manuales.

Tipos de scripts observados:

- demo local: `scripts/simulate_support_flow.py`
- sync externo: `scripts/sync_outlook_calendar.py`, `scripts/sync_microsoft_todo.py`
- OAuth Microsoft: `scripts/microsoft_oauth_authorize.py`, `scripts/microsoft_oauth_exchange_code.py`
- reminders y tracking: `scripts/run_due_reminders.py`, `scripts/record_session_completion.py`, `scripts/mark_missed_sessions.py`
- mantenimiento: `scripts/backfill_study_plan_instances.py`
- pruebas de extraccion: `scripts/check_image_extraction.py`

Evaluacion:

- Son utiles para operacion y debugging.
- Varios parecen no haber sido completamente actualizados tras el refactor.

### 4.8 `tests/`

La carpeta `tests/` tiene 45 archivos `test_*.py`.

Cobertura visible:

- onboarding
- scheduling
- personalization
- priorities
- planning
- reminders
- sync Microsoft
- multimodal parsing
- replanificacion
- guardrails de arquitectura

Archivo especialmente importante:

- `tests/test_refactor_guardrails.py`
  Hace enforcement de entrypoints, limites de importacion y ausencia de wrappers legacy.

Evaluacion:

- Para un MVP, la cobertura estructural es buena.
- El repositorio no depende solo de convenciones verbales.

## 5. Archivos criticos del sistema y su rol

- `langgraph.json`
  Punto de entrada efectivo del runtime LangGraph.
- `src/agents/support/agent.py`
  Grafo principal, routing y compilacion del agente.
- `src/agents/support/state.py`
  Contrato central del estado conversacional y operativo.
- `src/bootstrap/container.py`
  Composition root y wiring compartido de servicios.
- `src/bootstrap/settings.py`
  Resolucion centralizada de configuracion de base de datos y checkpointer.
- `src/agents/support/dependencies.py`
  Frontera que usa el agente para pedir dependencias sin acoplarse al container concreto.
- `src/services/onboarding/service.py`
  Activa el onboarding real y la verificacion de correo.
- `src/services/personalization/service.py`
  Materializa el radar de estudio y su persistencia.
- `src/services/planning/study_plan_sync_service.py`
  Conecta prioridades y plan semanal.
- `src/services/planning/study_planning_service.py`
  Genera el plan semanal inicial.
- `src/services/reminders/dispatcher.py`
  Ejecuta la entrega operativa de reminders.
- `src/services/sync/outlook_calendar_sync_service.py`
  Sincroniza el plan materializado con Outlook.
- `src/integrations/langgraph/checkpointer.py`
  Persistencia de threads del agente.
- `src/repositories/planning/repository.py`
  Persistencia versionada de subjects, priorities y study_plan.
- `src/repositories/microsoft_graph/state_repository.py`
  Estado durable de conexiones, links y metadata Microsoft.

## 6. Posibles puntos de entrada de ejecucion

### 6.1 Runtime principal del agente

El entrypoint real del sistema hoy es:

- `langgraph.json`
  - grafo: `./src/agents/support/agent.py:agent`
  - checkpointer: `./src/integrations/langgraph/checkpointer.py:create_checkpointer`

Este es el punto de entrada mas importante del producto.

### 6.2 Scripts operativos

Existen entrypoints CLI manuales en `scripts/*.py`.

Los mas relevantes:

- `scripts/simulate_support_flow.py`
- `scripts/sync_outlook_calendar.py`
- `scripts/sync_microsoft_todo.py`
- `scripts/run_due_reminders.py`
- `scripts/microsoft_oauth_authorize.py`
- `scripts/microsoft_oauth_exchange_code.py`
- `scripts/record_session_completion.py`
- `scripts/mark_missed_sessions.py`
- `scripts/backfill_study_plan_instances.py`

### 6.3 Entradas no productivas o ambiguas

- `main.py`
  Solo imprime `"Hello from academic-agentai!"` y no actua como entrypoint real del agente.
- `prueba1.py`
  Parece un experimento local para vision con Azure OpenAI, no un modulo productivo.

### 6.4 Empaquetado

No se detecto `project.scripts` en `pyproject.toml`, por lo que no hay CLI empaquetada formalmente.

## 7. Dependencias internas visibles entre modulos

La siguiente lectura se basa en imports top-level visibles en `src/`. No es un DAG formal, pero si muestra la direccion real de dependencias.

### 7.1 Patrón dominante observado

- `agents` importa principalmente `services`, `schemas` y algo de `bootstrap`.
- `services` importa `repositories`, `integrations`, `schemas`, `bootstrap` y helpers de su propia capa.
- `bootstrap` importa `services`, `repositories`, `integrations` y `project_env`.
- `repositories` importa casi solo `repositories.common`, `schemas` y un caso puntual de `services`.
- `integrations` importa `bootstrap`, `project_env` y un caso puntual de `repositories`.

### 7.2 Resumen cuantitativo aproximado

Conteo por ocurrencia de import top-level observado por grep:

- `agents`
  - hacia `services`: 64
  - hacia `schemas`: 25
  - hacia `bootstrap`: 4
  - hacia `repositories`: no se detectaron imports directos
  - hacia `integrations`: no se detectaron imports directos
- `services`
  - hacia `repositories`: 15
  - hacia `integrations`: 11
  - hacia `schemas`: 21
  - hacia `bootstrap`: 20
  - hacia `services`: 17
- `bootstrap`
  - hacia `services`: 9
  - hacia `repositories`: 1
  - hacia `integrations`: 1
  - hacia `project_env`: 1
- `repositories`
  - hacia `repositories`: 9
  - hacia `schemas`: 1
  - hacia `bootstrap`: 1
  - hacia `services`: 1
- `integrations`
  - hacia `repositories`: 1
  - hacia `bootstrap`: 1
  - hacia `project_env`: 1

### 7.3 Dependencias alineadas con la arquitectura deseada

Señales positivas:

- No se detectaron imports directos de `src/agents/` hacia `src/repositories/`.
- No se detectaron imports directos de `src/agents/` hacia `src/integrations/`.
- No se detectaron imports de `src/services/` hacia `src/agents/`.
- `tests/test_refactor_guardrails.py` refuerza varios de esos limites.

### 7.4 Dependencias internas que merecen atencion

- `src/repositories/planning/repository.py`
  Importa `validate_event` desde `services.scheduling.validation`.
  Esto introduce una dependencia desde persistencia hacia logica de servicio.
- `src/integrations/microsoft_graph/auth_client.py`
  Importa `repositories.microsoft_graph.state_repository`.
  Es un acoplamiento pragmatico entre integracion externa y persistencia durable.
- `src/agents/support/flows/planning/persistence_support.py`
  Aun conserva coordinacion de persistencia, materializacion y reminders desde la capa del agente.

## 8. Señales de orden o desorden estructural

### 8.1 Señales de orden

- La separacion top-level en `agents`, `services`, `repositories`, `integrations`, `schemas` y `bootstrap` es clara.
- `src/bootstrap/container.py` consolida el wiring principal del runtime.
- `langgraph.json` fija entrypoint del grafo y del checkpointer de forma explicita.
- Los repositorios siguen un patron consistente `Protocol` + `InMemory` + `Postgres`.
- Los nodos del grafo tienden a ser finos y los prompts estan desacoplados en `prompt.py`.
- `tests/test_refactor_guardrails.py` automatiza reglas de arquitectura relevantes.
- `src/rag/` y `src/integrations/whatsapp/` quedaron reservados sin contaminar el core.
- La arquitectura actual es razonable para un MVP con crecimiento incremental.

### 8.2 Señales de desorden o deuda transicional

- `src/agents/support/flows/` todavia mezcla logica conversacional con servicios de aplicacion.
- `src/agents/support/tools/` sigue existiendo como superficie legacy; `src/agents/support/tools/db.py` es un shim.
- Varios scripts siguen importando rutas legacy:
  - `scripts/run_due_reminders.py`
  - `scripts/record_session_completion.py`
  - `scripts/mark_missed_sessions.py`
  - `scripts/backfill_study_plan_instances.py`
  - `scripts/microsoft_oauth_exchange_code.py`
- `main.py` no representa el producto real y puede confundir.
- `prueba1.py` parece un experimento suelto en la raiz.
- Existen artefactos generados en el repo:
  - `.langgraph_api/`
  - `tmp/schedule.png`
  - `src/auth/__pycache__/...`
  - multiples `__pycache__`
- `src/auth/` ya no contiene codigo fuente activo, solo residuos compilados.

## 9. Dudas o zonas grises detectadas

- El dominio de replanificacion existe en `src/agents/support/flows/replanning/` y tiene pruebas en `tests/test_replanning_apply_modifications.py`, pero no aparece conectado al grafo principal en `src/agents/support/agent.py`.
- `src/agents/support/state.py` incluye la fase `"replan"` y el campo `replan`, pero `src/agents/support/agent.py` no define ruta ni nodo para esa fase.
- No hay evidencia de que `main.py` sea usado realmente por el runtime.
- No hay evidencia de que los scripts con imports legacy sigan funcionando despues del refactor.
- `src/integrations/whatsapp/` existe solo como placeholder y no existe aun `src/integrations/telegram/`.
- `src/utils/` esta casi vacio, por lo que algunos helpers transversales aun viven repartidos en capas locales.

## 10. Valoracion general del proyecto como MVP

Valoracion general:

- El proyecto esta bien orientado para un MVP serio.
- La arquitectura actual, despues del refactor reciente, es buena en terminos practicos.
- No parece necesario hablar de reescritura ni de rediseño total.
- La base actual ya tiene capas distinguibles, persistencia durable, runtime claro, integraciones reales y guardrails de arquitectura.

El principal riesgo hoy no es una arquitectura fallida, sino una arquitectura aun en transicion.

La deuda visible se concentra en:

- scripts y entrypoints secundarios no alineados del todo con la nueva estructura;
- cierta logica de aplicacion que sigue en `agents/support/flows/`;
- algunos residuos legacy y artefactos dentro del arbol.

Conclusión de esta fase:

- Como mapa de proyecto, el repositorio es entendible y trazable.
- Como MVP, la arquitectura es suficientemente buena y muestra una mejora clara respecto a un estado pre-refactor.
- Las siguientes fases de auditoria deben profundizar en arquitectura real, flujo del agente y base de datos para confirmar donde la separacion ya es estable y donde aun hay deuda tecnica estructural.
