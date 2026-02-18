from langgraph.graph import END, START, StateGraph

from agents.support.nodes import ask_next, chat_with_student, extract_info, next_question
from agents.support.state import StudentState


def route_next(state: StudentState) -> str:
    return "ask_next" if next_question(state) else "chat"


# Bloque de construccion del grafo: nodos, rutas y compilacion final.
builder = StateGraph(StudentState)
builder.add_node("extract_info", extract_info)
builder.add_node("ask_next", ask_next)
builder.add_node("chat", chat_with_student)
builder.add_edge(START, "extract_info")
builder.add_conditional_edges(
    "extract_info",
    route_next,
    {"ask_next": "ask_next", "chat": "chat"},
)
builder.add_edge("ask_next", END)
builder.add_edge("chat", END)

# Bloque de export: variable requerida por LangGraph CLI/Debugger.
agent = builder.compile()
