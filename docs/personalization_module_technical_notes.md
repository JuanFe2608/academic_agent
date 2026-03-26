# Personalization Module Technical Notes

Fecha: 2026-03-25

## Resumen

Se implemento el modulo de caracterizacion academica del estudiante como una extension aditiva del agente existente. El flujo nuevo:

1. inicia despues de `persist_schedule`
2. solo se activa si `ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE=1`
3. recolecta 10 respuestas cerradas con escala Likert 0..3
4. calcula scoring determinista en Python
5. rankea 8 tecnicas de estudio
6. persiste el resultado final y deja `study_profile` listo para el siguiente modulo

## Feature Flag

Variable:

- `ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE=1`

Comportamiento:

- apagado o ausente: el comportamiento actual se mantiene; el flujo termina despues de `persist_schedule`
- encendido: el grafo entra a `collect_study_profile` y luego a `persist_study_profile`

## Archivos Principales

Dominio nuevo:

- `src/agents/support/personalization/config.py`
- `src/agents/support/personalization/questionnaire.py`
- `src/agents/support/personalization/models.py`
- `src/agents/support/personalization/parser.py`
- `src/agents/support/personalization/scoring.py`
- `src/agents/support/personalization/formatter.py`
- `src/agents/support/personalization/repository.py`
- `src/agents/support/personalization/service.py`

Nodos nuevos:

- `src/agents/support/nodes/collect_study_profile/node.py`
- `src/agents/support/nodes/collect_study_profile/prompt.py`
- `src/agents/support/nodes/persist_study_profile/node.py`

Integracion:

- `src/agents/support/agent.py`
- `src/agents/support/state.py`
- `src/agents/support/tools/db.py`

Persistencia:

- `migrations/0004_personalization_profiles.sql`
- `migrations/0005_grant_personalization_permissions.sql`

Pruebas:

- `tests/test_personalization_parser.py`
- `tests/test_personalization_scoring.py`
- `tests/test_personalization_service.py`
- `tests/test_personalization_repository.py`
- `tests/test_personalization_flow.py`

## Estado En AgentState

Se reutilizo `study_profile` y se amplio de forma aditiva con:

- `questionnaire_version`
- `scoring_version`
- `status`
- `current_question_index`
- `answers`
- `weakness_tags`
- `scores`
- `top_techniques`
- `confidence`
- `observations`
- `persisted_profile_id`
- `persistence_error`

No se creo un nuevo estado top-level.

## Reglas De Scoring

Para cada tecnica:

- `raw_score = suma de respuestas asociadas`
- `max_score = numero de preguntas asociadas * 3`
- `normalized_score = raw_score / max_score`
- `percentage_score = normalized_score * 100`

Ranking:

1. `normalized_score DESC`
2. `priority_order ASC`
3. `technique_id ASC`

Confianza:

- `alta`: diferencia top1 - top2 >= 0.20
- `media`: diferencia entre 0.10 y 0.19
- `baja`: diferencia < 0.10

Observaciones:

- se generan de forma determinista para tecnicas con `normalized_score >= 0.67`

## Persistencia

Tablas nuevas:

- `study_personalization_profiles`
- `study_personalization_answers`
- `study_personalization_scores`

La persistencia:

- versiona por `student_id`
- vincula el resultado a `schedule_profile_id`
- guarda ranking completo, `top_techniques`, `weakness_tags` y `result_payload`
- marca el perfil anterior como `superseded` cuando aparece una nueva version

## Troubleshooting

Si el horario se guarda pero la caracterizacion falla con un error como:

- `permission denied for table study_personalization_profiles`

entonces el usuario de PostgreSQL con el que corre la app no recibio permisos sobre las tablas nuevas del modulo.

Corre la migracion:

- `migrations/0005_grant_personalization_permissions.sql`

Esa migracion:

- replica hacia las tablas de personalizacion los roles que ya tienen permisos de insercion sobre `schedule_profiles` y `recurring_schedule_blocks`
- concede permisos sobre las secuencias nuevas
- deja `ALTER DEFAULT PRIVILEGES` para evitar repetir el problema en migraciones futuras ejecutadas por el mismo rol owner

## Flujo Conversacional

El nodo `collect_study_profile`:

- presenta la introduccion una sola vez
- muestra una pregunta por turno
- valida respuestas vacias, invalidas y fuera de rango
- repregunta la misma afirmacion cuando la respuesta es invalida
- al terminar la pregunta 10 calcula el resultado y pasa a persistencia

El nodo `persist_study_profile`:

- guarda el resultado final
- responde con tecnica principal, secundaria, de apoyo, confianza y observaciones

## Estado Final Esperado

`study_profile` queda con un payload equivalente a:

- `questionnaire_version`
- `scoring_version`
- `status = completed`
- `answers`
- `weakness_tags`
- `scores`
- `top_techniques`
- `confidence`
- `observations`
- `method = null`
- `how_to = null`

## Validacion

Suite ejecutada:

- `./.venv/bin/python -m pytest -q`

Resultado:

- `156 passed, 1 warning`

Warning conocido:

- `BaseStateModel.Config` sigue usando sintaxis deprecada de Pydantic v2; no bloquea esta feature, pero conviene corregirlo antes de una migracion a Pydantic v3.
