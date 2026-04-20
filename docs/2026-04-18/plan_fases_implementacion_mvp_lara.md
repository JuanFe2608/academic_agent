# Plan De Fases Para Implementar El MVP Conversacional De Lara

Fecha: 2026-04-18

Documento rector principal: `docs/mvp_academic_agent_lara.md`

Documentos tecnicos relacionados:

- `docs/2026-04-03/informe_final_arquitectura_cerrada.md`
- `docs/2026-04-03/architecture_rules.md`
- `docs/2026-04-17/informe_implementacion_rag_fases_a_h.md`
- `docs/2026-04-17/flujo_conversacional_mvp_agente_academico.md`

## 1. Proposito Del Informe

Este informe define una ruta de implementacion por fases pequenas para llevar el proyecto hacia el MVP conversacional descrito en `docs/mvp_academic_agent_lara.md`, manteniendo la arquitectura actual:

```text
agents -> services -> repositories/integrations -> schemas/utils
```

La idea no es rehacer el agente. La estrategia correcta es:

1. conservar LangGraph como orquestador;
2. conservar `AgentState` como contrato del grafo;
3. agregar una capa conversacional previa para WhatsApp;
4. activar dominios que ya existen pero estan desactivados;
5. implementar las brechas del documento rector sin contaminar nodos con logica de negocio;
6. verificar cada fase con pruebas unitarias y de flujo antes de avanzar.

El documento esta escrito para que cada fase sea implementable sin abrir un cambio demasiado grande.

## 2. Diagnostico Actual Del Proyecto

### 2.1 Capacidades ya implementadas o muy avanzadas

El proyecto ya tiene una base solida:

- Grafo principal en `src/agents/support/agent.py`.
- Estado tipado y particionado en `src/agents/support/state.py`.
- Bienvenida y consentimiento en `src/agents/support/nodes/welcome_consent/`.
- Onboarding con validadores deterministas en `src/agents/support/flows/onboarding/` y `src/agents/support/onboarding/`.
- Verificacion de correo por codigo en `send_email_verification` y `verify_email_code`.
- Captura de horario fijo academico/laboral/extracurricular.
- Preview, validacion, persistencia y sincronizacion de horario fijo con Outlook.
- Integracion Microsoft OAuth en `src/integrations/microsoft_graph/auth_client.py`.
- Repositorios de Microsoft Graph y sync durable.
- Radar de estudio deterministico en `src/services/personalization/`.
- RAG de recomendaciones de estudio en `src/rag/` y `src/services/study_recommendations/`.
- Servicios de prioridades, plan semanal, materializacion, recordatorios y tracking, pero necesita ser ajustado y cambiado.
- Cliente y servicio base de WhatsApp en `src/integrations/whatsapp/` y `src/services/channels/`.
- Servicios de Microsoft To Do en `src/services/sync/microsoft_todo_sync_service.py`.

### 2.2 Capacidades existentes pero no activas en el flujo principal

Estas piezas existen, pero no forman todavia un flujo conversacional completo:

- `collect_priorities`.
- `build_study_plan`.
- `handle_academic_update`.
- persistencia de snapshot de planning.
- materializacion de sesiones de estudio.
- politicas y dispatches de recordatorios.
- tracking de sesiones iniciadas, completadas, omitidas o perdidas.
- Microsoft To Do para sesiones accionables.
- replanificacion posterior al Radar como loop operacional.

El grafo actualmente corta las fases `priorities`, `study_plan` y `running` hacia `end`. Esto coincide con el diagnostico del documento rector: despues del Radar no se ejecuta automaticamente la operacion semanal.

### 2.3 Brechas principales frente al documento rector

Las brechas mas importantes son:

1. Falta subflujo OAuth conversacional obligatorio despues del correo y antes de semestre.
2. Falta estado conversacional operativo: `active_intent`, `pending_entity_payload`, `missing_fields_json`, `confirmation_pending`, etc.
3. Falta buffer/agregador de mensajes WhatsApp antes del router.
4. Falta clasificacion formal de input: texto util, ruido, sticker, imagen, emoji, confirmacion.
5. Falta router conversacional por intents y dominios, complementario al router por `phase`.
6. Falta extraccion incremental de slots.
7. Falta CRUD conversacional completo para actividades academicas puntuales.
8. Falta activar priorizacion semanal y plan semanal despues del Radar.
9. Falta loop completo de recordatorios, seguimiento y replanificacion.
10. Falta politica robusta para fuera de alcance, evaluaciones y bienestar/crisis.

## 3. Principios De Implementacion

### 3.1 No romper la arquitectura actual

Cada fase debe respetar estas fronteras:

- `agents/support/`: orquestacion, nodos, prompts, routing del grafo y adaptacion del estado.
- `services/`: casos de uso, reglas de negocio, parsing, scoring, routers de negocio, buffer conversacional.
- `repositories/`: persistencia durable.
- `integrations/`: clientes externos: Microsoft, WhatsApp, AI, embeddings.
- `schemas/`: contratos y DTOs compartidos.
- `bootstrap/`: wiring y construccion de servicios.

Regla concreta:

```text
Ningun nodo nuevo debe importar repositorios ni integraciones directamente.
```

Si una fase necesita Microsoft, WhatsApp, DB o RAG, debe usar un servicio expuesto desde `agents/support/dependencies.py` y construido en `bootstrap/container.py`.

### 3.2 Mantener fases pequenas

Cada fase debe:

- tener un objetivo claro;
- tocar pocos dominios;
- dejar pruebas;
- poder revertirse o desactivarse por configuracion;
- no mezclar infraestructura conversacional con features de producto;
- no activar automaticamente una feature antes de tener estado, confirmaciones y persistencia listas.

### 3.3 Regla de compatibilidad

El flujo actual no debe degradarse:

```text
bienvenida -> consentimiento -> onboarding -> horario fijo -> sync -> Radar -> end
```

Las fases nuevas deben integrarse de forma incremental, idealmente detras de flags como:

- `ACADEMIC_AGENT_ENABLE_INTERACTION_STATE`
- `ACADEMIC_AGENT_ENABLE_MESSAGE_BUFFER`
- `ACADEMIC_AGENT_ENABLE_CONVERSATIONAL_ROUTER`
- `ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH`
- `ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW`

Los nombres exactos pueden cambiar, pero la idea de activacion controlada debe mantenerse.

## 4. Mapa De Capas Recomendado Para Las Nuevas Piezas

### 4.1 Estado conversacional operativo

Ubicacion recomendada:

- `src/schemas/conversation.py`
- `src/services/conversation/state_helpers.py`
- extension controlada de `src/agents/support/state.py`

Responsabilidad:

- declarar DTOs;
- normalizar valores;
- serializar/deserializar desde `AgentState`;
- no contener logica de dominio.

### 4.2 Buffer y clasificacion de input

Ubicacion recomendada:

- `src/schemas/channels.py` si los DTOs son compartidos;
- `src/services/channels/message_buffer.py`;
- `src/services/channels/input_classifier.py`;
- `src/services/channels/whatsapp_service.py` como consumidor.

Responsabilidad:

- unir mensajes fragmentados;
- decidir flush;
- clasificar tipo/utilidad de input;
- producir un payload listo para el grafo.

