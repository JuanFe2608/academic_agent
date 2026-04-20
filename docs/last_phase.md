# Informe técnico: evolución del agente académico híbrido **Lara**

**Proyecto:** Implementación de un agente de IA académico para el apoyo a estudiantes en la gestión del tiempo, la planificación de actividades y la recomendación de métodos de estudio personalizados.

**Contexto del MVP:**

- Población objetivo: estudiantes de Ingeniería de Sistemas y Computación.
- Canales e integraciones objetivo: WhatsApp, ecosistema Microsoft/Outlook, lista de tareas tipo To-Do.
- Stack base reportado: Python, LangGraph, PostgreSQL, pgvector, Azure OpenAI API.
- Alcance funcional: onboarding, captura de horarios, gestión de actividades, recomendación de técnicas de estudio, método de estudio personalizado y planificación semanal.

---

## 1. Resumen ejecutivo

El estado actual del proyecto muestra una base funcional valiosa: onboarding del estudiante, captura de horarios, base relacional, bloque de preguntas de personalización y una lógica progresiva para recomendar técnicas de estudio. Sin embargo, la siguiente evolución del producto no debe continuar por la ruta de un agente excesivamente determinístico basado en menús rígidos del tipo “elige opción 1, 2 o 3”, porque eso reduce naturalidad, escalabilidad conversacional y percepción de inteligencia.

La propuesta correcta para el cierre del MVP es convertir a Lara en un **agente híbrido**. Esto significa combinar:

- **LLM** para comprender intenciones en texto libre, generar preguntas de aclaración y producir respuestas naturales.
- **Regex + reglas de validación** para extraer fechas, horas, nombres de actividades, materias y recurrencias con seguridad operativa.
- **Lógica determinística** para validar, confirmar, persistir y ejecutar acciones sensibles.
- **RAG** para aterrizar técnicas y métodos de estudio de forma personalizada y contextualizada.
- **Herramientas externas** para calendario y lista de tareas.

El resultado buscado no es un agente “que entienda cualquier cosa”, sino un agente que **entienda texto libre dentro del dominio académico del proyecto**, pida solo los datos faltantes y confirme lo entendido antes de actuar. Esa definición es realista, implementable y defendible en un proyecto de grado.

---

## 2. Objetivo de esta evolución

### 2.1 Objetivo funcional

Lograr que, después del bloque de preguntas de personalización y recomendación de técnicas, Lara pueda pasar a un modo operativo conversacional en el que el estudiante escriba solicitudes naturales como:

- “Quiero agregar esta actividad extracurricular al calendario”.
- “Muéstrame qué tengo esta semana”.
- “Quiero cambiar la hora de mi grupo de estudio”.
- “Elimina la asesoría del viernes”.
- “Ayúdame a organizar mi semana porque tengo parcial de cálculo y una entrega de programación”.
- “¿Cómo aplico mi método de estudio para esta exposición?”.

Y que el agente responda adecuadamente sin depender de menús rígidos, pero manteniendo control y confirmación antes de ejecutar cambios.

### 2.2 Objetivo técnico

Rediseñar la experiencia conversacional y la arquitectura funcional para soportar:

1. Entendimiento de intención en lenguaje natural.
2. Extracción híbrida de entidades.
3. Recolección de datos faltantes mediante diálogo guiado.
4. Confirmación previa a acciones sensibles.
5. Ejecución sobre calendario, To-Do y motor de planificación.
6. Recomendación contextual de estudio con apoyo de RAG.

---

## 3. Diagnóstico del enfoque actual

A partir del contexto entregado durante el proyecto, se identifican los siguientes patrones en la lógica actual:

### 3.1 Fortalezas observadas

- Ya existe una noción de flujo por etapas: onboarding, caracterización, recomendación y posterior organización.
- Ya existe una estructura de captura de datos del estudiante y horarios.
- Ya existe una intención de usar un scoring determinístico para técnicas de estudio.
- Ya existe una base de datos relacional y una orientación hacia una base vectorial con pgvector.
- Ya existe preocupación por validación, persistencia y calidad del flujo.

### 3.2 Debilidades observadas

- Exceso de interacción basada en listas numeradas y respuestas cerradas.
- Fricción conversacional al pedir datos con redacciones poco naturales.
- Tendencia a mezclar descubrimiento de intención con ejecución directa.
- Riesgo de sobre-determinismo en la priorización semanal.
- Potencial acoplamiento fuerte entre el texto del agente y la lógica de negocio.
- Posible falta de separación clara entre: intención, extracción, validación, confirmación y acción.

### 3.3 Problema central a corregir

El agente corre el riesgo de sentirse como un formulario conversacional, cuando el objetivo del MVP debería ser que se perciba como un asistente académico operativo. El cambio no consiste en abandonar la lógica determinística, sino en **encapsularla detrás de una capa conversacional flexible**.

---

## 4. Visión objetivo del agente Lara

Lara debe ser un agente académico híbrido con cinco capacidades principales:

1. **Gestión de calendario académico**
   - Crear actividades.
   - Consultar agenda.
   - Modificar eventos.
   - Eliminar eventos.

2. **Gestión de tareas tipo To-Do**
   - Crear tareas.
   - Ver pendientes.
   - Marcar completadas.
   - Modificar o eliminar tareas.

3. **Planificación semanal**
   - Priorizar materias según señales reales.
   - Detectar carga y urgencia.
   - Proponer bloques de estudio realistas.
   - Evitar cruces.

4. **Método de estudio personalizado**
   - Explicar técnicas detectadas.
   - Recomendar cómo aplicarlas a parciales, entregas, exposiciones o repasos.
   - Adaptarse a la carga semanal.

