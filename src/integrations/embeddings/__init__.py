"""Embedding provider integrations."""

from .client import EmbeddingClient, EmbeddingClientError
from .openai_client import (
    AzureOpenAIEmbeddingClient,
    OpenAIEmbeddingClient,
    build_azure_openai_embedding_client_from_env,
    build_openai_embedding_client_from_env,
)

__all__ = [
    "AzureOpenAIEmbeddingClient",
    "EmbeddingClient",
    "EmbeddingClientError",
    "OpenAIEmbeddingClient",
    "build_azure_openai_embedding_client_from_env",
    "build_openai_embedding_client_from_env",
]
