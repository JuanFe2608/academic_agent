# Plan De Implementacion Del Modulo De Personalizacion Academica

Fecha: 2026-03-25

## 1. Resumen Ejecutivo

Se audito el proyecto actual antes de proponer cambios. El estado actual es estable y tiene una base clara para extender el flujo sin reescribir onboarding ni captura de horario:

- El agente productivo expuesto por LangGraph es `support`, declarado en `langgraph.json`.
- El flujo activo llega hasta persistencia del perfil del estudiante y persistencia del horario fijo.
- La arquitectura ya usa un patron consistente `node -> service -> repository`.
- El estado global ya contiene un placeholder llamado `study_profile` y fases futuras como `priorities`, `study_plan` y `replan`, pero ese bloque todavia no esta conectado al grafo activo.
- La persistencia conversacional ya existe mediante un checkpointer PostgreSQL de LangGraph, por lo que el proyecto ya tiene una solucion para recuperar conversaciones incompletas sin necesidad de persistir cada respuesta intermedia del nuevo modulo.

Baseline validado durante la auditoria:

- Suite actual ejecutada con `./.venv/bin/python -m pytest -q`
- Resultado: `136 passed, 1 warning in 3.37s`
- Warning observado: `BaseStateModel` usa configuracion de Pydantic estilo clase, hoy funciona pero esta deprecado para Pydantic v3

Conclusion principal:

- El mejor punto de integracion para el nuevo modulo es despues de `persist_schedule`, reutilizando el `student_id` persistido y el `schedule_profile_id` ya generado.
- La recomendacion es implementar el cuestionario y el scoring como un dominio nuevo y aislado, reutilizando `study_profile` como contrato de estado para el handoff al futuro constructor del metodo de estudio.
- El scoring debe vivir 100 por ciento en codigo Python versionado, nunca en el LLM.

## 2. Arquitectura Actual Relevante Para Este Modulo

### 2.1 Punto de entrada y orquestacion

El agente activo se compila en:

- `src/agents/support/agent.py`

El grafo:

- usa `StateGraph(AgentState)`
- entra por `welcome_consent`
- enruta por `phase`
- finaliza hoy despues de `persist_schedule`

Secuencia activa observada:

1. `welcome_consent`
2. `collect_profile`
3. `send_email_verification`
4. `verify_email_code`
5. `confirm_profile`
6. `persist_profile`
7. `request_schedules`
8. `parse_schedules_to_events`
9. `ask_extracurricular`
10. `collect_extracurricular_details`
11. `build_draft_schedule`
12. `render_schedule_preview`
13. `validate_schedule`
14. `apply_schedule_correction`
15. `persist_schedule`
16. `END`

Observacion importante:

- `persist_schedule` deja `phase = "sync"`, pero `_route_after_persist_schedule()` retorna siempre `end`.
- Ese `sync` ya existe como punto natural de handoff para insertar el nuevo modulo sin forzar un rediseno completo del grafo.

### 2.2 Estado compartido

El contrato central del flujo es:

- `src/agents/support/state.py`

Elementos relevantes del estado:

- `student_profile`: datos del estudiante y `persisted_student_id`
- `raw_inputs`: entradas crudas de horario
- `schedule`: `ScheduleFlowState` con bloques, conflictos y `persisted_profile_id`
- `study_profile`: placeholder actual para respuestas y metodo de estudio futuro
- `study_plan`, `replan`, `reminders`: estados futuros ya modelados

Hallazgo clave:

- `StudyProfile` ya existe pero esta subutilizado:
  - `answers: dict[str, object]`
  - `method: Optional[str]`
  - `how_to: Optional[str]`

Eso favorece ampliar ese modelo en vez de crear otro estado paralelo de personalizacion.

### 2.3 Patron de nodos

Los nodos siguen un patron consistente:

- leen `AgentState`
- detectan nueva entrada con `detect_new_input`
- devuelven un `dict` parcial
- delegan logica de negocio a servicios o helpers de dominio
- usan `prompt.py` y utilidades comunes para mantener mensajes separados de la logica

Esto ya se ve en:

- `src/agents/support/nodes/collect_profile/node.py`
- `src/agents/support/nodes/request_schedules/node.py`
- `src/agents/support/nodes/collect_extracurricular_details/node.py`
- `src/agents/support/nodes/persist_profile/node.py`
- `src/agents/support/nodes/persist_schedule/node.py`

### 2.4 Persistencia y servicios

El proyecto ya tiene una convencion clara:

- `src/agents/support/tools/db.py` expone singletons de servicios
- `onboarding/service.py` y `scheduling/service.py` orquestan casos de uso
- `onboarding/repository.py` y `scheduling/repository.py` tienen implementaciones:
  - `InMemory...Repository`
  - `Postgres...Repository`

Esto es exactamente el patron que conviene replicar para personalizacion.

### 2.5 Uso actual del LLM

El LLM se usa hoy para tareas de interpretacion o normalizacion:

- `src/agents/support/tools/llm.py`
- normalizacion hibrida en `src/agents/support/scheduling/normalizer.py`
- matching o parsing auxiliar en modulos de horario y extracurriculares

Patron actual relevante:

- el sistema ya mezcla logica determinista con apoyo del LLM
- pero conserva parsers y validadores deterministas para lo critico

Ese patron es compatible con el nuevo requisito:

- LLM para redactar o explicar
- scoring solamente determinista

### 2.6 Persistencia conversacional

El proyecto ya persiste el thread completo de LangGraph en PostgreSQL:

- `src/agents/support/tools/langgraph_checkpointer.py`
- migracion `migrations/0003_langgraph_thread_persistence.sql`

Implicacion practica:

- no hace falta persistir borradores incompletos del cuestionario en tablas nuevas durante la fase 1
- el estado intermedio puede vivir en el checkpointer y persistir a tablas del dominio solo cuando el perfil de personalizacion este completo

## 3. Componentes Existentes Que Se Pueden Reutilizar

### 3.1 Archivos y componentes reutilizables

| Componente | Ruta | Reutilizacion recomendada |
| --- | --- | --- |
| Grafo principal | `src/agents/support/agent.py` | Integrar nuevas fases y nodos sin crear un agente paralelo |
| Estado global | `src/agents/support/state.py` | Extender `StudyProfile` y `Phase` de forma aditiva |
| Utilidades de nodos | `src/agents/support/nodes/utils.py` | Reusar `detect_new_input`, `append_message`, `parse_yes_no`, `normalize_text` |
| Servicio factory | `src/agents/support/tools/db.py` | Agregar `get_personalization_service()` y `set_personalization_service()` |
| Patron de servicio | `src/agents/support/onboarding/service.py` | Replicar estructura para `PersonalizationService` |
| Patron de repositorio | `src/agents/support/onboarding/repository.py` | Replicar contrato `Protocol`, errores y variante in-memory/PostgreSQL |
| Persistencia de horario | `src/agents/support/scheduling/service.py` | Tomar como referencia para persistir resultados de personalizacion |
| Nodo de captura secuencial | `src/agents/support/nodes/collect_profile/node.py` | Base para un nodo secuencial de preguntas con validacion determinista |
| Nodo de persistencia | `src/agents/support/nodes/persist_profile/node.py` | Base para persistencia final del perfil de personalizacion |
| Handoff post horario | `src/agents/support/nodes/persist_schedule/node.py` | Punto ideal para iniciar personalizacion despues de guardar horario |
| Checkpointer | `src/agents/support/tools/langgraph_checkpointer.py` | Mantener respuestas parciales en thread sin escribir a BD antes de completar |
| Migraciones actuales | `migrations/0001_*.sql`, `0002_*.sql`, `0003_*.sql` | Seguir convencion con `0004_personalization_profiles.sql` |
| Tests de patron | `tests/test_onboarding_services.py`, `tests/test_schedule_persistence.py`, `tests/test_schedule_request_flow.py` | Replicar estilo de pruebas unitarias y de flujo |

### 3.2 Reutilizacion especifica del estado

