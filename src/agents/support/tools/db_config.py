"""Resolución compartida de la URL de PostgreSQL desde el entorno."""

from __future__ import annotations

import os
from urllib.parse import quote


def database_url_from_env() -> str:
    """Construye la URL de PostgreSQL desde variables de entorno."""

    explicit_url = os.getenv("ACADEMIC_AGENT_DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url

    host = os.getenv("PGHOST", "").strip()
    port = os.getenv("PGPORT", "").strip() or "5432"
    database = os.getenv("PGDATABASE", "").strip()
    user = os.getenv("PGUSER", "").strip()
    password = os.getenv("PGPASSWORD", "").strip()

    if not (host and database and user):
        return ""

    user_part = quote(user, safe="")
    password_part = f":{quote(password, safe='')}" if password else ""
    return f"postgresql://{user_part}{password_part}@{host}:{port}/{database}"