### 4.3 Router conversacional e intents

Ubicacion recomendada:

- `src/schemas/conversation.py`;
- `src/services/conversation/router.py`;
- `src/services/conversation/scope_policy.py`;
- `src/services/conversation/slot_extraction.py`.

Responsabilidad:

- detectar intent;
- respetar bloque activo;
- aplicar politica de alcance;
- producir una decision de enrutamiento;
- no ejecutar acciones externas.

### 4.4 Dominios de producto

Mantener los dominios donde ya estan:

- onboarding: `src/services/onboarding/`, `src/agents/support/flows/onboarding/`
- scheduling: `src/services/scheduling/`, `src/agents/support/flows/scheduling/`
- priorities: `src/services/priorities/`, `src/agents/support/flows/priorities/`
- planning: `src/services/planning/`, `src/agents/support/flows/planning/`
- reminders: `src/services/reminders/`
- sync: `src/services/sync/`
- recommendations: `src/services/study_recommendations/`

## 5. Roadmap Por Fases

## Fase 0. Baseline Y Contrato Del Flujo Actual

### Objetivo

Congelar el comportamiento actual antes de modificar routing, estado o OAuth. Esta fase evita que las siguientes introduzcan regresiones silenciosas.

### Por que va primero

El proyecto ya tiene muchas piezas implementadas. Antes de activar nuevas capas hay que dejar claro que el flujo actual sigue funcionando.

### Pasos

1. Crear una matriz de flujo actual con estas rutas:
   - consentimiento aceptado;
   - consentimiento rechazado;
   - onboarding completo;
   - correo invalido;
   - codigo estudiantil fuera de alcance;
   - horario solo estudio;
   - horario estudio y trabajo;
   - horario con cruce aceptado;
   - horario con correccion;
   - Radar sin desempate;
   - Radar con desempate.
2. Revisar que los tests existentes cubren esas rutas.
3. Agregar pruebas faltantes solo si hay huecos criticos.
4. Documentar en un archivo corto cuales fases estan activas y cuales no.

### Archivos probables

- `tests/test_agent_wait_routing.py`
- `tests/test_schedule_request_flow.py`
- `tests/test_personalization_flow.py`
- `tests/test_study_recommendation_agent_flow.py`
- `tests/test_refactor_guardrails.py`
- `docs/2026-04-18/estado_baseline_mvp_lara.md`

### Criterio de cierre

- El flujo actual pasa tests.
- El equipo sabe que las fases posteriores no deben romper el camino inicial.
- Queda documentada la diferencia entre MVP activo y MVP objetivo.

## Fase 1. Estado Conversacional Operativo Minimo

### Objetivo

Agregar una capa de estado conversacional separada del estado de dominio, tal como pide el documento rector.

### Alcance

Incluir campos minimos:

```json
{
  "active_intent": null,
  "current_domain": null,
  "interaction_mode": "guided",
  "pending_action": null,
  "pending_entity_type": null,
  "pending_entity_payload": {},
  "missing_fields_json": [],
  "confirmation_pending": false,
  "last_confirmation_payload": null,
  "noise_turn_count": 0,
  "last_user_messages": [],
  "aggregated_user_text": null,
  "router_confidence": null,
  "clarification_needed": false,
  "is_waiting_for_oauth": false,
  "is_waiting_for_verification_code": false,
  "current_step": null,
  "current_section": null
}
```

### Pasos

1. Crear DTOs en `src/schemas/conversation.py`.
2. Agregar helpers de normalizacion en `src/services/conversation/state_helpers.py`.
3. Extender `AgentState` con un campo nuevo, por ejemplo `interaction`.
4. Mantener defaults compatibles para estados antiguos.
5. Agregar propiedad tipada en `AgentState` similar a `conversation_state`.
6. No cambiar aun el router.
7. Agregar tests de serializacion, defaults y compatibilidad.

### Archivos probables

- `src/schemas/conversation.py`
- `src/services/conversation/__init__.py`
- `src/services/conversation/state_helpers.py`
- `src/agents/support/state.py`
- `tests/test_interaction_state.py`
- `tests/test_agent_state_partitioning.py`

### Criterio de cierre

- El nuevo estado existe.
- No cambia el comportamiento del flujo actual.
- Los tests actuales siguen pasando.
- `AgentState` no acumula logica de negocio.

## Fase 2. Buffer De Mensajes Y Agregacion WhatsApp

### Objetivo

Implementar la capa previa al router:

```text
Webhook WhatsApp -> Buffer -> Normalizador -> Payload agregado -> Grafo
```

### Por que es critica

WhatsApp rompe flujos si se procesa cada mensaje como turno completo. El documento rector identifica `provide_missing_data` y mensajes fragmentados como una de las piezas mas delicadas.

### Alcance

Implementar:

- `BufferedMessage`;
- `MessageBuffer`;
- `AggregatedInput`;
- reglas de flush;
- agregacion con saltos de linea;
- normalizacion ligera;
- almacenamiento in-memory inicial.

No implementar Redis todavia.

### Pasos

1. Definir DTOs en `schemas/channels.py` o `schemas/conversation.py`.
2. Crear `src/services/channels/message_buffer.py`.
3. Implementar `add_message`, `should_flush`, `flush`, `reset`, `aggregate_text`.
4. Implementar flush inmediato para:
   - imagen;
   - audio;
   - documento;
   - sticker;
   - confirmacion clara;
   - comando critico.
5. Implementar timeout configurable.
6. Integrarlo en el servicio de canal sin tocar aun el grafo principal.
7. Agregar tests unitarios del buffer.

### Archivos probables

- `src/schemas/channels.py`
- `src/services/channels/message_buffer.py`
- `src/services/channels/whatsapp_service.py`
- `tests/test_whatsapp_message_buffer.py`
- `tests/test_whatsapp_channel_service.py`

### Criterio de cierre

- Mensajes como `Andres`, `Gomez`, `67000921` pueden llegar a un payload agregado.
- `si`, `no`, `cancelar`, `borra`, `reagenda` hacen flush inmediato.
- Imagen en captura de horario se conserva como input util.
- Sticker sin contexto no dispara el grafo como si fuera texto academico.

## Fase 3. Clasificador De Input Y Politica De Alcance

### Objetivo

Clasificar cada input agregado antes del router principal:

- tipo de entrada;
- utilidad;
- posible intent;
- categoria de alcance;
- caso sensible.

### Alcance

Implementar primero reglas deterministicas. Usar LLM solo despues y solo si la confianza es baja.

Categorias minimas:

- `in_scope`
- `partially_in_scope`
- `redirectable_out_of_scope`
- `hard_out_of_scope`
- `human_support_case`

Tipos de input:

- `text`
- `emoji_only`
- `sticker_only`
- `image_only`
- `mixed`
- `audio`
- `document`

### Pasos

1. Crear modelos `InputClassification` y `ScopeDecision`.
2. Implementar clasificador deterministico.
3. Agregar politica especial para:
   - quiz;
   - parcial;
   - taller;
   - tarea;
   - ejercicio;
   - exposicion.