Recomiendo reutilizar `study_profile` como contrato canonico del nuevo modulo. No recomiendo crear un nuevo `personalization_state` top-level salvo que aparezca una necesidad fuerte de desacoplarlo.

Motivos:

- ya existe el campo
- ya se resetea junto con el resto del estado en `welcome_consent`
- reduce cambios estructurales en `AgentState`
- deja alineado el handoff al futuro modulo constructor del metodo de estudio

### 3.3 Componentes existentes pero no conectados

Durante la auditoria aparecieron piezas futuras o latentes:

- fases declaradas: `priorities`, `study_plan`, `running`, `replan`
- nodo no conectado al grafo principal: `src/agents/support/nodes/apply_modifications/node.py`

Esto sugiere que el proyecto ya fue pensado para crecer por etapas. El nuevo modulo debe respetar esa direccion y no mezclar personalizacion con replanificacion o edicion de agenda todavia.

## 4. Que Partes Del Flujo Actual Toca Integrar O Extender

### 4.1 Integracion recomendada

Punto de integracion recomendado:

- despues de `persist_schedule`

Razones:

- en ese punto ya existe `student_profile.persisted_student_id`
- tambien existe `schedule.persisted_profile_id`
- el horario fijo ya fue capturado y validado, que es justo el prerequisito descrito
- no obliga a cambiar onboarding ni captura de horario

### 4.2 Cambios concretos esperados

#### Grafo

Habra que tocar:

- `src/agents/support/agent.py`

Cambios esperados:

- extender `Phase` con fases del modulo
- agregar nodos nuevos al grafo
- enrutar desde `persist_schedule` hacia el nuevo modulo en vez de terminar inmediatamente
- mantener una salida segura a `END`

#### Estado

Habra que tocar:

- `src/agents/support/state.py`

Cambios esperados:

- ampliar `StudyProfile`
- agregar modelos auxiliares para scores y progreso
- mantener todos los campos nuevos con defaults y opcionales para no romper checkpoints existentes

#### Servicio y repositorio

Habra que agregar:

- un nuevo dominio `personalization`
- un nuevo servicio en `tools/db.py`
- un nuevo repositorio PostgreSQL y una variante in-memory

#### Migraciones

Habra que agregar:

- `migrations/0004_personalization_profiles.sql`

### 4.3 Flujo propuesto de alto nivel

Flujo actual:

```text
consent -> profile -> email_verification -> profile_confirm -> profile_persist
-> schedules -> extras -> draft -> validate -> schedule_persist -> end
```

Flujo recomendado:

```text
consent -> profile -> email_verification -> profile_confirm -> profile_persist
-> schedules -> extras -> draft -> validate -> schedule_persist
-> study_profile_collect -> study_profile_persist -> end
```

### 4.4 Opcion de despliegue seguro

Para no romper el flujo actual durante la transicion, recomiendo un feature flag temporal:

- `ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE=1`

Comportamiento recomendado:

- `0` o ausente: el grafo conserva salida actual a `END`
- `1`: habilita el nuevo handoff despues de `persist_schedule`

## 5. Riesgos De Romper Logica Existente

### Riesgos altos

1. Cambiar el ruteo final del grafo sin guardas puede alterar el comportamiento actual despues de `persist_schedule`.
2. Agregar nuevas fases a `Phase` sin actualizar `_route_from_phase()` puede enviar estados nuevos al fallback de `welcome_consent`.
3. Cambios no aditivos en `AgentState` pueden romper checkpoints ya persistidos por LangGraph.
4. Si se introduce parsing libre del usuario con ayuda del LLM, el scoring dejaria de ser verdaderamente determinista.

### Riesgos medios

1. `welcome_consent._restart_after_out_of_scope()` reinicia manualmente muchos fragmentos del estado. Si se anade un nuevo top-level state y no se resetea ahi, pueden quedar residuos entre conversaciones.
2. Si el modulo escribe en base de datos antes de completar el cuestionario, se puede terminar con perfiles parciales o dificiles de versionar.
3. Si se persisten resultados solo por `student_id` y no por `schedule_profile_id`, se pierde trazabilidad sobre que horario fijo acompanaba esa caracterizacion.
4. Si el ranking no tiene regla de desempate estable, el top 3 puede variar aunque el score bruto sea igual.

