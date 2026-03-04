"""Prompts base para solicitar horarios."""

PROMPT_LABORAL = (
    "Dime tu horario laboral en texto. "
    "Ejemplo: L-V 7am-4pm; Sab 8am-12pm. "
    "Por ahora no se aceptan imagenes."
)
PROMPT_LABORAL_TIPO = (
    "¿Tu horario laboral es fijo o flexible?\n"
    "1) fijo\n"
    "2) flexible"
)
PROMPT_ACADEMICO = (
    "Comparte tu horario academico en texto (pegado tal cual del correo). "
    "Por ahora no se aceptan imagenes."
)
PROMPT_AMBOS = (
    "Primero comparte tu horario academico en texto. "
    "Luego te preguntare si tu horario laboral es fijo o flexible y despues el horario laboral en texto."
)
PROMPT_NINGUNA = "Si no tienes horarios, lo dejamos hasta aqui."
