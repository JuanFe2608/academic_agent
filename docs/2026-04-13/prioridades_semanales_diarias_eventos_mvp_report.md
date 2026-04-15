# MVP de prioridades semanales, acompañamiento diario y actualizaciones por eventos

Fecha: 2026-04-13

## Objetivo

Rediseñar el bloque posterior a personalización/recomendación para separar tres ritmos de operación:

- capa semanal: snapshot confirmado de prioridades por materia;
- capa diaria: acompañamiento y cumplimiento sin rehacer el cuestionario semanal;
- capa por eventos: reacción puntual ante parciales, entregas, sesiones no realizadas o tareas completadas.

La implementación se hizo sobre el flujo existente del agente y no crea una arquitectura paralela.

## Alcance implementado

### Flujo semanal

Se reemplazó la captura pesada basada en:

```text
Materia | prioridad | dificultad | urgencia | carga semanal
```

por una captura guiada y más apta para WhatsApp:

1. Preguntar si desea actualizar prioridades de la semana.
2. Pedir top 3 de materias importantes con números, por ejemplo `3,1,2`.
3. Preguntar materia por materia si tiene quiz, parcial, entrega, exposición o actividad próxima.
4. Aceptar respuestas naturales como `parcial viernes`, `entrega lunes` o `no`.
5. Pedir materias difíciles de la semana.
6. Calcular prioridad con una función determinística.
7. Mostrar resumen por prioridad alta, media y baja.
8. Confirmar o editar antes de recalcular el plan semanal.

El flujo sigue usando el nodo `collect_priorities`, pero la lógica quedó delegada al servicio de captura semanal.

Archivos principales:

- `src/agents/support/flows/priorities/priority_capture_service.py`
- `src/agents/support/priorities/formatter.py`
- `src/services/priorities/weekly_priority_service.py`
- `src/schemas/planning.py`

### Parser y scoring

Se agregó parsing estructurado en capa de servicio para:

- `3,2,1`
- `parcial viernes` al preguntar por una materia concreta
- `ninguna`
- `usar horario`
- `omitir`
- entradas inválidas o duplicadas
- detalles como `2 parcial viernes`, `4 entrega jueves`, `1 quiz mañana`

La nueva función de prioridad usa componentes separados:

```text
priority_score =
  0.40 * importancia_semanal +
  0.30 * urgencia_por_fecha +
  0.15 * dificultad_percibida +
  0.15 * carga_semanal
```

El score se mapea a:

- `alta`: `>= 0.70`
- `media`: `>= 0.40`
- `baja`: resto

La urgencia ahora puede expirar por fecha: si `urgency_due_at` ya pasó, deja de sumar.

### Flujo diario

Se agregó un servicio determinístico para acompañamiento diario sin conectar todavía un scheduler o WhatsApp real:

- construye un enfoque diario desde instancias del plan del día;
- usa la técnica principal del perfil de estudio;
- interpreta cumplimiento con respuestas como `completado`, `a medias 50%`, `no pude estudiar hoy`;
- marca señal de replanificación ligera cuando hay bajo cumplimiento.

Archivo principal:

- `src/services/planning/daily_accompaniment_service.py`

### Flujo por eventos

Se agregó un nodo fino para mensajes académicos puntuales cuando el agente ya está en `end` o `running`.

Ejemplos soportados:

- `Tengo parcial de cálculo el viernes`
- `Me pusieron una entrega para mañana`
- `No pude estudiar hoy`
- `Ya terminé esta tarea`

Comportamiento:

- detecta si el mensaje parece actualización académica;
- clasifica el evento;
- intenta resolver materia, tipo y fecha;
- recalcula solo la materia afectada;
- marca señal de replanificación si el impacto lo amerita;
- pide aclaración si falta materia, fecha o instancia concreta.

Archivos principales:

- `src/agents/support/nodes/handle_academic_update/node.py`
- `src/agents/support/agent.py`
- `src/services/priorities/weekly_priority_service.py`

### Persistencia y base de datos

Se reutilizan las tablas ya existentes:

- `study_priority_profiles`
- `study_priority_subjects`
- `study_plan_profiles`
- `study_plan_events`
- `study_plan_event_instances`
- `study_session_checkins`

Además se agregó una migración incremental:

- `migrations/0014_weekly_priority_snapshot_metadata.sql`

Campos nuevos principales:

