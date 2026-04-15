# Informe De Orientacion: Agente Academico Vs Chatbot

Fecha: 2026-04-14

Estado: evaluacion arquitectonica y ruta recomendada

## 1. Objetivo del informe

Este informe evalua si el proyecto `academic_agentAI` esta orientado como un
agente de IA educativo o si se acerca mas a un chatbot, y propone una ruta para
continuar el desarrollo manteniendo arquitectura limpia.

El analisis se enfoca en:

- diferencia entre agente y chatbot;
- grado actual de comportamiento agentivo del proyecto;
- balance correcto entre logica deterministica, LLM y RAG;
- recomendaciones para Outlook, Microsoft To Do, CRUD de actividades,
  seguimiento, replanificacion y tutor academico;
- evolucion desde recomendacion de tecnicas hacia metodo de estudio
  personalizado.

## 2. Resumen ejecutivo

Dictamen principal:

El proyecto va bien orientado hacia un agente academico. No es solo un chatbot.
Tiene LangGraph, estado persistente, fases, servicios de negocio, persistencia,
materializacion de sesiones, recordatorios y servicios de sincronizacion. Eso
lo ubica por encima de una conversacion simple.

Pero todavia no es un agente educativo completo. Hoy es, sobre todo, un agente
operacional academico: captura datos, estructura agenda, planifica sesiones,
persiste informacion y reacciona a eventos academicos puntuales. Falta una capa
explicita de tutor academico que guie preguntas de contenido sin entregar la
respuesta directa, y falta conectar el RAG para construir metodos de estudio
personalizados fundamentados.

Lectura corta:

- Como arquitectura base, el proyecto esta bien encaminado.
- Como agente de agenda y planificacion academica, ya tiene rasgos fuertes de
  agente.
- Como tutor educativo con aprendizaje significativo, aun esta incompleto.
- Como RAG de metodos de estudio, hoy solo tiene corpus y estructura reservada;
  no hay retrieval operativo.
- La siguiente evolucion no debe ser "mas LLM en todos lados", sino agregar
  dominios claros: `study_methods`, `academic_tutoring`, `academic_scope` y RAG
  separado.

## 3. Que es un chatbot

Un chatbot es un sistema conversacional cuyo objetivo principal es responder
mensajes del usuario. Puede tener reglas, prompts, memoria basica o llamadas a
servicios, pero su unidad principal de trabajo es el turno conversacional.

Caracteristicas tipicas:

- responde a lo que el usuario escribe;
- puede seguir un flujo simple de preguntas y respuestas;
- suele depender mucho del texto generado por el modelo;
- puede no tener objetivos autonomos ni estado operacional fuerte;
- si no hay herramientas o persistencia, su efecto termina en la respuesta.

Un chatbot puede ser util, pero no necesariamente "actua" sobre el mundo del
usuario. Puede explicar, orientar o conversar, pero no siempre planifica,
ejecuta, verifica, registra ni reacciona ante cambios.

## 4. Que es un agente de IA

Un agente de IA es un sistema que persigue objetivos, mantiene estado, toma
decisiones, usa herramientas y ejecuta acciones en un entorno. Puede conversar,
pero la conversacion es solo una interfaz; el nucleo es la capacidad de decidir
y actuar.

Caracteristicas esperadas:

- tiene objetivo o mision definida;
- conserva estado de largo plazo;
- decide el siguiente paso con base en estado, reglas y contexto;
- usa herramientas o servicios externos;
- persiste resultados;
- puede planificar y replanificar;
- evalua restricciones;
- puede ejecutar acciones asincronas o por eventos;
- separa razonamiento, accion, memoria y respuesta.

En este proyecto, un agente academico no deberia limitarse a "contestar sobre
estudio". Deberia ayudar al estudiante a organizar su tiempo, construir un
metodo de estudio, acompanarlo, registrar cumplimiento, ajustar el plan y guiar
preguntas academicas de forma pedagogica.

