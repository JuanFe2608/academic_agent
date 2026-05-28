"""Helpers mínimos compartidos para repositorios PostgreSQL."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from .errors import RepositoryConfigurationError


def require_database_url(database_url: str | None) -> str:
    """Valida que exista una URL de base de datos utilizable."""

    if not database_url:
        raise RepositoryConfigurationError(
            "ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGPORT/PGDATABASE/PGUSER no estan configurados."
        )
    return database_url


@contextmanager
def postgres_connection(database_url: str) -> Iterator[Any]:
    """Abre una conexion PostgreSQL con `dict_row` y manejo comun de dependencias."""

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RepositoryConfigurationError(
            "psycopg no esta disponible en el entorno actual."
        ) from exc

    with psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=_connect_timeout_seconds(),
    ) as conn:
        yield conn


def _connect_timeout_seconds() -> int:
    raw_timeout = os.getenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", "5").strip()
    try:
        timeout = int(raw_timeout)
    except ValueError:
        return 5
    return max(timeout, 1)
