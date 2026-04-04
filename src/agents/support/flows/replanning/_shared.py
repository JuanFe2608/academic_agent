"""Helpers compartidos del flujo de replanificacion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplanTurnContext:
    """Contexto inmutable del turno actual dentro del flujo de replanificacion."""

    previous_user_message_count: int
    current_count: int
    has_new_input: bool
    last_user_text_value: str | None

    def user_message_count(self) -> int:
        return self.current_count if self.has_new_input else self.previous_user_message_count


def build_validate_update(
    ctx: ReplanTurnContext,
    *,
    awaiting_user_input: bool,
    phase: str = "validate",
    replan: dict | None = None,
    **extra: object,
) -> dict:
    """Construye el payload canonico que devuelve el flujo de replanificacion."""

    update = {
        "phase": phase,
        "user_message_count": ctx.user_message_count(),
        "last_user_text": ctx.last_user_text_value,
        "awaiting_user_input": awaiting_user_input,
    }
    if replan is not None:
        update["replan"] = replan
    update.update(extra)
    return update


def build_prompt_update(
    ctx: ReplanTurnContext,
    replan: dict,
    prompt: str,
    **extra: object,
) -> dict:
    """Atajo para respuestas que dejan una pregunta pendiente al usuario."""

    replan["pending_prompt"] = prompt
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=True,
        **extra,
    )


def clear_replan_change_request(replan: dict) -> None:
    """Limpia el estado temporal de cambio una vez aplicado o cancelado."""

    replan["change_request"] = None
    replan["pending_prompt"] = None


__all__ = [
    "ReplanTurnContext",
    "build_prompt_update",
    "build_validate_update",
    "clear_replan_change_request",
]