5. **Acompañamiento conversacional guiado**
   - Entender texto libre dentro del dominio.
   - Pedir solo lo que falta.
   - Confirmar antes de actuar.

---

## 5. Principio de diseño: agente híbrido y no puramente libre

### 5.1 Qué significa “híbrido” en este proyecto

En este contexto, híbrido no significa solo usar más de una tecnología. Significa que el sistema se divide en capas complementarias:

#### Capa A. Comprensión de intención

El LLM identifica qué quiere hacer el estudiante:

- crear evento
- consultar calendario
- modificar evento
- eliminar evento
- crear tarea
- consultar tareas
- actualizar tarea
- eliminar tarea
- generar plan semanal
- pedir explicación de técnica o método
- pedir ayuda general
- salir o volver al menú principal

#### Capa B. Extracción de entidades

A partir del texto libre, el sistema detecta:

- nombre de actividad o tarea
- materia asociada
- fecha o día
- hora de inicio
- hora de fin
- recurrencia
- prioridad
- urgencia
- tipo de actividad
- contexto académico

Esta extracción debe apoyarse en:

- regex para horas, rangos, fechas, am/pm, días de la semana, listas.
- normalizadores de texto.
- LLM para completar interpretación semántica cuando el texto sea flexible.

#### Capa C. Validación y completitud

La lógica de negocio decide:

- si la información es suficiente,
- qué datos faltan,
- qué formatos son válidos,
- si hay ambigüedad,
- si existen cruces.

#### Capa D. Confirmación

Antes de crear, actualizar o eliminar, el agente resume lo entendido y solicita confirmación. Si algo esta mal el estudiante lo puede cambiar diciendo que esta mal especificamente y colocandolo tal cual

#### Capa E. Ejecución

Solo después de confirmar, se llama la herramienta externa o se persiste el cambio.

### 5.2 Por qué este enfoque es el adecuado

- Mantiene naturalidad conversacional.
- Reduce errores operativos.
- Permite crecer por dominios.
- Facilita pruebas funcionales.
- Hace la arquitectura explicable y defendible.

---

## 6. Experiencia conversacional objetivo

### 6.1 Mensaje de transición después del bloque de preguntas del radar y del mensaje del agente sobre lo que identifico.

Este mensaje marca el paso entre caracterización y operación del agente.

```text
✨ Hola, {nombre}. Soy Lara, tu asistente académica.

Ya entiendo mejor cómo estudias y eso me ayudará a acompañarte de una forma más útil y personalizada. 📚

Desde ahora puedo apoyarte en cuatro frentes principales:

📅 organizar tus actividades académicas en el calendario
📝 registrar y dar seguimiento a tus tareas pendientes
🧠 proponerte un método de estudio según tu perfil
🗓️ ayudarte a planear tu semana para que no se te acumulen entregas, parciales o repasos

Puedes escribirme de forma natural, por ejemplo:
- “Agrega grupo de estudio de cálculo el miércoles de 4 a 6 pm”
- “Muéstrame lo que tengo esta semana”
- “Quiero cambiar la hora de una actividad”
- “Ayúdame a organizar mi semana”
- “¿Cómo aplico mi técnica de estudio para un parcial?”

Cuando haga falta información, te preguntaré solo lo necesario.
Antes de crear, editar o eliminar algo, siempre te mostraré lo que entendí para que lo confirmes. ✅

Cuando quieras volver al menú principal, escribe: salir.
```

### 6.2 Criterio de estilo conversacional

Los mensajes del agente deben ser:

- amables,
- breves,
- claros,
- operativos,
- con ejemplos,
- sin saturar al estudiante con demasiadas instrucciones a la vez.

---

## 7. Flujos conversacionales óptimos por dominio

- EL AGENTE DEBE SER CAPAZ DE PODER IDENTIFICAR MUY BIEN LA PETICION DEL ESTUDIANTE, USAR TECNICAS DE PROMPTING PARA LIMITAR AL AGENTE A SU PROPOSITO EL CUAL ES GESTIONAR EL TIEMPO DE LOS ESTUDIANTES, PLANIFICAR METODOS DE ESTUDIO Y RECOMENDAR METODOS DE ESTUDIO PERSONALIZADOS. EL AGENTE DEBE SABER CUANDO ACTIVAR CADA BLOQUE

- EL AGENTE DEBE SER NETAMENTE PARA TEMAS ACADEMICOS, ESTE AGENDE PUEDE RESPONDER PREGUNTAS SOLO ACADEMICAS Y EL ESTUDIANTE LE PIDE QUE HAGA UNA ACTIVIDAD, UN QUIZ O UN PARCIAL EL AGENTE NO LE DEBE RESPONDER LA PREGUNTA DIRECTAMENTE, DEBE LLEVARLO A UN PENSAMIENTO SOCRATICO Y SIEMPRE SE DEBE ES APOYAR AL ESTUDIANTE EN LA GESTION DEL TIEMPO, PLANIFICACION DE METODOS DE ESTUDIO Y RECOMENDACION DE METODOS DE ESTUDIO PERSONALIZADOS, ESE DEBE SER SU ENFOQUE.

## 7.1 Flujo: crear actividad en calendario

### Activaciones posibles

- “Quiero agregar esta actividad extracurricular al calendario”.
- “Agrega grupo de estudio de cálculo el miércoles de 4 a 6”.
- “Registra asesoría de física mañana”.

### Datos mínimos necesarios

- nombre
- fecha o día
- hora inicio
- hora fin

