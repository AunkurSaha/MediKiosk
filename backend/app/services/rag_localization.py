"""RAG question localization and translation service using configured TranslationProvider."""

import asyncio
import concurrent.futures
import logging
import time
from dataclasses import dataclass

from app.schemas.flow import Localized
from app.services.translation_provider import get_translation_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranslationMeta:
    provider: str
    translated_text: str | None
    fallback_used: bool
    latency_ms: int | None = None
    reason: str | None = None


# Process-level cache for translated questions:
# Key: (canonical_en, target_language) -> (Localized, TranslationMeta)
_TRANSLATION_CACHE: dict[tuple[str, str], tuple[Localized, TranslationMeta]] = {}
_MAX_CACHE_ENTRIES = 128


def _run_sync(coro):
    """Safely execute an async coroutine from synchronous code or threadpool."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def clear_translation_cache() -> None:
    """Clear in-memory translation cache (useful for tests)."""
    _TRANSLATION_CACHE.clear()


def localize_rag_question(
    canonical_en: str,
    target_language: str = "en",
    candidate_id: str | None = None,
) -> tuple[Localized, TranslationMeta]:
    """Localize an approved canonical English RAG question into MediKiosk's supported languages (en, bn, hi).

    Rules:
    1. Canonical English is authoritative and preserved in Localized.en.
    2. If target_language == "en": bypass translation completely to avoid latency.
    3. If target_language in ("bn", "hi"): call configured translation provider (e.g. Sarvam).
    4. On translation failure/timeout: fallback safely to canonical_en without failing clinical intake.
    5. Preserves clinical identity: candidate_id, target_field, concepts are unchanged.
    """
    clean_en = canonical_en.strip()
    clean_lang = (target_language or "en").strip().lower()
    if clean_lang not in ("en", "bn", "hi"):
        clean_lang = "en"

    cache_key = (clean_en, clean_lang)
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]

    # English path: bypass translation entirely
    if clean_lang == "en":
        localized = Localized(en=clean_en, bn=clean_en, hi=clean_en)
        meta = TranslationMeta(
            provider="none",
            translated_text=clean_en,
            fallback_used=False,
            latency_ms=0,
            reason=None,
        )
        if len(_TRANSLATION_CACHE) < _MAX_CACHE_ENTRIES:
            _TRANSLATION_CACHE[cache_key] = (localized, meta)
        return localized, meta

    # Non-English path (bn or hi): call translation provider
    provider = get_translation_provider()
    provider_name = getattr(provider, "name", "unknown")
    start_time = time.perf_counter()

    try:
        coro = provider.translate(
            text=clean_en,
            source_language="en",
            target_language=clean_lang,
        )
        response = _run_sync(coro)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        if response.status == "success" and response.translated_text:
            translated = response.translated_text.strip()
            if clean_lang == "bn":
                localized = Localized(en=clean_en, bn=translated, hi=clean_en)
            else:  # hi
                localized = Localized(en=clean_en, bn=clean_en, hi=translated)

            meta = TranslationMeta(
                provider=response.provider or provider_name,
                translated_text=translated,
                fallback_used=False,
                latency_ms=latency_ms,
                reason=None,
            )
            logger.info(
                "RAG candidate %s localized to %s in %d ms via %s",
                candidate_id,
                clean_lang,
                latency_ms,
                response.provider or provider_name,
            )
        else:
            # Provider returned unavailable or empty response
            logger.warning(
                "RAG translation to %s unavailable: %s; using canonical English fallback",
                clean_lang,
                response.reason,
            )
            localized = Localized(en=clean_en, bn=clean_en, hi=clean_en)
            meta = TranslationMeta(
                provider=response.provider or provider_name,
                translated_text=clean_en,
                fallback_used=True,
                latency_ms=latency_ms,
                reason=response.reason or "unavailable",
            )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        logger.warning(
            "RAG translation exception for candidate %s to %s: %s; using canonical English fallback",
            candidate_id,
            clean_lang,
            exc,
        )
        localized = Localized(en=clean_en, bn=clean_en, hi=clean_en)
        meta = TranslationMeta(
            provider=provider_name,
            translated_text=clean_en,
            fallback_used=True,
            latency_ms=latency_ms,
            reason=type(exc).__name__,
        )

    if len(_TRANSLATION_CACHE) < _MAX_CACHE_ENTRIES:
        _TRANSLATION_CACHE[cache_key] = (localized, meta)

    return localized, meta
