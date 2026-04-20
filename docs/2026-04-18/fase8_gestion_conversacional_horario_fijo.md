# Fase 8 - Gestion Conversacional Del Horario Fijo

Fecha: 2026-04-18

## Objetivo

Permitir que el estudiante consulte, modifique y elimine bloques del horario
fijo ya registrado usando lenguaje natural, con confirmacion antes de cambios
sensibles y reconciliacion de Outlook cuando aplique.

## Alcance Implementado

- Se agregaron contratos puros en `src/services/scheduling/fixed_schedule_management.py`.
- Se agrego el subflujo `fixed_schedule_management_service`.
- Se agrego el nodo `manage_fixed_schedule`.
- El router ahora reconoce:
  - `view_fixed_schedule`
  - `update_fixed_schedule`
  - `delete_fixed_schedule_item`
- El grafo mantiene la fase `fixed_schedule_management` para turnos de
  seleccion, detalles faltantes y confirmacion.
- La gestion opera sobre `schedule.blocks`, que es el estado canonico del
  horario fijo.
- Despues de confirmar, se sincronizan:
  - `schedule.blocks`
  - `events` derivados de bloques
  - `raw_inputs`
  - `extracurricular`
  - `extras_has_any`
- Los cambios confirmados se persisten con `ScheduleService.persist_schedule`.
- Luego se llama a `OutlookFixedScheduleSyncService.sync_schedule_profile`.
- Si Outlook falla, el cambio local queda guardado y se reporta la falla sin
  deshacer el horario.

## Reglas Aplicadas

- Ver el horario no requiere confirmacion.
- Modificar un bloque requiere vista previa y confirmacion.
- Eliminar un bloque requiere confirmacion.
- `interaction.confirmation_pending` y `interaction.last_confirmation_payload`
  se llenan antes de la confirmacion.
- Al confirmar o cancelar, se limpian los datos operativos de confirmacion.
- El router no captura comandos genericos como `borra esa actividad` si no hay
  senal real de horario fijo, clase, trabajo o extracurricular concreto.
- Se reutiliza el matching de titulos del dominio scheduling para encontrar
  bloques por nombre, dia u horario.

## Ejemplos Cubiertos

```text
mostrar mi horario fijo
cambiar mi clase de Calculo a viernes 10:00-12:00
eliminar trabajo del lunes
```

## Pruebas Relevantes

- `tests/test_fixed_schedule_management_flow.py`
- `tests/test_conversation_router.py`
- `tests/test_agent_wait_routing.py`
- `tests/test_schedule_modifications.py`
- `tests/test_replanning_apply_modifications.py`
- `tests/test_schedule_persistence.py`
- `tests/test_outlook_fixed_schedule_sync_service.py`
- `tests/test_outlook_fixed_schedule_reconciliation_service.py`

Verificacion focal ejecutada:

```bash
uv run --with pytest python -m pytest tests/test_fixed_schedule_management_flow.py tests/test_schedule_modifications.py tests/test_replanning_apply_modifications.py tests/test_schedule_persistence.py tests/test_outlook_fixed_schedule_sync_service.py tests/test_outlook_fixed_schedule_reconciliation_service.py
```

Resultado:

```text
31 passed
```

Verificacion completa ejecutada:

```bash
uv run --with pytest python -m pytest
```

Resultado:

```text
466 passed
```

## Riesgos Pendientes

- La edicion conversacional directa cubre cambio de dia y horario. Renombrar
  bloques esta soportado de forma conservadora, pero el editor guiado por campo
  sigue siendo la opcion mas precisa para cambios de nombre.
- La reconciliacion de Outlook depende de que exista conexion Microsoft valida.
  Si falta OAuth o token, se reporta una falla no destructiva.
- El webhook WhatsApp real y el flush por timeout siguen fuera de esta fase.
