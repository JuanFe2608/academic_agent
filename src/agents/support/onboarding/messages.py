"""Mensajes del flujo de onboarding."""

from __future__ import annotations

from services.onboarding import OnboardingConfig

PROFILE_FIELD_ORDER = (
    "full_name",
    "student_code",
    "age",
    "institutional_email",
    "semester",
    "average_grade",
)

EDITABLE_PROFILE_FIELDS = PROFILE_FIELD_ORDER

FIELD_LABELS = {
    "full_name": "nombre",
    "student_code": "codigo",
    "age": "edad",
    "institutional_email": "correo",
    "supported_program": "programa",
    "semester": "semestre",
    "average_grade": "promedio",
}

VALIDATION_ERROR_MESSAGES = {
    "full_name": (
        "Ups, ese nombre no me quedo claro 😅 Por favor escribelo solo con "
        "letras y espacios, por ejemplo: Maria Perez"
    ),
    "student_code": (
        "Necesito tu codigo estudiantil solo en numeros 😊 "
        "Por ejemplo: 67000912"
    ),
    "duplicate_student_code": (
        "Ese codigo estudiantil ya esta registrado en otra cuenta 🆔 "
        "Escribe un codigo diferente 😊"
    ),
    "age": "Necesito tu edad en numero 😊 Por ejemplo: 18 o 21",
    "institutional_email": (
        "Ese correo no tiene un formato valido 😕 Por favor ingresa tu correo "
        "Microsoft, por ejemplo: usuario@outlook.com"
    ),
    "duplicate_email": (
        "Ese correo Microsoft ya esta registrado en otra cuenta de estudiante. "
        "Escribe otro correo 📧 Puedes usar @ucatolica.edu.co o una cuenta "
        "Microsoft personal (@outlook.com, @hotmail.com, @live.com). "
        "Por ejemplo: usuario@outlook.com"
    ),
    "non_microsoft_personal_email": (
        "Ese dominio no esta permitido 😕 Usa una cuenta Microsoft personal "
        "(@outlook.com, @hotmail.com, @live.com, etc.) o un dominio habilitado "
        "para la prueba."
    ),
    "supported_program": "Responde si o no, por favor 😊",
    "semester": "Necesito el semestre en numero 😊 Por ejemplo: 1, 5 u 8",
    "average_grade": (
        "No pude entender ese promedio 😅 Escribelo en numero entero, por ejemplo: 76"
    ),
}


def build_field_prompt(
    field: str,
    config: OnboardingConfig,
    first_name: str | None = None,
) -> str:
    """Construye el prompt del campo solicitado."""

    if field == "full_name":
        return (
            "¡Hola! 👋 Me alegra acompanarte en este proceso. Para empezar, "
            "¿como te llamas? Puedes escribirme tu nombre y apellido, por "
            "ejemplo: Juan Perez"
        )

    if field == "student_code":
        return (
            "Ahora necesito tu codigo estudiantil 🆔 Escribelo solo en "
            f"numeros de {config.student_code_length} digitos, por ejemplo: 67000912"
        )

    if field == "age":
        name = first_name or "estudiante"
        return (
            f"Perfecto, {name} 🙌 Ahora cuentame, ¿Que edad tienes? "
            "Escribelo solo en numero, por ejemplo: 20"
        )

    if field == "institutional_email":
        allowed_domains = ", ".join(
            f"@{domain}" for domain in config.allowed_email_domains
        )
        return (
            "Para conectar tu cuenta Microsoft necesito tu correo 📧 "
            f"Puedes usar {allowed_domains} o una cuenta Microsoft personal "
            "(@outlook.com, @hotmail.com, @live.com). "
            "Por ejemplo: usuario@outlook.com"
        )

    if field == "supported_program":
        return (
            "Antes de seguir, quiero confirmar algo del alcance del proyecto. "
            f"¿Perteneces al programa de {config.supported_program_name}? "
            "Responde si o no."
        )

    if field == "semester":
        return (
            "¿En que semestre estas actualmente? 📚 Escribelo solo en numero, "
            "por ejemplo: 4"
        )

    if field == "average_grade":
        return (
            "Por ultimo, ¿cual es tu promedio academico acumulado? ⭐ "
            "Escribelo en numero entero entre 0 y 100, por ejemplo: 76"
        )

    return "Necesito un dato mas para continuar."


def build_prompt_with_error(
    field: str,
    config: OnboardingConfig,
    first_name: str | None = None,
    extra_note: str | None = None,
    *,
    error_key: str | None = None,
) -> str:
    """Agrega el mensaje de error al prompt del campo.

    error_key permite usar un mensaje especifico en lugar del mensaje generico del campo.
    """

    message = VALIDATION_ERROR_MESSAGES.get(error_key or field, VALIDATION_ERROR_MESSAGES.get(field, ""))
    if error_key in {"duplicate_student_code", "duplicate_email"}:
        return message
    parts = [message, build_field_prompt(field, config, first_name)]
    if extra_note:
        parts.append(extra_note)
    return "\n".join(part for part in parts if part)


def build_program_scope_note(config: OnboardingConfig) -> str:
    """Mensaje cuando el usuario no pertenece al programa objetivo."""

    return (
        "Puedes continuar si lo deseas. Solo ten presente que el alcance "
        "actual del MVP esta disenado para estudiantes de "
        f"{config.supported_program_name}."
    )


def build_out_of_scope_program_message(config: OnboardingConfig) -> str:
    """Mensaje final cuando el codigo deja al usuario fuera del alcance."""

    return (
        "Este agente ha sido disenado unicamente para estudiantes de "
        f"{config.supported_program_name}.\n"
        "Actualmente no puedo ayudarte porque el alcance del proyecto esta "
        "dirigido solo a este programa academico."
    )


def build_student_code_scope_prompt(config: OnboardingConfig) -> str:
    """Pregunta de confirmacion cuando el codigo no coincide con el programa objetivo."""

    return (
        "Este codigo no corresponde a uno de Ingenieria de Sistemas. "
        f"¿Perteneces al programa de {config.supported_program_name}? "
        "Responde si o no."
    )


def build_low_grade_confirmation_prompt(grade: int) -> str:
    """Pregunta de confirmacion cuando el promedio registrado es menor de 60."""

    return (
        f"Hmm, registre que tu promedio es *{grade}* 🤔\n"
        "¿Seguro que ese es tu promedio?\n(Responde con el numero de tu opcion)\n"
        "1. Si\n"
        "2. No\n"   
    )


def build_low_grade_motivation_message() -> str:
    """Mensaje motivacional cuando el estudiante confirma un promedio bajo."""

    return (
        "¡Anotado! 📝 Un promedio bajo es un punto de partida, no un limite. 💪\n"
        "Cada dia es una nueva oportunidad para mejorar y superarte. "
        "Estoy aqui para ayudarte a organizar mejor tu tiempo, estudiar con "
        "estrategias efectivas y subir ese promedio paso a paso. 🚀\n"
        "¡Tu puedes lograrlo! Con constancia y las herramientas correctas, "
        "los resultados van a llegar. Juntos vamos a trabajar en eso 🎯✨"
    )