### Datos opcionales

- recurrencia
- descripción
- materia
- ubicación

### Mensaje inicial del agente

```text
¡Claro! 📅 Vamos a registrarla.

Cuéntame estos datos de la actividad:
1. Nombre
2. Día o fecha
3. Hora de inicio
4. Hora de finalización

Si se repite cada semana, también dímelo.
Ejemplo: “Natación, martes y jueves, 5:00 pm a 6:30 pm, semanal”.
```

En caso de que se repita semanalmente el estudiante debe poner una fecha tentativa para que no se agente para siempre esta actividad.

### Cuando faltan campos

```text
Ya entendí el nombre y el día 👍
Solo me falta la hora de inicio y la hora de finalización para poder registrarla.
```

### Confirmación previa

```text
Esto fue lo que entendí 👇

📌 Actividad: {titulo}
📅 Día/fecha: {fecha_o_dias}
🕒 Hora: {hora_inicio} - {hora_fin}
🔁 Repetición: {frecuencia}

¿Está bien así para agregarla al calendario?
Responde: sí o no.
```

### Regla operativa

No crear el evento hasta que exista confirmación explícita.

---

## 7.2 Flujo: consultar calendario

### Activaciones posibles

- “Muéstrame qué tengo esta semana”.
- “¿Qué actividades tengo mañana?”.
- “Quiero visualizar mi calendario”.

### Respuesta de salida recomendada

Mostrar por días, no como bloque denso.

```text
🗓️ Esta es tu agenda de la semana

**Lunes**
✅ Cálculo — 7:00 am a 9:00 am
✅ Trabajo de grado — 3:00 pm a 5:00 pm

**Martes**
✅ Programación — 8:00 am a 10:00 am
✅ Grupo de estudio — 4:00 pm a 6:00 pm

**Miércoles**
Sin actividades registradas

¿Quieres que te ayude a organizar tiempos de estudio en los espacios libres?
```

### Posibles extensiones

- detectar huecos libres,
- detectar cruces,
- sugerir reorganización,
- ofrecer creación de bloques de estudio.

---

## 7.3 Flujo: modificar actividad en calendario

### Activaciones posibles

- “Quiero modificar una actividad”.
- “Cámbiale la hora al estudio de física”.
- “La asesoría del jueves pasó para el viernes”.

### Paso 1. Identificación de la actividad

```text
Claro, te ayudo a modificarla ✏️

Dime cuál actividad quieres cambiar.
Puedes escribirme el nombre, el día o ambos.
Ejemplo: “grupo de estudio de cálculo del miércoles”.
```

### Paso 2. Desambiguación si hay varias coincidencias

```text
Encontré varias actividades parecidas. ¿Cuál de estas quieres modificar? 👇

1. Grupo de estudio de cálculo — miércoles 4:00 pm
2. Grupo de estudio de cálculo — viernes 2:00 pm

Responde con el número.
```

### Paso 3. Campo a modificar

```text
Perfecto. ¿Qué quieres cambiar de esa actividad?

Puedes decirme:
- nombre
- día o fecha
- hora
- duración
- repetición
```

### Paso 4. Confirmación

```text
Esto fue lo que entendí 👇

Actividad a modificar: {actividad_original}
Nuevo dato: {cambio_solicitado}

Así quedaría:
📌 {titulo_final}
📅 {fecha_final}
🕒 {hora_final}
🔁 {frecuencia_final}

¿La actualizo así?
Responde: sí o no.
```

---

## 7.4 Flujo: eliminar actividad en calendario

### Mensaje inicial

```text
Claro 🗑️ Dime qué actividad quieres eliminar.

Puedes escribirme el nombre, el día o ambos.
Ejemplo: “la tutoría de física del jueves”.
```

### Confirmación

```text
Entendí que quieres eliminar esta actividad:

📌 {titulo}
📅 {fecha}
🕒 {hora}

¿Está bien eliminarla?
Responde: sí o no.
```

---

## 7.5 Flujo: crear tarea en To-Do

### Activaciones posibles

- “Agrega una tarea pendiente”.
- “Anota que debo entregar taller de programación el jueves”.
- “Registra leer el capítulo 3 para el viernes”.

### Mensaje inicial

```text
Perfecto 📝 Vamos a registrarla como tarea pendiente.

Dime:
1. Nombre de la tarea
2. Materia o contexto
3. Fecha límite
4. Prioridad, si ya la conoces

Ejemplo: “Entrega de informe, Programación, viernes, alta”.
```

### Confirmación

```text
Esto fue lo que entendí 👇

📝 Tarea: {titulo}
📚 Materia: {materia}
📅 Fecha límite: {fecha_limite}
🚨 Prioridad: {prioridad}

¿La guardo así en tu lista de pendientes?
Responde: sí o no.
```

---

## 7.6 Flujo: consultar tareas

```text
Estas son tus tareas pendientes 📝

🔴 Alta prioridad
❌ Entrega taller de cálculo — jueves
❌ Preparar exposición de redes — viernes

🟡 Prioridad media
❌ Leer capítulo de bases de datos — sábado

🟢 Completadas
✅ Resumen de física
✅ Quiz corto de inglés

¿Quieres que te ayude a convertir algunas de estas tareas en bloques de estudio en tu calendario?
```

---

## 7.7 Flujo: marcar tarea completada

```text
¡Buen trabajo! ✅

Marqué como completada:
{tarea}

¿Quieres que ahora revise cuáles pendientes siguen siendo más urgentes esta semana?
```

---

## 7.8 Flujo: plan semanal

El plan semanal debe tambien ser guardado en el calendario de outlook.

