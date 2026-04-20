# Fase 3 - Clasificador De Input Y Politica De Alcance

Fecha: 2026-04-18

## Objetivo

Implementar la primera version deterministica del clasificador de entrada y de
la politica de alcance de Lara, segun
`docs/2026-04-18/plan_fases_implementacion_mvp_lara.md` y
`docs/mvp_academic_agent_lara.md`.

## Alcance Implementado

- DTOs `InputClassification` y `ScopeDecision` en `src/schemas/conversation.py`.
- Clasificador deterministico en `src/services/conversation/input_classifier.py`.
- Politica de alcance en `src/services/conversation/scope_policy.py`.
- Normalizacion compartida en `src/services/conversation/text_normalization.py`.
- Integracion inicial solo para `phase=end`.
- `answer_scope_boundary` ahora responde segun politica y actualiza
  `interaction`.
- Pruebas unitarias de clasificacion, politica y ruteo de fase final.

## Categorias Cubiertas

- `in_scope`
- `partially_in_scope`
- `redirectable_out_of_scope`
- `hard_out_of_scope`
- `human_support_case`

## Tipos De Input Cubiertos

- `text`
- `emoji_only`
- `sticker_only`
- `image_only`
- `mixed`
- `audio`
- `document`

## Politicas Implementadas

### Evaluaciones y actividades

Si el estudiante menciona quiz, parcial, taller, tarea, ejercicio o exposicion,
la politica distingue entre:

- pedir organizacion, planificacion o guia: permitido;
- pedir solucion completa, respuesta exacta o texto para copiar: rechazado.

### Fuera de alcance

Las solicitudes generalistas se rechazan con limite claro y retorno al alcance:
agenda, plan de estudio, recordatorios, replanificacion y tecnicas de estudio.

### Redireccion

Los mensajes difusos pero conectables con carga academica se redirigen hacia
materias, entregas, evaluaciones y planificacion.

### Bienestar o crisis

Los mensajes con senales de crisis o necesidad de apoyo humano se separan del
fuera de alcance normal y recomiendan acompaniamiento humano directo.

## Decisiones De Arquitectura

- No se activo un router conversacional completo. Eso corresponde a la fase 4.
- No se usa LLM para esta fase; las reglas son deterministicas.
- La integracion se limita a `phase=end` para reducir riesgo.
- La politica vive en `services/conversation`, no en nodos.
- El nodo `answer_scope_boundary` solo adapta estado, mensajes y salida.

## Estado Respecto A Fase 2

La fase 3 quedo preparada para recibir texto agregado o tipos de media. Si el
buffer de WhatsApp de fase 2 no esta activo, la politica sigue funcionando con
el ultimo mensaje del usuario. Cuando el buffer este conectado, debera entregar
el texto agregado y `media_types` al clasificador.

## Pruebas Relevantes

- `tests/test_input_classification.py`
- `tests/test_scope_policy.py`
- `tests/test_study_recommendation_agent_flow.py`

Resultado de verificacion:

- `uv run --with pytest python -m pytest tests/test_input_classification.py tests/test_scope_policy.py tests/test_study_recommendation_agent_flow.py tests/test_agent_wait_routing.py tests/test_interaction_state.py`
  -> 37 passed
- `uv run --with pytest python -m pytest`
  -> 427 passed

## Riesgos Controlados

- Las solicitudes de evaluaciones no pasan primero por `handle_academic_update`
  si piden resolver o copiar respuestas.
- Los casos de bienestar no se tratan como plan academico normal.
- El flujo actual de onboarding, horario fijo, sync y Radar no cambia.

## Siguiente Fase

La fase 4 debe construir el router conversacional hibrido usando estas
decisiones, respetando primero alcance, bloque activo, confirmaciones y datos
faltantes.