## 5. Diferencias practicas entre chatbot y agente

| Criterio | Chatbot | Agente academico esperado |
|---|---|---|
| Centro del sistema | Mensajes | Objetivos academicos y estado |
| Memoria | Conversacional o corta | Perfil, agenda, plan, sesiones, eventos |
| Acciones | Responder | Crear, actualizar, sincronizar, recordar, replanificar |
| Decision | Prompt o reglas simples | Grafo, politicas, servicios y herramientas |
| Resultado | Texto | Cambios durables y acompanamiento |
| Riesgo | Respuestas genericas | Acciones incorrectas si no hay control |
| Arquitectura | Puede ser simple | Requiere capas, contratos y observabilidad |
| Evaluacion | Calidad de respuesta | Calidad de plan, seguimiento, aprendizaje y seguridad |

## 6. Debe ser deterministico, LLM o hibrido

Debe ser hibrido.

Para este proyecto no conviene que todo lo decida el LLM. Tampoco conviene que
todo sea deterministico, porque el usuario escribira en lenguaje natural,
mandara horarios incompletos, describira eventos con ambiguedad y hara
preguntas academicas variadas.

La regla recomendada es:

`LLM para interpretar y explicar; codigo deterministico para decidir, validar,
persistir y actuar.`

### 6.1 Lo que debe ser deterministico

- fases del grafo;
- validaciones de datos personales y consentimiento;
- parseo cerrado de respuestas de formularios;
- calculo de prioridades;
- deteccion de conflictos de agenda;
- reglas de disponibilidad;
- CRUD de actividades;
- persistencia en PostgreSQL;
- replanificacion aplicada;
- sync con Outlook y To Do;
- estado de sesiones;
- recordatorios;
- filtros de alcance academico;
- politicas de no entregar respuestas directas.

Motivo: estas partes modifican estado real del estudiante. Deben ser
testeables, reproducibles y auditables.

### 6.2 Lo que puede usar LLM

- normalizar horarios en texto libre o imagen;
- clasificar intencion cuando el texto es ambiguo;
- generar explicaciones pedagogicas;
- producir preguntas guia;
- reformular feedback;
- ensamblar una guia grounded desde RAG;
- detectar si una pregunta academica requiere metodo, tecnica, agenda o tutor.

Motivo: estas partes se benefician de lenguaje natural, pero no deben tener la
ultima palabra sobre acciones durables.

### 6.3 Lo que debe usar RAG

RAG debe usarse para conocimiento experto, no para datos operativos.

Usos correctos:

- seleccionar metodos de estudio desde el corpus;
- explicar por que una tecnica o metodo aplica;
- recuperar contraindicaciones;
- construir pasos de estudio por tipo de materia y actividad;
- fundamentar recomendaciones con evidencia y reglas del corpus;
- adaptar una sesion segun debilidades detectadas.

Usos incorrectos:

- decidir si un bloque se guarda en agenda;
- calcular disponibilidad;
- persistir tareas;
- resolver IDs de eventos;
- sustituir el estado de PostgreSQL;
- inventar calendario o actividades.

## 7. Estado actual del proyecto

### 7.1 Evidencia de comportamiento agentivo

El proyecto ya tiene varios elementos propios de agente:

- entrypoint LangGraph en `langgraph.json`;
- grafo principal en `src/agents/support/agent.py`;
- estado persistible en `src/agents/support/state.py`;
- checkpointer en `src/integrations/langgraph/checkpointer.py`;
- capas separadas en `agents`, `services`, `repositories`, `integrations`,
  `schemas`, `bootstrap` y `rag`;
- composition root en `src/bootstrap/container.py`;
- repositorios PostgreSQL e in-memory por dominio;
- onboarding, agenda, personalizacion, prioridades, plan semanal, tracking,
  materializacion y recordatorios;
- servicios Microsoft Graph para Outlook Calendar, horario fijo y To Do;
- pruebas de arquitectura en `tests/test_refactor_guardrails.py`.

