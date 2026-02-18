WELCOME_MESSAGE = (
    "¡Hola! 👋 Vamos a hacer que el tiempo sí te alcance. "
    "En 3 minutos organizo tu semana y te recomiendo métodos de estudio que se adapten a ti."
)

PURPOSE_MESSAGE = (
    "Te voy a pedir algunos datos para organizar tu semana. "
    "Tu decides que tan detallado."
)

STEP_LABELS = {
    1: "Onboarding Paso 1/5 ✅ Informacion personal",
    2: "Onboarding Paso 2/5 ✅ Materias y prioridades",
    3: "Onboarding Paso 3/5 ✅ Rutina y estudio",
    4: "Onboarding Paso 4/5 ✅ Horarios y compromisos",
    5: "Onboarding Paso 5/5 ✅ Calendario y recordatorios",
}

STEP_1_QUESTIONS = {
    "full_name": "Para comenzar, cual es tu nombre completo (incluye apellidos)?",
    "preferred_name": "Como te gusta que te llame? (Ej: Juan, Juanca, JF)",
    "institutional_email": "Cual es tu correo institucional? (usuario@ucatolica.edu.co)",
    "program": "A que programa perteneces?",
    "gpa": "Cual es tu promedio acumulado? (0 a 100)",
    "age": "Cuantos anos tienes?",
    "student_code": "Cual es tu codigo de estudiante?",
}

STEP_2_QUESTIONS = {
    "current_courses": "Listemos las materias del semestre. Escribelas una por linea.",
    "most_challenging_course": "Cual es la materia mas exigente para ti?",
}

COURSE_FORMAT_HINT = (
    "Formato sugerido: Materia - Profesor (opcional) - Codigo (opcional) - "
    "Prioridad (alta/media/baja) - Dificultad (1-5)."
)

STEP_3_QUESTIONS = {
    "wake_time": "A que hora sueles despertarte? (HH:MM)",
    "sleep_time": "A que hora te acuestas normalmente? (HH:MM)",
    "commute_one_way": (
        "Cuanto tiempo te toma el transporte al campus (solo ida, en minutos)? "
        "Si quieres, dime que dias vas."
    ),
    "best_study_time": "En que momento rindes mas para estudiar? (manana/tarde/noche/variable)",
    "focus_block_minutes": (
        "Cuanto tiempo seguido aguantas concentrado? (25/45/60/90) "
        "Si quieres, agrega descansos y meta semanal."
    ),
}

STEP_4_QUESTIONS = {
    "employment_status": "Trabajas actualmente? (si/no)",
    "employment_type": "Tu horario es fijo, por turnos o freelance?",
    "extracurriculars": (
        "Ademas de la U, haces alguna actividad? "
        "(gym/deporte/musica/semillero/cursos/familia/transporte largo/otra)"
    ),
    "time_blocks": "Comparteme tus horarios (clases, trabajo y extras).",
}

TIME_BLOCKS_FORMAT_HINT = (
    "Formato sugerido:\n"
    "Titulo\n"
    "Dia: HoraInicio-HoraFin | Lugar (campus/virtual)\n"
    "Dia: HoraInicio-HoraFin | Lugar\n\n"
    "Ejemplo:\n"
    "Programacion\n"
    "Lunes 07:00-09:00 | Campus\n"
    "Miercoles 07:00-09:00 | Campus"
)

STEP_5_QUESTIONS = {
    "calendar_sync_consent": "Autorizas que lo pase a tu Google Calendar? (si/no)",
    "calendar_event_naming_style": "Que nombre quieres para tus eventos? (emoji_prefix/plain)",
    "reminders_enabled": "Quieres recordatorios? (si/no)",
    "reminder_channel": (
        "Por donde prefieres los recordatorios? (whatsapp/email/both). "
        "Si quieres, agrega cuantos minutos antes."
    ),
}

SUMMARY_TEMPLATE = (
    "Resumen rapido de tu semana:\n"
    "- Clases: {class_blocks}\n"
    "- Trabajo: {work_blocks}\n"
    "- Actividades extra: {extra_blocks}\n"
    "- Otros: {personal_blocks}\n"
    "- Total bloques: {total_blocks}"
)