- `study_priority_profiles.week_start`
- `study_priority_profiles.week_end`
- `study_priority_profiles.snapshot_kind`
- `study_priority_profiles.confirmed_at`
- `study_priority_profiles.update_reason`
- `study_priority_subjects.importance_rank_selected_by_student`
- `study_priority_subjects.perceived_difficulty`
- `study_priority_subjects.urgency_type`
- `study_priority_subjects.urgency_due_at`
- `study_priority_subjects.computed_priority_score`
- `study_priority_subjects.priority_source`
- `study_priority_subjects.is_priority_confirmed`
- `study_priority_subjects.updated_from_flow_at`

No se creó tabla nueva para ejecución de bloques porque ya existe la combinación:

- `study_plan_event_instances`
- `study_session_checkins`

## Compatibilidad

Se mantiene compatibilidad con el formato legacy `Materia | prioridad | dificultad | urgencia | carga semanal` si llega una respuesta de ese tipo, pero el prompt nuevo ya no lo pide.

También se mantiene el flujo existente:

```text
persist_study_profile -> collect_priorities -> build_study_plan -> end
```

La mejora no cambia el entrypoint de LangGraph ni el nombre público del grafo.

## Lógica que se sigue

### Entrada al bloque semanal

El agente entra a `collect_priorities` después de `persist_study_profile` cuando el módulo de prioridades está activo y falta un snapshot semanal confirmado. La condición ya no depende de pedir urgencia manual por materia; ahora busca una base semanal confirmada con carga y prioridad estructurada.

Lógica:

1. Se cargan materias desde el estado o desde el horario fijo.
2. Se calcula la semana activa con `week_start` y `week_end`.
3. Se inicializa `PrioritiesState.capture_stage = ask_update`.
4. Se pregunta si el estudiante quiere actualizar prioridades.

Opciones visibles:

- `Sí, actualizarlas`
- `Después`

Si el estudiante responde `Después`, se reutiliza la base detectada y se pasa a `study_plan`.
Si responde `Sí, actualizarlas`, inicia la captura guiada.
`usar horario` se mantiene como alias interno de compatibilidad para la misma ruta de `Después`.
`omitir` se mantiene como escape técnico: termina con `status = skipped`, pero no se muestra como opción principal.

### Captura semanal por etapas

La captura semanal avanza con `capture_stage`:

```text
ask_update
ask_top3
ask_urgent_subjects
ask_difficult_subjects
confirm_summary
```

Reglas:

1. `ask_top3`: pide ranking de importancia semanal con números, por ejemplo `3,1,2`.
2. `ask_urgent_subjects`: recorre las materias detectadas y pregunta por cada una si tiene evaluación, entrega o actividad próxima; acepta respuestas naturales o `no`.
3. `ask_difficult_subjects`: pide 2 o 3 materias difíciles; acepta números o `ninguna`.
4. `confirm_summary`: muestra prioridad alta/media/baja y espera `confirmar` o `editar`.

`ask_urgency_details` queda solo como compatibilidad para estados persistidos del flujo anterior.

Solo cuando el usuario confirma, el estado pasa a `phase = study_plan`.

### Cálculo de prioridad

El cálculo no depende de texto libre por materia. Primero se estructura la información y luego se calcula:

```text
priority_score =
  0.40 * importancia_semanal +
  0.30 * urgencia_por_fecha +
  0.15 * dificultad_percibida +
  0.15 * carga_semanal
```

La importancia viene del ranking semanal del estudiante.
La urgencia viene del tipo de evento y de `urgency_due_at`.
La dificultad viene de la selección semanal de materias difíciles.
La carga semanal viene de la carga inferida o previamente capturada.

Mapeo:

- `alta`: score mayor o igual a `0.70`
- `media`: score mayor o igual a `0.40`
- `baja`: resto

Si una urgencia ya venció, deja de sumar al score.
Si una urgencia está muy cerca, puede elevar la prioridad aunque no sea top 1 del ranking.

### Persistencia del snapshot

Cuando el snapshot se confirma o se actualiza por evento:

1. Se reemplaza el snapshot vigente en `study_priority_profiles`.
2. Se marcan snapshots anteriores como `superseded`.
3. Se escriben materias en `study_priority_subjects`.
4. Se guardan `week_start`, `week_end`, `snapshot_kind`, `importance_rank_selected_by_student`, `urgency_type`, `urgency_due_at`, `computed_priority_score` y `is_priority_confirmed`.
5. Se recalcula el plan semanal usando el servicio de planificación existente.

### Lógica diaria

El flujo diario no entra a `collect_priorities`.