Esto significa que el proyecto no depende solo de respuestas del modelo. Hay
estado, reglas, persistencia, acciones y herramientas.

### 7.2 Flujo actual observado

El flujo principal esta estructurado asi:

```text
welcome_consent
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
-> persist_schedule
-> sync_fixed_schedule
-> collect_study_profile
-> collect_study_profile_tiebreaker
-> persist_study_profile
-> collect_priorities
-> build_study_plan
-> end
```

Ademas, cuando el estado esta en `end` o `running`, hay una entrada para
actualizaciones academicas puntuales mediante `handle_academic_update`.

### 7.3 Que ya hace bien

- Captura y valida perfil.
- Controla consentimiento.
- Verifica correo institucional.
- Captura horarios academicos, laborales y extracurriculares.
- Construye borrador de agenda.
- Valida conflictos y permite correcciones.
- Persiste horario recurrente.
- Sincroniza horario fijo a Outlook si existe conexion Microsoft.
- Ejecuta Radar de estudio con scoring deterministico.
- Usa desempate cuando hay baja discriminacion del perfil.
- Calcula prioridades semanales.
- Genera plan semanal inicial.
- Persiste snapshot de prioridades y plan.
- Materializa sesiones fechadas.
- Sincroniza recordatorios.
- Tiene servicios para tracking de sesiones.
- Tiene servicios para Outlook Calendar y Microsoft To Do.
- Tiene corpus de tecnicas, metodos, matriz y frameworks en
  `knowledge_base/study_recommendations/`.

### 7.4 Que todavia falta

- RAG operativo: `src/rag` aun es una estructura reservada.
- pgvector o tablas `rag.*`: no estan implementadas.
- Servicio de metodo de estudio personalizado: hoy se detectan tecnicas, pero
  no se construye un metodo compuesto y versionado.
- Tutor academico socratico: no hay capa dedicada para preguntas academicas de
  contenido.
- Filtro robusto de "academico y solo academico" para todo mensaje libre.
- CRUD durable y unificado de actividades despues del onboarding.
- Replanificacion conectada de punta a punta al calendario, plan, instancias,
  reminders y sync externo.
- Sync de sesiones de estudio a Outlook dentro del flujo principal.
- Sync de tareas accionables a To Do dentro del flujo principal.
- Observabilidad estructurada para depurar decisiones del agente.

## 8. El proyecto es agente o chatbot

El proyecto ya es mas agente que chatbot en la parte operacional.

Razon:

- tiene grafo;
- mantiene estado;
- ejecuta fases;
- llama servicios;
- persiste informacion;
- genera plan;
- materializa instancias;
- puede sincronizar Outlook;
- procesa eventos academicos.

Sin embargo, desde la perspectiva pedagogica, todavia tiene comportamiento
parcialmente de chatbot porque no existe una capa formal que tome una pregunta
academica y la convierta en un proceso de guia, diagnostico, pistas,
verificacion y aprendizaje significativo.

Dictamen:

`Agente operacional academico en buen camino, aun no agente tutor educativo completo.`

## 9. Evaluacion de arquitectura

### 9.1 Lo positivo

La arquitectura actual es adecuada para continuar. No se recomienda rehacer el
proyecto.

Fortalezas:

- separacion top-level clara;
- regla de dependencia documentada;
- `agents` no accede directamente a repositorios ni integraciones;
- `services` concentra logica de negocio;
- `repositories` encapsula persistencia;
- `integrations` encapsula proveedores externos;
- `bootstrap` centraliza wiring;
- `schemas` contiene contratos compartidos;
- tests protegen limites arquitectonicos.

La regla actual:

```text
agents -> services -> repositories/integrations -> schemas/utils
```

es correcta para este MVP.

### 9.2 Deuda arquitectonica relevante

No es deuda bloqueante, pero si debe controlarse antes de abrir muchas features:

