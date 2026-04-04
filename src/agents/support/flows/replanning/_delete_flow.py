"""Subflujo de eliminacion dentro de replanificacion."""

from __future__ import annotations

from agents.support.nodes.utils import parse_yes_no
from agents.support.state import AgentState

from ._activity_additions import delete_from_extracurricular, ensure_item, extract_activity_name_from_delete_text
from ._matching import (
    build_delete_confirmation_prompt,
    build_match_table,
    events_from_ids,
    filter_events_by_hint,
    find_delete_matches,
    has_day_or_time_hint,
    parse_delete_scope,
)
from ._shared import (
    ReplanTurnContext,
    build_prompt_update,
    build_validate_update,
    clear_replan_change_request,
)


def apply_delete_change(
    state: AgentState,
    details: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    change_request = dict(replan.get("change_request") or {})
    stage = str(change_request.get("stage") or "")
    candidate_ids = list(change_request.get("candidate_event_ids") or [])
    details = details.strip()

    if stage == "awaiting_delete_confirmation":
        answer = parse_yes_no(details)
        if answer is None:
            prompt = str(
                replan.get("pending_prompt") or "Responde si o no para confirmar la eliminacion."
            )
            return build_prompt_update(ctx, replan, prompt)
        if answer is False:
            clear_replan_change_request(replan)
            return build_validate_update(ctx, replan=replan, awaiting_user_input=False)
        return _delete_selected_events(state, candidate_ids, replan, ctx)

    if stage == "awaiting_delete_scope":
        scope = parse_delete_scope(details)
        if scope == "all":
            selected = events_from_ids(state.get("events", []), candidate_ids)
            change_request["stage"] = "awaiting_delete_confirmation"
            change_request["candidate_event_ids"] = [str(event.get("id")) for event in selected]
            replan["change_request"] = change_request
            return build_prompt_update(ctx, replan, build_delete_confirmation_prompt(selected))
        if scope == "specific":
            change_request["stage"] = "awaiting_delete_identifier"
            replan["change_request"] = change_request
            return build_prompt_update(
                ctx,
                replan,
                "Indica el dia y horario exactos de la actividad que deseas eliminar.",
            )
        if has_day_or_time_hint(details):
            change_request["stage"] = "awaiting_delete_identifier"
            replan["change_request"] = change_request
            return apply_delete_change(state, details, replan, ctx)
        return build_prompt_update(
            ctx,
            replan,
            (
                "Se encontraron varias actividades con ese nombre.\n"
                "Deseas eliminar todas las actividades con ese nombre o solo una especifica?\n"
                "1) Eliminar todas\n"
                "2) Especificar dia y horario"
            ),
        )

    if stage == "awaiting_delete_identifier":
        if not has_day_or_time_hint(details):
            return build_prompt_update(
                ctx,
                replan,
                "Indica el dia y horario exactos de la actividad que deseas eliminar.",
            )
        selected = filter_events_by_hint(events_from_ids(state.get("events", []), candidate_ids), details)
        if not selected:
            return build_prompt_update(
                ctx,
                replan,
                (
                    "No encontre una coincidencia exacta con ese dia y horario. "
                    "Indica el dia y horario exactos."
                ),
            )
        if len(selected) > 1:
            return build_prompt_update(
                ctx,
                replan,
                (
                    "Aun hay varias coincidencias con ese criterio.\n"
                    f"{build_match_table(selected)}\n"
                    "Indica un dia y horario mas especificos."
                ),
            )
        change_request["stage"] = "awaiting_delete_confirmation"
        change_request["candidate_event_ids"] = [str(selected[0].get("id"))]
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, build_delete_confirmation_prompt(selected))

    events = list(state.get("events", []))
    requested_name = (
        str(change_request.get("activity_name") or "").strip()
        or extract_activity_name_from_delete_text(details)
        or details
    )
    if not requested_name:
        change_request["stage"] = "awaiting_delete_name"
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, "Cual es la actividad que deseas eliminar?")

    matches = find_delete_matches(events, requested_name)
    if not matches:
        disponibles = ", ".join(sorted({str(event.get("titulo") or "") for event in events if event.get("titulo")}))
        return build_prompt_update(
            ctx,
            replan,
            f"No encontre la actividad indicada. Actividades disponibles: {disponibles}.",
        )

    if len(matches) > 1 and not has_day_or_time_hint(details):
        activity_name = str(matches[0].get("titulo") or requested_name)
        change_request["stage"] = "awaiting_delete_scope"
        change_request["activity_name"] = activity_name
        change_request["candidate_event_ids"] = [str(event.get("id")) for event in matches]
        replan["change_request"] = change_request
        return build_prompt_update(
            ctx,
            replan,
            (
                f"Se encontraron varias actividades con el nombre {activity_name}.\n"
                "Deseas eliminar todas las actividades con ese nombre o solo una especifica?\n"
                "1) Eliminar todas\n"
                "2) Especificar dia y horario"
            ),
        )

    selected = matches
    if len(matches) > 1 and has_day_or_time_hint(details):
        selected = filter_events_by_hint(matches, details)
        if not selected:
            return build_prompt_update(
                ctx,
                replan,
                (
                    "No encontre una coincidencia exacta con ese dia y horario. "
                    "Indica el dia y horario exactos."
                ),
            )
    change_request["candidate_event_ids"] = [str(event.get("id")) for event in selected]
    change_request["stage"] = "awaiting_delete_confirmation"
    change_request["activity_name"] = requested_name
    replan["change_request"] = change_request
    return build_prompt_update(ctx, replan, build_delete_confirmation_prompt(selected))


def _delete_selected_events(
    state: AgentState,
    candidate_ids: list[str],
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    id_set = set(candidate_ids)
    selected_events = [event for event in state.get("events", []) if str(event.get("id")) in id_set]
    updated_events = [event for event in state.get("events", []) if str(event.get("id")) not in id_set]
    updated_extracurricular = delete_from_extracurricular(
        [ensure_item(item) for item in state.get("extracurricular", [])],
        selected_events,
    )
    clear_replan_change_request(replan)
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        events=updated_events,
        extracurricular=updated_extracurricular,
        errors=list(state.get("errors", [])),
    )


__all__ = ["apply_delete_change"]
