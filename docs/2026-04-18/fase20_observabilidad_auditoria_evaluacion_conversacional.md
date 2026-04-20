# Fase 20. Observabilidad, Auditoria Y Evaluacion Conversacional

Fecha: 2026-04-18

## Objetivo

Hacer que el MVP de Lara sea explicable, auditable y regresionable antes de aumentar uso real por WhatsApp e integraciones Microsoft 365.

Esta fase tambien revisa como quedaron aplicadas las fases 0-19, identifica conflictos y deja el flujo esperado del agente en el estado actual del proyecto.

## Cambios Implementados En Fase 20

1. Se agrego `src/services/conversation/observability.py`.
2. Se agregaron snapshots seguros para:
   - decisiones del router;
   - flush del buffer de WhatsApp.
3. Los snapshots no incluyen texto crudo, raw payloads, ids reales de conversacion ni referencias de media.
4. Se agrego `tests/test_conversation_eval_dataset.py` como dataset minimo de regresion conversacional.
5. El dataset cubre:
   - actividades academicas;
   - tracking de sesiones;
   - replanificacion;
   - sync Outlook;
   - sync Microsoft To Do;
   - ayuda guiada;
   - modo socratico;
   - rechazo de quiz/parcial;
   - bienestar;
   - dato faltante;
   - confirmacion;
   - preservacion de bloque activo.

## Estado De Las Fases 0-19

| Fase | Estado | Revision |
| --- | --- | --- |
| 0. Baseline | Aplicada | El diagnostico inicial quedo documentado y sirvio para ordenar dependencias. |
| 1. Estado conversacional | Aplicada | `InteractionState` cubre intent, dominio, modo, pendientes, confirmaciones y trazabilidad basica. |
| 2. Buffer WhatsApp | Aplicada parcialmente operativa | Existe `MessageBuffer` in-memory con flush por timeout al llegar nuevo mensaje, flush inmediato por media, confirmacion y comando critico. Falta worker/webhook que fuerce timeout aunque no llegue un nuevo mensaje. |
| 3. Clasificador y politica de alcance | Aplicada | `input_classifier` y `scope_policy` separan utilidad, alcance, bienestar y evaluaciones. |
| 4. Router conversacional hibrido | Aplicada | `route_conversation_input` preserva bloques activos, datos faltantes y confirmaciones. Se agrego auditoria segura en fase 20. |
| 5. OAuth Microsoft bloqueante | Aplicada con flag | El onboarding puede bloquear en OAuth si `ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=1`. |
| 6. Slots onboarding | Aplicada | Se soporta captura incremental de datos de perfil sin romper el paso a paso. |
| 7. Slots horario y extras | Aplicada | Se sincronizan pendientes de scheduling con `interaction`. Imagenes fuera de captura no se interpretan automaticamente como horario. |
| 8. Gestion de horario fijo | Aplicada | Ver, actualizar y eliminar horario fijo pasa por servicios y confirmaciones donde aplica. |
| 9. Actividades academicas puntuales | Aplicada | Hay captura, persistencia, listado y eliminacion/edicion controlada de actividades. |
| 10. Priorizacion semanal | Aplicada con flag | Se activa por solicitud o post-Radar si `ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW=1`. |
| 11. Plan semanal | Aplicada con flag | Genera plan desde prioridades/actividades y respeta horario fijo. |
| 12. Materializacion y recordatorios | Aplicada con flags | Se activa con `ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION=1`; reminders pueden desactivarse con `ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS=0`. |
| 13. Dispatch WhatsApp recordatorios | Aplicada | Existe dispatcher y script operativo. Requiere ejecucion periodica externa. |
| 14. Tracking sesiones | Aplicada | Permite marcar sesiones completadas, omitidas o perdidas y generar senales de replanificacion. |
| 15. Replanificacion controlada | Aplicada | Propone antes de aplicar, exige confirmacion y mantiene trazabilidad si hay base durable. |
| 16. Sync sesiones Outlook | Aplicada | Sync externo confirmable, idempotente y bloqueado si falta OAuth. |
| 17. Microsoft To Do | Aplicada | Proyecta sesiones `missed` o `skipped` como tareas accionables, con confirmacion. |
| 18. Metodo aplicado a actividades | Aplicada | Usa Radar/RAG para pasos operativos sin inventar tecnicas fuera del corpus. |
| 19. Apoyo guiado y modo socratico | Aplicada | Guia sin resolver, rechaza respuestas finales y limita el modo socratico a tres turnos. |

