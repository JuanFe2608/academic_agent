---
paths:
  - "src/agents/support/flows/onboarding/**/*.py"
  - "src/agents/support/nodes/collect_profile/**/*.py"
  - "src/agents/support/nodes/confirm_profile/**/*.py"
  - "src/agents/support/nodes/welcome_consent/**/*.py"
  - "src/agents/support/onboarding/**/*.py"
  - "src/services/onboarding/**/*.py"
---

# Reglas para el flujo de onboarding

## Orden de campos del perfil

```python
PROFILE_FIELD_ORDER = (
    "full_name", "student_code", "age",
    "institutional_email", "semester", "average_grade",
)
```

El flujo avanza en este orden. `supported_program` se valida implícitamente
cuando se procesa `student_code`. `occupation` se infiere del horario, no se pregunta aquí.

## Validaciones clave

- `full_name`: solo letras y espacios
- `student_code`: solo dígitos, longitud definida por `OnboardingConfig.student_code_length`
- `age`: entero, rango implícito por contexto
- `institutional_email`: dominio Microsoft personal (`@outlook.com`, `@hotmail.com`, `@live.com`, etc.) — NO correos institucionales
- `semester`: entero 1–15
- `average_grade`: **entero 0–100** (no floats — validador usa `r"\d{1,3}"`)

## Flujo de confirmación de promedio bajo (< 60)

Cuando `average_grade < 60`:
1. No guardar el valor todavía
2. Guardar en `onboarding.pending_low_grade_value` y poner `onboarding.pending_low_grade_confirmation = True`
3. Preguntar confirmación con `build_low_grade_confirmation_prompt(grade)`
4. Si confirma → aplicar el valor + enviar `build_low_grade_motivation_message()` + avanzar
5. Si niega → limpiar pending + re-preguntar `average_grade`

## `parse_yes_no` — tokens aceptados

```python
_YES_TOKENS = {"si", "sí", "yes", "claro", "correcto", "exacto", "afirmativo", "1"}
_NO_TOKENS  = {"no", "nope", "negativo", "incorrecto", "2"}
```

El `"1"` cuenta como "sí" y `"2"` como "no" — útil para preguntas con opciones numeradas.

## Estado pending en OnboardingState

```python
pending_student_code_scope_confirmation: bool  # Estudiante fuera del programa objetivo
pending_low_grade_confirmation: bool           # Promedio < 60 esperando confirmación
pending_low_grade_value: Optional[int]         # Valor guardado temporalmente
```

Siempre verificar estos flags al inicio del handler antes de procesar input normal.

## Verificación de correo

El correo se verifica via código OTP enviado al email del estudiante.
El estado de verificación vive en `OnboardingState.email_verification`.
El OAuth de Microsoft se configura después, en la fase `microsoft_oauth`.

## Confirmación de perfil (`confirm_profile`)

El correo institucional **no aparece** en la pantalla de confirmación ni en las
opciones de edición — ya fue autenticado y no se puede cambiar en este flujo.

Campos editables en la confirmación: `full_name`, `student_code`, `age`, `semester`, `average_grade`.
