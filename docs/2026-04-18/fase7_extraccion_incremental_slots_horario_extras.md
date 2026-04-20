# Fase 7 - Extraccion Incremental Para Horario Fijo Y Extras

Fecha: 2026-04-18

## Objetivo

Aplicar el patron de slots pendientes al horario fijo academico/laboral y a
actividades extracurriculares, sin reescribir los parsers existentes.

## Alcance Implementado

- Se reutilizaron los pendientes existentes:
  - `PendingScheduleItem`
  - `PendingExtracurricularItem`
- Se agrego el puente `src/services/scheduling/pending_slot_state.py`.
- Se sincronizan pendientes de scheduling con `interaction`:
  - `active_intent`
  - `current_domain`
  - `pending_action`
  - `pending_entity_type`
  - `pending_entity_payload`
  - `missing_fields_json`
  - `clarification_needed`
  - `current_section`
- Se ajustaron prompts para pedir solo el dato faltante cuando el pendiente es
  simple:
  - dia o dias;
  - rango horario;
  - nombre de materia o actividad;
  - AM/PM.
- Se mantiene la resolucion de pendientes con respuestas cortas:
  - `viernes`
  - `9 a 11`
  - `Calculo`
  - `7 am a 8 am`
- Se limpia el pendiente operativo en `interaction` cuando el pendiente queda
  resuelto.

## Reglas Aplicadas

- No se reescribio el parser de horarios.
- `contextual_schedule_parsing` sigue completando pendientes academicos y
  laborales.
- `extracurricular_parsing` sigue completando pendientes extracurriculares.
- El estado durable del flujo sigue en la particion de scheduling.
- `interaction` solo refleja el bloqueo conversacional activo para el router y
  para futuras fases de slots.
- Imagenes fuera de captura de horario no se convierten automaticamente en
  horario fijo.

## Entidades Pendientes

### Horario fijo

```json
{
  "pending_entity_type": "fixed_schedule_item",
  "pending_action": "complete_fixed_schedule_item",
  "pending_entity_payload": {
    "schedule_type": "academic",
    "title": "Matematicas",
    "days": ["Miercoles"],
    "raw_text": "Miercoles Matematicas",
    "missing_fields": ["hora de inicio y fin"]
  },
  "missing_fields_json": ["time_range"]
}
```

### Actividad extracurricular

```json
{
  "pending_entity_type": "extracurricular_item",
  "pending_action": "complete_extracurricular_item",
  "pending_entity_payload": {
    "name": "Iglesia",
    "days": ["Domingo"],
    "raw_text": "los domingos voy a la iglesia",
    "is_variable": false,
    "missing_fields": ["hora de inicio y fin"]
  },
  "missing_fields_json": ["time_range"]
}
```

## Pruebas Relevantes

- `tests/test_schedule_request_flow.py`
- `tests/test_extracurricular_flow.py`
- `tests/test_fixed_schedule_pipeline.py`
- `tests/test_extracurricular_parsing.py`
- `tests/test_interaction_state.py`
- `tests/test_conversation_router.py`

Verificacion focal ejecutada:

```bash
uv run --with pytest python -m pytest tests/test_schedule_request_flow.py tests/test_extracurricular_flow.py tests/test_fixed_schedule_pipeline.py tests/test_extracurricular_parsing.py tests/test_interaction_state.py tests/test_conversation_router.py
```

Resultado:

```text
73 passed
```

## Riesgos Pendientes

- El buffer de WhatsApp aun necesita un flush operativo por timeout para webhook
  real. La fase 7 queda preparada para recibir texto agregado, pero el cierre
  automatico del turno pertenece a la integracion del canal.
- La normalizacion de `missing_fields_json` es deterministica y conservadora.
  Nuevos tipos de pendientes deben agregarse explicitamente al puente de
  scheduling.