4. Separar respuesta fuera de alcance de respuesta de bienestar/crisis.
5. Conectar inicialmente solo cuando `phase=end`, para reducir riesgo.
6. Reemplazar gradualmente `answer_scope_boundary` por una salida basada en politica.

### Archivos probables

- `src/schemas/conversation.py`
- `src/services/conversation/input_classifier.py`
- `src/services/conversation/scope_policy.py`
- `src/agents/support/nodes/answer_scope_boundary/node.py`
- `tests/test_scope_policy.py`
- `tests/test_input_classification.py`
- `tests/test_out_of_scope_restart.py`

### Criterio de cierre

- El agente no responde como asistente generalista.
- Solicitudes de resolver evaluaciones reciben limite claro y alternativa permitida.
- Mensajes de bienestar/crisis no se tratan como plan academico normal.
- Mensajes redirigibles vuelven al dominio academico con siguiente accion concreta.

## Fase 4. Router Conversacional Hibrido

### Objetivo

Agregar un router por dominios e intents que complemente al router por `phase`.

### Principio clave

El router debe respetar primero el bloque activo:

```text
1. riesgo/bienestar
2. fuera de alcance
3. onboarding incompleto
4. bloque activo en curso
5. confirmacion pendiente
6. nueva actividad academica
7. edicion de horario
8. priorizacion semanal
9. plan semanal
10. personalizacion de estudio
11. modo socratico
12. smalltalk contextual
```

### Alcance inicial

No implementar todos los intents de una vez. Empezar con:

- `provide_missing_data`
- `confirm_action`
- `reject_action`
- `smalltalk_contextual`
- `out_of_scope_request`
- `wellbeing_or_crisis_signal`
- `register_academic_activity`
- `request_study_method_recommendation`

### Pasos

1. Crear `ConversationRouteDecision`.
2. Crear `src/services/conversation/router.py`.
3. Implementar decision por reglas:
   - si hay `confirmation_pending`, interpretar confirmacion/rechazo;
   - si hay `missing_fields_json`, intentar `provide_missing_data`;
   - si el input es fuera de alcance, devolver politica;
   - si no hay bloque activo, detectar intent nuevo.
4. Integrar solo en `phase=end` al principio.
5. Luego integrarlo en fases activas sin romper `_should_wait`.
6. Agregar tests de prioridad entre bloque activo e intencion nueva.

### Archivos probables

- `src/services/conversation/router.py`
- `src/schemas/conversation.py`
- `src/agents/support/agent.py`
- `tests/test_conversation_router.py`
- `tests/test_agent_wait_routing.py`

### Criterio de cierre

- Un mensaje como `viernes` completa un dato pendiente, no abre una intencion nueva.
- Un mensaje como `borra esa actividad` no se mezcla con una captura anterior.
- `gracias`, `ok`, `jaja` no rompen el flujo activo.

## Fase 5. OAuth Microsoft Bloqueante En Onboarding

### Objetivo

Insertar el paso OAuth entre correo verificado y semestre cuando el MVP lo requiera.

### Estado actual

La integracion OAuth existe, pero el onboarding conversacional actual verifica correo por codigo y luego sigue hacia semestre. Falta:

- nodo conversacional;
- estado `is_waiting_for_oauth`;
- URL enviada por WhatsApp;
- callback que marque conexion;
- reanudacion del grafo.

### Pasos

1. Agregar flag `ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH`.
2. Crear fase nueva, por ejemplo `microsoft_oauth`.
3. Crear nodo `request_microsoft_oauth`.
4. Crear servicio de aplicacion para iniciar OAuth, por ejemplo `services/sync/microsoft_oauth_flow_service.py`.
5. Generar `state` seguro, aleatorio, expirable y asociado al estudiante.
6. Persistir `state` pendiente en repositorio Microsoft o tabla dedicada.
7. Enviar URL por WhatsApp o devolver mensaje con URL.
8. Crear handler/callback fuera del grafo que llame `exchange_authorization_code`.
9. Al completarse OAuth, limpiar `is_waiting_for_oauth` y continuar a semestre.
10. Si falla, permitir reintento sin reiniciar todo el onboarding.

### Archivos probables

- `src/agents/support/nodes/request_microsoft_oauth/node.py`
- `src/agents/support/agent.py`
- `src/agents/support/state.py`
- `src/services/sync/microsoft_oauth_flow_service.py`
- `src/repositories/microsoft_graph/state_repository.py`
- `src/bootstrap/container.py`
- `src/agents/support/dependencies.py`
- `tests/test_microsoft_auth_scaffold.py`
- `tests/test_onboarding_oauth_flow.py`

### Criterio de cierre

- Si el flag esta apagado, el onboarding actual sigue igual.
- Si el flag esta encendido, el agente no pide semestre hasta que exista conexion Microsoft persistida.
- El `state` OAuth no es deterministico.
- El usuario puede reintentar si el enlace vence o falla.

## Fase 6. Extraccion Incremental De Slots Para Onboarding

### Objetivo

Permitir que el estudiante entregue varios datos en un solo mensaje sin que el agente los ignore.

### Ejemplo esperado

Usuario:

```text
Soy Andres Gomez, tengo 20 y voy en octavo.
```

El sistema debe extraer:

- `full_name = Andres Gomez`
- `age = 20`
- `semester = 8`

Luego solo debe pedir lo que falta.

### Pasos

1. Crear extractor deterministico inicial para onboarding.
2. Fusionar slots extraidos con `student_profile`.
3. Validar cada slot con los validadores existentes.
4. Guardar errores por campo.
5. Preguntar solo el siguiente faltante.
6. Mantener compatibilidad con captura paso a paso.
7. Agregar fallback LLM solo si se justifica y con esquema estructurado.

### Archivos probables

- `src/services/onboarding/slot_extraction.py`
- `src/agents/support/flows/onboarding/collect_profile.py`
- `src/services/conversation/state_helpers.py`
- `tests/test_onboarding_slot_extraction.py`
- `tests/test_collect_profile_validation.py`

### Criterio de cierre

- El onboarding sigue aceptando respuestas paso a paso.
- Si el usuario da varios datos, el agente no los vuelve a pedir.
- Los validadores deterministas siguen siendo la fuente de verdad.

## Fase 7. Extraccion Incremental Para Horario Fijo Y Extras

### Objetivo

Aplicar el mismo patron de slots a horario academico, laboral y extracurricular.

### Alcance

No reescribir el parser de horarios. Reutilizar:

- `services/scheduling/`
- `schedule_parsing_service`
- `section_confirmation_service`
- pending items existentes.

### Pasos

1. Unificar el resultado de parsers en una estructura de slots faltantes.
2. Registrar `pending_entity_type = fixed_schedule_item`.
3. Registrar `pending_entity_payload` para items incompletos.
4. Usar `missing_fields_json` para pedir solo dia, hora, nombre o AM/PM.
5. Soportar mensajes fragmentados desde el buffer.
6. Mantener confirmacion por seccion antes de avanzar.

### Archivos probables

- `src/services/scheduling/parsing_results.py`
- `src/services/scheduling/pending_schedule_support.py`
- `src/agents/support/flows/scheduling/schedule_capture_service.py`
- `src/agents/support/flows/scheduling/schedule_pending_resolution_service.py`
- `tests/test_schedule_parsing_service.py`
- `tests/test_fixed_schedule_pipeline.py`

