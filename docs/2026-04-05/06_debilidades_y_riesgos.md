# Debilidades Tecnicas Y Riesgos Consolidados

Fecha: 2026-04-05

Estado: auditoria tecnica en progreso

## 1. Resumen ejecutivo

La base del proyecto es buena para un MVP y la refactorizacion reciente sí mejoró el orden general del repositorio. El problema principal ya no es desorden total, sino una combinación de deuda concentrada en unos pocos hotspots, deuda transicional en scripts y carencias operativas para seguir creciendo con seguridad.

Conclusión principal:

- El proyecto puede seguir evolucionando.
- No conviene refactorizar a ciegas.
- Sí conviene corregir antes de crecer algunos riesgos estructurales y operativos que ya están visibles en el código real.

Los frentes más delicados hoy son:

- estado global demasiado transversal en `src/agents/support/state.py`;
- lógica de aplicación todavía incrustada en `agents/support/flows/`;
- observabilidad y manejo de errores insuficientes;
- seguridad básica mejorable en onboarding y Microsoft Graph;
- deuda transicional en scripts y entrypoints operativos;
- capacidades sugeridas por la arquitectura pero todavía no realmente operativas;
- pruebas útiles pero demasiado apoyadas en `InMemory*`, `Fake*` y `monkeypatch`, sin pipeline CI visible.

## 2. Debilidades arquitectónicas

### 2.1 `AgentState` actúa como bus global transversal

Hechos observados:

- `src/agents/support/state.py` importa contratos de onboarding, scheduling, personalization, planning, reminders y Microsoft.
- `AgentState` concentra `student_profile`, `onboarding`, `raw_inputs`, `schedule`, `calendar`, `study_profile`, `priorities`, `study_plan`, `replan`, `reminders` y `constraints`.
- `src/agents/support/state.py` tiene 119 líneas, pero el problema no es tamaño bruto sino concentración semántica.

Problema detectado:

- demasiados subdominios comparten el mismo estado raíz;
- cada nuevo feature tiene incentivo natural a “agregar otra llave al estado”.

Impacto:

- sube el acoplamiento entre fases del agente;
- hace más costoso razonar sobre regresiones;
- dificulta modularizar futuras integraciones o flujos paralelos.

### 2.2 La capa `agents/support` todavía hace parte de la aplicación, no solo orquestación

Hechos observados:

- `src/agents/support/flows/planning/persistence_support.py` persiste planning, materializa instancias y sincroniza reminders.
- `src/agents/support/flows/scheduling/schedule_capture_service.py` tiene 559 líneas.
- `src/agents/support/flows/scheduling/schedule_review_service.py` tiene 677 líneas.
- `src/agents/support/agent.py` tiene 626 líneas y sigue concentrando routing y control de fases.

Problema detectado:

- la arquitectura declara una separación `agents -> services -> repositories/integrations`, pero parte de la lógica de aplicación todavía vive pegada al agente.

Impacto:

- crecer en onboarding, replanificación o nuevos canales obliga a tocar la capa conversacional más de lo deseable;
- aumenta la fragilidad del grafo y del enrutamiento.

### 2.3 Hay inversión de dependencias parcial, no completa

Hechos observados:

- `src/repositories/planning/repository.py` importa `validate_event` desde `services.scheduling.validation`.
- `src/integrations/microsoft_graph/auth_client.py` importa directamente `MicrosoftGraphStateRepository` y `MicrosoftGraphConnectionRecord`.
- `src/services/sync/outlook_calendar_sync_service.py` y `src/services/sync/microsoft_todo_sync_service.py` están modelados completamente alrededor de Microsoft-specific repos y clientes.

Problema detectado:

- existen fugas entre capas que vuelven menos nítida la frontera dominio/aplicación/infraestructura.

Impacto:

- más difícil desacoplar proveedores o mover piezas sin arrastrar imports cruzados.

### 2.4 El sistema sigue siendo un monolito modular razonable, pero con hotspots demasiado centrales

Hechos observados:

- `README.md` y `tests/test_refactor_guardrails.py` confirman reglas de capas claras.
- Aun así, `src/agents/support/agent.py`, `src/integrations/microsoft_graph/auth_client.py`, `src/agents/support/flows/scheduling/schedule_capture_service.py` y `src/agents/support/flows/scheduling/schedule_review_service.py` concentran una proporción alta de complejidad.

Problema detectado:

- el sistema no está mal cortado globalmente, pero sí depende demasiado de pocos archivos grandes.

Impacto:

- baja el throughput de cambios;
- sube el riesgo de regresión por edición concurrente.

## 3. Debilidades de diseño de código

### 3.1 Hotspots grandes y multitarea

Hechos observados:

- `src/agents/support/agent.py`: 626 líneas.
- `src/agents/support/flows/scheduling/schedule_capture_service.py`: 559 líneas.
- `src/agents/support/flows/scheduling/schedule_review_service.py`: 677 líneas.
- `src/integrations/microsoft_graph/auth_client.py`: 737 líneas.

Problema detectado:

- varios archivos importantes concentran demasiados casos y caminos de error.

Impacto:

- peor mantenibilidad;
- mayor dificultad para leer, probar y modificar.

### 3.2 Deuda transicional visible en scripts operativos

Hechos observados:

- `scripts/run_due_reminders.py` importa `agents.support.reminders_dispatcher`.
- `scripts/backfill_study_plan_instances.py` importa `agents.support.planning.materialization_service`, `agents.support.state` y `agents.support.tools.db_config`.
- `scripts/mark_missed_sessions.py` y `scripts/record_session_completion.py` importan `agents.support.planning.tracking_service`.
- `tests/test_refactor_guardrails.py` protege `src/` contra imports legacy, pero no cubre `scripts/`.

Problema detectado:

- los scripts siguen pegados a rutas o wrappers heredados de antes del refactor.

Impacto:

- alto riesgo de rotura silenciosa en tareas operativas;
- deuda de mantenimiento fuera del core productivo.

### 3.3 Nombres y vocabulario de dominio mezclan español e inglés

Hechos observados:

- `migrations/0002_recurring_schedule_profiles.sql` usa `day_of_week` en inglés y `occupation` con valores `solo_estudio`, `ambos`, `ninguna`.
- `migrations/0007_study_planning_profiles.sql` usa `day_label` en español y categorías también en español.
- En `schemas/` conviven `Event`, `StudyPlanState`, `SubjectItem`, `prioridad`, `urgencia`, `categoria`, `source_event_id`.

Problema detectado:

- el lenguaje del dominio no es completamente uniforme.

Impacto:

- complica onboarding técnico;
- sube el costo cognitivo de mantener validaciones y mappings.

### 3.4 Se usa un service locator controlado

Hechos observados:

- `src/bootstrap/container.py` expone singletons de servicios.
- `src/agents/support/dependencies.py` resuelve dependencias globales desde ese container.

Problema detectado:

- el patrón está controlado y testeado, pero sigue ocultando dependencias reales de algunos nodos y flujos.

Impacto:

- la testabilidad sigue siendo buena, pero la explicitud baja respecto a inyección pura.

## 4. Debilidades funcionales del flujo del agente

### 4.1 Hay partes del flujo que fallan en silencio o con muy poco detalle

Hechos observados:

- `src/agents/support/nodes/build_study_plan/node.py` captura `except Exception` y devuelve un mensaje genérico sin detalle técnico.
- `src/agents/support/nodes/persist_profile/node.py` captura una excepción genérica y la convierte en `persistence_error`.
- `src/agents/support/nodes/persist_study_profile/node.py` tiene varios `except Exception` de fallback.

Problema detectado:

- el flujo privilegia no romper UX, pero sacrifica diagnóstico.

Impacto:

- difícil distinguir entre error de validación, error de datos, error de proveedor o error de persistencia.

### 4.2 El agente hoy no usa varias capacidades que la arquitectura ya insinúa

Hechos observados:

- `src/integrations/whatsapp/README.md` es solo un placeholder.
- `src/rag/README.md` define subcapas reservadas, pero no hay implementación operativa.
- La base real tiene `study_replan_requests`, `study_replan_proposals`, `microsoft_graph_connections`, `outlook_calendar_event_links`, `microsoft_todo_task_links`, pero durante la auditoría esas tablas estaban vacías.
- En `src/services/reminders/dispatcher.py`, `whatsapp` se resuelve con `UnsupportedReminderSender("whatsapp")`.

