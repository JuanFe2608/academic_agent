# Fase 6 - Extraccion Incremental De Slots Para Onboarding

Fecha: 2026-04-18

## Objetivo

Permitir que el estudiante entregue varios datos de onboarding en un solo
mensaje sin que el agente ignore los datos adicionales.

Ejemplo soportado:

```text
Soy Andres Gomez, tengo 20 y voy en octavo.
```

El sistema extrae:

- `full_name = Andres Gomez`
- `age = 20`
- `semester = 8`

Luego solicita solo el siguiente campo faltante segun el orden del onboarding.

## Alcance Implementado

- Extractor deterministico en `src/services/onboarding/slot_extraction.py`.
- Integracion en `src/agents/support/flows/onboarding/collect_profile.py`.
- Persistencia transitoria de errores por campo en `onboarding.slot_errors`.
- Fusion de slots extraidos con `student_profile`.
- Validacion de cada slot con los validadores existentes.
- Fallback al flujo paso a paso cuando no se detectan slots.
- Pruebas dedicadas del extractor y del nodo de onboarding.

## Slots Soportados

- `full_name`
- `student_code`
- `age`
- `institutional_email`
- `semester`
- `average_grade`

## Reglas Aplicadas

- El extractor solo produce candidatos crudos.
- Los validadores deterministas siguen siendo la fuente de verdad.
- El nodo aplica slots en el orden oficial de `PROFILE_FIELD_ORDER`.
- Un slot valido limpia su error previo.
- Un slot invalido queda registrado en `onboarding.slot_errors`.
- Si el codigo estudiantil extraido esta fuera de alcance, se conserva el
  subflujo de confirmacion del programa.
- Si el correo institucional se captura junto con otros slots, se guarda el
  resto de datos validos y luego se mantiene el paso de verificacion por codigo.
- Si no se detectan slots, el flujo paso a paso se comporta igual que antes.

## Decisiones De Arquitectura

- No se uso LLM.
- No se movieron validadores fuera de su ubicacion actual.
- El servicio de extraccion no modifica estado ni importa nodos.
- `collect_profile` sigue siendo el adaptador entre el grafo y las reglas de
  onboarding.
- La fase no cambia OAuth; si el flag OAuth esta activo, el gate sigue ocurriendo
  despues de correo verificado.

## Pruebas Relevantes

- `tests/test_onboarding_slot_extraction.py`
- `tests/test_collect_profile_validation.py`
- `tests/test_onboarding_services.py`
- `tests/test_email_verification_nodes.py`
- `tests/test_confirm_profile_prompts.py`
- `tests/test_onboarding_oauth_flow.py`

Verificacion ejecutada:

```bash
uv run --with pytest python -m pytest tests/test_onboarding_slot_extraction.py tests/test_collect_profile_validation.py tests/test_onboarding_services.py tests/test_email_verification_nodes.py tests/test_confirm_profile_prompts.py tests/test_onboarding_oauth_flow.py tests/test_agent_wait_routing.py tests/test_interaction_state.py tests/test_agent_state_partitioning.py
```

Resultado:

```text
60 passed
```

## Riesgos Pendientes

- El extractor es deliberadamente conservador. Si el usuario escribe datos sin
  marcadores claros, el fallback paso a paso los maneja uno por uno.
- La extraccion de nombre prioriza frases como `soy`, `me llamo` y
  `mi nombre es`; nombres sueltos siguen usando el fallback del campo activo.
- El flush operativo real del buffer de WhatsApp sigue pendiente para pruebas de
  webhook real.