### Criterio de cierre

- Si falta dia, el agente pide solo dia.
- Si falta hora, pide solo rango horario.
- Si una imagen llega fuera de captura de horario, no se procesa como horario automaticamente.

## Fase 8. Gestion Conversacional Del Horario Fijo

### Objetivo

Implementar consulta, edicion y eliminacion del horario fijo ya registrado por lenguaje natural.

### Intents cubiertos

- `view_fixed_schedule`
- `update_fixed_schedule`
- `delete_fixed_schedule_item`

### Pasos

1. Definir contratos para operaciones de horario fijo.
2. Reutilizar servicios de matching y replanificacion existentes.
3. Mostrar resumen antes de cambios sensibles.
4. Pedir confirmacion antes de eliminar o sincronizar cambios externos.
5. Persistir cambios locales.
6. Reconciliar Outlook si aplica.
7. Actualizar `interaction.last_confirmation_payload`.

### Archivos probables

- `src/services/scheduling/activity_matching.py`
- `src/agents/support/flows/replanning/`
- `src/services/sync/outlook_fixed_schedule_reconciliation_service.py`
- `src/agents/support/nodes/apply_modifications/node.py`
- `tests/test_schedule_modifications.py`
- `tests/test_replanning_apply_modifications.py`
- `tests/test_outlook_fixed_schedule_reconciliation_service.py`

### Criterio de cierre

- El usuario puede ver su horario fijo.
- Puede cambiar una clase/trabajo/extracurricular.
- Puede eliminar un bloque con confirmacion.
- Outlook queda reconciliado o se reporta una falla no destructiva.

## Fase 9. Captura Durable De Actividades Academicas Puntuales

### Objetivo

Permitir registrar actividades no recurrentes:

- parcial;
- quiz;
- tarea;
- taller;
- entrega;
- exposicion;
- proyecto;
- estudio pendiente.

### Por que va antes de priorizacion

La priorizacion semanal necesita datos reales. Sin actividades puntuales, el plan semanal queda pobre y depende solo de materias del horario.

### Pasos

1. Definir modelo de actividad academica puntual.
2. Revisar si conviene usar `subjects` actuales o crear tabla/repositorio dedicado.
3. Implementar extractor de slots:
   - `activity_type`;
   - `subject_name`;
   - `activity_title`;
   - `due_date`;
   - `due_time`;
   - `estimated_effort_minutes`;
   - `priority_level`;
   - `difficulty_level`.
4. Implementar captura incremental.
5. Pedir confirmacion antes de persistir.
6. Permitir listar, editar y eliminar.
7. No resolver el contenido de la actividad.

### Archivos probables

- `src/schemas/planning.py`
- `src/services/priorities/weekly_priority_service.py`
- `src/services/planning/`
- `src/repositories/planning/`
- `src/agents/support/nodes/handle_academic_update/node.py`
- `tests/test_academic_update_flow.py`
- `tests/test_subject_prioritization_service.py`

### Criterio de cierre

- `Tengo parcial de calculo el viernes` crea una actividad pendiente o pide solo el dato faltante.
- `Borra el parcial de calculo` pide confirmacion antes de eliminar.
- Solicitudes de resolver el parcial son rechazadas y redirigidas a plan/guia.

## Fase 10. Activacion De Priorizacion Semanal

### Objetivo

Activar `collect_priorities` despues del Radar o cuando el usuario pida priorizar.

### Estado actual

El nodo existe y delega en `handle_priorities_turn`, pero el grafo lo corta hacia `end`.

### Pasos

1. Agregar flag `ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW`.
2. Cambiar salida de `persist_study_profile` para ir a `priorities` cuando el flag este activo.
3. Asegurar que `collect_priorities` pueda iniciar con:
   - materias derivadas del horario;
   - actividades academicas puntuales;
   - tecnica principal del Radar.
4. Persistir snapshot con `persist_planning_snapshot_for_update`.
5. Manejar opcion de omitir sin romper planificacion futura.
6. Agregar tests del nuevo routing.

### Archivos probables

- `src/agents/support/agent.py`
- `src/agents/support/nodes/collect_priorities/node.py`
- `src/agents/support/flows/priorities/priority_capture_service.py`
- `src/services/priorities/`
- `tests/test_priorities_flow.py`
- `tests/test_weekly_priority_service.py`

### Criterio de cierre

- Despues del Radar el agente puede pedir prioridades semanales.
- El usuario puede omitir o confirmar.
- La salida persiste snapshot sin duplicar materias.

## Fase 11. Activacion Del Plan Semanal De Estudio

### Objetivo

Activar `build_study_plan` como paso natural despues de priorizar.

### Pasos

1. Cambiar ruta de `priorities` completado hacia `study_plan`.
2. Usar `sync_subjects_and_study_plan`.
3. Enriquecer sesiones con RAG solo como apoyo pedagogico.
4. Mostrar resumen claro del plan.
5. Pedir confirmacion antes de crear eventos externos.
6. Persistir snapshot.
7. Mantener materializacion y recordatorios detras de fase siguiente si aun no estan listos.

### Archivos probables

- `src/agents/support/agent.py`
- `src/agents/support/nodes/build_study_plan/node.py`
- `src/services/planning/study_planning_service.py`
- `src/agents/support/planning/formatter.py`
- `tests/test_study_planning_service.py`
- `tests/test_study_planning_persistence.py`

### Criterio de cierre

- El agente genera un plan semanal realista.
- Las sesiones respetan horario fijo y restricciones.
- El resumen incluye tecnica/metodo recomendado sin inventar fuera del RAG.
- No se crean eventos externos sin confirmacion.

## Fase 12. Materializacion, Recordatorios Y Dispatch Inicial

### Objetivo

Convertir el plan semanal en instancias fechadas y recordatorios programables.

### Estado actual

Ya existen:

- `StudyPlanMaterializationService`;
- `StudyPlanRemindersService`;
- repositorios de instancias;
- repositorios de reminder policies y dispatches;
- scripts de apoyo.

La fase debe conectarlos al flujo de producto.

### Pasos

1. Confirmar que `persist_planning_snapshot_for_update` materializa y sincroniza reminders correctamente.
2. Definir politicas default de recordatorio para MVP:
   - 60 minutos antes;
   - 10 minutos antes;
   - seguimiento 15 minutos despues;
   - sesion perdida despues del cierre.
3. Definir canal inicial:
   - `in_app` si no hay WhatsApp dispatcher listo;
   - `whatsapp` cuando el canal este listo.
4. Implementar salida conversacional clara:
   - plan guardado;
   - sesiones materializadas;
   - recordatorios activados.
5. Agregar pruebas de idempotencia.

### Archivos probables

- `src/agents/support/flows/planning/persistence_support.py`
- `src/services/planning/materialization_service.py`
- `src/services/reminders/service.py`
- `scripts/run_due_reminders.py`
- `tests/test_study_plan_materialization_service.py`
- `tests/test_reminder_policy_persistence.py`
- `tests/test_reminder_dispatch_service.py`

### Criterio de cierre

