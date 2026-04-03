"""Carga perezosa del archivo .env del proyecto."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_project_env() -> bool:
    """Carga el primer `.env` encontrado al subir desde cwd y desde `src/`."""

    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return False

    seen: set[Path] = set()
    starts = (Path.cwd().resolve(), Path(__file__).resolve().parent)
    for start in starts:
        for base in (start, *start.parents):
            candidate = base / ".env"
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.is_file():
                load_dotenv(candidate, override=False)
                return True
    return False
