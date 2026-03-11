"""Prompts base para solicitar horarios."""

PROMPT_LABORAL = (
    "Dime tu horario laboral en texto. "
    "Puedes usar AM/PM o 24h. "
    "Ejemplo: L-V 7am-4pm; Sab 08:00-12:00; Domingo 17:00-21:00. "
    "Por ahora no se aceptan imagenes."
)
PROMPT_LABORAL_TIPO = (
    "¿Tu horario laboral es fijo o flexible?\n"
    "1) fijo\n"
    "2) flexible"
)
PROMPT_ACADEMICO = (
    "Comparte tu horario academico en texto (pegado tal cual del correo). "
    "Puedes usar horas como 5 am, 05:00 o 17:00; se interpretaran literal. "
    "Por ahora no se aceptan imagenes."
)
PROMPT_AMBOS = (
    "Primero comparte tu horario academico en texto. "
    "Luego te preguntare si tu horario laboral es fijo o flexible y despues el horario laboral en texto. "
    "Puedes escribir horas en AM/PM o en 24 horas."
)
PROMPT_NINGUNA = "Si no tienes horarios, lo dejamos hasta aqui."
