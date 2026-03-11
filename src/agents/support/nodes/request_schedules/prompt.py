"""Prompts base para solicitar horarios."""

PROMPT_LABORAL = (
    "Dime tu horario laboral en texto. "
    "Puedes usar AM/PM o 24h. "
    "Ejemplo: L-V 7am-4pm; Sab 08:00-12:00; Domingo 17:00-21:00."
)
PROMPT_ACADEMICO = (
    "Comparte tu horario academico en texto (pegado tal cual del correo). "
    "Puedes usar horas como 5 am, 05:00 o 17:00; se interpretaran literal."
)
PROMPT_AMBOS = (
    "Primero comparte tu horario academico en texto. "
    "Despues comparte tu horario laboral en texto. "
    "Puedes escribir horas en AM/PM o en 24 horas."
)
PROMPT_NINGUNA = "Si no tienes horarios, lo dejamos hasta aqui."