Problema detectado:

- hay capacidad estructural preparada, pero no capacidad funcional real.

Impacto:

- riesgo de sobreestimar la madurez del producto;
- riesgo de abrir nuevas líneas funcionales antes de estabilizar las existentes.

### 4.3 El flujo de personalización es estático respecto a seguimiento real del estudiante

Hechos observados:

- `src/services/personalization/` no consulta tracking ni check-ins.
- `rg` sobre `src/services/personalization` no muestra integración con `study_session_checkins` ni con `study_plan_event_instances`.
- La base real tenía `study_session_checkins = 0`.

Problema detectado:

- la personalización actual es un snapshot inicial de cuestionario, no un ciclo adaptativo basado en comportamiento real.

Impacto:

- limita el valor de largo plazo del Radar;
- frena personalización iterativa o recomendaciones adaptativas.

## 5. Debilidades del modelo de datos

### 5.1 Credenciales sensibles persistidas en claro

Hechos observados:

- `migrations/0013_microsoft_graph_connections_and_sync.sql` crea `access_token TEXT NOT NULL` y `refresh_token TEXT NULL`.
- `src/repositories/microsoft_graph/state_repository.py` guarda esos campos tal cual.

Problema detectado:

- la base mezcla metadata operativa y secretos de proveedor.

Impacto:

- riesgo de seguridad alto;
- mayor exposición si hay lectura indebida de base o logs de debugging.

### 5.2 Redundancia entre columnas estructuradas y snapshots JSONB

Hechos observados:

- `recurring_schedule_blocks.normalized_payload`
- `study_personalization_profiles.result_payload`
- `study_priority_profiles.result_payload`
- `study_plan_profiles.result_payload`
- `study_plan_events.event_payload`
- `study_plan_event_instances.instance_payload`

Problema detectado:

- se duplica mucha información.

Impacto:

- potencial drift;
- mantenimiento de schema más costoso;
- dudas sobre cuál es el dato canónico en cada caso.

### 5.3 La trazabilidad conversacional no está unida al negocio

Hechos observados:

- `migrations/0003_langgraph_thread_persistence.sql` modela `langgraph_thread_checkpoints` y `langgraph_checkpoint_writes`.
- No hay FK hacia `students`.
- En la base auditada ambas tablas estaban vacías.

Problema detectado:

- no hay traza end-to-end entre conversación, estudiante y entidad persistida de negocio.

Impacto:

- difícil auditar por qué un plan quedó como quedó;
- poca capacidad de debug funcional.

### 5.4 El modelo está adelantado respecto al uso real en varias áreas

Hechos observados:

- `study_replan_*`, `study_session_checkins`, `microsoft_graph_*` y `langgraph_thread_*` existen en schema.
- En la base real todavía no tenían uso visible.

Problema detectado:

- parte del esquema es más avanzado que el flujo operativo real.

Impacto:

- aumenta complejidad conceptual;
- riesgo de divergencia entre schema y comportamiento.

## 6. Riesgos de crecimiento

### 6.1 Agregar features nuevas hoy toca demasiados puntos del agente

Evidencia:

- `src/agents/support/agent.py` centraliza nodos, routers y fases.
- `src/agents/support/state.py` concentra gran parte del estado global.
- `src/agents/support/flows/planning/persistence_support.py` encadena persistencia, materialización y reminders.

Riesgo:

- Telegram, nuevos subflujos de onboarding o una replanificación real podrían incrementar la complejidad del grafo más rápido de lo saludable.

### 6.2 Las pruebas son útiles, pero todavía no validan suficientemente la realidad productiva

Hechos observados:

- Hay 40+ pruebas útiles en `tests/`.
- `tests/test_refactor_guardrails.py` protege varias reglas de arquitectura.
- La mayoría de las pruebas usan `InMemory*`, `_Fake*` y `monkeypatch`.
- No existe carpeta `.github/` con workflows visibles.

Problema detectado:

- hay buena cultura de pruebas unitarias y de guardrails, pero poca evidencia de ejecución automática o de integración real con PostgreSQL y proveedores.

Impacto:

- más riesgo de “todo pasa en local, falla en operación”.

### 6.3 El runtime depende mucho de configuración por entorno

Hechos observados:

- `src/bootstrap/settings.py`, `src/services/onboarding/config.py`, `src/services/personalization/config.py`, `src/agents/support/priorities/config.py`, `src/services/reminders/service.py`, `src/services/planning/materialization_service.py` y `src/integrations/microsoft_graph/auth_client.py` leen variables de entorno directamente.

Problema detectado:

- la configuración está parcialmente centralizada para DB, pero fragmentada para módulos y feature flags.

Impacto:

- difícil reproducibilidad entre entornos;
- riesgo de comportamientos distintos entre CLI, runtime LangGraph y tests.

## 7. Riesgos de integración futura

### 7.1 Microsoft Graph está integrado de forma pragmática, pero fuertemente vendor-specific

Hechos observados:

- `src/services/sync/outlook_calendar_sync_service.py` y `src/services/sync/microsoft_todo_sync_service.py` dependen de clientes y repositorios Microsoft concretos.
- `src/integrations/microsoft_graph/auth_client.py` habla directamente con repositorio durable vía `MicrosoftGraphStateTokenStore`.

Problema detectado:

- el diseño es razonable para MVP, pero cambiar de proveedor o soportar varios proveedores de forma simétrica no sería barato.

Impacto:

- mayor costo para Google Calendar, Telegram o futuros canales si se quiere paridad funcional.

### 7.2 WhatsApp está expuesto en políticas, pero no en entrega real

Hechos observados:

- `migrations/0010_reminder_policies_and_dispatches.sql` permite `channel IN ('in_app', 'email', 'whatsapp')`.
- `src/services/reminders/service.py` declara `_SUPPORTED_CHANNELS = {"in_app", "email", "whatsapp"}`.
- `src/services/reminders/dispatcher.py` resuelve `whatsapp` con `UnsupportedReminderSender("whatsapp")`.

Problema detectado:

- el dominio ya “acepta” WhatsApp, pero el runtime aún no lo soporta.

Impacto:

- si se habilita por configuración o por UI antes de tiempo, fallará en operación.

### 7.3 Los scripts de operación no están alineados con la arquitectura refactorizada

Hechos observados:

- `scripts/backfill_study_plan_instances.py` usa imports legacy.
- `scripts/run_due_reminders.py` usa ruta legacy.
- `scripts/microsoft_oauth_exchange_code.py` todavía usa `agents.support.tools.db_config`.

Problema detectado:

- los jobs y utilidades de soporte son una superficie de integración futura frágil.

Impacto:

- cualquier despliegue con cron, workers o automatizaciones puede heredar deuda del refactor.

## 8. Riesgos para personalización y RAG

### 8.1 La personalización actual es sólida para un cuestionario, pero no para aprendizaje adaptativo

Hechos observados:

- `src/services/personalization/service.py` persiste resultados del cuestionario final.
- `src/services/personalization/scoring.py` produce ranking determinista.
- No hay lectura de tracking o rendimiento real del estudiante desde personalización.

Problema detectado:

- el sistema personaliza bien una recomendación inicial, pero no aprende del uso.

Impacto:

- el módulo puede quedarse corto cuando el producto pida personalización más profunda.

### 8.2 RAG todavía no existe como capacidad operativa

Hechos observados:

- `src/rag/README.md` solo reserva `ingestion/`, `retrieval/` y `prompting/`.
- `migrations/` no contienen `pgvector` ni tablas vectoriales.
- La base auditada no tiene extensión `pgvector`.

Problema detectado:

- no hay infraestructura real de RAG ni separación ya implementada entre conocimiento y operación.

Impacto:

- riesgo de introducir RAG apresuradamente dentro del core operativo y contaminar la arquitectura.

### 8.3 El soporte de datos actual no separa todavía feedback comportamental de conocimiento experto

Hechos observados:

- el modelo actual separa bien operación académica, pero no existe aún un dominio de conocimiento experto ni una capa de feedback analítico cerrando el ciclo.