### Riesgos bajos pero reales

1. `BaseStateModel.Config` usa sintaxis deprecada de Pydantic.
2. `README.md` e `INDICATIONS.md` estan vacios; hoy el conocimiento vive casi todo en el codigo y tests.
3. `students` no guarda `occupation`; si un modulo futuro necesitara ese dato desde BD sin leer el thread, tendria que inferirlo desde `schedule_profiles`.

## 6. Plan De Implementacion Por Fases

Orden recomendado:

### Fase 1. Definicion funcional y contrato del dominio

Entregables:

- catalogo versionado de tecnicas de estudio
- catalogo versionado de preguntas
- matriz de scoring determinista
- contrato estructurado de salida para el futuro constructor del metodo

Objetivo:

- cerrar primero el diseno del dominio antes de tocar el grafo

### Fase 2. Modelo de estado y dominio Python

Entregables:

- expansion de `StudyProfile`
- modelos Pydantic para score, ranking y resultado
- parser determinista de respuestas
- motor de scoring puro en Python

Objetivo:

- poder calcular el resultado completo sin depender todavia de la base de datos ni del grafo

### Fase 3. Persistencia

Entregables:

- migracion `0004_personalization_profiles.sql`
- repositorio in-memory
- repositorio PostgreSQL
- `PersonalizationService`
- factory en `tools/db.py`

Objetivo:

- persistir resultados finales y permitir pruebas aisladas

### Fase 4. Integracion con LangGraph

Entregables:

- nuevos nodos de personalizacion
- nuevas fases en `AgentState`
- ruteo desde `persist_schedule`
- salida controlada a `END`

Objetivo:

- acoplar el modulo al flujo existente sin afectar onboarding ni horarios

### Fase 5. Presentacion de resultados y handoff

Entregables:

- mensaje conversacional con top 3 tecnicas
- resultado estructurado guardado en `study_profile`
- persistencia final en BD

Objetivo:

- dejar el estado listo para que un futuro modulo construya el metodo personalizado

### Fase 6. Pruebas y rollout

Entregables:

- tests unitarios, de flujo y de regresion
- validacion con feature flag
- activacion gradual

Objetivo:

- asegurar que el flujo previo permanece intacto

## 7. Propuesta De Estructura De Carpetas Y Archivos

Estructura recomendada:

```text
docs/
  personalization_module_implementation_plan.md

src/agents/support/personalization/
  __init__.py
  config.py
  questionnaire.py
  models.py
  parser.py
  scoring.py
  formatter.py
  repository.py
  service.py

src/agents/support/nodes/collect_study_profile/
  __init__.py
  node.py
  prompt.py

src/agents/support/nodes/persist_study_profile/
  __init__.py
  node.py

migrations/
  0004_personalization_profiles.sql

tests/
  test_personalization_scoring.py
  test_personalization_parser.py
  test_personalization_service.py
  test_personalization_repository.py
  test_personalization_flow.py
```

### Justificacion de la estructura

- `personalization/` concentra dominio, scoring y persistencia
- `nodes/` mantiene el patron actual del proyecto
- `questionnaire.py` deja el catalogo versionado en codigo
- `scoring.py` queda aislado para pruebas puras y deterministas
- `formatter.py` permite separar el resultado estructurado del mensaje conversacional

## 8. Decisiones Tecnicas Recomendadas Y Por Que

1. Reusar `study_profile` como contrato del modulo.
   Porque ya existe en el estado, reduce friccion y conecta naturalmente con el modulo futuro de metodo de estudio.

2. Mantener preguntas cerradas o semi-cerradas.
   Porque el scoring debe ser determinista. Lo mas seguro es preguntar con opciones numeradas, escalas Likert o si/no.

3. Definir cuestionario y scoring en codigo, no en base de datos.
   Porque son reglas de negocio versionadas, auditables y probables candidatas a pruebas unitarias.

4. Persistir solo resultados completos del cuestionario en tablas del dominio.
   Porque los estados intermedios ya pueden sobrevivir en el checkpointer de LangGraph.

