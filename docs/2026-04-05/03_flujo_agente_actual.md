# Flujo Actual Real Del Agente

Fecha: 2026-04-05

Estado: auditoria tecnica en progreso

## 1. Resumen del flujo general

El agente actual funciona como un flujo conversacional por turnos montado sobre LangGraph. No procesa una conversación de forma continua hasta el final; en cada turno ejecuta nodos hasta llegar a un punto de espera o cierre, persiste el estado y se detiene. En el siguiente mensaje del usuario retoma desde la `phase` guardada.

Hechos observados:

- El runtime real entra por `langgraph.json`, que apunta a `./src/agents/support/agent.py:agent`.
- El grafo se construye en `src/agents/support/agent.py` con `StateGraph(AgentState)`.
- El estado global del flujo se concentra en `src/agents/support/state.py`.
- La lógica de pausa entre turnos depende de `_should_wait(...)` en `src/agents/support/agent.py`, que usa `awaiting_user_input`, `user_message_count`, `last_user_text` y `last_user_images`.
- Los nodos agregan respuestas al canal `messages` de `AgentState`, que usa el reducer `add_messages` en `src/agents/support/state.py`.

Qué hace hoy el agente realmente:

1. Da bienvenida y solicita consentimiento.
2. Recolecta y valida perfil básico del estudiante.
3. Verifica correo institucional.
4. Persiste al estudiante.
5. Captura horario académico y, si aplica, laboral.
6. Detecta aclaraciones pendientes, conflictos y correcciones por sección.
7. Persiste el horario confirmado.
8. Si el feature flag está activo, aplica Radar de estudio.
9. Si el feature flag está activo y faltan datos, captura prioridades académicas.
10. Genera un plan semanal inicial de estudio, lo persiste y materializa instancias.
11. Sincroniza políticas de recordatorio, pero no ejecuta el envío dentro del grafo.

Qué no hace todavía dentro del flujo principal:

- no ejecuta sincronización real con Outlook Calendar ni Microsoft To Do;
- no dispara un flujo de WhatsApp;
- no usa RAG;
- no conecta la replanificación al grafo principal;
- no procesa imágenes de horario hasta convertirlas automáticamente en texto dentro del flujo activo.

## 2. Entry points

### 2.1 Entry point del runtime

Evidencia:

- `langgraph.json`
- `src/agents/support/agent.py`
- `src/integrations/langgraph/checkpointer.py`

Observación:

- `langgraph.json` declara el grafo `support` como `./src/agents/support/agent.py:agent`.
- El checkpointer real es `./src/integrations/langgraph/checkpointer.py:create_checkpointer`.
- `main.py` no es el entrypoint del producto; es un placeholder.

### 2.2 Punto de entrada del mensaje

Evidencia:

- `src/agents/support/state.py`
- `src/agents/support/nodes/utils.py`

Observación:

- El mensaje de entrada llega al estado en `AgentState.messages`.
- Los nodos detectan nueva entrada con `detect_new_input(...)`.
- La detección usa:
  - conteo de mensajes de usuario;
  - último texto del usuario;
  - últimas imágenes del usuario.

Implicación:

- El flujo está diseñado para canales conversacionales multi-turno y soporta mensajes de texto e imágenes en el contrato de entrada, aunque el flujo activo no explota completamente el canal de imágenes.

## 3. Grafo o secuencia principal del agente

### 3.1 Grafo principal observado

Nodos registrados en `src/agents/support/agent.py`:

- `welcome_consent`
- `collect_profile`
- `send_email_verification`
- `verify_email_code`
- `confirm_profile`
- `persist_profile`
- `request_schedules`
- `parse_schedules_to_events`
- `ask_extracurricular`
- `collect_extracurricular_details`
- `build_draft_schedule`
- `render_schedule_preview`
- `validate_schedule`
- `apply_schedule_correction`
- `persist_schedule`
- `collect_study_profile`
- `collect_study_profile_tiebreaker`
- `persist_study_profile`
- `collect_priorities`
- `build_study_plan`

