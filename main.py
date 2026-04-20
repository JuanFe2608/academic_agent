"""Punto de entrada de produccion del agente Lara.

Uso:
    uvicorn main:app --host 0.0.0.0 --port 8000
    python main.py                            # desarrollo local
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Asegura que src/ este en el path cuando se ejecuta directamente
_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from api.app import app  # noqa: E402  (import despues de sys.path setup)

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() in {"1", "true", "yes"}

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
