# Academic AgentAI (LangGraph) 
## By Juan Jaramillo y Laura Gutierrez

Este proyecto implementa un agente academico con LangGraph para guiar un onboarding, capturar informacion del estudiante y luego responder de forma contextual.

## Que es LangGraph (en palabras simples)
LangGraph es una forma de construir agentes como un grafo de pasos (nodos) con memoria (state). Cada nodo es una funcion que lee el state y escribe cambios. Las rutas entre nodos son explicitas, lo que permite flujos mas confiables que un simple prompt unico.

Ejemplo mental:
- Chatbot clasico: "una sola llamada" que intenta entender todo y responder.
- LangGraph: "varios pasos" que extraen datos, deciden la siguiente pregunta y actualizan el state.

## Diferencia con un chatbot tradicional
Un chatbot clasico suele ser lineal y conversacional sin control de flujo estricto. LangGraph permite:
- Rutas condicionales: preguntas diferentes segun lo que ya se sabe.
- Estado persistente: la informacion no se pierde entre turnos.
- Modularidad: nodos reutilizables (extraer info, preguntar, conversar).
- Observabilidad: puedes ver exactamente en que paso esta el flujo.

## Por que se usa LangGraph en este proyecto
Este agente necesita:
- Un onboarding con pasos definidos (paso 1/5, 2/5, etc.).
- Recolectar datos en orden y validar que no se repita una pregunta.
- Cambiar de modo a conversacion una vez se completa el registro.

LangGraph encaja porque permite modelar ese flujo de forma explicita y confiable, en lugar de depender solo de un prompt grande.

## Conceptos clave para entender el proyecto

### State (estado)
Es la memoria compartida entre nodos. Aqui se usa `StudentState`, que contiene nombre, email, cursos, preferencias, etc.

Ejemplo (simplificado):
```py
class StudentState(BaseModel):
    full_name: Optional[str] = None
    preferred_name: Optional[str] = None
    current_courses: list[Course] = Field(default_factory=list)
```

### Nodo
Un nodo es una funcion que lee el state y devuelve cambios. En este proyecto:
- `extract_info`: extrae datos del texto del usuario.
- `ask_next`: decide la siguiente pregunta.
- `chat`: conversa usando el contexto ya capturado.

Ejemplo real:
```py
builder.add_node("extract_info", extract_info)
builder.add_node("ask_next", ask_next)
```

### Prompt
Los prompts son instrucciones para el LLM. Aqui hay prompts para:
- Mensaje de bienvenida y pasos (`src/agents/support/nodes/ask_next/prompt.py`).
- Extraccion estructurada (`src/agents/support/nodes/extract_info/prompt.py`).

Ejemplo:
```py
EXTRACT_INFO_PROMPT = (
    "Extrae los datos del estudiante desde el texto..."
)
```

### Tools (herramientas)
Son llamadas externas (APIs, bases de datos, calendarios, etc.).
En este proyecto no hay tools integradas aun; el flujo se resuelve con extraction + estado. Si se quisiera, un tool podria ser "crear evento en Google Calendar".

## Como funciona el flujo principal
Grafo `support` (ver `langgraph.json`):
1. `extract_info` intenta llenar campos del state.
2. `route_next` decide: si faltan datos, va a `ask_next`; si no, pasa a `chat`.

Archivo clave:
- `src/agents/support/agent.py`

## Estructura del proyecto (lo esencial)
- `langgraph.json`: define los grafos disponibles y el archivo `.env`.
- `src/agents/support/agent.py`: grafo de onboarding + chat.
- `src/agents/support/state.py`: modelo de estado.
- `src/agents/support/nodes/ask_next/`: prompts y logica de preguntas.
- `src/agents/support/nodes/extract_info/`: extraccion estructurada.

## Configuracion y ejecucion
Requisitos:
- Python 3.12+
- Variables de entorno para Azure OpenAI:
  - `AZURE_OPENAI_DEPLOYMENT_NAME`
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_API_KEY`
  - `OPENAI_API_VERSION`

Ejemplo rapido:
```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Ejecutar el inspector de LangGraph
langgraph dev
```

Opcional: puedes usar el CLI de LangGraph con el grafo `support` o `academic_agent` definido en `langgraph.json`.

## Ejemplo de uso (flujo esperado)
Usuario: "Juan Perez"
- `extract_info` llena `full_name`
- `ask_next` pregunta "Como te gusta que te llame?"
Usuario: "Juan"
- `extract_info` llena `preferred_name`
- `ask_next` pasa a pedir el correo

---

