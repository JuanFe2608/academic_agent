"""Prompts para recolectar actividades extracurriculares por pasos."""

PROMPT_DETAILS = (
    "🏃 Escríbeme tus actividades extracurriculares en un solo mensaje.\n"
    "Incluye nombre, días y horas. Ejemplo: Gimnasio martes y jueves de 19:00 a 20:30."
)

PROMPT_FIXED_DETAILS = (
    "Comparte nombre y horario fijo de la actividad. "
    "Ejemplo: Natacion, martes y jueves 18:00-19:00 o Gym todos los dias de 5 am a 6 am."
)

PROMPT_FLEXIBLE_DETAILS = (
    "Comparte nombre y horario tentativo de la actividad. "
    "Ejemplo: Futbol, tentativo martes o jueves 18:00-19:00."
)

PROMPT_MORE = (
    "Si tienes más actividades, envíamelas ahora. "
    "Si ya terminaste, responde: no."
)