### Activaciones posibles

- “Ayúdame a organizar mi semana”.
- “Tengo muchas entregas y un parcial”.
- “Quiero planear la semana”.

### Mensaje inicial

```text
🗓️ Ya revisé tu semana y puedo ayudarte a organizarla mejor.

Voy a tener en cuenta:
- tus horarios fijos
- tus actividades registradas
- tus tareas pendientes
- las materias con más carga o urgencia
- tu forma de estudio

Con eso te propondré un plan semanal realista, sin cruzarte actividades y dejando espacios útiles para estudiar.
```

### Formato sugerido de salida

```text
📚 Plan semanal sugerido

**Enfoques principales de la semana**
- Cálculo: evaluación próxima
- Programación: entrega pendiente
- Física: repaso preventivo

**Bloques recomendados**
- Martes 4:00 pm a 6:00 pm → estudio de Cálculo
- Miércoles 6:00 pm a 7:30 pm → avance de entrega de Programación
- Jueves 5:00 pm a 6:00 pm → repaso de Física
- Sábado 9:00 am a 11:00 am → cierre de pendientes

**Recomendaciones**
✅ Prioriza primero lo que tiene fecha cercana
✅ No dejes una sola materia concentrar toda tu semana
✅ Usa bloques cortos cuando tengas días muy cargados
✅ Reserva un espacio final para revisar pendientes

¿Quieres que convierta este plan en actividades concretas dentro de tu calendario?
```

---

## 7.9 Flujo: método de estudio personalizado

### Activaciones posibles

- “Tengo parcial, ¿cómo puedo estudiar?”.
- “¿Cómo puedo prepararme para esta exposición?”.

### Mensaje base

```text
🧠 Según tu perfil, una de las estrategias que mejor encaja contigo es: {tecnica_o_metodo}.

Puedo ayudarte a aplicarla de forma práctica según lo que tengas esta semana. Por ejemplo:
- para un parcial
- para una entrega
- para una exposición
- para una sesión de repaso corto

Solo dime qué actividad quieres preparar y te propongo cómo usar tu método paso a paso.
```

### Respuesta aplicada

```text
Para tu parcial de {materia}, te propongo aplicar {tecnica} así:

1. Define el tema exacto que vas a repasar
2. Divide el estudio en bloques cortos y concentrados
3. Haz recuperación activa sin mirar apuntes
4. Cierra con una verificación breve de errores
5. Programa un repaso posterior antes de la evaluación

Si quieres, también puedo convertir esto en bloques concretos dentro de tu semana.
```

---

## 8. Checklist semanal de organización

La idea del checklist semanal es correcta, pero debe evitar sentirse como una encuesta repetitiva. Debe ser breve, útil y orientado a acción.

### Propuesta recomendada

1. Revisar entregas y evaluaciones próximas.
2. Registrar tareas pendientes que aún no estén en To-Do.
3. Definir qué materias requieren más atención esta semana.
4. Reservar bloques de estudio realistas.
5. Revisar cambios o nuevas cargas académicas.

### Mensaje base

```text
📌 Revisión semanal de organización

Vamos a comprobar rápidamente cómo va tu semana:

❌ Revisar entregas, quices o parciales próximos
❌ Registrar tareas pendientes que aún no estén anotadas
❌ Definir cuáles materias necesitan más atención esta semana
❌ Separar bloques de estudio en horarios reales disponibles
❌ Revisar si hubo cambios o nuevas cargas académicas

A medida que avancemos, te iré marcando cada punto como completado ✅
```

### Mensaje dinámico

```text
📌 Estado de tu organización semanal

✅ Ya revisaste tus próximas entregas
✅ Ya registraste tus tareas pendientes
❌ Aún falta definir las materias que requieren más atención esta semana
❌ Aún falta separar bloques de estudio en tu calendario
❌ Aún falta revisar si hubo cambios en tus actividades

Vamos paso a paso. Empecemos por las materias que están más sensibles esta semana 🎯
```

---

## 9. Priorización semanal sin rigidez excesiva

### 9.1 Problema del enfoque anterior

Un sistema que obliga cada semana a marcar materias de forma muy rígida se vuelve repetitivo, poco natural y puede llevar a que el estudiante ignore materias no priorizadas.

### 9.2 Solución propuesta

La prioridad semanal debe ser **sugerida por el sistema** y ajustada por el estudiante en lenguaje natural.

### 9.3 Señales para calcular prioridad sugerida

- entregas cercanas,
- parciales o quices próximos,
- tareas acumuladas,
- tiempo sin dedicar estudio a una materia,
- dificultad percibida,
- urgencia declarada,
- peso académico,
- riesgo de rezago.

### 9.4 Mensaje recomendado

```text
Con base en tus actividades de esta semana, estas materias parecen necesitar más atención 🎯

1. Cálculo — tienes evaluación próxima
2. Programación — tienes una entrega pendiente
3. Física — conviene repasar para no atrasarte

Si quieres, puedes ajustarlas escribiéndome algo como:
- “Quiero darle más prioridad a Física”
- “Programación ya está controlada”
- “Esta semana necesito enfocarme en Cálculo y Trabajo de Grado”
```

### 9.5 Beneficio

La decisión final no es totalmente automática ni totalmente manual. Es híbrida, explicable y flexible.

---

## 10. Lógica funcional del agente

## 10.1 Patrón general de operación

Para cualquier acción sensible, el agente debe seguir este ciclo:

1. Detectar intención.
2. Extraer entidades.
3. Validar completitud.
4. Pedir datos faltantes.
5. Confirmar lo entendido.
6. Ejecutar.
7. Reportar resultado.

