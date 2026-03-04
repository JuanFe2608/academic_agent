"""Prompts para recolectar actividades extracurriculares por pasos."""

PROMPT_TYPE = (
    "Tu actividad extracurricular es fija o flexible?\n"
    "1) fija\n"
    "2) flexible"
)

PROMPT_FIXED_DETAILS = (
    "Comparte nombre y horario fijo de la actividad. "
    "Ejemplo: Natacion, martes y jueves 18:00-19:00."
)

PROMPT_FLEXIBLE_DETAILS = (
    "Comparte nombre y horario tentativo de la actividad. "
    "Ejemplo: Futbol, tentativo martes o jueves 18:00-19:00."
)

PROMPT_MORE = "Deseas agregar otra actividad? Responde si o no."
