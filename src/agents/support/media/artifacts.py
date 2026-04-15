"""Compatibilidad para helpers multimedia usados por el agente."""

from utils.media_artifacts import (
    is_data_image_url,
    materialize_base64_image,
    materialize_image_reference,
    project_media_dir,
)

__all__ = [
    "is_data_image_url",
    "materialize_base64_image",
    "materialize_image_reference",
    "project_media_dir",
]