5. Guardar el ranking completo y no solo el top 3.
   Porque el siguiente modulo puede necesitar mas contexto que un simple top 3.

6. Usar una regla de desempate fija.
   Recomendacion: ordenar por `score DESC`, luego por `priority_order ASC` del catalogo, luego por `technique_id ASC`.

7. Enlazar el resultado a `student_id` y `schedule_profile_id`.
   Porque la personalizacion ocurre despues del horario fijo y el vinculo facilita trazabilidad y futuras analiticas.

8. Dejar `method` y `how_to` sin poblar en esta fase.
   Porque este modulo solo caracteriza y recomienda tecnicas; construir el metodo es responsabilidad del siguiente modulo.

9. Habilitar el modulo con feature flag temporal.
   Porque permite integrar sin interrumpir el flujo actual mientras se valida en QA.

10. Si se usa LLM, limitarlo a texto explicativo.
   Porque debe interpretar o redactar, no calcular scores ni decidir rankings.

## 9. Diseno Recomendado Del Resultado Estructurado

Contrato sugerido para `study_profile` una vez terminado el modulo:

```json
{
  "questionnaire_version": "v1",
  "scoring_version": "v1",
  "status": "completed",
  "answers": {
    "q01_procrastination": "often",
    "q02_memory_retention": "low",
    "q03_distraction": "high"
  },
  "weakness_tags": [
    "procrastination",
    "low_retention",
    "high_distraction"
  ],
  "scores": [
    {
      "technique_id": "pomodoro",
      "score": 18,
      "rank": 1,
      "rationale_tags": ["procrastination", "high_distraction"]
    },
    {
      "technique_id": "active_recall",
      "score": 16,
      "rank": 2,
      "rationale_tags": ["low_retention"]
    },
    {
      "technique_id": "spaced_repetition",
      "score": 14,
      "rank": 3,
      "rationale_tags": ["low_retention"]
    }
  ],
  "top_techniques": [
    "pomodoro",
    "active_recall",
    "spaced_repetition"
  ],
  "method": null,
  "how_to": null
}
```

Este formato deja listo el handoff para el modulo posterior sin mezclar responsabilidades.

## 10. Plan De Migracion De Base De Datos

### 10.1 Estrategia general

No recomiendo alterar tablas existentes para esta fase. Recomiendo agregar tablas nuevas y relaciones por FK.

Ventajas:

- menor riesgo sobre onboarding y horarios
- despliegue reversible y mas simple
- no requiere backfill

### 10.2 Tablas recomendadas

#### `study_personalization_profiles`

Propuesta de proposito:

- encabezado del resultado final del cuestionario por estudiante

Columnas recomendadas:

- `id BIGSERIAL PRIMARY KEY`
- `student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE`
- `schedule_profile_id BIGINT NULL REFERENCES schedule_profiles(id) ON DELETE SET NULL`
- `version_number INTEGER NOT NULL`
- `questionnaire_version TEXT NOT NULL`
- `scoring_version TEXT NOT NULL`
- `status TEXT NOT NULL`
- `top_techniques JSONB NOT NULL DEFAULT '[]'::jsonb`
- `weakness_tags JSONB NOT NULL DEFAULT '[]'::jsonb`
- `result_payload JSONB NOT NULL DEFAULT '{}'::jsonb`
- `is_current BOOLEAN NOT NULL DEFAULT TRUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Checks recomendados:

- `status IN ('completed', 'superseded')`
- `version_number >= 1`

Indices recomendados:

- indice unico parcial para un perfil actual por estudiante
- indice por `(student_id, version_number DESC)`

#### `study_personalization_answers`

Propuesta de proposito:

- respuestas por pregunta para auditoria y trazabilidad

Columnas recomendadas:

- `id BIGSERIAL PRIMARY KEY`
- `personalization_profile_id BIGINT NOT NULL REFERENCES study_personalization_profiles(id) ON DELETE CASCADE`
- `question_id TEXT NOT NULL`
- `option_id TEXT NULL`
- `answer_value JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Restriccion recomendada:

- `UNIQUE (personalization_profile_id, question_id)`

#### `study_personalization_scores`

Propuesta de proposito:

- ranking completo por tecnica

Columnas recomendadas:

- `id BIGSERIAL PRIMARY KEY`
- `personalization_profile_id BIGINT NOT NULL REFERENCES study_personalization_profiles(id) ON DELETE CASCADE`
- `technique_id TEXT NOT NULL`
- `technique_name TEXT NOT NULL`
- `score INTEGER NOT NULL`
- `rank SMALLINT NOT NULL`
- `rationale_tags JSONB NOT NULL DEFAULT '[]'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Restriccion recomendada:

- `UNIQUE (personalization_profile_id, technique_id)`

### 10.3 Que no migrar en esta fase

No recomiendo:

- guardar el catalogo de preguntas en BD
- guardar la matriz de scoring en BD
- alterar `students`
- alterar `schedule_profiles`

### 10.4 Secuencia de despliegue recomendada

1. Desplegar migracion `0004`
2. Desplegar codigo nuevo con feature flag apagado
3. Ejecutar pruebas
4. Activar feature flag en ambiente de prueba
5. Validar flujos end to end
6. Activar en produccion

## 11. Plan De Pruebas

### 11.1 Unitarias del dominio

- scoring por pregunta y por tecnica
- empates y tie-breakers
- parser de respuestas cerradas
- construccion del top 3
- serializacion del resultado estructurado

### 11.2 Unitarias de servicio y repositorio

- persistencia in-memory
- persistencia PostgreSQL
- versionado por estudiante
- marcado de `is_current`
- asociacion correcta con `student_id` y `schedule_profile_id`

### 11.3 Unitarias de nodos

- primer prompt del cuestionario
- avance pregunta a pregunta
- repregunta cuando la respuesta es invalida
- calculo final al completar la ultima respuesta
- persistencia final y salida del flujo

### 11.4 Pruebas de flujo LangGraph

- flujo completo desde `persist_schedule` hacia personalizacion
- flujo completo con feature flag apagado, validando que el comportamiento actual no cambie
- recuperacion de conversacion incompleta con checkpointer

### 11.5 Regresion

Ejecutar como minimo:

- suite completa actual
- nuevas pruebas del modulo
- pruebas especificas de:
  - onboarding
  - email verification
  - request schedules
  - persist schedule

### 11.6 Casos borde importantes

- respuestas ambiguas
- abandono a mitad del cuestionario
- empate en scores
- estudiante con perfil anterior que vuelve a caracterizarse
- falta de migracion o error de conexion de BD

## 12. Dudas O Supuestos Resueltos Para Poder Avanzar

Supuestos adoptados para poder disenar el plan:

1. El modulo de personalizacion empieza despues de que el horario fijo quedo persistido.
2. El cuestionario del MVP usara respuestas cerradas para mantener scoring determinista.
3. El LLM no clasificara respuestas para score; como mucho podra explicar el resultado ya calculado.
4. El sistema debe guardar el resultado final, no necesariamente cada borrador intermedio en tablas del dominio.
5. El siguiente modulo consumira `study_profile` como entrada principal para construir el metodo personalizado.
6. El estudiante podra rehacer la caracterizacion en versiones futuras, por eso se recomienda versionado en BD.
7. Outlook y WhatsApp no forman parte del alcance de esta implementacion.
8. No se requiere todavia generar sesiones de estudio ni bloques `estudio` en `schedule_profiles`; este modulo solo caracteriza y recomienda tecnicas.

## 13. Recomendacion Final

La implementacion deberia seguir esta estrategia:

1. ampliar `study_profile` y crear el dominio `personalization`
2. construir primero `questionnaire.py`, `parser.py` y `scoring.py`
3. agregar persistencia y migracion `0004`
4. integrar el modulo al grafo despues de `persist_schedule`
5. activar con feature flag y correr regresion completa

Ese orden minimiza el riesgo sobre el flujo actual y deja una base sostenible para el siguiente modulo de construccion del metodo de estudio personalizado.
