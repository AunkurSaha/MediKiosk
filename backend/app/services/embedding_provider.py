"""Embedding provider abstraction for RAG retrieval."""

from __future__ import annotations

import logging
import math
import os
from time import perf_counter
from typing import List, Protocol
from urllib.parse import urlsplit

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core.errors import ProviderFailure, ProviderUnavailable

logger = logging.getLogger(__name__)

DEFAULT_NVIDIA_EMBEDDING_MODEL = "nvidia/nemotron-3-embed-1b"
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_TIMEOUT_SECONDS = 8.0


class EmbeddingProvider(Protocol):
    name: str
    version: str
    model: str

    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        ...

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of document texts."""
        ...

    async def embed(self, text: str) -> List[float]:
        """Alias for embed_query."""
        ...

    async def embed_many(self, texts: List[str]) -> List[List[float]]:
        """Alias for embed_documents."""
        ...


class MockEmbeddingProvider:
    """Deterministic mock embedding provider for testing and demo.

    Returns a fixed-size 384-dimensional unit vector based on SHA-256 hash.
    Ensures offline reproducibility without external network dependencies.
    """

    name = "mock"
    version = "0.1.0"
    model = "mock"

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _hash_to_vector(self, text: str) -> List[float]:
        import hashlib

        text_norm = (text or "").strip().lower()
        if not text_norm:
            raise ValueError("Text to embed must be non-empty")
        hash_bytes = hashlib.sha256(text_norm.encode("utf-8")).digest()
        raw = []
        for i in range(self.dimension):
            b = hash_bytes[i % len(hash_bytes)]
            val = ((b + (i * 7)) % 256) / 127.5 - 1.0
            raw.append(val)
        norm = math.sqrt(sum(x * x for x in raw))
        if norm > 0:
            return [x / norm for x in raw]
        return raw

    async def embed_query(self, text: str) -> List[float]:
        return self._hash_to_vector(text)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return [self._hash_to_vector(t) for t in texts]

    async def embed(self, text: str) -> List[float]:
        return await self.embed_query(text)

    async def embed_many(self, texts: List[str]) -> List[List[float]]:
        return await self.embed_documents(texts)


class DisabledProvider:
    """Disabled embedding provider that raises ProviderUnavailable when invoked."""

    name = "disabled"
    version = "1.0.0"
    model = "disabled"
    dimension = 0

    async def embed_query(self, text: str) -> List[float]:
        raise ProviderUnavailable()

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise ProviderUnavailable()

    async def embed(self, text: str) -> List[float]:
        raise ProviderUnavailable()

    async def embed_many(self, texts: List[str]) -> List[List[float]]:
        raise ProviderUnavailable()


class NvidiaEmbeddingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr = Field(exclude=True, repr=False)
    model: str = DEFAULT_NVIDIA_EMBEDDING_MODEL
    base_url: str = DEFAULT_NVIDIA_BASE_URL
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    dimension: int = 2048

    @classmethod
    def validate_base_url_str(cls, base: str) -> str:
        base = base.rstrip("/")
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "NVIDIA_BASE_URL must be an HTTPS base URL without credentials/query/fragment"
            )
        return base

    @classmethod
    def from_environment(cls) -> NvidiaEmbeddingSettings:
        base = cls.validate_base_url_str(os.getenv("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL))
        model = os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_NVIDIA_EMBEDDING_MODEL).strip()
        if not model or len(model) > 160 or any(c.isspace() for c in model):
            raise ValueError("Invalid RAG_EMBEDDING_MODEL")
        try:
            timeout_val = float(os.getenv("RAG_EMBEDDING_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        except ValueError:
            raise ValueError("Invalid RAG_EMBEDDING_TIMEOUT_SECONDS") from None
        if not 0.1 <= timeout_val <= 60.0:
            raise ValueError("RAG_EMBEDDING_TIMEOUT_SECONDS must be between 0.1 and 60.0 seconds")
        key_str = os.getenv("NVIDIA_API_KEY", "").strip()
        return cls(
            api_key=SecretStr(key_str),
            model=model,
            base_url=base,
            timeout=timeout_val,
        )


class NvidiaEmbeddingProvider:
    """NVIDIA NIM semantic embedding provider.

    Calls the NVIDIA NIM embeddings endpoint (e.g. /v1/embeddings)
    and validates numeric vector outputs and dimensionality.
    """

    name = "nvidia"
    version = "1.0.0"

    def __init__(self, settings: NvidiaEmbeddingSettings | None = None, *, transport=None):
        self.settings = settings or NvidiaEmbeddingSettings.from_environment()
        self.model = self.settings.model
        self._transport = transport
        self.latency_ms: int | None = None

    def _validate_vector(self, vec: object, expected_dim: int | None = None) -> List[float]:
        if not isinstance(vec, list) or len(vec) == 0:
            raise ProviderFailure("empty_vector")
        if expected_dim is not None and len(vec) != expected_dim:
            raise ProviderFailure("dimension_mismatch")
        cleaned: List[float] = []
        for x in vec:
            if not isinstance(x, (int, float)) or math.isnan(x) or math.isinf(x):
                raise ProviderFailure("invalid_result")
            cleaned.append(float(x))
        return cleaned

    async def _call_api(self, texts: List[str], input_type: str) -> List[List[float]]:
        if not texts:
            return []
        api_key = self.settings.api_key.get_secret_value()
        if not api_key:
            raise ProviderFailure("missing_api_key")

        payload = {
            "model": self.model,
            "input": texts,
            "input_type": input_type,
        }

        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self.settings.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
                if response.status_code != 200:
                    reason = (
                        "authentication_failed"
                        if response.status_code in (401, 403)
                        else "rate_limited"
                        if response.status_code == 429
                        else "server_error"
                        if response.status_code >= 500
                        else "provider_unavailable"
                    )
                    raise ProviderFailure(reason)

                data = response.json()
                items = data.get("data")
                if not isinstance(items, list) or len(items) != len(texts):
                    raise ProviderFailure("invalid_result")

                # Sort by index if provided
                if any("index" in item for item in items):
                    items = sorted(items, key=lambda it: it.get("index", 0))

                vectors: List[List[float]] = []
                dim: int | None = None
                for it in items:
                    raw_vec = it.get("embedding")
                    v = self._validate_vector(raw_vec, expected_dim=dim)
                    if dim is None:
                        dim = len(v)
                    vectors.append(v)
                return vectors

        except httpx.TimeoutException:
            raise ProviderFailure("timeout") from None
        except httpx.RequestError:
            raise ProviderFailure("network_error") from None
        except (ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, ProviderFailure):
                raise
            raise ProviderFailure("invalid_result") from None
        finally:
            self.latency_ms = round((perf_counter() - started) * 1000)

    async def embed_query(self, text: str) -> List[float]:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("Text to embed must be non-empty")
        vectors = await self._call_api([cleaned], input_type="query")
        if not vectors:
            raise ProviderFailure("empty_vector")
        return vectors[0]

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned_texts = []
        for t in texts:
            c = (t or "").strip()
            if not c:
                raise ValueError("All documents to embed must be non-empty")
            cleaned_texts.append(c)
        return await self._call_api(cleaned_texts, input_type="passage")

    async def embed(self, text: str) -> List[float]:
        return await self.embed_query(text)

    async def embed_many(self, texts: List[str]) -> List[List[float]]:
        return await self.embed_documents(texts)


def configured_provider() -> EmbeddingProvider:
    """Return the embedding provider based on environment variable.

    Environment variable: RAG_EMBEDDING_PROVIDER
    Values: mock (default), disabled, nvidia
    """
    name = os.getenv("RAG_EMBEDDING_PROVIDER", "mock").strip().lower()
    if name == "mock":
        return MockEmbeddingProvider()
    if name == "disabled":
        return DisabledProvider()
    if name == "nvidia":
        return NvidiaEmbeddingProvider()
    raise ValueError(
        "RAG_EMBEDDING_PROVIDER must be mock, disabled, or nvidia"
    )


def validate_configuration():
    """Validate that the embedding provider is configured correctly."""
    configured_provider()