- El mismo plan no duplica instancias.
- Cambiar el plan supersede instancias anteriores.
- Los recordatorios pendientes quedan en DB.
- Las fallas de repositorio no rompen la conversacion.

## Fase 13. Ejecucion De Recordatorios Por WhatsApp

### Objetivo

Enviar recordatorios reales por WhatsApp usando la infraestructura de canal.

### Pasos

1. Definir `ReminderDispatchService` orientado a canal si no existe completo.
2. Leer dispatches vencidos.
3. Renderizar mensaje segun tipo:
   - pre-session;
   - followup;
   - missed-session.
4. Enviar via `WhatsAppChannelService`.
5. Marcar estado del dispatch:
   - enviado;
   - fallido;
   - reintentable;
   - cancelado.
6. Evitar reenvios duplicados.
7. Agregar comando/script operativo.

### Archivos probables

- `src/services/reminders/dispatcher.py`
- `src/services/channels/whatsapp_service.py`
- `scripts/run_due_reminders.py`
- `tests/test_reminder_dispatch_service.py`
- `tests/test_whatsapp_channel_service.py`

### Criterio de cierre

- Un reminder vencido genera un mensaje WhatsApp.
- El mismo dispatch no se envia dos veces.
- Fallos de WhatsApp quedan registrados.

## Fase 14. Seguimiento De Sesiones De Estudio

### Objetivo

Permitir que el estudiante confirme ejecucion de sesiones:

- iniciar;
- completar;
- omitir;
- reportar que no pudo estudiar;
- reportar avance parcial.

### Pasos

1. Definir intents:
   - `start_study_session`;
   - `complete_study_session`;
   - `skip_study_session`;
   - `report_missed_session`;
   - `provide_session_feedback`.
2. Resolver referencia de sesion por contexto:
   - ultima sesion recordada;
   - sesion proxima;
   - sesion por materia/dia.
3. Usar `StudySessionTrackingService`.
4. Actualizar estado de instancia.
5. Si una sesion queda perdida u omitida, marcar replanificacion candidata.
6. Sincronizar Microsoft To Do en fase posterior o cuando este habilitado.

### Archivos probables

- `src/services/planning/tracking_service.py`
- `src/agents/support/nodes/handle_academic_update/node.py`
- `src/services/conversation/router.py`
- `scripts/record_session_completion.py`
- `scripts/mark_missed_sessions.py`
- `tests/test_study_session_tracking_service.py`
- `tests/test_mark_missed_sessions.py`
- `tests/test_tracking_summary.py` si se crea.

### Criterio de cierre

- `Ya termine la sesion de calculo` marca la instancia correcta.
- `No pude estudiar hoy` no se pierde: genera estado para replanificar.
- El tracking no modifica horario fijo.

## Fase 15. Replanificacion Automatica Controlada

### Objetivo

Replanificar cuando cambian condiciones:

- nueva entrega;
- cambio de parcial;
- sesion perdida;
- cambio de disponibilidad;
- cambio de horario fijo;
- atraso acumulado.

### Principio

La replanificacion debe proponer antes de ejecutar cambios externos.

Patron:

```text
detectar cambio -> calcular impacto -> proponer ajuste -> confirmar -> aplicar -> persistir -> sincronizar
```

### Pasos

1. Definir `ReplanRequest` conversacional.
2. Detectar trigger desde:
   - actividad nueva;
   - tracking;
   - update de horario;
   - solicitud explicita.
3. Calcular propuesta usando servicios de planning existentes.
4. Mostrar diff corto:
   - sesiones movidas;
   - sesiones nuevas;
   - sesiones canceladas;
   - razon del cambio.
5. Pedir confirmacion.
6. Persistir nueva version del plan.
7. Superseder instancias anteriores.
8. Re-sincronizar recordatorios.
9. Reconciliar calendario si aplica.

### Archivos probables

- `src/services/planning/study_plan_sync_service.py`
- `src/services/planning/study_planning_service.py`
- `src/agents/support/flows/replanning/`
- `src/repositories/planning/`
- `migrations/0011_replan_requests_and_proposals.sql`
- `tests/test_replanning_apply_modifications.py`
- `tests/test_schedule_application_services.py`

### Criterio de cierre

- El agente no mueve eventos sin confirmacion.
- La propuesta explica el cambio.
- Se conserva trazabilidad de version anterior y nueva.
- Las instancias y recordatorios quedan consistentes.

## Fase 16. Sincronizacion De Sesiones Con Outlook Calendar

### Objetivo

Crear, mover o eliminar eventos de calendario para sesiones de estudio y actividades confirmadas.

### Diferencia frente a horario fijo

El horario fijo ya tiene sync Outlook. Esta fase cubre sesiones dinamicas del plan y actividades puntuales.

### Pasos

1. Reutilizar `OutlookCalendarSyncService`.
2. Definir payload de evento de estudio.
3. Mapear instancias/materializaciones a eventos Outlook.
4. Pedir confirmacion antes de crear/mover/eliminar.
5. Guardar external ids.
6. Reconciliar cuando el plan cambia.
7. Manejar falta de OAuth con mensaje no tecnico.

### Archivos probables

- `src/services/sync/outlook_calendar_sync_service.py`
- `src/integrations/microsoft_graph/calendar_client.py`
- `src/repositories/microsoft_graph/sync_repository.py`
- `src/agents/support/flows/planning/persistence_support.py`
- `tests/test_outlook_calendar_sync_service.py`
- `tests/test_microsoft_graph_calendar_client.py`

### Criterio de cierre

- Sesiones confirmadas se crean en Outlook.
- Replanificacion mueve o cancela eventos vinculados.
- No se duplica calendario si se reintenta.
- La ausencia de OAuth bloquea sync externo pero no destruye el plan local.

## Fase 17. Microsoft To Do Como Proyeccion Posterior

### Objetivo

Usar Microsoft To Do para tareas accionables sin hora exacta o sesiones no resueltas.

### Por que no antes

El documento rector dice que Microsoft To Do es fase posterior. Primero debe estar estable el plan, materializacion, tracking y replanificacion.

### Pasos

1. Definir que elementos van a To Do:
   - sesiones perdidas;
   - sesiones omitidas;
   - actividades desglosadas sin hora;
   - checklist de proyecto/taller.
2. Reutilizar `MicrosoftTodoSyncService`.
3. Resolver task list default.
4. Crear tareas idempotentes.
5. Borrar o completar tareas cuando ya no sean accionables.
6. Agregar resumen conversacional.

### Archivos probables

- `src/services/sync/microsoft_todo_sync_service.py`
- `src/integrations/microsoft_graph/todo_client.py`
- `src/repositories/microsoft_graph/state_repository.py`
- `tests/test_microsoft_todo_service.py`

### Criterio de cierre

- Sesiones `missed` o `skipped` generan tareas.
- Tareas se eliminan o completan cuando se resuelven.
- No se crean duplicados por reintento.

## Fase 18. Personalizacion De Metodo Aplicada A Actividades

### Objetivo

Convertir el resultado del Radar y RAG en instrucciones operativas por actividad.

### Ejemplos

- Como estudiar para un parcial teorico.
- Como abordar un taller numerico.
- Como preparar una exposicion.
- Como dividir una lectura y sintesis.

### Pasos

