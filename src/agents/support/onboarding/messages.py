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
    "age": "Necesito tu edad en numero 😊 Por ejemplo: 18 o 21",
    "institutional_email": (
        "Ese correo no parece valido para este entorno 😕 Por favor ingresa "
        "un correo permitido, por ejemplo: {email_examples}"
    ),
    "verification_code": (
        "Ese codigo no coincide o ya vencio 😕 Revisalo de nuevo o pide que "
        "te envie uno nuevo."
    ),
    "supported_program": "Responde si o no, por favor 😊",
    "semester": "Necesito el semestre en numero 😊 Por ejemplo: 1, 5 u 8",
    "average_grade": (
        "No pude entender ese promedio 😅 Escribelo en numero, por ejemplo: "
        "76 o 76.5"
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
            f"Perfecto, {name} 🙌 Ahora cuentame, ¿cuantos anos tienes? "
            "Escribelo solo en numero, por ejemplo: 20"
        )

    if field == "institutional_email":
        return (
            "Ahora necesito tu correo institucional o de pruebas 📧 "
            "Por favor escribelo completo. Ejemplo: "
            f"{_email_examples(config)}"
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
            "Escribelo en numero entre 0 y 100, por ejemplo: 76 o 76.5"
        )

    return "Necesito un dato mas para continuar."


def build_prompt_with_error(
    field: str,
    config: OnboardingConfig,
    first_name: str | None = None,
    extra_note: str | None = None,
) -> str:
    """Agrega el mensaje de error al prompt del campo."""

    parts = [VALIDATION_ERROR_MESSAGES[field], build_field_prompt(field, config, first_name)]
    if field == "institutional_email":
        parts[0] = VALIDATION_ERROR_MESSAGES[field].format(
            email_examples=_email_examples(config)
        )
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


def build_verification_sent_prompt(config: OnboardingConfig) -> str:
    """Mensaje al enviar el codigo de verificacion."""

    return (
        "¡Gracias! Ya casi terminamos esta parte ✨ Voy a enviarte un codigo "
        "de verificacion a tu correo institucional. Cuando lo recibas, "
        "escribemelo aqui para continuar.\n"
        "Codigo enviado 📩\n"
        f"El codigo vence en {config.verification_ttl_minutes} minutos."
    )


def build_verification_prompt(config: OnboardingConfig) -> str:
    """Prompt base para capturar el codigo."""

    return (
        "¿Me compartes el codigo que te llego al correo? 🔐 Escribelo tal "
        "como aparece, por ejemplo: "
        f"{'4' * config.verification_code_length}\n"
        "Si no te llega, escribe: reenviar"
    )


def build_verification_error_prompt(
    config: OnboardingConfig,
    detail: str | None = None,
) -> str:
    """Prompt de error para la verificacion del correo."""

    parts = [VALIDATION_ERROR_MESSAGES["verification_code"]]
    if detail:
        parts.append(detail)
    parts.append(build_verification_prompt(config))
    return "\n".join(parts)


def _email_examples(config: OnboardingConfig) -> str:
    domains = tuple(config.allowed_email_domains or (config.institutional_email_domain,))
    examples = [f"usuario@{domain}" for domain in domains if domain]
    if not examples:
        return f"usuario@{config.institutional_email_domain}"
    if len(examples) == 1:
        return examples[0]
    return " o ".join(examples[:2])