- `src/agents/support/agent.py` concentra mucho routing.
- `AgentState` sigue siendo contrato plano amplio, aunque ya tiene particiones.
- Parte de la logica conversacional de aplicacion vive en
  `src/agents/support/flows`.
- `persistence_support.py` en capa de agente coordina persistencia,
  materializacion y reminders.
- `study_planning_service.py` es denso y puede crecer demasiado.
- `auth_client.py` de Microsoft Graph concentra demasiadas responsabilidades.
- La configuracion esta distribuida entre varios modulos.
- RAG esta reservado, pero no tiene contratos implementados.

### 9.3 Veredicto de arquitectura

La arquitectura es buena para un MVP y permite evolucionar a agente educativo si
se agregan los dominios nuevos sin romper capas.

No conviene:

- meter RAG directamente en nodos de LangGraph;
- dejar que el LLM actualice agenda sin servicios deterministas;
- convertir `AgentState` en un repositorio informal de todo;
- crear clientes Outlook o To Do desde nodos;
- mezclar preguntas academicas, agenda y metodo de estudio en un solo nodo.

## 10. Ruta recomendada de evolucion

La evolucion recomendada es agregar capacidades por dominios, no por prompts
sueltos.

### 10.1 Dominio `academic_scope`

Objetivo: garantizar que el agente solo atienda casos academicos.

Ubicacion sugerida:

```text
src/services/academic_scope/
  classifier.py
  policy.py
  models.py
```

Responsabilidades:

- clasificar mensajes en categorias permitidas o bloqueadas;
- diferenciar agenda academica, estudio, metodos, seguimiento y preguntas de
  contenido;
- rechazar temas no academicos;
- detectar peticiones de respuesta directa a tareas, parciales o examenes;
- devolver una accion: permitir, guiar, pedir aclaracion o rechazar.

Categorias sugeridas:

- `academic_schedule`
- `study_planning`
- `study_method`
- `academic_question`
- `deadline_update`
- `session_tracking`
- `non_academic`
- `academic_integrity_risk`
- `unknown`

Regla:

El LLM puede ayudar a clasificar, pero la politica final debe ser
deterministica.

### 10.2 Dominio `academic_tutoring`

Objetivo: responder preguntas academicas guiando al estudiante, no entregando la
respuesta de una vez.

Ubicacion sugerida:

```text
src/services/academic_tutoring/
  service.py
  policy.py
  socratic_flow.py
  models.py
```

Nodo sugerido:

```text
src/agents/support/nodes/handle_academic_question/
```

Politica pedagogica:

- si el estudiante pide una respuesta directa, no entregar solucion completa;
- primero preguntar que ha intentado;
- dar una pista concreta;
- pedir que el estudiante complete el siguiente paso;
- validar la respuesta del estudiante;
- corregir errores con explicacion corta;
- solo aumentar ayuda si hay intento o bloqueo real;
- cerrar con una mini verificacion.

Flujo recomendado:

```text
detectar pregunta academica
-> clasificar tipo de ayuda
-> recuperar contexto RAG si aplica
-> preguntar diagnostico o pedir intento
-> dar pista
-> recibir respuesta
-> verificar
-> ajustar explicacion
-> registrar debilidad detectada
```

Esto convierte la pregunta academica en aprendizaje significativo, no en
respuesta inmediata.

### 10.3 Dominio `study_methods`

Objetivo: convertir tecnicas detectadas en un metodo de estudio personalizado.

Ubicacion sugerida:

```text
src/services/study_methods/
  method_selection_service.py
  method_builder.py
  adaptation_service.py
  models.py
```

Responsabilidad:

- tomar `weakness_tags`, `top_techniques`, materias, prioridades, tipo de
  evaluacion, fechas y disponibilidad;
- consultar RAG;
- seleccionar un metodo operativo del corpus o componer uno;
- producir fases de estudio;
- asociar tecnicas por fase;
- generar instrucciones para sesiones;
- guardar version del metodo recomendado.