No registrados en el grafo principal aunque existen en código:

- `replan`
- `apply_modifications`
- nodos o rutas de sync Outlook/To Do

### 3.2 Secuencia principal inferida

```text
Usuario -> AgentState.messages
        -> welcome_consent
        -> collect_profile
        -> send_email_verification
        -> verify_email_code
        -> confirm_profile
        -> persist_profile
        -> request_schedules
        -> parse_schedules_to_events
        -> ask_extracurricular
        -> collect_extracurricular_details
        -> build_draft_schedule
        -> render_schedule_preview
        -> validate_schedule
        -> apply_schedule_correction (si hace falta)
        -> persist_schedule
        -> sync (fase lógica, no nodo real)
        -> collect_study_profile (si el módulo está habilitado)
        -> collect_study_profile_tiebreaker (si hace falta)
        -> persist_study_profile
        -> collect_priorities (si el módulo está habilitado y faltan datos)
        -> build_study_plan
        -> END
```

### 3.3 Comportamiento por turnos

Hecho clave:

- `END` no siempre significa “caso de uso terminado”.

Evidencia:

- `_should_wait(...)` en `src/agents/support/agent.py`
- múltiples routers del grafo retornan `end` cuando `awaiting_user_input` es `True` y no hay nueva entrada

Interpretación:

- el grafo usa `END` como pausa técnica entre turnos;
- el hilo se reanuda en el próximo mensaje gracias a la `phase` persistida y al checkpointer de LangGraph.

## 4. Nodos/etapas y su responsabilidad

### 4.1 Bienvenida y consentimiento

Evidencia:

- `src/agents/support/nodes/welcome_consent/node.py`

Responsabilidad real:

- envía saludo inicial;
- solicita consentimiento;
- interpreta respuestas simples de sí/no;
- corta el flujo si no hay consentimiento;
- reinicia el estado si el usuario venía de `out_of_scope` y vuelve a escribir.

### 4.2 Recolección de perfil

Evidencia:

- `src/agents/support/flows/onboarding/collect_profile.py`
- `src/agents/support/onboarding/validators.py`
- `src/agents/support/onboarding/messages.py`

Responsabilidad real:

- recolecta, en orden:
  - `full_name`
  - `student_code`
  - `age`
  - `institutional_email`
  - `semester`
  - `average_grade`
- valida formato y rango;
- detecta si el código estudiantil está fuera del alcance;
- marca `supported_program` y `academic_program`;
- dispara el subflujo de verificación de correo cuando ya existe `institutional_email`.

### 4.3 Verificación de correo institucional

Evidencia:

- `src/agents/support/nodes/send_email_verification/node.py`
- `src/agents/support/nodes/verify_email_code/node.py`
- `src/services/onboarding/service.py`
- `src/repositories/onboarding/repository.py`

Responsabilidad real:

- genera o reenvía un reto de verificación;
- persiste hash del código y expiración;
- valida formato del código;
- controla expiración e intentos máximos;
- permite reenviar.

Matiz importante:

- el sender default del onboarding es `DisabledEmailSender` en `src/services/onboarding/service.py`;
- por defecto no hay envío externo real de correo en este subflujo.

### 4.4 Confirmación y persistencia del perfil

Evidencia:

- `src/agents/support/nodes/confirm_profile/node.py`
- `src/agents/support/nodes/persist_profile/node.py`

Responsabilidad real:

- muestra resumen del perfil;
- permite corregir un campo específico;
- persiste el estudiante;
- maneja duplicados de correo y de código;
- impide persistir si `email_verified` es falso.

### 4.5 Captura de horarios académico y laboral

Evidencia:

- `src/agents/support/nodes/request_schedules/node.py`
- `src/agents/support/flows/scheduling/schedule_capture_service.py`
- `tests/test_schedule_request_flow.py`

Responsabilidad real:

- pregunta si el usuario:
  - solo estudia,
  - estudia y trabaja,
  - ninguna de las anteriores;
- almacena `occupation`;
- captura texto de horario académico y laboral;
- permite captura en varios mensajes;
- permite cerrar una sección con comandos como `seguimos`;
- controla si faltan pendientes por resolver.

### 4.6 Parseo y normalización de horarios

Evidencia:

- `src/agents/support/nodes/parse_schedules_to_events/node.py`
- `src/agents/support/flows/scheduling/schedule_parsing_service.py`
- `src/agents/support/scheduling/pipeline.py`
- `src/agents/support/scheduling/contextual_parser.py`
- `src/agents/support/scheduling/normalizer.py`

Responsabilidad real:

- parsea texto académico y laboral a bloques recurrentes;
- convierte bloques a `events`;
- detecta datos faltantes o ambiguos;
- genera `academic_pending_items` o `work_pending_items`;
- cambia a fase `extras` cuando la captura fija queda completa.

Matiz importante:

- si hay solo imagen sin texto, el flujo actual no la procesa; pide texto explícitamente.
- esto está probado en:
  - `tests/test_schedule_request_flow.py`
  - `tests/test_schedule_parsing_service.py`

### 4.7 Actividades extracurriculares

Evidencia:

- `src/agents/support/nodes/ask_extracurricular/node.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`
- `src/agents/support/nodes/collect_extracurricular_details/parsing.py`

Responsabilidad real:

- pregunta si hay actividades extracurriculares;
- captura una o varias actividades;
- soporta aclaraciones pendientes;
- mezcla esas actividades dentro de `schedule.blocks`;
- luego pasa al borrador del horario.

### 4.8 Construcción del draft y preview

Evidencia:

- `src/agents/support/flows/scheduling/schedule_draft_service.py`
- `src/agents/support/nodes/render_schedule_preview/node.py`
- `src/agents/support/scheduling/render.py`
- `src/agents/support/scheduling/schedule_renderer.py`

Responsabilidad real:

- detecta conflictos de horario;
- construye resumen textual;
- genera una imagen PNG del horario en `tmp/schedule.png`;
- adjunta texto e imagen en la respuesta del agente.

### 4.9 Revisión final y correcciones

Evidencia:

- `src/agents/support/nodes/validate_schedule/node.py`
- `src/agents/support/flows/scheduling/schedule_review_service.py`

Responsabilidad real:

- pide confirmación del horario;
- si hay conflictos, ofrece:
  - aceptarlos,
  - o corregir;
- permite corregir por sección:
  - académico,
  - laboral,
  - extracurricular;
- recalcula solo la sección modificada;
- vuelve a generar el draft si la corrección fue exitosa.

### 4.10 Persistencia del horario

Evidencia:

- `src/agents/support/nodes/persist_schedule/node.py`
- `src/services/scheduling/service.py`
- `src/repositories/scheduling/repository.py`

Responsabilidad real:

- persiste `schedule_profile`, `recurring_schedule_blocks` y `schedule_conflicts`;
- guarda versionado por estudiante;
- deja la fase en `sync`.

Hecho importante:

- `sync` no dispara un nodo de sincronización externa;
- en `_route_from_phase(...)` de `src/agents/support/agent.py`, `sync` solo decide si pasa a `collect_study_profile` o si termina.

### 4.11 Radar de estudio

Evidencia:

- `src/agents/support/nodes/collect_study_profile/node.py`
- `src/agents/support/nodes/collect_study_profile_tiebreaker/node.py`
- `src/agents/support/nodes/persist_study_profile/node.py`
- `src/services/personalization/service.py`
- `src/services/personalization/questionnaire.py`

Responsabilidad real:

- solo corre si `ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE=1`;
- hace 10 preguntas tipo Likert;
- evalúa técnicas sugeridas;
- si hay empate o baja discriminación, activa 3 preguntas extra;
- persiste el perfil de personalización;
- genera resumen textual con técnicas recomendadas.