Riesgo:

- si RAG o personalización avanzada entran sin un corte claro, terminarán mezclándose con scheduling, planning y persistencia operativa.

## 9. Riesgos para mantenibilidad del MVP

### 9.1 Observabilidad insuficiente

Hechos observados:

- no se detectaron imports de `logging` o `logger` en `src/`, `tests/` o `scripts`.
- `src/integrations/ai/_llm_impl.py` usa un `_LAST_LLM_ERROR` global como memoria de error.
- `scripts/*.py` operativos reportan por `print(...)`.

Problema detectado:

- no hay logging estructurado, métricas ni tracing visibles.

Impacto:

- operación difícil;
- troubleshooting lento;
- poca capacidad de auditoría técnica.

### 9.2 Seguridad básica mejorable

Hechos observados:

- `src/services/onboarding/config.py` define `verification_secret = "development-only-secret"` por defecto.
- `src/services/onboarding/config.py` define `fixed_verification_code = "123456"` por defecto.
- En modos `disabled` o `fixed`, `_resolve_allowed_email_domains(...)` puede incluir `outlook.com`.
- `src/repositories/microsoft_graph/state_repository.py` persiste tokens OAuth.

Problema detectado:

- hay defaults de desarrollo que serían peligrosos si llegan a producción.

Impacto:

- mayor riesgo de configuración insegura;
- menor robustez del onboarding y de integraciones externas.

### 9.3 Carga cognitiva alta para nuevos mantenedores

Hechos observados:

- varios dominios ya están presentes: onboarding, scheduling, personalization, priorities, planning, reminders, tracking, Microsoft sync, LangGraph persistence.
- parte de la lógica está bien separada, pero otra parte está repartida entre `agents/`, `services/`, `repositories/`, scripts y docs históricas.

Problema detectado:

- para entender un flujo completo hay que atravesar demasiadas piezas.

Impacto:

- más lenta la incorporación de nuevos desarrolladores;
- más probables cambios incompletos.

## 10. Priorización de hallazgos

### 10.1 Clasificación por prioridad

#### Críticos

- Estado global transversal en `AgentState`.
- Lógica de aplicación todavía incrustada en `agents/support`.
- Observabilidad y manejo de errores insuficientes.
- Seguridad básica débil en onboarding y Microsoft Graph.

#### Importantes

- Scripts operativos con imports legacy.
- Configuración dispersa y muy dependiente de `os.getenv`.
- Acoplamiento alto con Microsoft Graph.
- Modelo de datos con snapshots redundantes y trazabilidad conversacional incompleta.
- Suite de pruebas fuerte en unitarias, débil en integración real y sin CI visible.
- Capacidades prometidas por la arquitectura todavía no operativas: WhatsApp, RAG, replanificación efectiva.

#### Convenientes

- Inconsistencia terminológica español/inglés.
- Service locator controlado pero no completamente explícito.
- Hotspots grandes que aún no son bloqueo inmediato, pero sí deuda clara.

### 10.2 Matriz de hallazgos