Salida esperada:

```text
StudyMethodProfile
  method_id
  source
  confidence
  primary_weaknesses
  selected_method
  phases
  techniques_by_phase
  contraindications
  rag_sources
  adaptation_rules
```

La clave es no guardar solo:

```text
top_techniques = ["pomodoro", "active_recall", "feynman"]
```

Sino construir algo como:

```text
Metodo personalizado:
1. Preparacion de sesion con Pomodoro como contenedor.
2. Comprension inicial con Feynman o sintesis.
3. Recuperacion activa sin mirar apuntes.
4. Correccion con retroalimentacion.
5. Repaso espaciado segun fecha de evaluacion.
6. Cierre con autoevaluacion y senal de replanificacion.
```

### 10.4 RAG especializado de estudio

El corpus ya esta bien orientado. Hay tecnicas, metodos, framework de decision
y matriz de combinacion.

Ruta recomendada:

```text
src/rag/ingestion/
  study_recommendations_loader.py
  chunker.py
  manifest_builder.py

src/rag/retrieval/
  study_recommendations_retriever.py
  filters.py
  reranker.py

src/rag/prompting/
  study_method_grounding.py
```

Persistencia futura:

```text
src/repositories/rag/
  repository.py

migrations/
  00xx_rag_pgvector.sql
```

Modelo recomendado:

- `rag.documents`
- `rag.chunks`
- embeddings con `pgvector`
- metadata JSONB para filtros
- indice vectorial y busqueda textual/hibrida

Primera version pragmatica:

- loader local sobre Markdown;
- retrieval por metadata y texto;
- tests de seleccion;
- sin pgvector todavia si se quiere validar el contrato primero.

No conectar RAG directo desde `agents`. El agente debe llamar un servicio de
negocio, por ejemplo `StudyMethodRecommendationService`, y ese servicio consume
RAG.

### 10.5 CRUD de actividades y agenda

Hoy existen flujos de replanificacion y modificacion, pero conviene consolidar
un servicio canonico de mutaciones.

Ubicacion sugerida:

```text
src/services/scheduling/activity_crud_service.py
src/services/scheduling/schedule_mutation_service.py
```

Operaciones:

- crear bloque academico;
- crear bloque laboral;
- crear actividad extracurricular;
- actualizar bloque;
- eliminar bloque;
- pausar bloque;
- renovar vigencia;
- listar agenda actual;
- validar conflicto;
- persistir nuevo snapshot;
- disparar sync.

Contrato de comando:

```text
ActivityMutationCommand
  operation: add | update | delete | pause | renew
  target: academic | work | extracurricular | study_session
  selector
  payload
  requested_by
  source_message
```

Regla:

El LLM puede extraer una intencion, pero el CRUD debe resolver candidatos,
pedir confirmacion y aplicar cambios en codigo deterministico.

### 10.6 Outlook y Microsoft To Do

El proyecto ya tiene piezas utiles:

- `OutlookFixedScheduleSyncService`
- `OutlookCalendarSyncService`
- `MicrosoftTodoSyncService`
- repositorios de estado Microsoft Graph;
- OAuth client;
- scripts operativos.

Lo que falta es integrarlo como flujo de producto.

Ruta recomendada:

1. Crear fase explicita `connect_calendar` despues de persistir perfil u
   horario.
2. Preguntar si el estudiante quiere conectar Outlook.
3. Si acepta, generar URL OAuth y guardar `state`.
4. Al completar OAuth, marcar conexion como autorizada.
5. Despues de `persist_schedule`, sincronizar horario fijo.
6. Despues de `build_study_plan`, persistir snapshot, materializar instancias,
   sincronizar recordatorios y sincronizar sesiones de estudio a Outlook.
7. Cuando una sesion quede `missed` o `skipped`, proyectarla a Microsoft To Do.
8. Si se replanifica, cancelar o actualizar links externos obsoletos.