1. Crear servicio de metodo aplicado, no nodo con logica.
2. Entradas:
   - top tecnicas del Radar;
   - senales/debilidades;
   - materia;
   - tipo de actividad;
   - tiempo disponible;
   - urgencia.
3. Usar `StudyRecommendationService`.
4. Devolver pasos breves y accionables.
5. Integrar en:
   - plan semanal;
   - sesiones de estudio;
   - respuestas directas de recomendacion.

### Archivos probables

- `src/services/study_recommendations/service.py`
- `src/services/planning/study_planning_service.py`
- `src/agents/support/nodes/answer_study_recommendation/node.py`
- `tests/test_study_recommendation_service.py`
- `tests/test_rag_grounded_prompting.py`

### Criterio de cierre

- La recomendacion esta conectada al perfil del estudiante.
- La respuesta no inventa tecnicas fuera del corpus.
- El metodo se expresa como acciones de estudio, no como texto generico.

## Fase 19. Apoyo Academico Guiado Y Modo Socratico

### Objetivo

Ayudar al estudiante a abordar actividades sin resolverlas por completo.

### Alcance

Permitido:

- descomponer una actividad;
- hacer preguntas orientadoras;
- proponer checklist;
- sugerir estrategia de estudio;
- guiar primeros pasos.

No permitido:

- resolver quices/parciales/talleres completos;
- dar respuestas finales para copiar;
- redactar entregas finales como sustituto del estudiante.

### Pasos

1. Implementar intents:
   - `request_guided_academic_help`;
   - `enter_socratic_mode`.
2. Crear politica de limites por tipo de actividad.
3. Crear estado `interaction_mode = socratic`.
4. Pedir materia, tema y objetivo si faltan.
5. Generar primera pregunta o checklist.
6. Limitar profundidad para no convertirse en tutor generalista.
7. Registrar salida permitida.

### Archivos probables

- `src/services/conversation/scope_policy.py`
- `src/services/conversation/router.py`
- `src/services/study_recommendations/service.py`
- `src/agents/support/nodes/answer_scope_boundary/node.py` o nodo nuevo
- `tests/test_guided_academic_support.py`
- `tests/test_scope_policy.py`

### Criterio de cierre

- `Ayudame con este taller pero no me lo resuelvas` activa guia.
- `Resuelveme este quiz` recibe rechazo claro con alternativa.
- El modo socratico no pisa un bloque activo de calendario o confirmacion.

## Fase 20. Observabilidad, Auditoria Y Evaluacion Conversacional

### Objetivo

Hacer el sistema depurable antes de aumentar uso real.

### Pasos

1. Registrar decisiones del router:
   - intent;
   - confianza;
   - dominio;
   - bloque activo;
   - razon de politica.
2. Registrar payload agregado del buffer sin exponer datos sensibles en logs inseguros.
3. Agregar dataset de evaluacion conversacional:
   - onboarding fragmentado;
   - cambio de intencion;
   - fuera de alcance;
   - quiz/parcial;
   - bienestar;
   - actividades academicas;
   - replanificacion.
4. Agregar metricas:
   - intent accuracy;
   - slot extraction accuracy;
   - tasa de clarificaciones;
   - tasa de acciones confirmadas;
   - errores de sync.
5. Documentar comandos de diagnostico.

### Archivos probables

- `src/services/conversation/`
- `src/rag/evaluation/` si aplica a recomendaciones;
- `tests/test_conversation_eval_dataset.py`
- `docs/2026-04-18/checklist_pruebas_mvp_lara.md`

### Criterio de cierre

- Cada decision importante del agente se puede explicar.
- Hay pruebas de regresion para casos WhatsApp reales.
- Los fallos de integracion quedan trazables sin romper la UX.

## 5.1 Trazabilidad Explicita Contra El Documento Rector

Esta seccion deja explicito como se cubren los apartados de `docs/mvp_academic_agent_lara.md`.

El plan no copia literalmente cada politica ni cada intent dentro de una fase unica. Los distribuye por capas para mantener la arquitectura limpia:

```text
politicas y clasificacion -> services/conversation
estado y slots -> schemas/conversation + services/conversation
buffer WhatsApp -> services/channels
routing LangGraph -> agents/support/agent.py
features academicas -> services/priorities, services/planning, services/reminders
integraciones externas -> services/sync + integrations/*
```

### Alcance Del Proyecto

| Apartado del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| Proposito exacto del MVP | Mantiene agenda, planificacion, recordatorios, seguimiento, replanificacion y recomendaciones como linea central del roadmap. | Fases 0-20 |
| Lo que el agente si atiende | Se distribuye en dominios: perfil, horario, actividades, priorizacion, plan, calendario, recomendaciones y guia academica controlada. | Fases 6-19 |
| Lo que el agente no atiende | Se implementa como politica de alcance y guardrails de evaluaciones, bienestar/crisis y temas no academicos. | Fase 3, Fase 19 |
| No actuar como asistente generalista | Se cubre con `scope_policy`, clasificador de input y respuestas de rechazo/redireccion. | Fase 3 |
| No resolver quices, parciales, talleres o tareas | Se cubre como politica especial y como condicion previa del modo socratico. | Fase 3, Fase 19 |
| No acceder ni modificar servicios externos sin autorizacion | Se cubre con OAuth bloqueante, confirmaciones y `last_confirmation_payload`. | Fase 5, Fase 8, Fase 11, Fase 15, Fase 16 |

### Reglas De Router Y Prioridad De Bloques

| Apartado del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| Dominios del router: perfil, horario, actividades, priorizacion, recomendaciones, plan, calendario, apoyo guiado, fuera de alcance, bienestar y smalltalk | Se implementan como `ConversationRouteDecision`, `active_intent`, `current_domain` y router hibrido. | Fase 1, Fase 4 |
| Reglas base del router | Se implementan en `services/conversation/router.py`, separadas de `agent.py`. | Fase 4 |
| Regla general antes de todos los bloques | Se traduce a orden de decision: alcance, bloque activo, dato faltante, prioridad de intent y confirmacion. | Fase 4 |
| Prioridad entre bloques cuando compiten | Se incluye explicitamente como orden del router hibrido: riesgo, fuera de alcance, onboarding incompleto, bloque activo, confirmacion, actividades, horario, prioridades, plan, personalizacion, modo socratico y smalltalk. | Fase 4 |
| Regla de bloque activo | Se implementa con `pending_entity_payload`, `missing_fields_json`, `confirmation_pending` y `provide_missing_data`. | Fase 1, Fase 4, Fase 6, Fase 7 |
| Cuando se reactiva cada bloque | Se reparte por triggers: onboarding incompleto, cambio de horario, recalibracion de perfil, nuevas actividades, priorizacion semanal, plan, To Do y modo socratico. | Fases 4, 8-19 |
| Regla practica para no romper el flujo | Se conserva la secuencia: identidad -> tiempo -> perfil de estudio -> operacion semanal -> ejecucion. | Seccion 6 |
| Recomendacion de diseno de bloques | Se mapea a dominios: onboarding, fixed schedule, study profile, study method, activity capture, prioritization, planning, todo, calendar, socratic. | Fases 6-19 |

### Quiz, Parcial, Taller, Tarea Y Evaluaciones

