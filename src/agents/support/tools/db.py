"""Shim legacy hacia `agents.support.dependencies`.

La ruta correcta para el runtime del agente es `agents.support.dependencies`.
Este módulo se conserva solo para compatibilidad externa mientras se apaga la
deuda de transición.
"""

from agents.support.dependencies import *  # noqa: F401,F403
