---
paths:
  - "src/agents/support/flows/scheduling/**/*.py"
  - "src/services/scheduling/**/*.py"
  - "src/agents/support/nodes/validate_schedule/**/*.py"
  - "src/agents/support/nodes/request_schedules/**/*.py"
---

# Reglas para el dominio de horarios

## GOTCHA — ScheduleReviewStage: doble registro obligatorio

Al agregar un nuevo stage al flujo de revisión de horarios, actualizar los **dos lugares**:

```python
# 1. src/services/scheduling/constants.py
ScheduleReviewStage = Literal[
    "idle",
    "awaiting_conflict_decision",
    "awaiting_confirmation",
    ...,
    "mi_nuevo_stage",   # ← AGREGAR AQUÍ
]

# 2. src/agents/support/flows/scheduling/section_confirmation_service.py
_SECTION_REVIEW_STAGES: set[str] = {
    "section_awaiting_confirmation",
    ...,
    "mi_nuevo_stage",               # ← AGREGAR AQUÍ TAMBIÉN
}
```

Falta en (1) → `Pydantic literal_error` en runtime al escribir el estado.
Falta en (2) → el handler del stage nunca se ejecuta (flujo se rompe silenciosamente).

## Tipos y constantes clave

```python
# Categorías de bloque (usadas en DB y en lógica de sección)
ScheduleBlockType = Literal["academic", "work", "extracurricular"]

# Días de la semana (en inglés en DB y en lógica interna)
DayOfWeek = Literal["monday", "tuesday", "wednesday", "thursday",
                     "friday", "saturday", "sunday"]

# Mapeo días ES → EN para input del usuario
SPANISH_TO_ENGLISH = {"Lunes": "monday", "Martes": "tuesday", ...}
```

## Parsers de texto de horario

```python
# Para bloques académicos y laborales
from services.scheduling.text_parser.academic import normalize_schedule_section

# Para actividades extracurriculares
from services.scheduling.text_parser.extracurricular import parse_extracurricular_section
```

Usar estos parsers para convertir texto libre del usuario en `list[WeeklyScheduleBlock]`.
No implementar parsers propios — ya están probados y manejan edge cases.

## Estructura de WeeklyScheduleBlock

Los bloques tienen `block_id` (UUID estable). Al editar un bloque, buscar por `block_id`,
no por posición en la lista. Las listas de bloques pueden reordenarse.

## Renderizado de preview

```python
from agents.support.scheduling.render import render_preview_blocks

# Genera imagen PNG del horario y la adjunta como mensaje
result = render_preview_blocks(blocks, state)
```

Llamar siempre que el horario cambia y se quiere mostrar el estado actualizado al usuario.

## Flujo de captura de horario (ScheduleCaptureStage)

```
idle → awaiting_input → awaiting_more → (fin)
```

El nodo `request_schedules` gestiona esta etapa. La captura puede ser:
- Texto libre (el parser lo procesa en `parse_schedules_to_events`)
- Imagen (LLM multimodal extrae los eventos)

## Conflictos

Los conflictos se detectan en `build_draft_schedule` y se guardan en `state.schedule["conflicts"]`.
El nodo `validate_schedule` los presenta al usuario y espera decisión antes de persistir.