| Apartado del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| Regla especial para quiz, parcial, taller, tarea, ejercicio o exposicion | Se trata como clasificacion obligatoria antes de responder. El agente debe distinguir planificar/abordar vs resolver. | Fase 3 |
| Politica especial para evaluaciones | Se implementa en `scope_policy` con rechazo claro y alternativa permitida. | Fase 3 |
| Ayuda permitida | Se cubre con planificacion, descomposicion, checklist, metodo aplicado y modo socratico. | Fase 9, Fase 18, Fase 19 |
| Ayuda no permitida | Se bloquea en politica: respuestas finales, solucion completa, texto para copiar. | Fase 3, Fase 19 |
| Modo socratico controlado | Se activa solo si hay actividad, tema, materia u objetivo concreto. | Fase 19 |

### Politica De Fuera De Alcance

| Apartado del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| Politica de manejo de solicitudes fuera de alcance | Se convierte en `scope_policy.py` y `input_classifier.py`. | Fase 3 |
| Salidas permitidas del agente | Se implementan como acciones de politica: redirigir, responder limitado, rechazar, escalar/recomendar apoyo humano. | Fase 3 |
| Arbol de decision de la politica | Se implementa como clasificacion: `in_scope`, `partially_in_scope`, `redirectable_out_of_scope`, `hard_out_of_scope`, `human_support_case`. | Fase 3 |
| Definiciones operativas por categoria | Se convierten en reglas y tests de `scope_policy`. | Fase 3 |
| Politica de tono para fuera de alcance | Se cubre en plantillas de respuesta: limite claro, alternativa permitida y siguiente paso academico. | Fase 3 |
| Bienestar/crisis | Se separa de fuera de alcance normal y no activa planificacion academica automaticamente. | Fase 3 |

### Intents Y Slots

| Apartado del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| Intents minimos | No se implementan todos de una vez. Se priorizan por riesgo y dependencia. | Fases 4, 8-19 |
| `provide_missing_data` | Se considera intent critico para WhatsApp y bloque activo. | Fase 4, Fase 6, Fase 7 |
| `confirm_action` y `reject_action` | Se conectan con `confirmation_pending` y `last_confirmation_payload`. | Fase 1, Fase 4 |
| `register_academic_activity` | Se implementa despues de estabilizar router y slots. | Fase 9 |
| `request_weekly_prioritization` y `request_weekly_plan` | Se activan despues de actividades y post-Radar. | Fase 10, Fase 11 |
| `request_replan` | Se implementa cuando tracking, plan e instancias ya existen. | Fase 15 |
| `create_calendar_event`, `update_calendar_event`, `delete_calendar_event` | Se implementan para sesiones dinamicas despues de plan, confirmacion y OAuth. | Fase 16 |
| `create_todo`, `update_todo`, `delete_todo` | Se dejan como proyeccion posterior porque el documento rector marca To Do como fase posterior. | Fase 17 |
| `request_guided_academic_help` y `enter_socratic_mode` | Se implementan despues de politica de alcance y metodo aplicado. | Fase 19 |
| Slots de perfil, horario, actividades, calendario, To Do y ayuda guiada | Se implementan progresivamente con extractores por dominio, no con un extractor universal inicial. | Fase 6, Fase 7, Fase 9, Fase 16, Fase 17, Fase 19 |
| Slots mas importantes: materia, tipo de actividad, fecha, hora, referencia, campo a actualizar, confirmacion, objetivo y tema | Se incorporan como contratos de extraccion y validacion. | Fase 6-19 |

### Estado Conversacional Minimo

| Campo del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| `active_intent` | Campo del nuevo `InteractionState`. | Fase 1 |
| `current_domain` | Campo del nuevo `InteractionState`. | Fase 1 |
| `interaction_mode` | Soporta guided, correccion, confirmacion y socratico. | Fase 1, Fase 19 |
| `pending_action` | Se usa para crear, editar, eliminar, confirmar o corregir. | Fase 1, Fase 4 |
| `pending_entity_type` | Se usa para perfil, horario, actividad, calendario, To Do o sesion. | Fase 1 |
| `pending_entity_payload` | Permite captura incremental y bloque activo. | Fase 1, Fase 6, Fase 7, Fase 9 |
| `missing_fields_json` | Permite pedir solo lo faltante. | Fase 1, Fase 6, Fase 7, Fase 9 |
| `confirmation_pending` | Requisito antes de acciones sensibles. | Fase 1, Fase 4 |
| `last_confirmation_payload` | Evita confirmar una accion distinta a la resumida. | Fase 1, Fase 8, Fase 15, Fase 16 |
| `noise_turn_count` | Soporta ruido, stickers y smalltalk contextual. | Fase 1, Fase 2, Fase 3 |
| `last_user_messages` | Conectado con buffer y trazabilidad. | Fase 1, Fase 2 |
| `aggregated_user_text` | Salida del buffer hacia router. | Fase 1, Fase 2 |
| `router_confidence` | Trazabilidad del router. | Fase 1, Fase 4, Fase 20 |
| `clarification_needed` | Controla no ejecutar cuando faltan datos. | Fase 1, Fase 4 |
| `is_waiting_for_oauth` | Bloqueo conversacional del OAuth. | Fase 1, Fase 5 |
| `is_waiting_for_verification_code` | Mantiene compatibilidad con verificacion actual. | Fase 1, Fase 5 |
| `current_step` y `current_section` | Ubican el paso exacto dentro de onboarding, horario, extras, radar o plan. | Fase 1, Fase 6, Fase 7 |

### Buffer De Mensajes, Flush Y Clasificacion De Input

| Apartado del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| Buffer como capa previa al router | Se implementa en `services/channels/message_buffer.py`. | Fase 2 |
| `BufferedMessage` | DTO del buffer. | Fase 2 |
| `MessageBuffer` | Estado temporal por conversacion/usuario. | Fase 2 |
| `AggregatedInput` | Payload final que recibe el router. | Fase 2 |
| `add_message`, `should_flush`, `flush`, `reset`, `aggregate_text` | Operaciones obligatorias del buffer. | Fase 2 |
| Flush por timeout | Configurable inicialmente in-memory. | Fase 2 |
| Flush inmediato por imagen, audio, documento o sticker | Regla del buffer. | Fase 2 |
| Flush inmediato por confirmacion clara | Regla del buffer conectada con `confirmation_pending`. | Fase 2, Fase 4 |
| Flush inmediato por comando critico | Regla para `elimina`, `borra`, `confirma`, `cancelar`, `reagenda`. | Fase 2 |
| Agregacion con saltos de linea | Se conserva para mejorar extraccion de horarios y slots. | Fase 2 |
| Normalizacion ligera | Trim, colapso de espacios, preservacion de texto util. | Fase 2 |
| No unir de mas | Confirmaciones sensibles, comandos destructivos, archivos, imagenes y cambios claros de intencion rompen agregacion. | Fase 2 |
| Almacenamiento in-memory y luego Redis | El plan empieza con in-memory y deja Redis para cuando haya concurrencia real. | Fase 2, futuro |
| Clasificacion de input util, ruido, emoji, sticker, imagen | Se cubre en `input_classifier`. | Fase 3 |

