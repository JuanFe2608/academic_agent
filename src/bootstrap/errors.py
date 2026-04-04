"""Errores compartidos de bootstrap e infraestructura."""

from __future__ import annotations


class BootstrapError(Exception):
    """Error base para bootstrap e infraestructura compartida."""


class InfrastructureConfigurationError(BootstrapError):
    """La configuracion compartida de infraestructura es invalida o incompleta."""


class RepositoryConfigurationError(InfrastructureConfigurationError):
    """La persistencia o sus dependencias no estan configuradas correctamente."""
