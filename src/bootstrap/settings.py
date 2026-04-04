"""Resolucion centralizada de configuracion compartida del runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

from project_env import load_project_env

_DEFAULT_POSTGRES_PORT = "5432"


@dataclass(frozen=True)
class BootstrapSettings:
    """Settings compartidos usados por bootstrap e infraestructura."""

    database_url: str = ""
    checkpoint_database_url: str = ""


def load_bootstrap_settings() -> BootstrapSettings:
    """Carga la configuracion compartida desde variables de entorno."""

    settings = _settings_from_current_env()
    if settings.database_url or settings.checkpoint_database_url:
        return settings

    load_project_env()
    return _settings_from_current_env()


def database_url_from_env() -> str:
    """Retorna la URL canonica de PostgreSQL de la aplicacion."""

    return load_bootstrap_settings().database_url


def checkpoint_database_url_from_env() -> str:
    """Retorna la URL efectiva para el checkpointer de LangGraph."""

    return load_bootstrap_settings().checkpoint_database_url


def _settings_from_current_env() -> BootstrapSettings:
    database_url = _resolve_database_url()
    return BootstrapSettings(
        database_url=database_url,
        checkpoint_database_url=_resolve_checkpoint_database_url(database_url),
    )


def _resolve_database_url() -> str:
    explicit_url = os.getenv("ACADEMIC_AGENT_DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url

    host = os.getenv("PGHOST", "").strip()
    port = os.getenv("PGPORT", "").strip() or _DEFAULT_POSTGRES_PORT
    database = os.getenv("PGDATABASE", "").strip()
    user = os.getenv("PGUSER", "").strip()
    password = os.getenv("PGPASSWORD", "").strip()

    if not (host and database and user):
        return ""

    user_part = quote(user, safe="")
    password_part = f":{quote(password, safe='')}" if password else ""
    return f"postgresql://{user_part}{password_part}@{host}:{port}/{database}"


def _resolve_checkpoint_database_url(default_database_url: str) -> str:
    explicit_url = os.getenv("LANGGRAPH_CHECKPOINTER_DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url

    postgres_uri = os.getenv("POSTGRES_URI", "").strip()
    if postgres_uri and postgres_uri != ":memory:":
        return postgres_uri

    return default_database_url
