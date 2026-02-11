
# Bloque de imports: tipado, mensajes, LLM y utilidades de LangGraph.
import os
import re
from typing import Annotated, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# Bloque de configuracion: credenciales y patrones de validacion.
DEFAULT_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
DEFAULT_API_VERSION = os.getenv("OPENAI_API_VERSION")
DEFAULT_AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
DEFAULT_AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@ucatolica\.edu\.co$")


# Bloque de estado: define la informacion que el agente va capturando y flags de control.
class StudentState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    full_name: Optional[str] = None
    institutional_email: Optional[str] = None
    program: Optional[str] = None
    semester: Optional[int] = None
    gpa: Optional[float] = None
    age: Optional[int] = None
    strengths_topics: Optional[str] = None
    difficulty_topics: Optional[str] = None
    intro_sent: bool = False


# Bloque de esquema de extraccion: estructura que el LLM debe devolver.
class StudentInfo(BaseModel):
    full_name: Optional[str] = Field(default=None, description="Nombre completo con apellidos.")
    institutional_email: Optional[str] = Field(
        default=None, description="Correo institucional @ucatolica.edu.co"
    )
    program: Optional[str] = Field(
        default=None, description="Programa academico del estudiante."
    )
    semester: Optional[int] = Field(
        default=None, description="Semestre actual del estudiante."
    )
    gpa: Optional[float] = Field(
        default=None, description="Promedio acumulado en escala 0 a 100."
    )
    age: Optional[int] = Field(default=None, description="Edad del estudiante.")
    strengths_topics: Optional[str] = Field(
        default=None, description="Temas o areas que se le facilitan."
    )
    difficulty_topics: Optional[str] = Field(
        default=None, description="Temas o areas que se le dificultan."
    )


# Bloque de validacion: normaliza y valida cada campo extraido.
def _clean_full_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned if len(cleaned.split()) >= 2 else None


def _clean_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned if EMAIL_PATTERN.match(cleaned) else None


