"""Prompts para recolectar perfil del estudiante paso a paso."""

PROMPTS_BY_FIELD = {
    "nombre": "Empecemos. ¿Cuál es tu nombre completo? Usa solo letras y espacios.",
    "edad": "¿Cuántos años tienes? Escribe solo números.",
    "correo": (
        "¿Cuál es tu correo institucional o personal? "
        "(Ej: usuario@ucatolica.edu.co, usuario@gmail.com, usuario@outlook.com)"
    ),
    "codigo": "¿Cuál es tu código estudiantil? Escribe solo números.",
    "semestre": "¿En qué semestre estás? Escribe solo números.",
    "promedio": "¿Cuál es tu promedio actual? Escribe solo números.",
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
