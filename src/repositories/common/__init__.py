"""Primitivas compartidas de persistencia para repositorios top-level."""

from .errors import RepositoryConfigurationError
from .postgres import postgres_connection, require_database_url

__all__ = [
    "RepositoryConfigurationError",
    "postgres_connection",
    "require_database_url",
]