## Evaluacion De Preparacion Para Despliegue

El proyecto esta cerca de un despliegue MVP controlado. El estado actual es adecuado para un ambiente `staging` o un piloto pequeno con pocos usuarios, siempre que se configuren correctamente base de datos, variables de entorno, credenciales Microsoft, WhatsApp y jobs operativos.

No conviene tratarlo todavia como produccion abierta para muchos estudiantes hasta cerrar estos puntos:

1. Conectar auditoria segura a un sink real: logs estructurados, tabla de auditoria o backend de observabilidad.
2. Implementar flush operativo del buffer por timeout aunque no llegue otro mensaje del usuario.
3. Configurar scheduler externo para recordatorios, sesiones perdidas y retries operativos.
4. Validar OAuth, Outlook Calendar y Microsoft To Do contra un tenant real o sandbox Microsoft.
5. Revisar el orden de migraciones en ambientes limpios, especialmente los dos archivos con prefijo `0014`.
6. Definir politica de privacidad y logs: no registrar texto crudo, `raw_payload`, ids reales ni referencias de media.
7. Activar los flags correctos para el flujo completo post-Radar, materializacion y recordatorios.

La recomendacion practica es desplegar primero en `staging` con 2-5 usuarios de prueba, WhatsApp real o sandbox, Microsoft Graph real, logs sanitizados y jobs programados. Despues de validar el flujo completo, se puede pasar a un piloto academico mas amplio.

## Cumplimiento Del Objetivo Del Agente

El objetivo del proyecto es que Lara apoye a estudiantes de Ingenieria de Sistemas en:

- gestion del tiempo academico;
- planificacion de actividades;
- seguimiento;
- replanificacion;
- recomendacion personalizada de metodos de estudio;
- conversacion por WhatsApp;
- integracion con Microsoft 365, principalmente Outlook Calendar y Microsoft To Do.

Con las fases 0-20, el MVP cubre ese objetivo de forma razonable:

| Objetivo | Estado actual |
| --- | --- |
| Gestion de tiempo | Horario fijo, actividades puntuales, sesiones materializadas y recordatorios. |
| Planificacion academica | Priorizacion semanal, plan de estudio y sesiones basadas en disponibilidad. |
| Seguimiento | Tracking de sesiones completadas, omitidas o perdidas. |
| Replanificacion | Propuestas controladas con diff y confirmacion antes de aplicar. |
| Metodos personalizados | Radar, RAG, recomendacion de tecnicas y metodo aplicado por actividad. |
| WhatsApp | Canal, buffer, mapeo de mensajes, recordatorios y dispatch. |
| Outlook Calendar | OAuth, sync de horario fijo y sesiones de estudio con confirmacion. |
| Microsoft To Do | Proyeccion de sesiones perdidas u omitidas como tareas accionables. |
| Guardrails academicos | Rechazo de evaluaciones para copiar, fuera de alcance y bienestar/crisis. |

El producto ya no es solo un chatbot de preguntas y respuestas. Tiene estado, memoria operacional, planificacion, persistencia, integraciones externas y acciones confirmables.

## Naturaleza Del Agente: Hibrido, No Chatbot Libre

Lara quedo deliberadamente como un agente hibrido: deterministico donde hay riesgo operacional y con IA donde aporta valor pedagogico o interpretativo.

Esto es una decision correcta para el MVP. No conviene que un LLM decida libremente acciones como:

- borrar actividades;
- mover eventos;
- confirmar operaciones externas;
- sincronizar Outlook o To Do;
- interpretar confirmaciones ambiguas;
- resolver evaluaciones;
- cambiar horario fijo.

Por eso son deterministicas estas partes:

