"""Prompts base para solicitar el horario semanal recurrente."""

from agents.support.nodes.schedule_input_guidance import build_schedule_capture_prompt

PROMPT_OCCUPATION = (
    "🗓️ Antes de organizar tu agenda, necesito saber cómo está distribuida tu rutina.\n"
    "(Escribe el número de la opción que quieres elegir)\n"
    "Elige una opción:\n"
    "1. 📚 Solo estudio\n"
    "2. 📚💼 Estudio y trabajo\n"
    "3. ✨ Ninguna de las anteriores"
)
PROMPT_ACADEMICO = build_schedule_capture_prompt(
    "📚 Ahora compárteme tu horario académico.\n\n"
    "Puedes copiarlo y pegarlo tal como aparece en tu correo o en el sistema donde inscribiste tus materias.",
    [
        "Indica el día y la hora de inicio y fin de cada materia.",
        "Escribe cada materia por separado o asegúrate de que estén bien diferenciadas.",
        "Si usas formato normal, escribe am o pm.",
        "Si no escribes am/pm, asumiré que usas horario militar.",
        "Puedes escribir varias materias en un mismo mensaje, una debajo de otra.",
        "Si una materia se repite en varios días, puedes escribir los días juntos.",
    ],
    [
        "Lunes - Cálculo - 07:00 a 09:00",
        "Martes y jueves - Física - 10:00 a 12:00",
        "Viernes - Programación - 2:00 pm a 4:00 pm",
    ],
)
PROMPT_LABORAL = build_schedule_capture_prompt(
    "💼 Ahora compárteme tu horario laboral.",
    [
        "Indica el día o los días en los que trabajas.",
        "Incluye la hora de inicio y fin.",
        "Si usas formato normal, escribe am o pm.",
        "Si no escribes am/pm, asumiré que usas horario militar.",
        "Si trabajas varios días con el mismo horario, puedes escribirlos juntos.",
    ],
    [
        "Lunes a viernes - Trabajo - 07:00 a 18:00",
        "Sábado - Trabajo - 8:00 am a 12:00 pm",
    ],
)
PROMPT_AMBOS = PROMPT_ACADEMICO
PROMPT_NINGUNA = (
    "¡Entiendo! 😊 Soy un asistente especializado en gestión del tiempo académico, "
    "planificación de materias y métodos de estudio, por lo que solo puedo acompañarte "
    "si actualmente estás en un proceso de estudio activo. "
    "Cuando empieces a estudiar, ¡estaré aquí para ayudarte a organizar tu agenda! 📚\n\n"
    "Si elegiste esta opción por error o tu situación cambió, selecciona de nuevo:\n"
    "🗓️ Antes de organizar tu agenda, necesito saber cómo está distribuida tu rutina.\n"
    "(Escribe el número de la opción que quieres elegir)\n"
    "Elige una opción:\n"
    "1. 📚 Solo estudio\n"
    "2. 📚💼 Estudio y trabajo\n"
    "3. ✨ Ninguna de las anteriores"
)
PROMPT_MORE_ACADEMIC = (
    "📚 ¿Quieres agregar más materias o ya terminamos con esta parte?\n"
    "(Escribe el número de la opción que quieres elegir)\n"
    "1. Sí, quiero agregar más materias\n"
    "2. No, seguimos"
)
PROMPT_MORE_WORK = (
    "💼 ¿Quieres agregar más horarios de trabajo o continuamos?\n"
    "(Escribe el número de la opción que quieres elegir)\n"
    "1. Sí, quiero agregar más horarios\n"
    "2. No, seguimos"
)