### Flujo Normal Y Reactivacion De Bloques

| Apartado del documento rector | Como lo cubre este plan | Fases |
| --- | --- | --- |
| Orden normal inicial | Se respeta: onboarding, horario fijo, perfil de estudio, prioridades, plan, ejecucion. | Seccion 6 |
| Flujo normal de uso cotidiano | Se implementa con actividades, repriorizacion, plan, calendario, tracking y replanificacion. | Fase 9-16 |
| Onboarding se reactiva si faltan datos o se actualizan | Cubierto por router y estado conversacional. | Fase 4, Fase 6 |
| Horario fijo se reactiva al inicio o cambio de semestre/rutina | Cubierto por gestion de horario fijo. | Fase 8 |
| Diagnostico se recalibra solo si aplica | Mantiene Radar como perfil base y no como flujo repetitivo. | Fase 18 |
| Priorizacion semanal se reactiva cada semana o ante cambios | Cubierto por actividades y replanificacion. | Fase 10, Fase 15 |
| Plan semanal se reactiva despues de priorizar o ante cambios | Cubierto por plan y replanificacion. | Fase 11, Fase 15 |
| To Do se activa cuando hay tareas accionables | Fase posterior por dependencia de tracking/materializacion. | Fase 17 |
| Modo socratico se activa con actividad concreta | Cubierto como modo controlado. | Fase 19 |

### Arquitectura Recomendada Del Documento Rector

| Componente recomendado | Ubicacion propuesta en este plan | Fases |
| --- | --- | --- |
| Canal WhatsApp | `integrations/whatsapp` + `services/channels` | Fase 2, Fase 13 |
| Buffer de mensajes | `services/channels/message_buffer.py` | Fase 2 |
| Clasificador de entrada | `services/conversation/input_classifier.py` o `services/channels/input_classifier.py` | Fase 3 |
| Router conversacional | `services/conversation/router.py` + adaptacion en `agent.py` | Fase 4 |
| Extractor incremental de slots | extractores por dominio en `services/*` | Fase 6, Fase 7, Fase 9 |
| Gestor de estado conversacional | `schemas/conversation.py` + `services/conversation/state_helpers.py` | Fase 1 |
| Validador de dominio | validadores existentes y nuevos en `services/*` | Fase 6-19 |
| Confirmacion / ejecucion | `confirmation_pending` + nodos/servicios por dominio | Fase 4, Fase 8, Fase 15, Fase 16 |
| Servicios DB, Outlook, To Do, RAG | Se mantienen en `services`, `repositories` e `integrations` segun reglas de arquitectura. | Fase 5, Fase 11, Fase 16, Fase 17, Fase 18 |

## 6. Secuencia Recomendada De Activacion

La secuencia mas segura es:

1. Fase 0: baseline.
2. Fase 1: estado conversacional.
3. Fase 2: buffer WhatsApp.
4. Fase 3: clasificador y politica de alcance.
5. Fase 4: router hibrido.
6. Fase 5: OAuth bloqueante.
7. Fase 6: slots incrementales de onboarding.
8. Fase 7: slots incrementales de horario.
9. Fase 8: gestion de horario fijo.
10. Fase 9: actividades academicas puntuales.
11. Fase 10: priorizacion semanal.
12. Fase 11: plan semanal.
13. Fase 12: materializacion y recordatorios.
14. Fase 13: dispatch WhatsApp.
15. Fase 14: tracking.
16. Fase 15: replanificacion.
17. Fase 16: sesiones en Outlook.
18. Fase 17: Microsoft To Do.
19. Fase 18: metodo aplicado a actividades.
20. Fase 19: modo socratico.
21. Fase 20: observabilidad y evaluacion continua.

Esta secuencia respeta la logica del producto:

```text
identidad -> autorizacion -> estructura de tiempo -> perfil de estudio
-> actividades -> prioridades -> plan -> recordatorios -> seguimiento
-> replanificacion -> integraciones externas avanzadas
```

## 7. Features Que No Deben Implementarse Antes De Tiempo

Para proteger el MVP, no conviene adelantar estas piezas:

- Microsoft To Do antes de tracking y materializacion.
- Modo socratico antes de politica de alcance.
- Replanificacion automatica sin confirmacion.
- LLM router antes de reglas deterministicas de bloque activo.
- Redis para buffer antes de validar el buffer in-memory.
- Calendar execution para sesiones dinamicas antes de persistir plan e instancias.
- Generacion de respuestas academicas largas sin guardrails de evaluaciones.

## 8. Definition Of Done Global

Una feature del MVP se considera lista cuando cumple todo esto:

1. Respeta la regla `agents -> services -> repositories/integrations -> schemas/utils`.
2. Tiene DTOs en `schemas` si cruza capas.
3. Tiene logica de negocio en `services`, no en nodos.
4. Tiene persistencia en `repositories` si necesita durabilidad.
5. Tiene tests unitarios de servicio.
6. Tiene al menos una prueba de flujo conversacional si toca el grafo.
7. Tiene manejo de error no destructivo.
8. No ejecuta acciones externas sensibles sin confirmacion.
9. No rompe el flujo actual.
10. Esta documentada en `docs`.

## 9. Riesgos Y Mitigaciones

### Riesgo 1. Convertir el router en un monolito

Mitigacion:

- separar `input_classifier`, `scope_policy`, `router` y `slot_extraction`;
- mantener tests por pieza;
- no poner prompts ni reglas grandes dentro de `agent.py`.

### Riesgo 2. Duplicar estado entre `phase` e `interaction`

Mitigacion:

- `phase` sigue decidiendo nodo LangGraph;
- `interaction` describe intencion, slots, confirmaciones y modo;
- helpers de normalizacion deben resolver defaults.

### Riesgo 3. Acciones externas sin confirmacion

Mitigacion:

- toda accion de crear, mover, eliminar o sincronizar eventos pasa por `confirmation_pending`;
- guardar `last_confirmation_payload`;
- ejecutar solo si la confirmacion apunta al mismo payload.

### Riesgo 4. Replanificacion demasiado agresiva

Mitigacion:

- primero proponer;
- mostrar diff;
- confirmar;
- versionar;
- superseder instancias en vez de borrar sin rastro.

### Riesgo 5. El agente se vuelve tutor generalista

Mitigacion:

- politica especial para evaluaciones;
- modo socratico limitado;
- RAG solo para metodos/tecnicas de estudio;
- rechazar respuestas finales para copiar.

## 10. Primer Paquete De Trabajo Recomendado

El primer paquete concreto deberia ser:

1. Fase 0: baseline.
2. Fase 1: estado conversacional.
3. Fase 2: buffer WhatsApp in-memory.
4. Fase 3: politica de alcance deterministica.

Este paquete no activa todavia post-Radar ni cambia OAuth. Su valor es construir la base que evita que las features siguientes se implementen de forma fragil.

Despues de ese paquete, el segundo paquete deberia ser:

1. Fase 4: router hibrido.
2. Fase 5: OAuth bloqueante.
3. Fase 6: slots incrementales de onboarding.

Con eso el agente queda preparado para operar de forma mas realista en WhatsApp sin perder la arquitectura limpia ya conseguida.
