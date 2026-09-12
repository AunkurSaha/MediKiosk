"""Unit tests for RAG embedding providers.

Covers:
- MockEmbeddingProvider: deterministic 384-dim vectors, unit normalization, batching
- DisabledProvider: fail-open exception raising
- NvidiaEmbeddingProvider: settings validation, mocked httpx2 responses, batching, error translation
- configured_provider() factory
"""

import asyncio
import json

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from app.core.errors import ProviderFailure, ProviderUnavailable
from app.services.embedding_provider import (
    DEFAULT_NVIDIA_BASE_URL,
    DEFAULT_NVIDIA_EMBEDDING_MODEL,
    DisabledProvider,
    MockEmbeddingProvider,
    NvidiaEmbeddingProvider,
    NvidiaEmbeddingSettings,
    configured_provider,
)

# ============================================================================
# MockEmbeddingProvider Tests
# ============================================================================


def test_mock_embedding_provider_dimension_and_determinism():
    provider = MockEmbeddingProvider(dimension=384)
    assert provider.name == "mock"
    assert provider.dimension == 384

    v1 = asyncio.run(provider.embed_query("chest pain on exertion"))
    v2 = asyncio.run(provider.embed_query("chest pain on exertion"))
    assert len(v1) == 384
    assert v1 == v2

    v_diff = asyncio.run(provider.embed_query("shortness of breath"))
    assert v1 != v_diff
    assert any(x != 0.0 for x in v1)


def test_mock_embedding_provider_batching():
    provider = MockEmbeddingProvider(dimension=384)
    texts = ["query 1", "query 2", "query 3"]
    vectors = asyncio.run(provider.embed_documents(texts))
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 384


def test_mock_embedding_empty_text():
    provider = MockEmbeddingProvider()
    with pytest.raises(ValueError, match="must be non-empty"):
        asyncio.run(provider.embed_query("   "))


# ============================================================================
# DisabledProvider Tests
# ============================================================================


def test_disabled_provider_raises_unavailable():
    provider = DisabledProvider()
    assert provider.name == "disabled"

    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.embed_query("test query"))

    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.embed_documents(["doc 1", "doc 2"]))


# ============================================================================
# NvidiaEmbeddingSettings Tests
# ============================================================================


def test_nvidia_settings_validation():
    settings = NvidiaEmbeddingSettings(api_key=SecretStr("test_key"))
    assert settings.base_url == DEFAULT_NVIDIA_BASE_URL
    assert settings.model == DEFAULT_NVIDIA_EMBEDDING_MODEL
    assert settings.api_key.get_secret_value() == "test_key"


@pytest.mark.parametrize(
    "key,value",
    [
        ("NVIDIA_BASE_URL", "http://unsafe.invalid/v1"),
        ("NVIDIA_BASE_URL", "https://secret@nim.invalid/v1"),
        ("NVIDIA_BASE_URL", "https://nim.invalid/v1?key=secret"),
        ("RAG_EMBEDDING_MODEL", ""),
        ("RAG_EMBEDDING_TIMEOUT_SECONDS", "infinity"),
        ("RAG_EMBEDDING_TIMEOUT_SECONDS", "0.0"),
        ("RAG_EMBEDDING_TIMEOUT_SECONDS", "100.0"),
    ],
)
def test_bad_configuration_rejected(monkeypatch, key, value):
    monkeypatch.setenv("NVIDIA_API_KEY", "valid_key")
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        NvidiaEmbeddingSettings.from_environment()


def test_nvidia_settings_from_environment(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "env_key_123")
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://nim.custom.org/v1")
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b")
    monkeypatch.setenv("RAG_EMBEDDING_TIMEOUT_SECONDS", "5.0")

    settings = NvidiaEmbeddingSettings.from_environment()
    assert settings.base_url == "https://nim.custom.org/v1"
    assert settings.model == "nvidia/nemotron-3-embed-1b"
    assert settings.timeout == 5.0
    assert settings.api_key.get_secret_value() == "env_key_123"


