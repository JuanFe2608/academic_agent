# Personalization Module Technical Notes

Fecha: 2026-03-30

## Proposito

El bloque de personalizacion ahora tiene dos capas deterministas:

1. `Radar de estudio`
2. `Desempate de perfil`

El Radar identifica dificultades y tecnicas probables.
El desempate solo aparece cuando el perfil principal tiene baja discriminacion y sirve para refinar la prioridad inicial sin anular el scoring base.

## Flujo Resultante

El punto de integracion sigue estando despues de `persist_schedule`, pero ahora el flujo puede bifurcarse:

1. `persist_schedule`
2. `collect_study_profile`
3. si no hace falta desempate: `persist_study_profile`
4. si hace falta desempate: `collect_study_profile_tiebreaker -> persist_study_profile`

La activacion sigue controlada por `ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE=1`.

## Arquitectura

El cambio se mantuvo dentro del dominio `personalization` y de nodos aditivos del mismo flujo.

- `src/agents/support/personalization/questionnaire.py`
  Centraliza el Radar principal, los 3 retos extra, pesos, boosts y copys conversacionales.
- `src/agents/support/personalization/models.py`
  Define estructuras para scoring, `signals`, `tiebreaker`, boosts y respuestas persistibles.
- `src/agents/support/personalization/parser.py`
  Valida `0..3` para el Radar y `1..4` para el desempate.
- `src/agents/support/personalization/scoring.py`
  Ejecuta scoring principal, deteccion de baja discriminacion y refinamiento por desempate.
- `src/agents/support/personalization/formatter.py`
  Renderiza prompts WhatsApp y el cierre final determinista.
- `src/agents/support/personalization/runtime.py`
  Reutiliza utilidades de timestamps y coercion de respuestas para ambos subflujos.
- `src/agents/support/nodes/collect_study_profile/node.py`
  Recolecta el Radar principal y deriva al desempate cuando el dominio lo indica.
- `src/agents/support/nodes/collect_study_profile_tiebreaker/node.py`
  Orquesta los 3 retos extra con progreso, validacion y refinamiento final.
- `src/agents/support/nodes/persist_study_profile/node.py`
  Persiste el resultado final refinado sin cambiar el contrato de salida del agente.

## Reglas De Activacion Del Desempate

La funcion reusable vive en `scoring.py` como `assess_tiebreaker_need(...)`.

Campos detectados:

- `uniform_response`
- `uniform_value`
- `profile_confidence`
- `needs_tiebreaker`
- `activation_reasons`
- `score_tie`
- `top_gap`

Semantica actual de `activation_reasons`:

- `uniform_answers`
- `full_score_tie`
- `low_gap_between_top_scores`

El desempate se activa cuando se cumple cualquiera de estas condiciones:

- todas las respuestas del Radar principal son iguales
- todos los scores normalizados quedan empatados
- la confianza del perfil queda en `baja` y la diferencia entre el top 1 y top 2 es muy corta

## Cuestionario Principal

Versiones activas:

- `QUESTIONNAIRE_VERSION = "v3"`
- `SCORING_VERSION = "v3"`

Mapa principal:

| Pregunta | Tecnica primaria | Tecnica secundaria |
| --- | --- | --- |
| Q01 | Pomodoro | - |
| Q02 | Pomodoro | - |
| Q03 | Feynman | Active Recall |
| Q04 | Active Recall | - |
| Q05 | Metodo Cornell | Active Recall |
| Q06 | Mapas conceptuales | - |
| Q07 | Mnemotecnia | - |
| Q08 | Spaced Repetition | - |
| Q09 | Interleaving | - |
| Q10 | Interleaving | - |

Pesos del Radar:

- primario: `100`
- secundario: `40`

Scoring base por tecnica:

- `raw_score = suma(answer_value * weight)`
- `max_score = suma(3 * weight)`
- `normalized_score = raw_score / max_score`

Esto evita recomendar una tecnica solo porque tenga mas preguntas asociadas.

## Desempate De Perfil

El subbloque usa 3 preguntas de opcion unica.
Cada opcion aporta un boost controlado a una tecnica.

Peso del boost:

- `TIEBREAKER_BOOST_WEIGHT = 100`

El boost fue elegido para que:

- rompa empates artificiales
- complemente el score principal
- no reemplace el diagnostico base

Para mantener justicia entre tecnicas, el refinamiento usa un techo normalizado por tecnica:

- `refined_raw_score = base_raw_score + boost_score`
- `refined_max_score = base_max_score + max_boost_posible_para_esa_tecnica`
- `refined_normalized_score = refined_raw_score / refined_max_score`