### 4.12 Prioridades académicas

Evidencia:

- `src/agents/support/nodes/collect_priorities/node.py`
- `src/agents/support/flows/priorities/priority_capture_service.py`
- `src/agents/support/priorities/parser.py`

Responsabilidad real:

- solo corre si `ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE=1`;
- propone materias derivadas del horario;
- permite:
  - usar lo detectado,
  - enviar un catálogo manual,
  - omitir;
- normaliza prioridad, dificultad, urgencia y carga semanal.

### 4.13 Plan semanal de estudio

Evidencia:

- `src/agents/support/nodes/build_study_plan/node.py`
- `src/services/planning/study_plan_sync_service.py`
- `src/services/planning/study_planning_service.py`
- `src/agents/support/flows/planning/persistence_support.py`

Responsabilidad real:

- sincroniza materias y plan semanal;
- genera `study_plan.plan_events`;
- persiste snapshot académico;
- materializa instancias futuras;
- sincroniza políticas de reminders y dispatches durables.

## 5. Estado conversacional o estado de sesión detectado

### 5.1 Estado global

Evidencia:

- `src/agents/support/state.py`

Campos operativos más importantes:

- `phase`
- `messages`
- `awaiting_user_input`
- `user_message_count`
- `last_user_text`
- `last_user_images`
- `user_status`
- `errors`

### 5.2 Subestados de negocio

Subestados principales observados:

- `consent`
- `student_profile`
- `onboarding`
- `raw_inputs`
- `academic_pending_items`
- `work_pending_items`
- `extracurricular`
- `events`
- `schedule_preview`
- `schedule`
- `study_profile`
- `subjects`
- `priorities`
- `study_plan`
- `replan`
- `reminders`
- `constraints`

### 5.3 Estado del subflujo de horarios

Evidencia:

- `src/services/scheduling/models.py`

Campos clave de `ScheduleFlowState`:

- `blocks`
- `conflicts`
- `summary_text`
- `review_stage`
- `capture_target`
- `capture_stage`
- `correction_target`
- `pending_correction_text`
- `conflicts_accepted`
- `persisted_profile_id`
- `persistence_error`

### 5.4 Lectura funcional del estado

Interpretación:

- `phase` indica en qué etapa del flujo está el agente;
- `awaiting_user_input` indica si debe pausarse;
- `schedule.review_stage` refina el subestado dentro de la validación del horario;
- `replan` existe como subestado, pero no gobierna hoy el grafo principal.

## 6. Persistencia durante el flujo

### 6.1 Persistencia de hilo conversacional

Evidencia:

- `src/integrations/langgraph/checkpointer.py`

Qué se persiste:

- checkpoints del hilo LangGraph;
- writes pendientes por `thread_id`.

Dependencia:

- PostgreSQL.

### 6.2 Persistencia de onboarding

Evidencia:

- `src/services/onboarding/service.py`
- `src/repositories/onboarding/repository.py`

Qué se persiste:

- `email_verification_challenges`
- `students`

### 6.3 Persistencia de horarios

Evidencia:

- `src/services/scheduling/service.py`
- `src/repositories/scheduling/repository.py`

Qué se persiste:

- `schedule_profiles`
- `recurring_schedule_blocks`
- `schedule_conflicts`

### 6.4 Persistencia de personalización

Evidencia:

- `src/services/personalization/service.py`
- `src/repositories/personalization/repository.py`

Qué se persiste:

- perfil de caracterización;
- respuestas;
- scores;
- payload completo del resultado.

### 6.5 Persistencia de prioridades y plan semanal

Evidencia:

- `src/agents/support/flows/planning/persistence_support.py`
- `src/services/planning/persistence_service.py`
- `src/repositories/planning/repository.py`

Qué se persiste:

- snapshot versionado de prioridades;
- materias;
- plan semanal.

### 6.6 Persistencia derivada posterior

Evidencia:

- `src/services/planning/materialization_service.py`
- `src/services/reminders/service.py`
- `tests/test_reminder_policy_persistence.py`

Qué se persiste:

- instancias materializadas del plan;
- políticas de reminders;
- dispatches futuros.

Matiz:

- el flujo principal si deja “sembrados” reminders;
- el envío real se hace luego mediante `src/services/reminders/dispatcher.py`, fuera del grafo.

## 7. Validaciones existentes

### 7.1 Validaciones determinísticas de onboarding

Evidencia:

- `src/agents/support/onboarding/validators.py`

Validaciones observadas:

- nombre completo sin dígitos ni símbolos;
- código estudiantil numérico de 8 dígitos;
- alcance por prefijo `67`;
- edad entre 15 y 60;
- correo institucional por dominio permitido;
- semestre entre 1 y 15;
- promedio entre 0 y 100;
- código de verificación con longitud exacta.

### 7.2 Validaciones de verificación de correo

Evidencia:

- `src/services/onboarding/service.py`

Validaciones observadas:

- reto existente;
- expiración;
- intentos máximos;
- hash del código;
- duplicidad de correo antes de crear estudiante.

### 7.3 Validaciones de captura de horarios

Evidencia:

- `src/agents/support/flows/scheduling/schedule_capture_service.py`
- `src/agents/support/scheduling/contextual_parser.py`
- `src/agents/support/scheduling/normalizer.py`
- `tests/test_schedule_request_flow.py`

Validaciones observadas:

- ocupación válida;
- datos mínimos por bloque;
- detección de AM/PM ambiguo;
- detección de falta de días, horas o título;
- exigencia de texto cuando solo llega imagen;
- control de captura por secciones.

### 7.4 Validaciones de eventos y plan

Evidencia:

- `src/services/scheduling/validation.py`
- `src/services/planning/persistence_service.py`
- `src/services/planning/materialization_service.py`

Validaciones observadas:

- día normalizado;
- horas en `HH:MM`;
- inicio menor que fin;
- categorías y tipos válidos;
- eventos del plan válidos antes de persistir y materializar.

### 7.5 Validaciones de prioridades

Evidencia:

- `src/agents/support/priorities/parser.py`

Validaciones observadas:

- formato de cada línea;
- prioridad válida;
- urgencia válida;
- dificultad entre 1 y 5;
- carga semanal en minutos u horas;
- materias no repetidas.

## 8. Casos de uso actuales

### 8.1 Casos de uso implementados y conectados al grafo

- onboarding completo con consentimiento, validación y persistencia.
- verificación de correo institucional.
- detección de usuario fuera de alcance y reinicio posterior.
- captura de horario fijo académico.
- captura de horario fijo laboral.
- manejo de aclaraciones pendientes de horario.
- captura de actividades extracurriculares.
- generación de borrador semanal.
- preview visual del horario.
- aceptación de conflictos o corrección por sección.
- persistencia del horario.
- Radar de estudio opcional.
- desempate del Radar opcional.
- captura opcional de prioridades académicas.
- generación y persistencia de plan semanal inicial.
- materialización y sincronización de políticas de recordatorios.

### 8.2 Casos de uso implementados pero no conectados al grafo principal

- replanificación por modificación o eliminación de actividades:
  - `src/agents/support/flows/replanning/apply_modifications.py`
  - `src/agents/support/nodes/apply_modifications/node.py`
  - `tests/test_replanning_apply_modifications.py`

Conclusión:

- la capacidad existe a nivel de función y pruebas;
- hoy no participa del flujo conversacional principal de `agent.py`.

## 9. Funcionalidades incompletas o débiles

### 9.1 Sync externo sugerido pero no ejecutado en el flujo principal

Hecho observado:

- después de `persist_schedule`, la fase pasa a `sync`;
- no existe un nodo `sync` en `src/agents/support/agent.py`;
- los servicios `OutlookCalendarSyncService` y `MicrosoftTodoSyncService` existen, pero no están conectados al grafo principal.

