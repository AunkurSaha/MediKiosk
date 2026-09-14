"""PaddleOCR AI Studio asynchronous job provider."""

import asyncio
import json
import os
import time
from typing import Any, Protocol

import requests
from pydantic import BaseModel, ConfigDict, Field, SecretStr

DEFAULT_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_MODEL = "PaddleOCR-VL-1.6"


class PaddleOcrSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    token: SecretStr = Field(exclude=True, repr=False)
    job_url: str = DEFAULT_JOB_URL
    model: str = DEFAULT_MODEL
    request_timeout: float = Field(default=30.0, ge=1.0, le=120.0)
    poll_interval: float = Field(default=5.0, ge=0.1, le=30.0)
    max_polls: int = Field(default=60, ge=1, le=360)

    @classmethod
    def from_environment(cls) -> "PaddleOcrSettings":
        return cls(
            token=SecretStr(os.getenv("PADDLEOCR_TOKEN", "").strip()),
            job_url=os.getenv("PADDLEOCR_JOB_URL", DEFAULT_JOB_URL).strip(),
            model=os.getenv("PADDLEOCR_MODEL", DEFAULT_MODEL).strip(),
            request_timeout=float(os.getenv("PADDLEOCR_REQUEST_TIMEOUT_SECONDS", "30")),
            poll_interval=float(os.getenv("PADDLEOCR_POLL_INTERVAL_SECONDS", "5")),
            max_polls=int(os.getenv("PADDLEOCR_MAX_POLLS", "60")),
        )


class RequestsClient(Protocol):
    def post(self, url: str, **kwargs: Any) -> requests.Response: ...

    def get(self, url: str, **kwargs: Any) -> requests.Response: ...


def _reason(error: Exception) -> str:
    if isinstance(error, requests.Timeout):
        return "timeout"
    if isinstance(error, requests.RequestException):
        return "provider_error"
    if isinstance(error, (KeyError, TypeError, ValueError, json.JSONDecodeError)):
        return "invalid_provider_response"
    return "provider_error"


class PaddleOcrProvider:
    name = "paddleocr"
    version = DEFAULT_MODEL

    def __init__(
        self,
        settings: PaddleOcrSettings,
        client: RequestsClient | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        if not settings.token.get_secret_value():
            raise ValueError("PADDLEOCR_TOKEN is required when OCR_PROVIDER=paddleocr")
        self.settings = settings
        self.version = settings.model
        self._client = client or requests.Session()
        self._sleep = sleep
        self.operation_timeout = (
            settings.request_timeout * 2
            + settings.max_polls * (settings.poll_interval + settings.request_timeout)
        )

    async def extract(
        self,
        image_bytes: bytes,
        media_type: str,
        filename: str,
    ) -> tuple[str, float | None, dict[str, Any]]:
        clean_media = media_type.split(";", 1)[0].strip().lower()
        if clean_media not in (
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
            "application/pdf",
        ):
            return "", None, {"engine": self.name, "reason": "unsupported_media_type"}
        if not image_bytes or len(image_bytes) > 10 * 1024 * 1024:
            return "", None, {"engine": self.name, "reason": "invalid_file_size"}

        try:
            return await asyncio.to_thread(
                self._extract_sync, image_bytes, clean_media, filename
            )
        except Exception as error:
            return "", None, {"engine": self.name, "reason": _reason(error)}

    def _extract_sync(
        self, image_bytes: bytes, media_type: str, filename: str
    ) -> tuple[str, float | None, dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.settings.token.get_secret_value()}"}
        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }
        response = self._client.post(
            self.settings.job_url,
            headers=headers,
            data={
                "model": self.settings.model,
                "optionalPayload": json.dumps(optional_payload),
            },
            files={"file": (filename, image_bytes, media_type)},
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        job_id = response.json()["data"]["jobId"]

        for _ in range(self.settings.max_polls):
            status_response = self._client.get(
                f"{self.settings.job_url}/{job_id}",
                headers=headers,
                timeout=self.settings.request_timeout,
            )
            status_response.raise_for_status()
            data = status_response.json()["data"]
            state = data["state"]
            if state == "done":
                json_url = data["resultUrl"]["jsonUrl"]
                result_response = self._client.get(
                    json_url, timeout=self.settings.request_timeout
                )
                result_response.raise_for_status()
                raw_text = self._parse_jsonl(result_response.text)
                return raw_text, None, {
                    "engine": self.name,
                    "model": self.settings.model,
                    "job_id": job_id,
                    "status": "completed",
                }
            if state == "failed":
                return "", None, {
                    "engine": self.name,
                    "job_id": job_id,
                    "reason": "job_failed",
                }
            if state not in ("pending", "running"):
                return "", None, {
                    "engine": self.name,
                    "job_id": job_id,
                    "reason": "invalid_job_state",
                }
            self._sleep(self.settings.poll_interval)

        return "", None, {"engine": self.name, "job_id": job_id, "reason": "timeout"}

    @staticmethod
    def _parse_jsonl(content: str) -> str:
        pages: list[str] = []
        for line in content.splitlines():
            if not line.strip():
                continue
            result = json.loads(line)["result"]
            for parsed_page in result.get("layoutParsingResults", []):
                text = parsed_page.get("markdown", {}).get("text", "")
                if text.strip():
                    pages.append(text.strip())
        return "\n\n".join(pages)