Eso evita favorecer una tecnica solo porque aparece en mas opciones del desempate.

## Casos Uniformes

Cuando el Radar principal es totalmente uniforme:

- todo `0`: no se afirma una necesidad fuerte; el desempate solo prioriza una tecnica de refuerzo inicial
- todo `1`: se interpreta como dificultad leve distribuida
- todo `2`: se interpreta como dificultad moderada general
- todo `3`: se interpreta como dificultad alta general o baja discriminacion

Para esos casos, la confianza final se limita a un maximo de `media`, incluso si el desempate aclara la prioridad.

## Señales Y Observaciones Deterministicas

Las observaciones no dependen del LLM.
Se construyen a partir de:

- reglas declarativas del Radar principal
- contexto del desempate cuando se activa
- tecnicas con score alto

Regla de composicion actual:

- primero salen hallazgos del estudiante
- despues, si hace falta, observaciones de tecnica que no repiten una senal ya emitida
- se omiten observaciones de tecnica cuando sus `rationale_tags` ya quedaron cubiertos por una senal equivalente

Ejemplos:

- dificultad para iniciar y sostener sesiones con foco
- dependencia de relectura en lugar de recuperacion activa
- olvido rapido sin repasos espaciados
- dificultad para conectar ideas en temas amplios
- necesidad de definir una prioridad inicial cuando el perfil es uniforme

## UX Conversacional

El bloque conserva formato texto plano para WhatsApp:

- `Reto X/10` para el Radar principal
- `Reto extra X` para el desempate
- barra visual `🟩⬜`
- microfeedback breve y no sesgado
- validacion amable de respuestas invalidas

El estudiante siempre sabe:

- por que aparecieron retos extra
- cuantas preguntas faltan
- como responder
- para que sirve el subbloque

## Persistencia

Se agrego la migracion `migrations/0006_personalization_score_columns.sql`.

Motivo:

- evitar ambiguedad analitica en `study_personalization_scores`
- mantener compatibilidad hacia atras con la columna existente `score`
- dejar el modelo SQL alineado con el objeto `TechniqueScore`

Persistencia actual de `study_personalization_scores`:

- `score`: `raw_score` legado, se mantiene por compatibilidad
- `max_score`: maximo alcanzable para la tecnica en esa corrida
- `normalized_score`: score normalizado `0..1` usado por ranking y analitica

Persistencia final del dominio:

- respuestas del Radar principal
- respuestas del desempate
- `signals`
- `tiebreaker.assessment`
- `tiebreaker.boosts_by_technique`
- `tiebreaker.ranking_before`
- `tiebreaker.ranking_after`
- `tiebreaker.confidence_before`
- `tiebreaker.confidence_after`
- `scores[].raw_score`
- `scores[].max_score`
- `scores[].normalized_score`
- timestamps del desempate y del perfil final

Distincion entre respuestas:

- respuestas del Radar principal: `answer_stage = "radar"`
- respuestas del desempate: `answer_stage = "tiebreaker"`

Las respuestas intermedias turno a turno quedan persistidas por el checkpointer PostgreSQL de LangGraph ya existente.
La persistencia de dominio sigue ocurriendo al cerrar el bloque completo.

## Datos Historicos

La misma migracion `0006_personalization_score_columns.sql` hace dos limpiezas seguras sobre datos previos:

- pone `option_id = NULL` en respuestas historicas del Radar principal (`answer_stage = "radar"`)
- reescribe `result_payload.tiebreaker.assessment.activation_reasons` con la nueva semantica

Esto es seguro porque:

- `option_id` solo tiene significado en el desempate
- la nueva semantica de `activation_reasons` se puede reconstruir con `uniform_response`, `score_tie`, `top_gap` y `profile_confidence`

Si se quiere auditar antes o despues de correr la migracion, el indicador mas util es:

- filas en `study_personalization_answers` con `answer_value->>'answer_stage' = 'radar'` y `option_id IS NOT NULL`

## Participacion Del LLM

El cierre sigue siendo completamente determinista.

El LLM no:

- decide el desempate
- altera boosts
- modifica el top 3
- inventa observaciones

Si mas adelante se usa LLM, debe limitarse a una capa opcional de redaccion sobre el resultado estructurado.

## Validacion

Suite ejecutada:

- `./.venv/bin/python -m pytest -q`

Resultado:

- `179 passed, 1 warning`

Warning conocido:

- `BaseStateModel.Config` sigue usando sintaxis deprecada de Pydantic v2; no bloquea esta implementacion, pero conviene corregirlo antes de una migracion a Pydantic v3.
