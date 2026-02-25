"""Prompts base para solicitar horarios."""

PROMPT_LABORAL = (
    "Dime tu horario laboral en texto. Ejemplo: L-V 7am-4pm; Sab 8am-12pm."
)
PROMPT_LABORAL_TIPO = (
    "¿Tu horario laboral es fijo o flexible?\n"
    "1) fijo\n"
    "2) flexible"
)
PROMPT_ACADEMICO = (
    "Comparte tu horario academico. Puedes enviar la imagen del correo con el "
    "horario (formato institucional) o pegar el texto tal cual."
)
PROMPT_AMBOS = (
    "Comparte tu horario academico y laboral. Puedes enviar la imagen del correo "
    "para el horario academico y el horario laboral en texto. Indica cual es cual."
)
PROMPT_NINGUNA = "Si no tienes horarios, lo dejamos hasta aqui."
