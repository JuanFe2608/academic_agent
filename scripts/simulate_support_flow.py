"""Simula una conversacion completa con el agente de soporte."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from langchain_core.messages import AIMessage, HumanMessage

from agents.support.nodes.ask_extracurricular import ask_extracurricular
from agents.support.nodes.build_draft_schedule import build_draft_schedule
from agents.support.nodes.collect_extracurricular_details import (
    collect_extracurricular_details,
)
from agents.support.nodes.collect_profile import collect_profile
from agents.support.nodes.confirm_profile import confirm_profile
from agents.support.nodes.generate_tentative_extracurricular import (
    generate_tentative_extracurricular,
)
from agents.support.nodes.parse_schedules_to_events import parse_schedules_to_events
from agents.support.nodes.render_schedule_preview import render_schedule_preview
from agents.support.nodes.request_schedules import request_schedules
from agents.support.nodes.validate_schedule import validate_schedule
from agents.support.nodes.welcome_consent import welcome_consent
from agents.support.state import AgentState, make_initial_state

NODE_MAP = {
    "welcome_consent": welcome_consent,
    "collect_profile": collect_profile,
    "confirm_profile": confirm_profile,
    "request_schedules": request_schedules,
    "parse_schedules_to_events": parse_schedules_to_events,
    "ask_extracurricular": ask_extracurricular,
    "collect_extracurricular_details": collect_extracurricular_details,
    "generate_tentative_extracurricular": generate_tentative_extracurricular,
    "build_draft_schedule": build_draft_schedule,
    "render_schedule_preview": render_schedule_preview,
    "validate_schedule": validate_schedule,
}


def apply_update(state: AgentState, update: dict) -> AgentState:
    """Aplica la actualizacion parcial devuelta por un nodo."""
    if "messages" in update:
        messages = list(state.get("messages", []))
        messages.extend(update.get("messages") or [])
        update = dict(update)
        update["messages"] = messages
    if hasattr(state, "model_copy"):
        return state.model_copy(update=update)
    return state.copy(update=update)


def add_user_message(state: AgentState, text: str) -> AgentState:
    """Agrega un mensaje del usuario al estado."""
    messages = list(state.get("messages", []))
    messages.append(HumanMessage(content=text))
    return apply_update(state, {"messages": messages})


def get_last_assistant_message(state: AgentState) -> str:
    """Obtiene el ultimo mensaje del asistente si existe."""
    for message in reversed(state.get("messages", [])):
        if isinstance(message, AIMessage):
            return str(message.content).strip()
    return ""


def run_step(
    state: AgentState, node_name: str, user_text: str | None = None
) -> AgentState:
    """Ejecuta un nodo con un mensaje de usuario opcional."""
    if user_text is not None:
        state = add_user_message(state, user_text)
    update = NODE_MAP[node_name](state)
    state = apply_update(state, update)

    assistant_text = get_last_assistant_message(state)
    print(f"\n[{node_name}]")
    if user_text is not None:
        print(f"Usuario: {user_text}")
    if assistant_text:
        print(f"Asistente: {assistant_text}")
    return state


def run_demo() -> AgentState:
    """Ejecuta una simulacion completa con datos de ejemplo."""
    state = make_initial_state()

    state = run_step(state, "welcome_consent", "si")
    state = run_step(
        state,
        "collect_profile",
        "nombre: Ana Perez, edad: 21, correo: ana@example.com, codigo: 12345, "
        "programa: Ingenieria de Sistemas y Computacion, semestre: 5, promedio: 85, "
        "ocupacion: solo trabajo",
    )
    state = run_step(state, "confirm_profile", "si")
    state = run_step(state, "request_schedules", "L-V 07:00-16:00; Sabado 8:00-12:00")
    state = run_step(state, "parse_schedules_to_events")
    state = run_step(state, "ask_extracurricular", "si")
    state = run_step(
        state,
        "collect_extracurricular_details",
        "Natacion fija, martes y jueves 6-7pm; "
        "Futbol variable, 2 veces/semana entre lun-jue 6-8pm",
    )
    state = run_step(state, "collect_extracurricular_details", "no")
    state = run_step(state, "generate_tentative_extracurricular")
    state = run_step(state, "build_draft_schedule")
    state = run_step(state, "render_schedule_preview")
    state = run_step(state, "validate_schedule", "si")

    print("\n[resumen]")
    print(f"Fase: {state.get('phase')}")
    print(f"Eventos: {len(state.get('events', []))}")
    print(f"Extracurriculares: {len(state.get('extracurricular', []))}")
    print(f"Validado: {state.get('events_validated')}")
    preview = state.get("schedule_preview", {})
    print(f"Preview imagen: {preview.get('image_path')}")
    return state


if __name__ == "__main__":
    run_demo()
