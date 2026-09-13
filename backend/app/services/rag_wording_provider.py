"""Provider abstraction for wording an already-approved RAG clinical question.

CRITICAL ARCHITECTURAL RULE:
The LLM does NOT decide what clinical information to collect, candidate_id,
target_field, target_concepts, whether a question is redundant, whether RAG should
run, red-flag priority, mandatory workflow priority, RAG budget, source chunk
selection, or whether the interview is complete.

The LLM is invoked ONLY after a candidate has already survived:
- deterministic candidate retrieval
- field deduplication
- concept deduplication
- positive/negative fact checking
- previous-question checking
- grounding validation
- budget checking
- safety/workflow priority

The LLM ONLY formulates patient-friendly phrasing for that approved candidate.
If generation fails or fails validation, the system falls back immediately to
the deterministic template question.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, List, Optional
from urllib.parse import urlsplit

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core.config import (
    RAG_GENERATION_MAX_TOKENS,
    RAG_GENERATION_MODEL,
    RAG_GENERATION_PROVIDER,
    RAG_GENERATION_TEMPERATURE,
    RAG_GENERATION_TIMEOUT_SECONDS,
)
from app.services.rag_wording_validator import validate_generated_wording

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parents[3] / "ai/prompts/rag_question_wording_nvidia_v1.md"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_GENERATION_MODEL = "meta/llama-3.2-11b-vision-instruct"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


@dataclass(frozen=True)
class WordingResult:
    question: str
    template_question: str
    provider: str
    model: Optional[str]
    fallback_used: bool
    latency_ms: Optional[int]
    fallback_reason: Optional[str] = None


class NvidiaWordingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr = Field(exclude=True, repr=False)
    model: str = DEFAULT_GENERATION_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 15.0
    temperature: float = 0.1
    max_tokens: int = 100

    @classmethod
    def from_environment(cls) -> "NvidiaWordingSettings":
        base = os.getenv("NVIDIA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("NVIDIA_BASE_URL must be an HTTPS base URL without credentials/query/fragment")

        model = os.getenv("RAG_GENERATION_MODEL", RAG_GENERATION_MODEL or DEFAULT_GENERATION_MODEL).strip()
        if not model or len(model) > 160 or any(c.isspace() for c in model):
            raise ValueError(f"Invalid RAG_GENERATION_MODEL: {model}")

        timeout = float(os.getenv("RAG_GENERATION_TIMEOUT_SECONDS", str(RAG_GENERATION_TIMEOUT_SECONDS)))
        temperature = float(os.getenv("RAG_GENERATION_TEMPERATURE", str(RAG_GENERATION_TEMPERATURE)))
        max_tokens = int(os.getenv("RAG_GENERATION_MAX_TOKENS", str(RAG_GENERATION_MAX_TOKENS)))

        api_key = os.getenv("NVIDIA_API_KEY", "").strip()

        return cls(
            api_key=SecretStr(api_key),
            model=model,
            base_url=base,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
        )


class GroqWordingSettings(BaseModel):
    """Configuration for Groq's OpenAI-compatible chat-completions API."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr = Field(exclude=True, repr=False)
    model: str = DEFAULT_GROQ_MODEL
    base_url: str = DEFAULT_GROQ_BASE_URL
    timeout: float = 6.0
    temperature: float = 0.1
    max_tokens: int = 256

    @classmethod
    def from_environment(cls) -> "GroqWordingSettings":
        base = os.getenv("GROQ_BASE_URL", DEFAULT_GROQ_BASE_URL).rstrip("/")
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("GROQ_BASE_URL must be an HTTPS base URL without credentials/query/fragment")
        model = os.getenv("RAG_GENERATION_MODEL", DEFAULT_GROQ_MODEL).strip()
        if not model or len(model) > 160 or any(char.isspace() for char in model):
            raise ValueError("Invalid RAG_GENERATION_MODEL")
        timeout = float(os.getenv("RAG_GENERATION_TIMEOUT_SECONDS", "6"))
        if not 0.5 <= timeout <= 30:
            raise ValueError("RAG_GENERATION_TIMEOUT_SECONDS must be between 0.5 and 30")
        return cls(
            api_key=SecretStr(os.getenv("GROQ_API_KEY", "").strip()),
            model=model,
            base_url=base,
            timeout=timeout,
            temperature=float(os.getenv("RAG_GENERATION_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("RAG_GENERATION_MAX_TOKENS", "256")),
        )


class RAGWordingProvider:
    name: str = "base"

    def word_candidate(
        self,
        candidate: dict,
        clinical_context: dict,
        supporting_chunks: List[Any],
    ) -> WordingResult:
        raise NotImplementedError


class TemplateWordingProvider(RAGWordingProvider):
    name: str = "template"

    def word_candidate(
        self,
        candidate: dict,
        clinical_context: dict,
        supporting_chunks: List[Any],
    ) -> WordingResult:
        template_q = (candidate.get("question") or "").strip()
        return WordingResult(
            question=template_q,
            template_question=template_q,
            provider="template",
            model=None,
            fallback_used=False,
            latency_ms=0,
            fallback_reason=None,
        )


class DisabledWordingProvider(RAGWordingProvider):
    name: str = "disabled"

    def word_candidate(
        self,
        candidate: dict,
        clinical_context: dict,
        supporting_chunks: List[Any],
    ) -> WordingResult:
        template_q = (candidate.get("question") or "").strip()
        return WordingResult(
            question=template_q,
            template_question=template_q,
            provider="disabled",
            model=None,
            fallback_used=False,
            latency_ms=0,
            fallback_reason=None,
        )


class NvidiaWordingProvider(RAGWordingProvider):
    name: str = "nvidia"

    def __init__(self, settings: Optional[NvidiaWordingSettings] = None, *, transport=None):
        self.settings = settings or NvidiaWordingSettings.from_environment()
        self._transport = transport

    def _build_minimal_clinical_context(
        self,
        candidate: dict,
        clinical_context: dict,
        supporting_chunks: List[Any],
    ) -> str:
        """Construct minimal clinical context without PII, session IDs, or unrelated documents."""
        chief_complaint = "Chest pain"  # Chest pain reference pipeline
        known_texts = clinical_context.get("raw_answer_texts", [])
        known_summary = "; ".join(known_texts[:4]) if known_texts else "central pressure-like discomfort"

        cid = candidate.get("candidate_id", "unknown")
        target_concept = candidate.get("concept") or (
            candidate.get("target_concepts", [cid.upper()])[0]
            if candidate.get("target_concepts")
            else cid.upper()
        )

        chunk_excerpts = []
        for ch in supporting_chunks:
            content = getattr(ch, "content", None) or (ch.get("content") if isinstance(ch, dict) else str(ch))
            if content:
                chunk_excerpts.append(content.strip()[:300])
        supporting_ctx = " ".join(chunk_excerpts) if chunk_excerpts else candidate.get("reason", "")

        fallback_q = candidate.get("question", "").strip()

        return (
            f"Chief complaint: {chief_complaint}\n"
            f"Known clinical facts: {known_summary}\n"
            f"Approved clinical information need: {target_concept}\n"
            f"Retrieved clinical source context: {supporting_ctx}\n"
            f"Deterministic fallback question: {fallback_q}"
        )

    def _build_system_prompt(self) -> str:
        if PROMPT_FILE.exists():
            return PROMPT_FILE.read_text(encoding="utf-8").strip()
        return (
            "You are wording one clinical history-taking question for a patient.\n"
            "The clinical information need has already been selected by a deterministic medical workflow.\n"
            "Your only job is to formulate ONE short, neutral, patient-friendly question asking about that exact information need.\n"
            "Do not diagnose. Do not suggest a diagnosis. Do not recommend treatment. Do not recommend medication.\n"
            "Do not provide medical advice. Do not introduce another symptom or information need.\n"
            "Do not ask multiple questions. Do not mention clinical guidelines, retrieved sources, AI, or reasoning.\n"
            "Do not change the clinical intent.\n"
            'Output strictly a JSON object with this exact schema: {"question": "..."}'
        )

    async def _generate_async(
        self,
        candidate: dict,
        clinical_context: dict,
        supporting_chunks: List[Any],
    ) -> WordingResult:
        template_q = (candidate.get("question") or "").strip()
        cid = candidate.get("candidate_id", "")
        start_time = perf_counter()

        api_key_val = self.settings.api_key.get_secret_value()
        if not api_key_val:
            logger.warning("NVIDIA wording requested but NVIDIA_API_KEY is empty; using template fallback.")
            return WordingResult(
                question=template_q,
                template_question=template_q,
                provider="nvidia",
                model=self.settings.model,
                fallback_used=True,
                latency_ms=0,
                fallback_reason="missing_api_key",
            )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_minimal_clinical_context(candidate, clinical_context, supporting_chunks)

        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": False,
        }

        raw_content = None
        fallback_reason = None

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                headers = {
                    "Authorization": f"Bearer {api_key_val}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                response = await client.post(
                    f"{self.settings.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code != 200:
                    fallback_reason = f"http_{response.status_code}"
                    logger.warning("NVIDIA chat completions returned status %s", response.status_code)
                else:
                    data = response.json()
                    choices = data.get("choices") or []
                    if not choices:
                        fallback_reason = "empty_choices"
                    else:
                        first_choice = choices[0]
                        finish_reason = first_choice.get("finish_reason")
                        if finish_reason == "length":
                            fallback_reason = "truncated_response"
                        else:
                            msg = first_choice.get("message") or {}
                            raw_content = msg.get("content")

        except httpx.TimeoutException:
            fallback_reason = "timeout"
            logger.warning("NVIDIA chat completions timed out after %ss", self.settings.timeout)
        except httpx.RequestError as exc:
            fallback_reason = f"network_error_{type(exc).__name__}"
            logger.warning("NVIDIA chat completions network error: %s", exc)
        except Exception as exc:
            fallback_reason = f"unexpected_error_{type(exc).__name__}"
            logger.warning("NVIDIA chat completions unexpected error: %s", exc)

        latency_ms = round((perf_counter() - start_time) * 1000)

        # If HTTP or network failed, fallback immediately
        if raw_content is None:
            return WordingResult(
                question=template_q,
                template_question=template_q,
                provider="nvidia",
                model=self.settings.model,
                fallback_used=True,
                latency_ms=latency_ms,
                fallback_reason=fallback_reason or "no_content",
            )

        # Deterministic validation and clinical guardrails
        is_valid, validation_reason, final_q = validate_generated_wording(
            raw_content=raw_content,
            candidate_id=cid,
            template_question=template_q,
        )

        if not is_valid:
            logger.info(
                "NVIDIA generated wording rejected by deterministic validator: reason=%s, candidate=%s, fallback_used=True",
                validation_reason,
                cid,
            )
            return WordingResult(
                question=template_q,
                template_question=template_q,
                provider="nvidia",
                model=self.settings.model,
                fallback_used=True,
                latency_ms=latency_ms,
                fallback_reason=f"validation_failed:{validation_reason}",
            )

        logger.info(
            "NVIDIA generated wording accepted: candidate=%s, latency=%sms, question='%s'",
            cid,
            latency_ms,
            final_q,
        )

        return WordingResult(
            question=final_q,
            template_question=template_q,
            provider="nvidia",
            model=self.settings.model,
            fallback_used=False,
            latency_ms=latency_ms,
            fallback_reason=None,
        )

    def word_candidate(
        self,
        candidate: dict,
        clinical_context: dict,
        supporting_chunks: List[Any],
    ) -> WordingResult:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self._generate_async(candidate, clinical_context, supporting_chunks),
                )
                return future.result()
        else:
            return asyncio.run(
                self._generate_async(candidate, clinical_context, supporting_chunks)
            )


def configured_wording_provider(provider_name: Optional[str] = None) -> RAGWordingProvider:
    name = (provider_name or os.getenv("RAG_GENERATION_PROVIDER", RAG_GENERATION_PROVIDER) or "template").strip().lower()
    if name == "nvidia":
        return NvidiaWordingProvider()
    elif name == "disabled":
        return DisabledWordingProvider()
    else:
        return TemplateWordingProvider()