## 10.2 Ejemplo abstracto

**Entrada del estudiante:** “Agrega entrenamiento de fútbol los martes a las 5”.

**Interpretación:**

- intención: crear evento
- título: entrenamiento de fútbol
- día: martes
- hora inicio: 5:00 pm (inferencia si aplica)
- hora fin: faltante
- recurrencia: posiblemente semanal

**Respuesta del agente:**
“Ya entendí el nombre, el día y la hora de inicio. Solo me falta la hora de finalización para poder registrarlo.”

## 10.3 Regla de seguridad

Ninguna operación de escritura debe ejecutarse si:

- hay ambigüedad en la entidad objetivo,
- faltan campos mínimos,
- no existe confirmación explícita,
- se detecta un conflicto no resuelto.

---

## 11. Datos necesarios para implementar esta evolución

## 11.1 Datos del estudiante

- student_id
- full_name
- university_email
- age
- semester
- gpa
- current_status (estudia / estudia y trabaja)
- timezone
- preferred_calendar_provider
- preferred_task_provider

## 11.2 Datos del perfil de estudio

- questionnaire_session_id
- question_id
- selected_option_id
- score_by_dimension
- detected_top_techniques
- inferred_strengths
- inferred_weaknesses
- confidence_score
- last_profile_update_at

## 11.3 Datos académicos estructurados

- subjects
- subject_priority_base
- subject_difficulty
- weekly_minutes_target
- urgency_status
- active_term

## 11.4 Datos operativos del calendario

- activity_id
- student_id
- provider (google / microsoft / local)
- provider_event_id
- title
- category (academic / work / extracurricular / study_block / exam / delivery)
- subject_id nullable
- start_at
- end_at
- recurrence_rule nullable
- location nullable
- description nullable
- created_by_agent boolean
- status
- original_user_text
- parsed_payload
- confirmation_status

## 11.5 Datos operativos de tareas

- task_id
- student_id
- provider
- provider_task_id
- title
- subject_id nullable
- due_at nullable
- priority
- status (pending / in_progress / completed / cancelled)
- completion_at nullable
- notes nullable
- created_by_agent boolean
- original_user_text
- parsed_payload
- confirmation_status

## 11.6 Datos de planificación semanal

- weekly_plan_id
- student_id
- week_start_date
- week_end_date
- generated_at
- summary
- priority_subjects_snapshot
- workload_snapshot
- recommended_blocks_json
- recommendations_json
- accepted_by_user boolean
- version

## 11.7 Datos conversacionales y de estado del agente

- conversation_id
- student_id
- current_domain
- active_intent
- pending_action
- pending_entity_type
- pending_entity_payload
- missing_fields_json
- last_confirmation_payload
- last_system_decision
- state_version
- updated_at

---

## 12. Implementación de base de datos relacional

A continuación se plantea una expansión natural del modelo relacional existente. No implica necesariamente reemplazar el esquema actual; puede implementarse por fases y adaptarse a la nomenclatura del proyecto.

## 12.1 Entidades principales recomendadas

### students

Información base del estudiante.

Campos sugeridos:

- id
- student_code
- full_name
- university_email
- age
- semester
- gpa
- status_type
- timezone
- created_at
- updated_at

### study_profiles

Resultado consolidado del bloque de personalización.

Campos:

- id
- student_id
- profile_version
- top_technique_1
- top_technique_2
- top_technique_3
- strengths_json
- weaknesses_json
- scoring_json
- confidence_score
- created_at

### study_profile_answers

Persistencia de respuestas individuales.

Campos:

- id
- study_profile_id
- question_id
- option_id
- answer_text nullable
- score_vector_json
- created_at

### subjects

Materias del estudiante.

Campos:

- id
- student_id
- name
- base_priority
- difficulty_level
- target_minutes_per_week
- active boolean
- created_at
- updated_at

### calendar_activities

Eventos académicos y operativos.

Campos:

- id
- student_id
- external_provider
- external_event_id
- title
- activity_type
- subject_id nullable
- start_at
- end_at
- recurrence_rule nullable
- location nullable
- description nullable
- origin_source
- original_user_text nullable
- parsed_payload_json nullable
- confirmation_status
- is_deleted boolean
- created_at
- updated_at

### tasks

Tareas pendientes.

Campos:

- id
- student_id
- external_provider
- external_task_id
- title
- subject_id nullable
- due_at nullable
- priority_level
- status
- notes nullable
- original_user_text nullable
- parsed_payload_json nullable
- confirmation_status
- created_at
- updated_at

### weekly_priority_snapshots

Foto semanal de prioridades sugeridas.

Campos:

- id
- student_id
- week_start_date
- priorities_json
- rationale_json
- user_adjustments_json nullable
- created_at

### weekly_plans

Plan semanal generado.

Campos:

- id
- student_id
- week_start_date
- summary_text
- blocks_json
- recommendations_json
- linked_subjects_json
- linked_tasks_json
- linked_events_json
- accepted boolean
- created_at
- updated_at

### agent_conversation_state

Estado operativo del flujo conversacional.

Campos:

- id
- student_id
- conversation_channel
- current_domain
- active_intent
- pending_action
- pending_entity_json
- missing_fields_json
- last_confirmation_json
- status
- updated_at

### rag_documents

Catálogo de documentos indexados.

Campos:

- id
- source_type
- title
- topic
- technique_name nullable
- method_name nullable
- audience
- metadata_json
- created_at

### rag_chunks

Fragmentos embebidos.

Campos:

