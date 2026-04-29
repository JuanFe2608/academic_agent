"""Cobertura del cap de historial de mensajes en el nodo academic_agent.

Problema E: state.messages crece sin límite con cada turno. El nodo academic_agent
ahora emite RemoveMessage para los mensajes más antiguos cuando el historial supera
_MAX_PERSISTED_MESSAGES, manteniendo el checkpoint liviano.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from agents.support.nodes.academic_agent.node import (
    _MAX_PERSISTED_MESSAGES,
    _capped_messages_update,
)
from langgraph.graph.message import add_messages


def _make_history(n_pairs: int) -> list:
    """Construye n_pairs pares Human+AI con IDs reales asignados por add_messages."""
    msgs: list = []
    for i in range(n_pairs):
        msgs = add_messages(msgs, [HumanMessage(content=f"pregunta {i}")])
        msgs = add_messages(msgs, [AIMessage(content=f"respuesta {i}")])
    return msgs


def test_no_removal_when_under_cap() -> None:
    history = _make_history(5)  # 10 messages, under cap of 20
    update = _capped_messages_update(history, "nueva respuesta")

    assert len(update) == 1
    assert isinstance(update[0], AIMessage)
    assert update[0].content == "nueva respuesta"


def test_no_removal_when_exactly_at_cap() -> None:
    # 19 existing + 1 new = 20 (exactly at cap, no overflow)
    history = _make_history(9)  # 18 messages
    history = add_messages(history, [HumanMessage(content="ultimo human")])  # 19
    update = _capped_messages_update(history, "nueva respuesta")

    assert len(update) == 1
    assert isinstance(update[0], AIMessage)


def test_removes_oldest_message_when_one_over_cap() -> None:
    # 20 existing + 1 new = 21, need to remove 1
    history = _make_history(_MAX_PERSISTED_MESSAGES // 2)  # exactly 20 messages
    update = _capped_messages_update(history, "nueva respuesta")

    removes = [m for m in update if isinstance(m, RemoveMessage)]
    adds = [m for m in update if isinstance(m, AIMessage)]

    assert len(removes) == 1
    assert len(adds) == 1
    assert removes[0].id == history[0].id


def test_removes_multiple_oldest_when_far_over_cap() -> None:
    # 30 existing + 1 new = 31, need to remove 11
    history = _make_history(15)  # 30 messages
    update = _capped_messages_update(history, "nueva respuesta")

    removes = [m for m in update if isinstance(m, RemoveMessage)]
    adds = [m for m in update if isinstance(m, AIMessage)]

    assert len(removes) == 11
    assert len(adds) == 1
    removed_ids = {r.id for r in removes}
    assert removed_ids == {m.id for m in history[:11]}


def test_skips_messages_without_id_in_removal_list() -> None:
    # Messages without IDs (created directly, no reducer) should be skipped safely
    no_id_msgs = [HumanMessage(content=f"h{i}") for i in range(_MAX_PERSISTED_MESSAGES + 5)]
    update = _capped_messages_update(no_id_msgs, "nueva respuesta")

    removes = [m for m in update if isinstance(m, RemoveMessage)]
    adds = [m for m in update if isinstance(m, AIMessage)]

    # No removes because messages lack IDs
    assert removes == []
    assert len(adds) == 1


def test_reducer_applies_cap_correctly() -> None:
    """Verifica que el ciclo completo add_messages + RemoveMessage mantiene el límite."""
    history = _make_history(_MAX_PERSISTED_MESSAGES // 2)  # 20 messages
    update = _capped_messages_update(history, "nueva respuesta")

    final = add_messages(history, update)

    assert len(final) == _MAX_PERSISTED_MESSAGES
    assert final[-1].content == "nueva respuesta"
