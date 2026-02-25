# AGENTS.md (Instrucciones del proyecto)

## Objetivo

Implementar un MVP de agente académico (LangGraph + Python) enfocado SOLO en:

1. Gestión de tiempo/agenda
2. Planificación de sesiones de estudio basadas en método de estudio
3. Recordatorios/seguimiento
4. Replanificación automática ante cambios

## Restricciones

- NO responder preguntas sobre contenido de materias.
- La fuente de verdad del horario es una lista de eventos:
  [{"dia","inicio","fin","titulo","tipo","categoria","origen",...}]
- Mantener código modular:existe una carpeta support, en esta va toda la logica del agente, hay una carpeta llamada node donde hay un ejemplo de la arquitectura que se va a manejar, cada nodo tiene una carpeta independiente con el nombre del nodo, dentro hay diferentes archivos como el **init**.py, node.py (logica del nodo), prompt y en caso tal que el nodo necesite tools enotnces irira tools.py. En la carpeta support entan los archivos como agent.py que es donde va la construccion del agente con cada nodo, state.py y si es necesario agregar otros archivos.
- Siempre escribir tests básicos para parse/render.

## Stack

- Python 3.11+
- LangGraph
- PostgreSQL + pgvector (más adelante)
- Integración calendario: Outlook (Microsoft Graph) / Google Calendar (OAuth)