Conclusión:

- la arquitectura sugiere sincronización con Microsoft;
- el flujo real hoy no la ejecuta.

### 9.2 Soporte multimodal parcial

Hecho observado:

- existen utilidades y wrappers LLM multimodales en `src/integrations/ai/_llm_impl.py`;
- el flujo activo de `schedule_parsing_service.py` exige texto cuando solo llega imagen.

Conclusión:

- el contrato soporta imágenes;
- la experiencia real todavía depende de que el usuario escriba el horario.

### 9.3 Replanificación no integrada

Hecho observado:

- `replan` está en `AgentState`;
- hay pruebas y flujo aislado de modificación;
- `agent.py` no registra ni enruta un nodo de replanificación.

Conclusión:

- es una capacidad parcial, no un caso de uso activo.

### 9.4 Envío real de onboarding por correo no operativo por defecto

Hecho observado:

- `build_onboarding_service()` usa `DisabledEmailSender`.

Conclusión:

- la verificación existe lógicamente;
- el canal externo de email para onboarding no está operativo por defecto.

### 9.5 WhatsApp y RAG no forman parte del flujo actual

Evidencia:

- `src/integrations/whatsapp/`
- `src/rag/`

Conclusión:

- son estructuras preparadas o placeholders;
- no participan en la ejecución real del agente actual.

## 10. Riesgos funcionales del flujo

- El uso de `END` como pausa técnica y como cierre funcional puede dificultar depuración si no se interpreta junto con `phase`.
- `AgentState` concentra demasiada información y hace que cualquier cambio en el flujo toque un estado transversal amplio.
- La fase `sync` puede inducir a error: su nombre sugiere integraciones externas activas, pero hoy solo es un punto de transición.
- El soporte de imágenes genera expectativa funcional, pero el flujo real las rechaza si no hay texto asociado.
- La replanificación existe en pruebas y módulos, pero no está disponible para el usuario final dentro del grafo actual.
- Parte del flujo posterior a personalización persiste snapshots, materializa instancias y sincroniza reminders de forma silenciosa; si falla, el usuario puede no percibir claramente qué parte quedó incompleta.

## 11. Qué parte del flujo es determinística, cuál depende de LLM, base de datos o integraciones

### 11.1 Lógica determinística

Principalmente determinístico:

- consentimiento y parsing sí/no;
- validación de perfil;
- verificación de formato de códigos;
- captura por etapas del horario;
- parseo contextual de horarios;
- detección de conflictos;
- corrección por sección;
- scoring del Radar;
- parser manual de prioridades;
- construcción del plan semanal;
- validación de eventos.

### 11.2 Lógica dependiente de LLM

Dependencia real, pero parcial y condicional:

- `src/agents/support/scheduling/normalizer.py`
  - `llm_normalize_schedule(...)`
  - `llm_extract_schedule_blocks(...)`
- `src/agents/support/nodes/collect_extracurricular_details/parsing.py`
  - `llm_normalize_extracurricular_items(...)`

Lectura:

- el flujo no es LLM-first;
- primero intenta parseo determinístico y heurístico;
- el LLM entra como apoyo o fallback.

### 11.3 Lógica dependiente de base de datos

Dependencia fuerte:

- checkpointer de LangGraph;
- onboarding;
- horarios;
- personalización;
- priorities/study_plan snapshot;
- materialización del plan;
- reminders.

### 11.4 Lógica dependiente de integraciones externas

Dependencia externa hoy en el flujo principal:

- AI provider Azure/OpenAI, solo si el normalizador híbrido necesita fallback y hay credenciales.

Dependencias externas fuera del flujo principal:

- Microsoft Graph para email reminders;
- Outlook Calendar sync;
- Microsoft To Do sync.

## 12. Tabla resumida de nodos y responsabilidades

