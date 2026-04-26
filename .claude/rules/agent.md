---
paths:
  - "src/agents/**/*.py"
---

# Reglas para trabajar en el agente (nodos, flujos, routing)

## Contrato de un nodo

```python
def my_node(state: AgentState) -> dict:
    # 1. Leer estado via particiones tipadas
    messages = state.get("messages", [])
    profile = dict(state.get("student_profile", {}))

    # 2. Detectar nuevo input del usuario
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )

    # 3. Si no hay input nuevo → emitir prompt y esperar
    if not has_new_input:
        return {
            "phase": "mi_fase",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", "Mi pregunta al usuario"),
        }

    # 4. Procesar input y avanzar → siempre actualizar user_message_count y last_user_text
    return {
        "phase": "fase_siguiente",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
    }
```

**Solo retornar los campos que cambian.** LangGraph hace merge parcial — retornar el estado completo sobrescribe campos que no debían cambiar.

## Helpers disponibles en `src/agents/support/nodes/utils.py`

```python
detect_new_input(messages, count, awaiting, last_text) -> (bool, str|None, int)
append_message(messages, role, text) -> list
copy_onboarding_state(state) -> dict
```

## Acceder a servicios desde un nodo

Siempre via `src/agents/support/dependencies.py`:

```python
from agents.support.dependencies import get_onboarding_service

def my_node(state: AgentState) -> dict:
    service = get_onboarding_service()
    ...
```

Nunca instanciar `AppContainer` ni servicios directamente desde un nodo.

## Agregar un nodo nuevo

1. Crear `src/agents/support/nodes/{nombre}/node.py` y `prompt.py`
2. Registrar el nodo en `src/agents/support/agent.py` con `builder.add_node(...)`
3. Añadir las aristas condicionales correspondientes (`builder.add_conditional_edges`)
4. Si necesita una fase nueva: agregar al enum `Phase` en `src/agents/support/state.py`

## Sub-flujos en `src/agents/support/flows/`

Los sub-flujos son servicios de orquestación multi-turno (no nodos de LangGraph).
El nodo llama al sub-flujo con el estado actual y recibe un `dict` de retorno.
El sub-flujo maneja internamente los estados de conversación de ese dominio.

## Routing de mensajes del usuario

El sistema clasifica cada mensaje antes de llegar al nodo:
- `classify_input()` → `intent + scope` (ver `src/services/conversation/`)
- Si `awaiting_user_input = True` → el input va al nodo actual
- Si `awaiting_user_input = False` → el router decide el siguiente nodo según `phase + intent`

## Mensajes al usuario

- Siempre en español
- Usar `append_message(messages, "assistant", texto)` para agregar al historial
- No modificar mensajes anteriores del historial — solo agregar al final
