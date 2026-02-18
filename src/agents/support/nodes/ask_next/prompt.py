INTRO_PROMPT = (
    "Hola! Soy tu asistente virtual educativo. "
    "Mi funcion es apoyarte en tu aprendizaje y guiarte paso a paso. "
    "Si algo no queda claro, lo vemos con ejemplos."
)

QUESTIONS = {
    "full_name": (
        "Hola! Estoy aqui para ayudarte. "
        "Para comenzar, cual es tu nombre completo (incluye apellidos)?"
    ),
    "institutional_email": (
        "Gracias! Cual es tu correo institucional "
        "(ej: usuario@ucatolica.edu.co)?"
    ),
    "program": "Perfecto. A que programa perteneces?",
    "semester": "Cual es tu semestre actual (1 a 10)?",
    "gpa": "Cual es tu promedio acumulado (0 a 100)?",
    "age": "Gracias. Cuantos años tienes?",
    "strengths_topics": (
        "Que temas de tu carrera se te facilitan mas? "
        "Puedes mencionar algunos ejemplos."
    ),
    "difficulty_topics": (
        "Y que temas se te dificultan mas? "
        "Esto me ayuda a saber en que reforzar."
    ),
}

SUMMARY_TEMPLATE = (
    "Registro completo. Datos capturados:\n"
    "- Nombre: {full_name}\n"
    "- Correo: {institutional_email}\n"
    "- Programa: {program}\n"
    "- Semestre: {semester}\n"
    "- Promedio: {gpa}\n"
    "- Edad: {age}\n"
    "- Temas faciles: {strengths_topics}\n"
    "- Temas a reforzar: {difficulty_topics}\n\n"
    "Gracias por compartirlos. Estoy aqui para ayudarte con tus estudios. "
    "Que tema o materia te gustaria trabajar hoy?"
)
