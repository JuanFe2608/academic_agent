# Fase 10 - Priorizacion Semanal

## Objetivo

Activar la captura conversacional de prioridades semanales despues del Radar de estudio y cuando el estudiante pida priorizar sus materias.

## Decision de activacion

- El salto automatico post-Radar queda detras de `ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW=1`.
- El flag historico `ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE` no activa el post-Radar por si solo.
- Si el flag nuevo esta apagado, una solicitud libre de priorizacion desde `phase=end` se bloquea en la frontera conversacional actual.

## Logica aplicada

1. `persist_study_profile` ahora deja `phase=priorities` solo cuando el Radar se guarda correctamente y el flag post-Radar esta activo.
2. El grafo enruta `phase=priorities` hacia `collect_priorities` cuando el flag esta activo.
3. `collect_priorities` puede iniciar desde:
   - materias derivadas del horario fijo;
   - actividades academicas puntuales pendientes;
   - tecnica principal del Radar.
4. Las actividades academicas pendientes se mezclan en el catalogo de materias sin duplicar por nombre.
5. Una actividad pendiente puede subir carga, dificultad, prioridad y urgencia de la materia.
6. Si el usuario pide priorizar directamente, Lara no interpreta ese mensaje como una respuesta invalida al prompt; entra al paso de ranking semanal.
7. Al omitir o confirmar prioridades, se conserva la persistencia con `persist_planning_snapshot_for_update`.

## Archivos principales

- `src/agents/support/priorities/config.py`
- `src/agents/support/agent.py`
- `src/agents/support/nodes/persist_study_profile/node.py`
- `src/agents/support/flows/priorities/priority_capture_service.py`
- `src/services/priorities/subject_prioritization_service.py`
- `src/services/conversation/router.py`
- `src/services/planning/study_plan_sync_service.py`

## Pruebas ejecutadas

```bash
uv run --with pytest python -m pytest \
  tests/test_priorities_flow.py \
  tests/test_subject_prioritization_service.py \
  tests/test_conversation_router.py \
  tests/test_agent_wait_routing.py \
  tests/test_study_planning_persistence.py \
  tests/test_weekly_priority_service.py
```

Resultado:

```text
47 passed
```

## Como probar manualmente

1. Activar:
   ```bash
   export ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW=1
   ```
2. Completar el Radar de estudio.
3. Verificar que Lara, despues del resumen del Radar, pregunta por prioridades semanales.
4. Responder `Despues` para usar la base detectada o `Si` para ajustar el ranking, urgencias y dificultad.
5. Con actividades ya registradas, por ejemplo un parcial de Calculo, verificar que Calculo aparece una sola vez y con urgencia priorizada.
