"""Prompts para recolectar actividades extracurriculares por pasos."""

PROMPT_DETAILS = (
    "Describe la actividad extracurricular en texto libre. "
    "Incluye nombre, dias y horario. "
    "Ejemplo: Gym todos los dias de 5 am a 6 am o Futbol martes y jueves 18:00-19:00."
)

PROMPT_FIXED_DETAILS = (
    "Comparte nombre y horario fijo de la actividad. "
    "Ejemplo: Natacion, martes y jueves 18:00-19:00 o Gym todos los dias de 5 am a 6 am."
)

PROMPT_FLEXIBLE_DETAILS = (
    "Comparte nombre y horario tentativo de la actividad. "
    "Ejemplo: Futbol, tentativo martes o jueves 18:00-19:00."
)

PROMPT_MORE = "Deseas agregar otra actividad? Responde si o no."