- clasificacion inicial;
- politica de alcance;
- router por dominio e intent;
- confirmaciones;
- slots basicos;
- preservacion de bloque activo;
- materializacion de sesiones;
- recordatorios;
- sync externo;
- replanificacion confirmable.

Y son componentes de IA o comportamiento agentico estas partes:

- LangGraph como grafo con estado;
- interpretacion multimodal/LLM de horarios cuando aplica;
- RAG de tecnicas y metodos de estudio;
- recomendacion personalizada segun Radar;
- metodo aplicado por actividad;
- planificacion y replanificacion usando contexto academico;
- modo socratico y ayuda guiada controlada;
- uso de herramientas, repositorios e integraciones externas.

Por tanto, Lara si es un agente de IA, pero no es un asistente generativo libre. La descripcion mas precisa es:

```text
Agente academico hibrido con IA, RAG, estado conversacional, planificacion,
herramientas e integraciones externas, protegido por reglas deterministicas
para seguridad, privacidad y acciones sensibles.
```

El grado de determinismo no le quita valor como agente. En este dominio lo hace mas confiable, porque maneja calendario, tareas, datos personales y decisiones academicas sensibles.

## Arquitectura Actual

La arquitectura general esta alineada con el objetivo del agente:

```text
integrations/*          adaptadores externos: WhatsApp, Microsoft Graph, LangGraph
repositories/*          persistencia PostgreSQL / Microsoft state
services/*              reglas de negocio, politicas, sync, planning, reminders
agents/support/flows/*  coordinacion conversacional por caso de uso
agents/support/nodes/*  nodos finos que adaptan estado LangGraph
agents/support/agent.py wiring del grafo y rutas por phase
schemas/*               contratos entre capas
```

El patron bueno se mantiene:

- Los nodos no importan repositorios ni integraciones directamente.
- Los servicios no importan `agents.support`.
- `AgentState` sigue siendo plano por compatibilidad con LangGraph, pero expone particiones tipadas por dominio.
- Las acciones externas sensibles usan confirmacion y `last_confirmation_payload`.
- La politica de alcance y el router viven en `services/conversation`, no en prompts ni nodos.

## Flujo Actual Del Agente

### Entrada Por WhatsApp

1. WhatsApp normaliza el mensaje como `ChannelInboundMessage`.
2. `WhatsAppChannelService.buffer_inbound` lo pasa a `MessageBuffer`.
3. `MessageBuffer` decide si agrega o hace flush:
   - timeout;
   - media;
   - confirmacion;
   - comando critico;
   - limite de mensajes pendientes;
   - flush manual.
4. El flush produce `AggregatedInput`.
5. `aggregated_input_to_human_message` convierte el payload en `HumanMessage`.
6. LangGraph recibe el nuevo mensaje en `AgentState.messages`.

### Router Y Politica

1. `_route_welcome` detecta entrada nueva cuando `phase=end`.
2. Antes de abrir una intencion nueva, revisa renovacion o reparacion de horario fijo.
3. `route_conversation_input` clasifica el texto, aplica politica de alcance y decide:
   - responder politica;
   - continuar bloque activo;
   - completar dato faltante;
   - confirmar/rechazar;
   - enrutar a un nodo de dominio.
4. La decision incluye intent, dominio, accion, ruta, prioridad, razon, confianza y senales.

### Onboarding Normal

```text
welcome_consent
-> collect_profile
-> send_email_verification
-> verify_email_code
-> request_microsoft_oauth si el flag lo exige
-> confirm_profile
-> persist_profile
-> request_schedules
```

Si el estudiante entrega varios datos en un solo mensaje, el extractor incremental actualiza slots y solo pide lo faltante.

### Horario Fijo Y Extras

```text
request_schedules
-> parse_schedules_to_events
-> ask_extracurricular
-> collect_extracurricular_details
-> build_draft_schedule
-> render_schedule_preview
-> validate_schedule
-> persist_schedule
-> sync_fixed_schedule
```

Despues del onboarding, el horario fijo se puede consultar, modificar o eliminar por `manage_fixed_schedule`.

