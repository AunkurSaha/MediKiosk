"""Sarvam Document Intelligence / OCR provider using the pinned official Python SDK."""

import asyncio
import os
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sarvamai import SarvamAI
from sarvamai.errors import ForbiddenError, TooManyRequestsError, UnauthorizedError

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_MAX_POLLS = 16  # 16 * 0.5s = 8 seconds polling window


class SarvamOcrSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr = Field(exclude=True, repr=False)
    timeout: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1, le=30)
    poll_interval: float = Field(default=DEFAULT_POLL_INTERVAL_SECONDS, ge=0.1, le=2.0)
    max_polls: int = Field(default=DEFAULT_MAX_POLLS, ge=1, le=40)

    @classmethod
    def from_environment(cls) -> "SarvamOcrSettings":
        key = os.getenv("SARVAM_API_KEY", "").strip()
        try:
            timeout = int(os.getenv("SARVAM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        except ValueError:
            raise ValueError("SARVAM_TIMEOUT_SECONDS must be an integer") from None
        return cls(
            api_key=SecretStr(key),
            timeout=timeout,
        )


def _failure_reason(error: Exception) -> str:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, (UnauthorizedError, ForbiddenError)):
        return "authentication_failed"
    if isinstance(error, TooManyRequestsError):
        return "rate_limited"
    return "provider_error"


class SarvamOcrProvider:
    name: str = "sarvam"
    version: str = "doc-ai-digitise-v1"

    def __init__(
        self,
        settings: SarvamOcrSettings,
        client_factory: Callable[..., Any] = SarvamAI,
    ) -> None:
        self.settings = settings
        self._client = client_factory(
            api_subscription_key=settings.api_key.get_secret_value(),
            timeout=settings.timeout,
        )

    async def extract(
        self,
        image_bytes: bytes,
        media_type: str,
        filename: str,
    ) -> tuple[str, float | None, dict[str, Any]]:
        clean_media = media_type.split(";", 1)[0].strip().lower()
        if clean_media not in ("image/png", "image/jpeg", "image/jpg", "application/pdf"):
            return "", None, {"engine": self.name, "reason": "unsupported_media_type"}

        if not image_bytes or len(image_bytes) > 10 * 1024 * 1024:
            return "", None, {"engine": self.name, "reason": "invalid_file_size"}

        try:
            # 1. Start digitization job asynchronously in threadpool to keep event loop free
            start_response = await asyncio.to_thread(
                self._client.doc_ai.digitise,
                file=[(filename, image_bytes, clean_media)],
                output_format="md",
            )
            job_id = getattr(start_response, "job_id", None)
            if not job_id:
                return "", None, {"engine": self.name, "reason": "job_start_failed"}

            # 2. Poll job status within bounded limit
            completed = False
            for _ in range(self.settings.max_polls):
                await asyncio.sleep(self.settings.poll_interval)
                status_res = await asyncio.to_thread(self._client.doc_ai.get_status, job_id)
                current_status = getattr(status_res, "status", "")
                if current_status == "completed":
                    completed = True
                    break
                if current_status in ("failed", "cancelled"):
                    return "", None, {"engine": self.name, "job_id": job_id, "reason": f"job_{current_status}"}

            if not completed:
                return "", None, {"engine": self.name, "job_id": job_id, "reason": "timeout"}

            # 3. Retrieve results and assemble extracted text
            results = await asyncio.to_thread(self._client.doc_ai.get_results, job_id)
            results_dict = results.model_dump() if hasattr(results, "model_dump") else (results if isinstance(results, dict) else {})
            
            blocks_text = []
            for doc in results_dict.get("documents", []):
                for page in doc.get("pages", []):
                    for block in page.get("blocks", []):
                        txt = block.get("text", "")
                        if txt and txt.strip():
                            blocks_text.append(txt.strip())

            raw_text = "\n\n".join(blocks_text)
            metadata = {
                "engine": self.name,
                "model": self.version,
                "job_id": job_id,
                "status": "completed",
            }
            # Strictly nullable confidence per non-negotiable clinical boundary
            return raw_text, None, metadata

        except Exception as error:
            return "", None, {"engine": self.name, "reason": _failure_reason(error)}
