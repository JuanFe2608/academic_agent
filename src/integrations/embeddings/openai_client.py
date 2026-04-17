"""OpenAI embeddings client for RAG ingestion."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from project_env import load_project_env

from .client import EmbeddingClientError


class OpenAIEmbeddingClient:
    """Small wrapper around the official OpenAI embeddings API."""

    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise EmbeddingClientError("openai package is not available.") from exc

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings preserving input order."""

        cleaned = [text.strip() for text in texts]
        if not cleaned:
            return []
        if any(not text for text in cleaned):
            raise EmbeddingClientError("Cannot embed empty text chunks.")

        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=cleaned,
                dimensions=self.dimensions,
            )
        except Exception as exc:  # pragma: no cover - network/provider failures
            raise EmbeddingClientError(str(exc)) from exc

        vectors = [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(cleaned):
            raise EmbeddingClientError(
                f"Embedding response count mismatch: expected {len(cleaned)}, got {len(vectors)}."
            )
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingClientError(
                    f"Embedding dimension mismatch: expected {self.dimensions}, got {len(vector)}."
                )
        return vectors


class AzureOpenAIEmbeddingClient:
    """Azure OpenAI embeddings client using a deployment name."""

    provider = "azure_openai"

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        deployment_name: str,
        api_version: str,
        dimensions: int,
    ) -> None:
        self.model = deployment_name
        self.dimensions = dimensions
        try:
            from openai import AzureOpenAI
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise EmbeddingClientError("openai package is not available.") from exc

        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=_normalize_azure_endpoint(endpoint),
            api_version=api_version,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate Azure OpenAI embeddings preserving input order."""

        cleaned = [text.strip() for text in texts]
        if not cleaned:
            return []
        if any(not text for text in cleaned):
            raise EmbeddingClientError("Cannot embed empty text chunks.")

        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=cleaned,
                dimensions=self.dimensions,
            )
        except Exception as exc:  # pragma: no cover - network/provider failures
            raise EmbeddingClientError(str(exc)) from exc

        vectors = [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(cleaned):
            raise EmbeddingClientError(
                f"Embedding response count mismatch: expected {len(cleaned)}, got {len(vectors)}."
            )
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingClientError(
                    f"Embedding dimension mismatch: expected {self.dimensions}, got {len(vector)}."
                )
        return vectors


def build_openai_embedding_client_from_env(
    *,
    model: str,
    dimensions: int,
) -> OpenAIEmbeddingClient:
    """Build an OpenAI embedding client using project environment variables."""

    load_project_env()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise EmbeddingClientError("OPENAI_API_KEY is required for OpenAI embeddings.")
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    return OpenAIEmbeddingClient(
        api_key=api_key,
        model=model,
        dimensions=dimensions,
        base_url=base_url,
    )


def build_azure_openai_embedding_client_from_env(
    *,
    deployment_name: str,
    dimensions: int,
) -> AzureOpenAIEmbeddingClient:
    """Build an Azure OpenAI embedding client from embedding-specific variables."""

    load_project_env()
    api_key = (
        os.getenv("AZURE_OPENAI_API_KEY_EMBEDDINGS", "").strip()
        or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    )
    endpoint = (
        os.getenv("AZURE_OPENAI_ENDPOINT_EMBEDDINGS", "").strip()
        or os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    )
    effective_deployment = (
        deployment_name.strip()
        or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS", "").strip()
    )
    api_version = (
        os.getenv("OPENAI_API_VERSION_EMBEDDINGS", "").strip()
        or os.getenv("OPENAI_API_VERSION", "").strip()
    )
    missing = [
        name
        for name, value in [
            ("AZURE_OPENAI_API_KEY_EMBEDDINGS", api_key),
            ("AZURE_OPENAI_ENDPOINT_EMBEDDINGS", endpoint),
            ("AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS", effective_deployment),
            ("OPENAI_API_VERSION_EMBEDDINGS", api_version),
        ]
        if not value
    ]
    if missing:
        raise EmbeddingClientError(
            "Missing Azure OpenAI embeddings environment variables: "
            + ", ".join(missing)
            + "."
        )
    return AzureOpenAIEmbeddingClient(
        api_key=api_key,
        endpoint=endpoint,
        deployment_name=effective_deployment,
        api_version=api_version,
        dimensions=dimensions,
    )


def _normalize_azure_endpoint(endpoint: str) -> str:
    """Accept either a resource endpoint or a full embeddings URL."""

    parsed = urlsplit(endpoint.strip())
    path = parsed.path or ""
    marker = "/openai/"
    if marker in path:
        path = path.split(marker, 1)[0]
    return urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


__all__ = [
    "AzureOpenAIEmbeddingClient",
    "OpenAIEmbeddingClient",
    "build_azure_openai_embedding_client_from_env",
    "build_openai_embedding_client_from_env",
]