- id
- document_id
- chunk_index
- chunk_text
- embedding vector
- metadata_json
- created_at

---

## 12.2 Principios del modelo relacional

- Separar perfil de estudio de operación diaria.
- Guardar texto original del usuario cuando sea útil para auditoría y trazabilidad.
- Guardar payload parseado cuando se use extracción híbrida.
- Persistir snapshots semanales para evaluación posterior.
- Mantener un estado conversacional mínimo pero explícito.

---

## 13. Implementación de RAG

## 13.1 Rol del RAG en el proyecto

El RAG no debe encargarse de crear o editar eventos. Tampoco debe tomar decisiones operativas del calendario. Su función es enriquecer las respuestas relacionadas con:

- explicación de técnicas de estudio,
- explicación de métodos de estudio,
- aplicación práctica de técnicas según actividad académica,
- sugerencias de organización compatibles con el perfil del estudiante,
- justificación breve de recomendaciones.
- Si no tiene informacion academica sobre algo que el estudiente quiere saber que se apoye en el LLM

## 13.2 Qué información debe vivir en el RAG

### Fuentes ideales

- documentos estructurados sobre técnicas de estudio,
- métodos de estudio,
- aplicación de técnicas por tipo de evaluación,
- recomendaciones pedagógicas basadas en evidencia,
- guías expertas curadas por el proyecto.

### Ejemplos de temas útiles

- active recall,
- spaced repetition,
- pomodoro,
- interleaving,
- elaboración,
- mapas conceptuales,
- estudio por casos,
- preparación para exposiciones,
- lectura activa,
- gestión de carga académica.

## 13.3 Qué no debe meter el RAG

- lógica de agenda,
- validaciones de fecha y hora,
- decisiones de negocio del CRUD,
- estado conversacional efímero.

## 13.4 Estructura recomendada del documento base

Cada técnica o método debería tener una plantilla uniforme:

- nombre,
- definición,
- para qué sirve,
- cuándo conviene,
- cuándo no conviene,
- señales del perfil que la favorecen,
- pasos de aplicación,
- errores comunes,
- ejemplo aplicado a parcial,
- ejemplo aplicado a entrega,
- ejemplo aplicado a exposición,
- variantes según tiempo disponible.

## 13.5 Proceso RAG recomendado

1. Curar contenido.
2. Normalizar formato.
3. Dividir en chunks semánticos.
4. Embeder en pgvector.
5. Recuperar por técnica, actividad y contexto académico.
6. Construir prompt de respuesta contextual.

## 13.6 Ejemplo de uso del RAG

**Pregunta del estudiante:** “¿Cómo aplico mi técnica para un parcial de cálculo?”

**Entradas del generador:**

- perfil del estudiante,
- top técnicas detectadas,
- materia objetivo,
- tipo de actividad: parcial,
- fragmentos relevantes del RAG.

**Salida esperada:**
Una guía corta, accionable y alineada al perfil.

## 13.7 Integración ideal entre perfil y RAG

El sistema no debe preguntar al RAG “qué técnica tiene el estudiante”. Eso ya debe venir de la capa determinística de caracterización. El RAG debe responder: **cómo aplicar esa técnica o método al caso actual**.

---

## 14. Revisión de la arquitectura actual del agente

### 14.1 Evaluación general

Con base en el recorrido previo del proyecto, la arquitectura parece estar evolucionando desde un flujo centrado en formularios conversacionales hacia una arquitectura por dominios del agente. Ese movimiento es correcto y debe consolidarse.

### 14.2 Riesgos típicos detectables en este punto

Aunque en este turno no se inspeccionó el repositorio directamente, por el comportamiento descrito del sistema los riesgos más probables son:

1. **Acoplamiento entre mensajes y lógica**
   El texto del agente puede estar incrustado junto con decisiones de negocio, dificultando mantenimiento.

2. **Estado conversacional disperso**
   La información de qué falta, qué se entendió y qué está pendiente puede estar repartida entre nodos o helpers.

3. **Nodos demasiado grandes**
   Un mismo nodo podría estar clasificando intención, parseando datos, validando y respondiendo.

4. **Baja separación entre dominios**
   Calendario, tareas, priorización y estudio podrían compartir flujo sin contratos claros.

5. **Persistencia insuficiente de contexto operativo**
   Si el agente no guarda claramente la acción pendiente y los campos faltantes, los diálogos se vuelven frágiles.

### 14.3 Arquitectura objetivo recomendada

Se recomienda una arquitectura modular por capacidades, manteniendo el proyecto como **monolito modular**. No es necesario migrar a microservicios para este MVP.

#### Módulos sugeridos

- `conversation_router`
- `intent_classifier`
- `entity_extractor`
- `validation_service`
- `confirmation_service`
- `calendar_domain`
- `todo_domain`
- `weekly_planning_domain`
- `study_profile_domain`
- `study_method_domain`
- `rag_retrieval`
- `state_store`
- `integration_google`
- `integration_microsoft`

### 14.4 Flujo de arquitectura recomendado

1. Entrada del mensaje.
2. Router conversacional.
3. Clasificación de intención.
4. Extracción de entidades.
5. Validación.
6. Generación de pregunta faltante o confirmación.
7. Ejecución de herramienta.
8. Persistencia.
9. Respuesta final.

### 14.5 Recomendación estructural principal

El proyecto debe mantenerse como un sistema centralizado, pero con fronteras claras entre:

- orquestación conversacional,
- lógica de dominio,
- acceso a datos,
- integraciones,
- RAG.

---

## 15. Diseño lógico sugerido del agente

