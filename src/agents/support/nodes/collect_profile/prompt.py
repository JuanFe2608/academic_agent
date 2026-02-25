"""Prompts para recolectar perfil del estudiante paso a paso."""

PROMPTS_BY_FIELD = {
    "nombre": "Empecemos. ¿Cuál es tu nombre completo?",
    "edad": "¿Cuántos años tienes?",
    "correo": (
        "¿Cuál es tu correo institucional o personal? "
        "(Ej: usuario@ucatolica.edu.co, usuario@gmail.com, usuario@outlook.com)"
    ),
    "codigo": "¿Cuál es tu código estudiantil?",
    "programa": "¿Cuál es tu programa académico? (Ej: Sistemas)",
    "semestre": "¿En qué semestre estás?",
    "promedio": "¿Cuál es tu promedio actual? (1-100)",
    "ocupacion": (
        "¿Cuál es tu ocupación? Elige una opción:\n"
        "1) solo estudio\n"
        "2) solo trabajo\n"
        "3) estudio y trabajo\n"
        "4) ninguna"
    ),
}

FALLBACK_PROMPT = (
    "Necesito algunos datos para crear tu perfil. Empecemos con tu nombre."
)
