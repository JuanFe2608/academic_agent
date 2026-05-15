"""Prompts para recolectar actividades extracurriculares por pasos."""

from agents.support.nodes.schedule_input_guidance import build_schedule_capture_prompt

PROMPT_DETAILS = build_schedule_capture_prompt(
    "🏃 Ahora vamos a registrar tus actividades extracurriculares.\n\n"
    "Escríbelas en un solo mensaje.",
    [
        "Indica siempre el día y la hora de inicio y fin.",
        "Si usas formato normal, escribe am o pm.",
        "Si no escribes am/pm, asumiré que usas horario militar (por ejemplo: 14:00).",
        "Puedes escribir varias actividades en el mismo mensaje, una debajo de otra o bien separadas.",
        "Si una actividad ocurre varios días, puedes escribirlos juntos.",
    ],
    [
        "Martes y jueves - Gimnasio - 19:00 a 20:30",
        "Sábado - Natación - 8:00 am a 10:00 am",
    ],
)

PROMPT_FIXED_DETAILS = (
    "Comparte nombre y horario fijo de la actividad. "
    "Ejemplo: Natación, martes y jueves 18:00-19:00 o Gym todos los días de 5 am a 6 am."
)

PROMPT_FLEXIBLE_DETAILS = (
    "Comparte nombre y horario tentativo de la actividad. "
    "Ejemplo: Fútbol, tentativo martes o jueves 18:00-19:00."
)

PROMPT_MORE = (
    "🎯 ¿Quieres agregar más actividades extracurriculares o continuamos?\n"
    "(Escribe el número de la opción que quieres elegir)\n"
    "1. Sí, quiero agregar más actividades\n"
    "2. No, seguimos"
)