| Nodo / función | Propósito | Entrada principal | Salida típica | Dependencias clave |
| --- | --- | --- | --- | --- |
| `welcome_consent` | Saludo, consentimiento, reinicio tras `out_of_scope` | `messages`, `consent`, `user_status` | `phase=profile` o `phase=end` o espera | `nodes/utils.py` |
| `collect_profile` | Captura perfil base | texto usuario, `student_profile`, `onboarding` | `phase=profile_confirm` o verificación | `onboarding/validators.py` |
| `send_email_verification` | Genera y prepara envío del código | `institutional_email` | `phase=email_verification` | `OnboardingService` |
| `verify_email_code` | Verifica código o reenvío | código usuario | `phase=profile` o sigue verificando | `OnboardingService` |
| `confirm_profile` | Confirma o reabre un campo | respuesta sí/no o campo | `phase=profile_persist` o `phase=profile` | prompts onboarding |
| `persist_profile` | Persiste estudiante | `student_profile` validado | `phase=schedules` | `OnboardingService`, PostgreSQL |
| `request_schedules` | Captura ocupación y texto del horario | ocupación, texto usuario | `phase=schedules` o parseo | `schedule_capture_service.py` |
| `parse_schedules_to_events` | Normaliza horarios a bloques/eventos | `raw_inputs` | `phase=extras` o aclaraciones | parser contextual + normalizer híbrido |
| `ask_extracurricular` | Pregunta si hay extras | sí/no usuario | `phase=extras` o `phase=draft` | parser sí/no |
| `collect_extracurricular_details` | Captura extras y pendientes | texto actividad | `phase=extras` o `phase=draft` | parseo determinístico + fallback LLM |
| `build_draft_schedule` | Consolida draft y detecta conflictos | `schedule.blocks` | `phase=validate` | conflicto + summary |
| `render_schedule_preview` | Genera resumen e imagen | `schedule.blocks` | mensaje con texto + imagen | renderer local PNG |
| `validate_schedule` | Revisión final, aceptar o corregir | respuesta del usuario | `phase=schedule_persist` o corrección | `schedule_review_service.py` |
| `apply_schedule_correction` | Recalcula una sección | payload de corrección | `phase=draft` o vuelve a validar | parser sección / raw_inputs |
| `persist_schedule` | Persiste horario | bloques confirmados | `phase=sync` | `ScheduleService`, PostgreSQL |
| `collect_study_profile` | Hace preguntas del Radar | respuestas 0..3 | sigue cuestionario o pasa a persistencia | `PersonalizationService` |
| `collect_study_profile_tiebreaker` | Hace 3 preguntas extra | respuestas 1..4 | `phase=study_profile_persist` | `PersonalizationService` |
| `persist_study_profile` | Persiste Radar y prepara planning | `study_profile` completo | `phase=priorities` o `end` | personalización + planning persistence |
| `collect_priorities` | Captura materias y prioridades | materias manuales o comando | `phase=study_plan` o `end` | parser prioridades |
| `build_study_plan` | Genera plan semanal final | `subjects`, `study_profile`, `schedule` | `phase=end` | `study_plan_sync_service.py` |

## 13. Conclusión de esta fase

El flujo real actual del agente sí está implementado y es más amplio de lo que parece a simple vista. Hoy no es solamente “onboarding + horario”; realmente ya cubre un pipeline completo de:

- onboarding validado,
- horario fijo confirmado,
- personalización opcional,
- prioridades opcionales,
- plan semanal inicial,
- persistencia de snapshots,
- materialización,
- y siembra de reminders.

Sin embargo, todavía no debe interpretarse como un agente académico integral completamente conectado. Varias capacidades existen solo como arquitectura preparada o como implementación parcial:

- sync Microsoft;
- envío operativo de onboarding por correo;
- RAG;
- WhatsApp;
- replanificación dentro del grafo principal;
- explotación real del canal multimodal.

La mejor lectura técnica de esta fase es:

`el agente actual ya resuelve bien el onboarding y la planificación base de un MVP, pero aún no expone en el runtime principal todas las capacidades que la arquitectura ya insinúa`