### Perfil De Estudio, Prioridades Y Plan

```text
collect_study_profile
-> collect_study_profile_tiebreaker si aplica
-> persist_study_profile
-> collect_priorities si ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW=1
-> build_study_plan
```

El plan puede materializar sesiones y recordatorios si los flags operacionales estan activos.

### Uso Diario

Con `phase=end`, Lara puede recibir:

- nueva actividad: `handle_academic_update`;
- tracking de sesion: `handle_academic_update`;
- solicitud de replanificacion: `request_replan`;
- sync Outlook: `sync_study_calendar`;
- sync To Do: `sync_study_todo`;
- pregunta de metodo de estudio: `answer_study_recommendation`;
- ayuda guiada o modo socratico: `guided_academic_support`;
- fuera de alcance o bienestar: `answer_scope_boundary`.

### Acciones Externas

Las acciones con Outlook o To Do siguen este patron:

```text
detectar solicitud
-> construir preview/diff
-> guardar last_confirmation_payload
-> esperar si/no
-> ejecutar solo si confirma
-> reportar resultado sin romper plan local si falla
```

## Observabilidad Implementada

### Router

`build_router_audit_event(decision, phase, interaction)` produce un dict seguro con:

- intent;
- dominio;
- accion;
- route name;
- confianza;
- prioridad;
- razon;
- si preserva o interrumpe bloque activo;
- categoria y razon de politica;
- tipo/utilidad del input;
- estado del bloque activo sin payload sensible.

No incluye `normalized_text`, mensaje crudo ni payloads completos.

### Buffer

`build_buffer_audit_event(aggregated)` produce:

- canal;
- fingerprints de conversacion, sender y mensaje;
- cantidad de mensajes;
- razon de flush;
- tipos de media;
- estadisticas del texto;
- clasificacion.

No incluye texto crudo, raw payload, ids reales ni referencias de archivos.

## Metricas Recomendadas

Para fase 20, las metricas minimas deben salir de eventos de auditoria y tests de dataset:

| Metrica | Fuente | Uso |
| --- | --- | --- |
| Intent accuracy | `tests/test_conversation_eval_dataset.py` + logs router | Detectar regresiones del router. |
| Scope accuracy | `scope.reason`, `scope.intent` | Evitar que Lara responda fuera de alcance o resuelva evaluaciones. |
| Tasa de clarificaciones | `decision.action=provide_missing_data` y `clarification_needed` | Saber si los extractores piden demasiados datos. |
| Tasa de confirmaciones | `confirm_action` vs `reject_action` | Medir friccion antes de acciones externas. |
| Bloques preservados | `preserves_active_block=true` | Detectar interrupciones indebidas. |
| Errores de sync | resultados de Outlook/To Do/WhatsApp | Separar problemas externos de errores conversacionales. |
| Flush por timeout | `flush_reason=timeout` | Validar si el buffer esta esperando demasiado o muy poco. |
| Eventos de bienestar | `domain=risk_or_wellbeing` | Asegurar respuesta segura y no academica automatica. |

## Problemas Y Advertencias

### Alta Prioridad

1. El buffer es in-memory y el flush por timeout depende de una nueva entrada o un flush manual. Para produccion por webhook falta un mecanismo periodico por conversacion o un worker que invoque `flush_inbound_buffer`.
2. Los eventos de auditoria seguros existen, pero aun no se envian a ningun sink durable. Falta decidir si van a logs estructurados, tabla de auditoria o backend de observabilidad.
3. `migrations/` tiene dos archivos con prefijo `0014`: `0014_grant_microsoft_graph_permissions.sql` y `0014_weekly_priority_snapshot_metadata.sql`. En ambientes nuevos puede generar confusion operacional. No renombrar a ciegas si ya fueron aplicados; documentar orden real o crear una migracion de control.
4. Los scripts operativos de recordatorios, sesiones perdidas, Outlook y To Do requieren scheduler externo. El MVP no tiene daemon propio.
5. No se debe loggear directamente `AggregatedInput`, `BufferedMessage` ni `ChannelInboundMessage`, porque contienen texto crudo, raw payload o referencias de media. Usar siempre `build_buffer_audit_event`.

