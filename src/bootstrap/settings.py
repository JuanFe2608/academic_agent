"""Resolucion centralizada de configuracion compartida del runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

from project_env import load_project_env

_DEFAULT_POSTGRES_PORT = "5432"
_DEFAULT_RAG_CORPUS_ROOT = "knowledge_base/study_recommendations"
_DEFAULT_RAG_CORPUS_NAME = "study_recommendations"
_DEFAULT_RAG_EMBEDDING_PROVIDER = "openai"
_DEFAULT_RAG_EMBEDDING_MODEL = "text-embedding-3-small"
_DEFAULT_RAG_EMBEDDING_DIMENSIONS = 1536


@dataclass(frozen=True)
class BootstrapSettings:
    """Settings compartidos usados por bootstrap e infraestructura."""

    database_url: str = ""
    checkpoint_database_url: str = ""


@dataclass(frozen=True)
class RagSettings:
    """Settings del pipeline RAG y retrieval."""

    enabled: bool = False
    corpus_root: str = _DEFAULT_RAG_CORPUS_ROOT
    corpus_name: str = _DEFAULT_RAG_CORPUS_NAME
    embedding_provider: str = _DEFAULT_RAG_EMBEDDING_PROVIDER
    embedding_model: str = _DEFAULT_RAG_EMBEDDING_MODEL
    embedding_dimensions: int = _DEFAULT_RAG_EMBEDDING_DIMENSIONS
    top_k_vector: int = 8
    top_k_lexical: int = 8
    top_k_final: int = 5
    min_score: float = 0.0


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


def load_rag_settings() -> RagSettings:
    """Carga configuracion del pipeline RAG desde variables de entorno."""

    load_project_env()
    inferred_provider = (
        "azure_openai"
        if os.getenv("AZURE_OPENAI_API_KEY_EMBEDDINGS", "").strip()
        else _DEFAULT_RAG_EMBEDDING_PROVIDER
    )
    embedding_provider = os.getenv("RAG_EMBEDDING_PROVIDER", inferred_provider).strip()
    embedding_model_default = (
        os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS", "").strip()
        if embedding_provider in {"azure", "azure_openai"}
        else _DEFAULT_RAG_EMBEDDING_MODEL
    ) or _DEFAULT_RAG_EMBEDDING_MODEL
    return RagSettings(
        enabled=_env_bool("RAG_ENABLED", False),
        corpus_root=os.getenv("RAG_CORPUS_ROOT", _DEFAULT_RAG_CORPUS_ROOT).strip()
        or _DEFAULT_RAG_CORPUS_ROOT,
        corpus_name=os.getenv("RAG_CORPUS_NAME", _DEFAULT_RAG_CORPUS_NAME).strip()
        or _DEFAULT_RAG_CORPUS_NAME,
        embedding_provider=embedding_provider or inferred_provider,
        embedding_model=os.getenv(
            "RAG_EMBEDDING_MODEL",
            embedding_model_default,
        ).strip()
        or embedding_model_default,
        embedding_dimensions=_env_int(
            "RAG_EMBEDDING_DIMENSIONS",
            _DEFAULT_RAG_EMBEDDING_DIMENSIONS,
            minimum=1,
        ),
        top_k_vector=_env_int("RAG_TOP_K_VECTOR", 8, minimum=1),
        top_k_lexical=_env_int("RAG_TOP_K_LEXICAL", 8, minimum=1),
        top_k_final=_env_int("RAG_TOP_K_FINAL", 5, minimum=1),
        min_score=_env_float("RAG_MIN_SCORE", 0.0, minimum=0.0),
    )


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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "si", "on"}


def _env_int(name: str, default: int, *, minimum: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed >= minimum else default


def _env_float(name: str, default: float, *, minimum: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed >= minimum else default