# ============================================================================
# NvidiaEmbeddingProvider Tests (Mocked Transport)
# ============================================================================


def test_nvidia_provider_embed_query_success():
    expected_dim = 2048
    fake_embedding = [0.01 * (i % 10) for i in range(expected_dim)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer mock_nv_key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "nvidia/nemotron-3-embed-1b"
        assert body["input"] == ["chest pain"]
        assert body["input_type"] == "query"

        resp = {
            "data": [
                {"index": 0, "embedding": fake_embedding}
            ],
            "model": "nvidia/nemotron-3-embed-1b",
            "usage": {"total_tokens": 5},
        }
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    settings = NvidiaEmbeddingSettings(
        api_key=SecretStr("mock_nv_key"),
        model="nvidia/nemotron-3-embed-1b",
        dimension=2048,
    )
    provider = NvidiaEmbeddingProvider(settings=settings, transport=transport)

    res = asyncio.run(provider.embed_query("chest pain"))
    assert len(res) == 2048
    assert res == fake_embedding


def test_nvidia_provider_embed_documents_batch():
    expected_dim = 2048
    emb1 = [0.1] * expected_dim
    emb2 = [0.2] * expected_dim

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["input_type"] == "passage"
        assert len(body["input"]) == 2
        resp = {
            "data": [
                {"index": 0, "embedding": emb1},
                {"index": 1, "embedding": emb2},
            ],
            "model": "nvidia/nemotron-3-embed-1b",
        }
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    settings = NvidiaEmbeddingSettings(api_key=SecretStr("k"), dimension=2048)
    provider = NvidiaEmbeddingProvider(settings=settings, transport=transport)

    results = asyncio.run(provider.embed_documents(["doc 1", "doc 2"]))
    assert len(results) == 2
    assert results[0] == emb1
    assert results[1] == emb2


def test_nvidia_provider_http_errors():
    # 401 Unauthorized
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    settings = NvidiaEmbeddingSettings(api_key=SecretStr("bad_key"))
    provider = NvidiaEmbeddingProvider(settings=settings, transport=httpx.MockTransport(handler_401))
    with pytest.raises(ProviderFailure, match="authentication_failed"):
        asyncio.run(provider.embed_query("test"))

    # 500 Server Error
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Error")

    provider_500 = NvidiaEmbeddingProvider(settings=settings, transport=httpx.MockTransport(handler_500))
    with pytest.raises(ProviderFailure, match="server_error"):
        asyncio.run(provider_500.embed_query("test"))


def test_nvidia_provider_timeout():
    def handler_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out")

    settings = NvidiaEmbeddingSettings(api_key=SecretStr("key"), timeout=0.1)
    provider = NvidiaEmbeddingProvider(settings=settings, transport=httpx.MockTransport(handler_timeout))

    with pytest.raises(ProviderFailure, match="timeout"):
        asyncio.run(provider.embed_query("test"))


def test_nvidia_provider_malformed_response():
    def handler_malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"missing_embedding": True}]})

    settings = NvidiaEmbeddingSettings(api_key=SecretStr("key"))
    provider = NvidiaEmbeddingProvider(settings=settings, transport=httpx.MockTransport(handler_malformed))

    with pytest.raises(ProviderFailure, match="empty_vector"):
        asyncio.run(provider.embed_query("test"))


# ============================================================================
# configured_provider Factory Tests
# ============================================================================


def test_configured_provider_factory(monkeypatch):
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "mock")
    p1 = configured_provider()
    assert isinstance(p1, MockEmbeddingProvider)

    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "disabled")
    p2 = configured_provider()
    assert isinstance(p2, DisabledProvider)

    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "test_key_abc")
    p3 = configured_provider()
    assert isinstance(p3, NvidiaEmbeddingProvider)

    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "unknown_provider")
    with pytest.raises(ValueError, match="RAG_EMBEDDING_PROVIDER must be mock, disabled, or nvidia"):
        configured_provider()
