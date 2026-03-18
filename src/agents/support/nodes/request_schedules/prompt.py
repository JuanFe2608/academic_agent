"""Prompts base para solicitar el horario semanal recurrente."""

PROMPT_OCCUPATION = (
    "Antes de organizar tu agenda, necesito saber cómo está distribuida tu rutina.\n"
    "Elige una opción:\n"
    "1. Solo estudio\n"
    "2. Estudio y trabajo\n"
    "3. Ninguna de las anteriores"
)
PROMPT_ACADEMICO = (
    "📚 Compárteme tu horario académico en un solo mensaje.\n"
    "Puedes copiarlo tal como te llegó al correo o como te aparece cuando inscribiste tus materias."
)
PROMPT_LABORAL = (
    "💼 Ahora compárteme tu horario laboral.\n"
    "Por favor incluye los días y las horas, por ejemplo: lunes a viernes de 7:00 a 18:00."
)
PROMPT_AMBOS = (
    "Perfecto. Empecemos por tu horario académico 📚\n"
    "Envíamelo en un solo mensaje, idealmente como lo tienes en tu correo o en el portal."
)
PROMPT_NINGUNA = (
    "Soy un agente especializado en gestión del tiempo, planificación de actividades y "
    "recomendación de métodos de estudio. Lo siento, no puedo ayudarte en este momento "
    "porque necesito que actualmente estés estudiando."
)