| Hallazgo | Evidencia | Impacto | Probabilidad | Severidad | Recomendación inicial |
| --- | --- | --- | --- | --- | --- |
| `AgentState` demasiado transversal | `src/agents/support/state.py` concentra múltiples subdominios | Alto | Alta | Crítica | Definir límites más claros del estado y evitar nuevas llaves top-level por defecto |
| Lógica de aplicación todavía en `agents/support` | `src/agents/support/flows/planning/persistence_support.py`; `schedule_capture_service.py`; `schedule_review_service.py` | Alto | Alta | Crítica | Seguir moviendo coordinación durable a `services/` cuando se abra la fase de intervención |
| Manejo de errores con poco diagnóstico | `src/agents/support/nodes/build_study_plan/node.py`; `persist_profile/node.py`; `persist_study_profile/node.py`; `src/integrations/ai/_llm_impl.py` | Alto | Alta | Crítica | Estandarizar error codes, logging estructurado y contexto mínimo por operación |
| Observabilidad casi inexistente | Sin `logging` en `src/`; `src/integrations/ai/_llm_impl.py` usa `_LAST_LLM_ERROR`; scripts usan `print(...)` | Alto | Alta | Crítica | Agregar logging estructurado por servicio, worker e integración |
| Seguridad básica insuficiente | `src/services/onboarding/config.py`; `migrations/0013_microsoft_graph_connections_and_sync.sql`; `src/repositories/microsoft_graph/state_repository.py` | Alto | Media-Alta | Crítica | Eliminar defaults inseguros en producción y proteger tokens con cifrado/secret store |
| Scripts operativos desalineados con el refactor | `scripts/run_due_reminders.py`; `scripts/backfill_study_plan_instances.py`; `scripts/mark_missed_sessions.py`; `scripts/record_session_completion.py` | Alto | Alta | Importante | Alinear scripts a `services/`, `bootstrap/` y repositorios actuales antes de ampliar jobs |
| Configuración dispersa | `src/bootstrap/settings.py`; `src/services/onboarding/config.py`; `src/services/personalization/config.py`; `src/agents/support/priorities/config.py`; `src/integrations/microsoft_graph/auth_client.py` | Medio-Alto | Alta | Importante | Consolidar criterios de configuración y documentar matriz de variables por módulo |
| Acoplamiento fuerte con Microsoft Graph | `src/integrations/microsoft_graph/auth_client.py`; `src/services/sync/outlook_calendar_sync_service.py`; `src/services/sync/microsoft_todo_sync_service.py` | Medio-Alto | Alta | Importante | Introducir puertos más neutros si se abre soporte multi-proveedor |
| Tests poco cercanos a producción | `tests/` usa ampliamente `InMemory*`, `_Fake*`, `monkeypatch`; no hay `.github/` | Alto | Media | Importante | Añadir pruebas de integración con PostgreSQL y un pipeline CI mínimo |
| Snapshots JSONB redundantes | `migrations/0002...`, `0004...`, `0007...`, `0009...`; repositorios de scheduling, personalization y planning | Medio-Alto | Media | Importante | Declarar dato canónico por tabla y testear consistencia snapshot/columnas |
| Trazabilidad conversacional incompleta | `migrations/0003_langgraph_thread_persistence.sql`; tablas LangGraph sin vínculo a `students` | Medio | Media | Importante | Persistir vínculo `thread_id -> student_id` y, cuando aplique, hacia perfiles |
| WhatsApp sugerido pero no operativo | `migrations/0010...`; `src/services/reminders/service.py`; `src/services/reminders/dispatcher.py`; `src/integrations/whatsapp/README.md` | Medio-Alto | Alta | Importante | No exponer el canal fuera de ambientes controlados hasta tener sender real |
| RAG reservado pero inexistente | `src/rag/README.md`; ausencia de `pgvector` en `migrations/` y en la base auditada | Medio-Alto | Alta | Importante | Mantener RAG fuera del core hasta crear persistencia y contratos separados |
| Personalización no usa feedback real | `src/services/personalization/`; ausencia de integración con tracking/check-ins | Medio | Alta | Importante | Diseñar un ciclo posterior que lea tracking antes de “reentrenar” recomendaciones |
| Lenguaje de dominio inconsistente | `migrations/0002_recurring_schedule_profiles.sql`; `migrations/0007_study_planning_profiles.sql`; `src/schemas/*` | Medio | Alta | Conveniente | Unificar convenciones de idioma y nombres en nuevos módulos |
| Service locator controlado | `src/bootstrap/container.py`; `src/agents/support/dependencies.py` | Medio | Media | Conveniente | Mantenerlo acotado y preferir dependencias explícitas en nuevos servicios |

### 10.3 Dictamen final

Si el proyecto sigue creciendo sin corregir los riesgos más serios, lo más probable no es un colapso inmediato del MVP, sino un deterioro progresivo en cuatro áreas:

- más lentitud para cambiar el grafo y los flujos;
- más dificultad para operar y diagnosticar errores reales;
- más exposición en seguridad/configuración;
- más fricción cuando entren proveedores, canales o personalización avanzada.

La base es suficientemente buena para continuar, pero no conviene abrir todavía nuevas superficies grandes sin atender primero el núcleo de riesgos críticos e importantes.