### Media Prioridad

1. `src/agents/support/agent.py` tiene 959 lineas. Sigue aceptable para el MVP, pero el wiring y las rutas por phase ya estan cerca del limite. Proximo refactor: mover tablas/rutas por dominio a modulos de routing del grafo.
2. `src/agents/support/nodes/handle_academic_update/node.py` tiene 606 lineas. Ya coordina actividades, tracking y replanificacion. Proximo refactor: separar en flujo de actividad y flujo de tracking.
3. Servicios grandes:
   - `academic_activity_service.py`: 1026 lineas;
   - `replanning_service.py`: 781 lineas;
   - `applied_method_service.py`: 728 lineas;
   - `weekly_priority_service.py`: 749 lineas.
   No rompen arquitectura, pero conviene separar parsing, rendering, politicas y persistencia cuando se agreguen mas reglas.
4. `router.py`, `scope_policy.py` e `input_classifier.py` son deterministas y estan cubiertos por tests, pero cada nuevo intent aumenta riesgo de shadowing. La fase 20 deja dataset para contenerlo.
5. La activacion completa de prioridad/plan depende de flags. En pruebas manuales, si los flags estan apagados el agente puede responder limites aunque el codigo exista.

### Baja Prioridad

1. Algunas integraciones Microsoft pueden funcionar con clientes placeholder si no hay configuracion real. Antes de prueba de campo se debe validar OAuth, Calendar y To Do contra tenant real o sandbox.
2. RAG y metodo aplicado dependen de corpus, pgvector y fuentes. Si no hay fuentes, el servicio evita inventar, lo cual es correcto, pero puede verse como respuesta limitada.
3. `AgentState` conserva contrato plano mas particiones tipadas. Es una transicion razonable; no conviene migrarlo de golpe mientras LangGraph y tests esten estables.

## Recomendaciones

1. Antes de nuevas features, conectar `build_router_audit_event` y `build_buffer_audit_event` al punto de entrada real del webhook.
2. Agregar una tabla o sink de auditoria con retencion corta y datos sanitizados.
3. Crear job de flush de buffer por timeout si WhatsApp no entrega un nuevo mensaje.
4. Crear scheduler para:
   - `scripts/run_due_reminders.py`;
   - `scripts/mark_missed_sessions.py`;
   - sync/retry externo si aplica.
5. Separar `handle_academic_update` antes de sumar mas reglas de seguimiento.
6. Mantener todo nuevo intent dentro del dataset de evaluacion conversacional.
7. Documentar flags necesarios para pruebas end-to-end del MVP:
   - `ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW`;
   - `ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION`;
   - `ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS`;
   - `ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH`.
8. No ampliar modo socratico hacia tutor generalista. Debe seguir acotado a actividad, materia y tema.

## Comandos De Diagnostico

Pruebas focalizadas de fase 20:

```bash
uv run --with pytest python -m pytest \
  tests/test_conversation_eval_dataset.py \
  tests/test_conversation_router.py \
  tests/test_whatsapp_message_buffer.py \
  tests/test_scope_policy.py \
  tests/test_input_classification.py
```

Resultado validado:

```text
52 passed
```

Suite completa:

```bash
uv run --with pytest python -m pytest
```

Resultado validado:

```text
534 passed
```

Revision de formato de diff:

```bash
git diff --check
```

Diagnosticos operativos existentes:

```bash
uv run python scripts/run_due_reminders.py --help
uv run python scripts/mark_missed_sessions.py --help
uv run python scripts/record_session_completion.py --help
uv run python scripts/sync_microsoft_todo.py --help
uv run python scripts/evaluate_rag.py --help
```

## Criterio De Cierre

- Cada decision importante del router puede explicarse con un snapshot seguro.
- El buffer puede auditarse sin exponer texto del estudiante.
- Hay dataset de regresion para casos conversacionales reales.
- El informe deja claro el flujo actual del agente, riesgos y recomendaciones.