Ya existen unos intents deberia revisarse si sirven los que ya estan implementados par aver si pueden servir o se tiene que agregar alguno.

## 15.1 Intents mínimos del MVP

- `create_calendar_activity`
- `view_calendar`
- `update_calendar_activity`
- `delete_calendar_activity`
- `create_task`
- `view_tasks`
- `update_task`
- `complete_task`
- `delete_task`
- `generate_weekly_plan`
- `explain_study_method`
- `apply_study_technique`
- `weekly_review`
- `help`
- `exit`

## 15.2 Slots por intención

Ya existen unos slots deberia revisarse si sirven los que ya estan implementados par aver si pueden servir o se tiene que agregar alguno.

### create_calendar_activity

- title
- date_or_days
- start_time
- end_time
- recurrence optional
- subject optional

### update_calendar_activity

- target_activity_identifier
- field_to_update
- new_value

### create_task

- title
- subject optional
- due_date optional
- priority optional

### generate_weekly_plan

- week_reference optional
- focus_subjects optional
- urgency_signals optional

### apply_study_technique

- target_subject
- target_activity_type
- target_date optional

## 15.3 Estado conversacional mínimo

- domain
- intent
- candidate_entities
- resolved_entity
- missing_fields
- confirmation_pending
- last_user_goal
- tool_execution_pending

---

## 16. Reglas de implementación del entendimiento híbrido

## 16.1 Qué debe resolver el LLM

- intención,
- reformulación natural,
- pregunta de aclaración,
- desambiguación semántica,
- generación del plan semanal,
- aplicación explicada del método de estudio.

## 16.2 Qué debe resolver regex/parsers

- días de la semana,
- fechas absolutas,
- fechas relativas,
- horarios,
- rangos de hora,
- patrones de recurrencia frecuentes,
- listas de materias cuando vengan enumeradas.

## 16.3 Qué debe resolver la lógica determinística

- campos mínimos requeridos,
- normalización de datos,
- detección de conflictos,
- decisión de si ejecutar o seguir preguntando,
- confirmación previa,
- persistencia,
- scoring del perfil,
- priorización semanal base.

---

## 17. Planificación semanal: lógica recomendada

## 17.1 Entradas necesarias

- horario fijo académico,
- horario laboral si existe,
- actividades extracurriculares,
- eventos actuales del calendario,
- tareas pendientes,
- fechas de entregas y parciales,
- materias activas,
- dificultad por materia,
- minutos objetivo por semana,
- técnica o método recomendado,
- urgencia declarada por el estudiante.

## 17.2 Proceso sugerido

1. Consolidar agenda fija.
2. Insertar eventos ya registrados.
3. Analizar tareas y evaluaciones próximas.
4. Calcular prioridades sugeridas.
5. Detectar huecos reales.
6. Proponer bloques realistas.
7. Aplicar reglas de equilibrio para no abandonar materias no críticas.
8. Generar resumen y recomendaciones.
9. Preguntar si desea convertir el plan en eventos reales.

## 17.3 Reglas de equilibrio académico

- No dedicar toda la semana a una sola materia salvo urgencia extrema.
- Mantener al menos un bloque de mantenimiento para materias activas relevantes.
- Priorizar fecha cercana, pero sin destruir sostenibilidad semanal.
- Ajustar intensidad según carga y disponibilidad.

---

## 18. Métricas de evaluación recomendadas

Para la fase final del proyecto conviene medir no solo si “funciona”, sino cómo funciona.

### 18.1 Métricas de entendimiento

- accuracy de clasificación de intención,
- tasa de extracción correcta de fecha/hora,
- tasa de identificación correcta de entidad objetivo,
- número promedio de repreguntas por tarea.

### 18.2 Métricas operativas

- porcentaje de acciones ejecutadas correctamente,
- porcentaje de errores evitados por confirmación,
- tasa de conflictos detectados,
- tiempo conversacional hasta completar una acción.

### 18.3 Métricas de usabilidad

- satisfacción subjetiva del estudiante,
- percepción de claridad del agente,
- percepción de utilidad del plan semanal,
- percepción de personalización del método de estudio.

### 18.4 Métricas del componente RAG

- relevancia percibida de recomendaciones,
- grounding con técnica detectada,
- utilidad práctica de la explicación,
- consistencia con el perfil del estudiante.

---

## 19. Plan de implementación por fases

## Fase 0. Auditoría y preparación

### Objetivo

Preparar el sistema actual para evolucionar sin romper lo existente.

### Tareas

- documentar arquitectura actual,
- mapear nodos, servicios y repositorios,
- identificar ownership de estado,
- identificar mensajes actuales del flujo,
- detectar duplicación o acoplamiento fuerte,
- listar intents ya existentes.

### Entregables

- mapa del flujo actual,
- inventario de módulos,
- lista de refactors mínimos previos.

---

## Fase 1. Capa de entendimiento híbrido

### Objetivo

Permitir que el estudiante escriba solicitudes libres dentro del dominio.

### Tareas

- crear catálogo de intents,
- implementar classifier de intención,
- definir contratos de salida estructurada,
- crear extractor híbrido de entidades,
- implementar normalizadores de fecha y hora,
- definir estado conversacional mínimo.

### Entregables

- servicio de intención,
- servicio de extracción,
- esquema de payload normalizado,
- pruebas de ejemplos reales.

---

## Fase 2. Calendario conversacional

### Objetivo

Implementar CRUD conversacional de calendario con confirmación.

### Tareas

- crear flujo create/view/update/delete,
- manejar desambiguación,
- guardar confirmaciones,
- conectar con proveedor de calendario,
- persistir eventos y metadatos operativos.