Importante:

No conviene que el nodo de LangGraph conozca detalles de Graph API. El nodo debe
llamar servicios de sync. Los servicios deben usar repositorios e integraciones.

### 10.7 Replanificacion automatica

La replanificacion deberia tener una politica clara:

Entradas:

- parcial o entrega nueva;
- sesion perdida;
- sesion completada parcialmente;
- cambio de horario fijo;
- actividad nueva;
- conflicto detectado;
- baja adherencia durante varios dias.

Salida:

- propuesta de cambio;
- impacto explicado;
- confirmacion del estudiante;
- aplicacion deterministica;
- persistencia;
- rematerializacion;
- resync de reminders, Outlook y To Do.

Pipeline recomendado:

```text
evento
-> clasificacion
-> calculo de impacto
-> propuesta de ajuste
-> confirmacion
-> aplicacion
-> persistencia
-> materializacion
-> reminders
-> sync externo
```

## 11. Como manejar preguntas academicas sin dar respuesta directa

Se recomienda una politica de tutor socratico, no una prohibicion absoluta de
explicar.

El agente puede explicar conceptos, pero debe evitar reemplazar el esfuerzo del
estudiante en tareas evaluables.

### 11.1 Si el estudiante pide "dame la respuesta"

Respuesta esperada:

```text
Puedo ayudarte a resolverlo paso a paso. Primero dime que entiendes del
enunciado o que intento hiciste. Si no sabes por donde empezar, te doy una pista
inicial.
```

### 11.2 Si el estudiante pregunta un concepto

Puede explicar brevemente y luego verificar:

```text
La idea central es...
Ahora dime con tus palabras cual seria la diferencia entre A y B.
```

### 11.3 Si el estudiante trae un ejercicio

Flujo:

1. identificar tema;
2. pedir intento o datos;
3. dar pista;
4. pedir siguiente paso;
5. verificar;
6. corregir;
7. cerrar con pregunta de transferencia.

### 11.4 Si el estudiante se equivoca

No solo corregir. Registrar senal:

- confusion conceptual;
- dependencia de relectura;
- falta de procedimiento;
- memoria debil;
- dificultad para transferir;
- baja planificacion.

Esas senales deben retroalimentar `study_methods` y prioridades.

## 12. Personalizacion: de tecnicas a metodo

El Radar actual es una buena base, porque detecta tecnicas y debilidades con
scoring reproducible.

Debilidad actual:

El resultado todavia se parece mas a "ranking de tecnicas" que a "metodo de
estudio personalizado".

Mejora recomendada:

Convertir:

```text
top_techniques + weakness_tags + prioridades + agenda + RAG
```

en:

```text
metodo personalizado + sesiones concretas + seguimiento + adaptacion
```

Ejemplo de mapeo:

| Senal | Tecnica | Rol dentro del metodo |
|---|---|---|
| procrastination/distraction | Pomodoro | Contenedor de sesion |
| passive_review_dependence | Active Recall | Verificacion principal |
| rapid_forgetting | Repeticion espaciada | Calendario de repaso |
| explanation_gap | Feynman | Comprension y explicacion |
| note_organization | Cornell | Entrada y sintesis |
| concept_connections | Mapas conceptuales | Estructura conceptual |
| exact_memory | Mnemotecnia | Apoyo puntual de memoria |
| difficulty_switching_topics | Interleaving | Transferencia y discriminacion |

La recomendacion final debe tener fases, no solo nombres de tecnicas.

## 13. Arquitectura objetivo recomendada

Estructura sugerida sin romper la base actual:

```text
src/
  agents/
    support/
      agent.py
      nodes/
        handle_academic_question/
        handle_calendar_connection/
        handle_activity_mutation/
  services/
    academic_scope/
    academic_tutoring/
    study_methods/
    scheduling/
    planning/
    priorities/
    reminders/
    sync/
  repositories/
    rag/
    scheduling/
    planning/
    microsoft_graph/
  integrations/
    ai/
    microsoft_graph/
    langgraph/
    whatsapp/
  rag/
    ingestion/
    retrieval/
    prompting/
  schemas/
```

