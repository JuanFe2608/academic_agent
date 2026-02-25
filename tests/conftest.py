"""Configura el path de importacion para los tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    # Permite importar paquetes desde src/ en los tests.
    sys.path.insert(0, str(SRC))
