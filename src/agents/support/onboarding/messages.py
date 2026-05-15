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
_MICROSOFT_PERSONAL_DOMAIN_ROOTS = frozenset({"outlook", "hotmail", "live", "msn"})
_MICROSOFT_PERSONAL_EXAMPLES = "@outlook.com, @hotmail.com, @live.com"

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
        "Ups, ese nombre no me quedó claro 😅 Por favor escríbelo solo con "
        "letras y espacios, por ejemplo: Maria Perez"
    ),
    "student_code": (
        "Necesito tu código estudiantil solo en números 😊 "
        "Por ejemplo: 67000912"
    ),
    "duplicate_student_code": (
        "Ese código estudiantil ya está registrado en otra cuenta 🆔 "
        "Escribe un código diferente 😊"
    ),
    "age": "Necesito tu edad en número 😊 Por ejemplo: 18 o 21",
    "institutional_email": (
        "Ese correo no tiene un formato válido 😕 Por favor ingresa tu correo "
        "Microsoft, por ejemplo: usuario@outlook.com"
    ),
    "duplicate_email": (
        "Ese correo Microsoft ya está registrado en otra cuenta de estudiante. "
        "Escribe otro correo Microsoft personal 📧 "
        f"Puedes usar {_MICROSOFT_PERSONAL_EXAMPLES}. "
        "Por ejemplo: usuario@outlook.com"
    ),
    "non_microsoft_personal_email": (
        "Ese dominio no está permitido 😕 Usa una cuenta Microsoft personal "
        f"({_MICROSOFT_PERSONAL_EXAMPLES}, etc.)."
    ),
    "supported_program": "Responde sí o no, por favor 😊",
    "semester": "Necesito el semestre en número 😊 Por ejemplo: 1, 5 u 8",
    "average_grade": (
        "No pude entender ese promedio 😅 Escríbelo en número entero, por ejemplo: 76"
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
            "¡Hola! 👋 Me alegra acompañarte en este proceso. Para empezar, "
            "¿cómo te llamas? Puedes escribirme tu nombre y apellido, por "
            "ejemplo: Juan Perez"
        )

    if field == "student_code":
        return (
            "Ahora necesito tu código estudiantil 🆔 Escríbelo solo en "
            f"números de {config.student_code_length} dígitos, por ejemplo: 67000912"
        )

    if field == "age":
        name = first_name or "estudiante"
        return (
            f"Perfecto, {name} 🙌 Ahora cuéntame, ¿Qué edad tienes? "
            "Escríbelo solo en número, por ejemplo: 20"
        )

    if field == "institutional_email":
        allowed_domains = _non_personal_allowed_domains(config.allowed_email_domains)
        if not allowed_domains:
            return (
                "Para conectar tu cuenta Microsoft necesito tu correo 📧 "
                f"Usa una cuenta Microsoft personal ({_MICROSOFT_PERSONAL_EXAMPLES}). "
                "Por ejemplo: usuario@outlook.com"
            )
        allowed_domains_text = ", ".join(f"@{domain}" for domain in allowed_domains)
        return (
            "Para conectar tu cuenta Microsoft necesito tu correo 📧 "
            f"Puedes usar {allowed_domains_text} o una cuenta Microsoft personal "
            f"({_MICROSOFT_PERSONAL_EXAMPLES}). "
            "Por ejemplo: usuario@outlook.com"
        )

    if field == "supported_program":
        return (
            "Antes de seguir, quiero confirmar algo del alcance del proyecto. "
            f"¿Perteneces al programa de {config.supported_program_name}? "
            "Responde sí o no."
        )

    if field == "semester":
        return (
            "¿En qué semestre estás actualmente? 📚 Escríbelo solo en número, "
            "por ejemplo: 4"
        )

    if field == "average_grade":
        return (
            "Por último, ¿cuál es tu promedio académico acumulado? ⭐ "
            "Escríbelo en número entero entre 0 y 100, por ejemplo: 76"
        )

    return "Necesito un dato más para continuar."


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


def _non_personal_allowed_domains(domains: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for raw_domain in domains:
        domain = str(raw_domain or "").strip().lower()
        if not domain:
            continue
        domain_root = domain.split(".")[0]
        if domain_root in _MICROSOFT_PERSONAL_DOMAIN_ROOTS:
            continue
        normalized.append(domain)
    return normalized


def build_program_scope_note(config: OnboardingConfig) -> str:
    """Mensaje cuando el usuario no pertenece al programa objetivo."""

    return (
        "Puedes continuar si lo deseas. Solo ten presente que el alcance "
        "actual del MVP está diseñado para estudiantes de "
        f"{config.supported_program_name}."
    )


def build_out_of_scope_program_message(config: OnboardingConfig) -> str:
    """Mensaje final cuando el codigo deja al usuario fuera del alcance."""

    return (
        "Este agente ha sido diseñado únicamente para estudiantes de "
        f"{config.supported_program_name}.\n"
        "Actualmente no puedo ayudarte porque el alcance del proyecto está "
        "dirigido solo a este programa academico."
    )


def build_student_code_scope_prompt(config: OnboardingConfig) -> str:
    """Pregunta de confirmacion cuando el codigo no coincide con el programa objetivo."""

    return (
        "Este código no corresponde a uno de Ingeniería de Sistemas. "
        f"¿Perteneces al programa de {config.supported_program_name}? "
        "Responde sí o no."
    )


def build_low_grade_confirmation_prompt(grade: int) -> str:
    """Pregunta de confirmacion cuando el promedio registrado es menor de 60."""

    return (
        f"Hmm, registré que tu promedio es *{grade}* 🤔\n"
        "¿Seguro que ese es tu promedio?\n(Responde con el numero de tu opcion)\n"
        "1. Si\n"
        "2. No\n"   
    )


def build_low_grade_motivation_message() -> str:
    """Mensaje motivacional cuando el estudiante confirma un promedio bajo."""

    return (
        "¡Anotado! 📝 Un promedio bajo es un punto de partida, no un límite. 💪\n"
        "Cada dia es una nueva oportunidad para mejorar y superarte. "
        "Estoy aquí para ayudarte a organizar mejor tu tiempo, estudiar con "
        "estrategias efectivas y subir ese promedio paso a paso. 🚀\n"
        "¡Tú puedes lograrlo! Con constancia y las herramientas correctas, "
        "los resultados van a llegar. Juntos vamos a trabajar en eso 🎯✨"
    )