Regla clave:

Los nodos siguen siendo delgados. Los servicios toman decisiones de negocio. Los
repositorios persisten. Las integraciones hablan con proveedores. RAG entrega
conocimiento grounded, no estado operacional.

## 14. Roadmap recomendado

### Fase 1 - Cerrar core operacional

- Unificar CRUD de actividades.
- Conectar tracking diario al grafo o a jobs operativos.
- Conectar replanificacion con persistencia, materializacion y reminders.
- Mejorar observabilidad con logs estructurados.
- Evitar que `agent.py` siga creciendo sin subrouters.

### Fase 2 - Outlook y To Do como producto

- Agregar flujo de conexion OAuth visible al estudiante.
- Sincronizar horario fijo solo si hay conexion autorizada.
- Sincronizar sesiones de estudio materializadas a Outlook.
- Proyectar sesiones perdidas o saltadas a Microsoft To Do.
- Registrar errores de sync sin romper el plan interno.

### Fase 3 - Metodo de estudio personalizado

- Crear `services/study_methods`.
- Usar Radar, prioridades, tipo de materia y fechas.
- Recuperar metodos del corpus.
- Construir `StudyMethodProfile`.
- Persistir metodo recomendado.
- Hacer que el plan semanal use fases del metodo, no solo tecnica principal.

### Fase 4 - RAG operativo

- Crear loader y chunker del corpus.
- Validar frontmatter y manifests.
- Implementar retrieval por metadata.
- Agregar embeddings y pgvector cuando el contrato este estable.
- Evaluar precision con `processed/evals`.

### Fase 5 - Tutor academico

- Crear `academic_scope`.
- Crear `academic_tutoring`.
- Implementar guia socratica.
- Registrar debilidades detectadas durante preguntas.
- Integrar esas senales con metodo y replanificacion.

### Fase 6 - Canal WhatsApp

- Mantener WhatsApp en `integrations/whatsapp`.
- No poner logica de negocio en el adaptador.
- Consumir grafo y servicios existentes.
- Cuidar prompts cortos, confirmaciones y botones/listas si el canal lo permite.

## 15. Riesgos si se continua mal

Riesgos principales:

- convertir el agente en chatbot por agregar respuestas libres sin acciones;
- meter RAG directo en nodos y romper capas;
- dejar que el LLM actualice agenda sin confirmacion;
- duplicar logica entre replanificacion, CRUD y scheduling;
- tener Outlook sincronizado pero no idempotente;
- recomendar tecnicas sueltas y no metodos;
- resolver tareas academicas directamente y afectar aprendizaje significativo;
- crecer `AgentState` hasta hacerlo inmanejable.

## 16. Recomendacion final

El proyecto no debe reorientarse desde cero. Ya tiene buena base de agente. La
mejor decision es seguirlo como agente academico hibrido:

- deterministico en acciones y estado;
- LLM para interpretacion y lenguaje;
- RAG para conocimiento experto;
- tutor socratico para preguntas academicas;
- servicios de dominio para metodo, alcance, CRUD y replanificacion;
- integraciones externas aisladas.

La proxima meta tecnica deberia ser:

`pasar de agente de agenda + tecnicas a agente academico con metodo personalizado, seguimiento y tutor guiado.`

Para lograrlo, la secuencia mas sana es:

1. cerrar CRUD/replanificacion/sync;
2. crear `study_methods`;
3. activar RAG especializado;
4. agregar `academic_tutoring`;
5. exponerlo por WhatsApp u otros canales.

Con esta ruta, el proyecto mantiene arquitectura limpia y se diferencia de un
chatbot porque no solo conversa: diagnostica, planifica, acompana, registra,
sincroniza, replanifica y guia el aprendizaje.