Lógica:

1. Se leen instancias del plan del día.
2. Se toma la técnica principal del perfil de estudio.
3. Se construye un mensaje corto de enfoque diario.
4. Al cierre de un bloque, se interpreta la respuesta:
   - `completado` -> cumplimiento 100%.
   - `a medias` -> cumplimiento parcial, por defecto 50% o el porcentaje indicado.
   - `no pude` -> bloque omitido y señal de replanificación ligera.
5. Si hay bajo cumplimiento, se marca señal para ajuste, pero no se rehace el cuestionario semanal.

### Lógica por eventos

Cuando el agente está en `end` o `running`, revisa si el nuevo mensaje parece una actualización académica.

Ejemplos:

- `Tengo parcial de cálculo el viernes`
- `Me pusieron una entrega para mañana`
- `No pude estudiar hoy`
- `Ya terminé esta tarea`

Lógica:

1. Detectar intención académica.
2. Clasificar tipo: evaluación/entrega, sesión no realizada o tarea completada.
3. Resolver materia por número o por nombre.
4. Resolver fecha relativa, por ejemplo `mañana` o `viernes`.
5. Recalcular solo la materia afectada.
6. Si la prioridad resultante es alta, enrutar a `study_plan` para ajuste del plan.
7. Si faltan datos, pedir aclaración concreta.

Este flujo actualiza urgencia y prioridad sin volver a ejecutar todo el cuestionario semanal.

## Tests y verificación

Se agregaron o actualizaron pruebas en:

- `tests/test_weekly_priority_service.py`
- `tests/test_priorities_flow.py`
- `tests/test_academic_update_flow.py`
- `tests/test_study_planning_persistence.py`

Casos cubiertos:

- ranking válido top 3;
- selección de materias difíciles;
- respuesta `ninguna`;
- respuesta `usar horario`;
- respuesta visible `Después`;
- respuesta `omitir`;
- urgencia natural por materia, por ejemplo `parcial viernes`;
- inputs inválidos o duplicados;
- cálculo de prioridad;
- expiración de urgencia por fecha;
- snapshot semanal;
- lógica diaria sin rehacer el flujo semanal;
- actualización por evento;
- persistencia de campos nuevos;
- compatibilidad con el formato legacy.

Comandos ejecutados:

```bash
python3 -m compileall src
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_priorities_flow.py tests/test_weekly_priority_service.py
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_study_planning_persistence.py tests/test_academic_update_flow.py tests/test_subject_prioritization_service.py
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest
git diff --check
```

Resultado:

```text
python3 -m compileall src: ok
tests/test_priorities_flow.py + tests/test_weekly_priority_service.py: 12 passed
tests/test_study_planning_persistence.py + tests/test_academic_update_flow.py + tests/test_subject_prioritization_service.py: 8 passed
suite completa: 313 passed, 1 failed por fecha de recurrencia Outlook fuera del bloque de prioridades
git diff --check sin hallazgos
```

## Pendiente por terminar

### Operativo

- Aplicar la migración `migrations/0014_weekly_priority_snapshot_metadata.sql` en la base PostgreSQL real.
- Validar manualmente en BD que los snapshots semanales escriben `week_start`, `week_end`, `urgency_due_at` y `computed_priority_score`.

### Producto

- Conectar el servicio diario a un scheduler, worker o webhook real de WhatsApp.
- Definir UX de confirmación para mensajes ambiguos, por ejemplo cuando el usuario dice `ya terminé esta tarea` sin identificar la tarea.
- Agregar persistencia específica de eventos académicos múltiples si se requiere modelar más de una urgencia por materia en la misma semana.

### Replanificación

- El sistema ya marca señales de replanificación ligera y enruta eventos de alto impacto hacia `build_study_plan`, pero todavía no implementa un motor completo de propuestas usando `study_replan_requests` y `study_replan_proposals`.
- Falta conectar una política de replanificación diaria basada en bajo cumplimiento repetido.

### Integraciones

- WhatsApp sigue como placeholder de integración.
- Microsoft Graph / Outlook Calendar / Microsoft To Do siguen preparados en capas existentes, pero esta feature no sincroniza automáticamente los eventos académicos nuevos hacia esas integraciones.

## Estado final

La feature queda implementada como MVP robusto para el flujo conversacional interno y verificada por tests. Lo pendiente es principalmente operativo e integracional: aplicar migración, conectar canales reales y evolucionar el motor de replanificación persistida.