def _clean_program(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    if "sistemas" in cleaned.lower() and "comput" in cleaned.lower():
        return "Ingenieria de Sistemas y Computacion"
    return cleaned


def _clean_semester(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return value if 1 <= value <= 10 else None


def _clean_gpa(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value if 0 <= value <= 100 else None


def _clean_age(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return value if 10 <= value <= 100 else None


def _clean_topics(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _coerce_text(value: object) -> str:
    # Normaliza entradas del usuario que pueden venir como lista o dicts.
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item and isinstance(item["text"], str):
                parts.append(item["text"])
        return " ".join(parts)
    return ""


def _extract_number(text: str) -> Optional[float]:
    # Extrae el primer numero (entero o decimal) para fallbacks simples.
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


# Bloque LLM: crea el modelo con salida estructurada para extraer campos.
def _get_extractor():
    if not DEFAULT_DEPLOYMENT:
        raise ValueError("Missing AZURE_OPENAI_DEPLOYMENT_NAME.")
    if not DEFAULT_AZURE_ENDPOINT:
        raise ValueError("Missing AZURE_OPENAI_ENDPOINT.")
    if not DEFAULT_AZURE_API_KEY:
        raise ValueError("Missing AZURE_OPENAI_API_KEY.")
    if not DEFAULT_API_VERSION:
        raise ValueError("Missing OPENAI_API_VERSION.")
    llm = AzureChatOpenAI(
        azure_deployment=DEFAULT_DEPLOYMENT,
        api_key=DEFAULT_AZURE_API_KEY,
        azure_endpoint=DEFAULT_AZURE_ENDPOINT,
        api_version=DEFAULT_API_VERSION,
        temperature=0,
    )
    return llm.with_structured_output(StudentInfo)


def _get_chat_model():
    # LLM generativo para conversar una vez finalizado el registro.
    if not DEFAULT_DEPLOYMENT:
        raise ValueError("Missing AZURE_OPENAI_DEPLOYMENT_NAME.")
    if not DEFAULT_AZURE_ENDPOINT:
        raise ValueError("Missing AZURE_OPENAI_ENDPOINT.")
    if not DEFAULT_AZURE_API_KEY:
        raise ValueError("Missing AZURE_OPENAI_API_KEY.")
    if not DEFAULT_API_VERSION:
        raise ValueError("Missing OPENAI_API_VERSION.")
    return AzureChatOpenAI(
        azure_deployment=DEFAULT_DEPLOYMENT,
        api_key=DEFAULT_AZURE_API_KEY,
        azure_endpoint=DEFAULT_AZURE_ENDPOINT,
        api_version=DEFAULT_API_VERSION,
        temperature=0.6,
    )


# Bloque de extraccion: toma el ultimo mensaje del usuario y actualiza el estado.
def extract_info(state: StudentState) -> dict:
    if not state.messages or not isinstance(state.messages[-1], HumanMessage):
        return {}

    user_text = _coerce_text(state.messages[-1].content)
    extractor = _get_extractor()

    prompt = (
        "Extrae los datos del estudiante desde el texto. "
        "Si no hay un dato, deja el campo en null."
    )
    # LLM estructurado para extraer campos del mensaje actual.
    extracted: StudentInfo = extractor.invoke(
        [{"role": "system", "content": prompt}, {"role": "user", "content": user_text}]
    )

    # Fallbacks: usa numericos o texto libre cuando el LLM no extrae correctamente.
    fallback_number = _extract_number(user_text)
    fallback_semester: Optional[int] = None
    fallback_gpa: Optional[float] = None
    fallback_age: Optional[int] = None
    fallback_strengths: Optional[str] = None
    fallback_difficulties: Optional[str] = None
    if fallback_number is not None:
        if state.semester is None and extracted.semester is None:
            if fallback_number.is_integer():
                candidate = int(fallback_number)
                if 1 <= candidate <= 10:
                    fallback_semester = candidate
        if (
            fallback_semester is None
            and state.gpa is None
            and extracted.gpa is None
            and 0 <= fallback_number <= 100
        ):
            fallback_gpa = fallback_number
        if (
            fallback_semester is None
            and fallback_gpa is None
            and state.gpa is not None
            and state.semester is not None
            and state.age is None
            and extracted.age is None
            and fallback_number.is_integer()
        ):
            candidate = int(fallback_number)
            if 10 <= candidate <= 100:
                fallback_age = candidate
    # Fallbacks de texto para temas cuando ya se completo la informacion base.
    if (
        state.full_name
        and state.institutional_email
        and state.program
        and state.semester is not None
        and state.gpa is not None
        and state.age is not None
    ):
        if not state.strengths_topics and not extracted.strengths_topics and user_text:
            fallback_strengths = user_text.strip()
        if (
            state.strengths_topics
            and not state.difficulty_topics
            and not extracted.difficulty_topics
            and user_text
        ):
            fallback_difficulties = user_text.strip()

    # Actualiza el estado con prioridad: extraido -> fallback -> valor previo.
    return {
        "full_name": _clean_full_name(extracted.full_name) or state.full_name,
        "institutional_email": _clean_email(extracted.institutional_email)
        or state.institutional_email,
        "program": _clean_program(extracted.program) or state.program,
        "semester": _clean_semester(extracted.semester)
        or fallback_semester
        or state.semester,
        "gpa": _clean_gpa(extracted.gpa) or fallback_gpa or state.gpa,
        "age": _clean_age(extracted.age) or fallback_age or state.age,
        "strengths_topics": _clean_topics(extracted.strengths_topics)
        or _clean_topics(fallback_strengths)
        or state.strengths_topics,
        "difficulty_topics": _clean_topics(extracted.difficulty_topics)
        or _clean_topics(fallback_difficulties)
        or state.difficulty_topics,
    }


# Bloque de control: decide cual es la siguiente pregunta requerida.
def _next_question(state: StudentState) -> Optional[str]:
    if not state.full_name:
        return (
            "Hola! Estoy aqui para ayudarte. "
            "Para comenzar, cual es tu nombre completo (incluye apellidos)?"
        )
    if not state.institutional_email:
        return (
            "Gracias! Cual es tu correo institucional "
            "(ej: usuario@ucatolica.edu.co)?"
        )
    if not state.program:
        return "Perfecto. A que programa perteneces?"
    if not state.semester:
        return "Cual es tu semestre actual (1 a 10)?"
    if state.gpa is None:
        return "Cual es tu promedio acumulado (0 a 100)?"
    if state.age is None:
        return "Gracias. Cuantos años tienes?"
    if not state.strengths_topics:
        return (
            "Que temas de tu carrera se te facilitan mas? "
            "Puedes mencionar algunos ejemplos."
        )
    if not state.difficulty_topics:
        return (
            "Y que temas se te dificultan mas? "
            "Esto me ayuda a saber en que reforzar."
        )
    return None


# Bloque de respuesta: genera la siguiente pregunta o finaliza el flujo.
def ask_next(state: StudentState) -> dict:
    # Genera la pregunta siguiente o el resumen si ya se completo el registro.
    question = _next_question(state)
    if not question:
        summary = (
            "Registro completo. Datos capturados:\n"
            f"- Nombre: {state.full_name}\n"
            f"- Correo: {state.institutional_email}\n"
            f"- Programa: {state.program}\n"
            f"- Semestre: {state.semester}\n"
            f"- Promedio: {state.gpa}\n"
            f"- Edad: {state.age}\n"
            f"- Temas faciles: {state.strengths_topics}\n"
            f"- Temas a reforzar: {state.difficulty_topics}\n\n"
            "Gracias por compartirlos. Estoy aqui para ayudarte con tus estudios. "
            "Que tema o materia te gustaria trabajar hoy?"
        )
        # Mensaje de presentacion solo una vez.
        if not state.intro_sent:
            intro = (
                "Hola! Soy tu asistente virtual educativo. "
                "Mi funcion es apoyarte en tu aprendizaje y guiarte paso a paso. "
                "Si algo no queda claro, lo vemos con ejemplos."
            )
            return {
                "messages": [AIMessage(content=intro), AIMessage(content=summary)],
                "intro_sent": True,
            }
        return {"messages": [AIMessage(content=summary)], "intro_sent": True}
    if not state.intro_sent:
        intro = (
            "Hola! Soy tu asistente virtual educativo. "
            "Mi funcion es apoyarte en tu aprendizaje y guiarte paso a paso. "
            "Si algo no queda claro, lo vemos con ejemplos."
        )
        return {
            "messages": [AIMessage(content=intro), AIMessage(content=question)],
            "intro_sent": True,
        }
    return {"messages": [AIMessage(content=question)]}


def chat_with_student(state: StudentState) -> dict:
    # Conversacion educativa con contexto del estudiante.
    if not state.messages or not isinstance(state.messages[-1], HumanMessage):
        return {}
    user_text = _coerce_text(state.messages[-1].content)
    llm = _get_chat_model()
    system_prompt = (
        "Eres un asistente virtual educativo disenado para apoyar a estudiantes "
        "universitarios y de secundaria.\n"
        "Personalidad: amable, paciente, motivadora, respetuosa y clara.\n"
        "Objetivo: ayudar al estudiante a aprender, no solo dar respuestas.\n"
        "Reglas:\n"
        "1) Lenguaje cercano, positivo y profesional.\n"
        "2) Explica paso a paso cuando sea necesario.\n"
        "3) Si hay confusion, reformula con ejemplos sencillos.\n"
        "4) Motiva al estudiante cuando tenga dificultades.\n"
        "5) Fomenta pensamiento critico con preguntas suaves.\n"
        "6) Nunca ridiculices ni minimices las dudas.\n"
        "7) Prioriza el aprendizaje sobre la rapidez.\n"
        "8) Si el tema es tecnico, usa analogias simples.\n"
        "9) Resume puntos clave al final si el contenido es largo.\n"
        "10) Ofrece ayuda adicional.\n"
        "Restricciones: no hagas tareas completas sin explicar, no fomentes trampas "
        "academicas, no uses lenguaje ofensivo, no des informacion peligrosa, "
        "mantente educativo.\n"
        "Formato: usa titulos cortos, viñetas cuando sea util, da ejemplos y "
        "finaliza con una pregunta abierta.\n"
        "Contexto del estudiante:\n"
        f"- Nombre: {state.full_name}\n"
        f"- Programa: {state.program}\n"
        f"- Semestre: {state.semester}\n"
        f"- Edad: {state.age}\n"
        f"- Temas faciles: {state.strengths_topics}\n"
        f"- Temas a reforzar: {state.difficulty_topics}\n"
    )
    response = llm.invoke(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}]
    )
    return {"messages": [AIMessage(content=response.content)]}


# Bloque de ruteo: define si el grafo termina o sigue preguntando.
def route_next(state: StudentState) -> str:
    return "ask_next" if _next_question(state) else "chat"


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