### Entregables

- flujos completos de calendario,
- mensajes optimizados,
- pruebas funcionales sobre casos ambiguos.

---

## Fase 3. To-Do conversacional

### Objetivo

Replicar el patrón híbrido para pendientes.

### Tareas

- crear flujos create/view/update/complete/delete,
- modelar prioridades y estados,
- conectar proveedor de tareas o tabla local,
- integrar con agenda y priorización.

### Entregables

- dominio To-Do operativo,
- vista de tareas por prioridad y estado,
- pruebas funcionales.

---

## Fase 4. Priorización semanal híbrida

### Objetivo

Transformar la priorización rígida en una priorización sugerida y ajustable.

### Tareas

- definir señales de prioridad,
- crear motor base de scoring semanal,
- generar snapshot semanal,
- producir mensaje de priorización sugerida,
- permitir ajuste libre por el estudiante.

### Entregables

- servicio de prioridad semanal,
- mensaje conversacional,
- persistencia de ajustes del usuario.

---

## Fase 5. Generador de plan semanal

### Objetivo

Producir un plan realista y accionable.

### Tareas

- consolidar agenda fija y eventos,
- cruzar con tareas y fechas límite,
- detectar espacios disponibles,
- generar bloques propuestos,
- producir resumen y recomendaciones,
- ofrecer convertir bloques a calendario.

### Entregables

- motor de planificación semanal,
- formato de salida estándar,
- aceptación o rechazo del plan por el usuario.

---

## Fase 6. Integración RAG para método de estudio

- EL RAG YA ESTA IMPLEMENTADO.

---

## Fase 7. Observabilidad, pruebas y cierre

### Objetivo

Validar el MVP con criterios claros.

### Tareas

- crear suite de casos conversacionales,
- medir clasificación de intención,
- medir calidad de extracción,
- evaluar ejecución correcta,
- evaluar utilidad percibida,
- documentar resultados para sustentación.

### Entregables

- matriz de pruebas,
- métricas finales,
- informe de validación.

---

## 20. Orden recomendado de implementación práctica

Si el tiempo es limitado, se recomienda este orden:

1. intención + extracción híbrida,
2. CRUD de calendario,
3. CRUD de tareas,
4. priorización semanal híbrida,
5. plan semanal,
6. integración RAG,
7. métricas y cierre.

Este orden maximiza valor visible del producto y reduce riesgo.

---

## 21. Riesgos de implementación y mitigación

### Riesgo 1. El LLM interpreta mal una acción sensible

**Mitigación:** confirmación obligatoria antes de ejecutar.

### Riesgo 2. Exceso de preguntas al usuario

**Mitigación:** preguntar solo por campos faltantes mínimos.

### Riesgo 3. Ambigüedad al modificar o eliminar

**Mitigación:** desambiguación por lista cuando haya múltiples coincidencias.

### Riesgo 4. Plan semanal poco realista

**Mitigación:** usar agenda real, carga disponible y reglas de equilibrio.

### Riesgo 5. RAG demasiado teórico

**Mitigación:** estructurar corpus con ejemplos aplicados a parciales, entregas y exposiciones.

### Riesgo 6. Mezcla de responsabilidades en el código

**Mitigación:** separar router, extractor, validación, dominio y persistencia.

---

## 22. Recomendaciones finales de arquitectura

1. Mantener el proyecto como **monolito modular**.
2. Separar claramente flujo conversacional y lógica de dominio.
3. Persistir estado conversacional mínimo, no solo mensajes.
4. Tratar calendario y To-Do como dominios hermanos, no como un solo bloque.
5. Mantener el scoring de perfil como componente determinístico.
6. Usar RAG para aplicación del método, no para decidir la técnica detectada.
7. Hacer que toda acción operativa pase por confirmación.
8. Diseñar el sistema para ser agnóstico al modelo LLM.

---

## 23. Conclusión

Sí es posible convertir Lara en el agente académico que plantea el proyecto, siempre que se evite el extremo de dos enfoques incorrectos:

- un sistema puramente rígido basado en menús y opciones numeradas,
- o un sistema puramente libre sin control, validación ni confirmación.

La solución correcta es un **agente híbrido**, donde el LLM aporta comprensión y naturalidad, mientras la lógica determinística protege consistencia, seguridad y trazabilidad. Bajo esta arquitectura, Lara puede:

- entender solicitudes en lenguaje natural,
- gestionar calendario y tareas,
- priorizar materias semana a semana,
- generar planes de estudio realistas,
- y recomendar la aplicación práctica de técnicas y métodos personalizados.

Esa evolución está alineada con el objetivo general del proyecto y constituye un cierre de MVP sólido, medible y defendible.

---

## 24. Próximos pasos inmediatos sugeridos

1. documentar el flujo actual del agente,
2. definir catálogo de intents y slots,
3. diseñar el estado conversacional mínimo,
4. implementar primero el flujo híbrido de calendario,
5. replicar el patrón en To-Do,
6. luego construir la priorización y el plan semanal,
7. por último integrar RAG para la explicación aplicada del método de estudio.

---

## 25. Nota de alcance de este informe

Este informe consolida y aterriza la solución objetivo del agente con base en el contexto funcional y arquitectónico compartido en el proyecto. La sección de revisión de arquitectura actual se formula como una evaluación técnica orientada por los flujos y decisiones ya discutidos; para convertirla en una auditoría de código de nivel repositorio debe complementarse con inspección directa de módulos, nodos, servicios, repositorios, entidades y prompts en el código fuente.
