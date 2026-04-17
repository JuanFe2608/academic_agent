"""Tests for embedding provider helpers."""

from __future__ import annotations

from integrations.embeddings.openai_client import _normalize_azure_endpoint


def test_normalize_azure_endpoint_accepts_full_embeddings_url() -> None:
    endpoint = (
        "https://example.openai.azure.com/openai/deployments/embed/embeddings"
        "?api-version=2024-12-01-preview"
    )

    assert _normalize_azure_endpoint(endpoint) == "https://example.openai.azure.com"


def test_normalize_azure_endpoint_keeps_resource_endpoint() -> None:
    assert (
        _normalize_azure_endpoint("https://example.openai.azure.com/")
        == "https://example.openai.azure.com"
    )
