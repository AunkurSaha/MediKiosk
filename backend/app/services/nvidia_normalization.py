"""Small NVIDIA HTTP adapter. No clinical policy, retry, fallback or secret serialization."""

import json
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.schemas.normalization import LiveProviderResult, ProviderInput, TokenUsage
from app.services.normalization_provider import (
    ProviderFailure,
    UnsupportedLanguage,
    concept_catalog,
    timeout_seconds,
)

DEFAULT_MODEL = "google/gemma-4-31b-it"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
PROMPT_VERSION = "nvidia-1.0"
PROMPT_PATH = Path(__file__).resolve().parents[3] / "ai/prompts/clinical_normalization_nvidia_v1.md"


class NvidiaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr = Field(exclude=True, repr=False)
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 8
    max_tokens: int = 768

    @classmethod
    def from_environment(cls):
        base = os.getenv("NVIDIA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        parsed = urlsplit(base)
        # Operator-configured HTTPS hosts only; never redirects or credentials in a URL.
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
        model = os.getenv("CLINICAL_NORMALIZATION_MODEL", DEFAULT_MODEL).strip()
        if not model or len(model) > 160 or any(c.isspace() for c in model):
            raise ValueError("Invalid CLINICAL_NORMALIZATION_MODEL")
        try:
            budget = int(os.getenv("CLINICAL_NORMALIZATION_MAX_TOKENS", "768"))
        except ValueError:
            raise ValueError("Invalid CLINICAL_NORMALIZATION_MAX_TOKENS") from None
        if not 128 <= budget <= 1536:
            raise ValueError("CLINICAL_NORMALIZATION_MAX_TOKENS must be between 128 and 1536")
        return cls(
            api_key=SecretStr(os.getenv("NVIDIA_API_KEY", "").strip()),
            model=model,
            base_url=base,
            timeout=timeout_seconds(),
            max_tokens=budget,
        )


def strict_json(text):
    """Reject duplicate JSON keys and nonstandard numeric constants, without repairing output."""

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    def invalid_constant(_):
        raise ValueError("Nonstandard JSON constant")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


class NvidiaClinicalNormalizationProvider:
    name = "nvidia"
    version = "1.0.0"
    prompt_version = PROMPT_VERSION

    def __init__(self, settings=None, *, transport=None):
        self.settings = settings or NvidiaSettings.from_environment()
        self.model = self.settings.model
        self._transport = transport
        self.latency_ms = None
        self.token_usage = None
        self.http_status = None

    def payload(self, request):
        # Intentionally exclude request.context: it contains internal flow/question identifiers.
        source = {
            "text": request.text,
            "language": request.language,
            "canonical_field": request.canonical_field,
        }
        instructions = PROMPT_PATH.read_text(encoding="utf-8")
        instructions += "\nAllowed concepts and trusted meanings:\n" + json.dumps(
            concept_catalog(), ensure_ascii=False
        )
        instructions += "\nOutput JSON schema:\n" + json.dumps(
            LiveProviderResult.model_json_schema(), ensure_ascii=False
        )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
            "max_tokens": self.settings.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }

    async def normalize(self, request: ProviderInput) -> object:
        self.latency_ms, self.token_usage, self.http_status = None, None, None
        started = perf_counter()
        try:
            if request.language not in ("en", "bn", "hi"):
                raise UnsupportedLanguage()
            if not self.settings.api_key.get_secret_value():
                raise ProviderFailure("missing_api_key")
            async with httpx.AsyncClient(
                timeout=self.settings.timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                # Stream the transport to cap bytes; the inference itself is explicitly non-streaming.
                async with client.stream(
                    "POST",
                    self.settings.base_url + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + self.settings.api_key.get_secret_value(),
                        "Accept": "application/json",
                    },
                    json=self.payload(request),
                ) as response:
                    self.http_status = response.status_code
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
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise ProviderFailure("invalid_result")
            try:
                data = strict_json(body)
                usage = data.get("usage") or {}
                self.token_usage = TokenUsage.model_validate(
                    {
                        k: usage[k]
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                        if k in usage
                    }
                )
                choices = data["choices"]
                if not isinstance(choices, list) or len(choices) != 1:
                    raise ValueError("Expected one completion")
                choice = choices[0]
                if choice.get("finish_reason") == "length":
                    raise ProviderFailure("truncated_response")
                if choice.get("finish_reason") != "stop":
                    raise ValueError("Incomplete completion")
                message = choice["message"]
                if message.get("tool_calls") or message.get("refusal"):
                    raise ValueError("Not a normalization response")
                content = message["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Empty content")
                parsed = strict_json(content)
                # Validate once at the adapter boundary and again at the domain boundary.
                return LiveProviderResult.model_validate(parsed).model_dump()
            except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
                raise ProviderFailure("invalid_result") from None
        except httpx.TimeoutException:
            raise TimeoutError() from None
        except httpx.RequestError:
            raise ProviderFailure("network_error") from None
        finally:
            self.latency_ms = round((perf_counter() - started) * 1000)
