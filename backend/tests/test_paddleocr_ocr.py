import asyncio
import json

import requests

from app.services.paddleocr_ocr import PaddleOcrProvider, PaddleOcrSettings


def response(status: int = 200, *, payload=None, text: str | None = None) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.url = "https://provider.test/result"
    result._content = (
        text.encode()
        if text is not None
        else json.dumps(payload if payload is not None else {}).encode()
    )
    result.headers["Content-Type"] = "application/json"
    return result


class MockClient:
    def __init__(self, get_responses):
        self.get_responses = iter(get_responses)
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return response(payload={"data": {"jobId": "job-123"}})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return next(self.get_responses)


def settings(**overrides):
    return PaddleOcrSettings(
        token="synthetic-token",
        job_url="https://provider.test/jobs",
        request_timeout=1,
        poll_interval=0.1,
        max_polls=3,
        **overrides,
    )


def test_settings_redacts_token():
    configured = settings()
    assert "synthetic-token" not in repr(configured)


def test_missing_token_is_rejected():
    try:
        PaddleOcrProvider(
            PaddleOcrSettings(
                token="",
                job_url="https://provider.test/jobs",
                request_timeout=1,
                poll_interval=0.1,
                max_polls=3,
            )
        )
    except ValueError as error:
        assert "PADDLEOCR_TOKEN" in str(error)
    else:
        raise AssertionError("Expected missing token to be rejected")


def test_submit_poll_and_parse_jsonl():
    jsonl = "\n".join(
        [
            json.dumps(
                {
                    "result": {
                        "layoutParsingResults": [
                            {"markdown": {"text": "Page one", "images": {}}}
                        ]
                    }
                }
            ),
            json.dumps(
                {
                    "result": {
                        "layoutParsingResults": [
                            {"markdown": {"text": "Page two", "images": {}}}
                        ]
                    }
                }
            ),
        ]
    )
    client = MockClient(
        [
            response(payload={"data": {"state": "pending"}}),
            response(
                payload={
                    "data": {
                        "state": "done",
                        "resultUrl": {"jsonUrl": "https://provider.test/result.jsonl"},
                    }
                }
            ),
            response(text=jsonl),
        ]
    )
    provider = PaddleOcrProvider(settings(), client=client, sleep=lambda _: None)

    raw_text, confidence, metadata = asyncio.run(
        provider.extract(b"valid image bytes", "image/png", "scan.png")
    )

    assert raw_text == "Page one\n\nPage two"
    assert confidence is None
    assert metadata == {
        "engine": "paddleocr",
        "model": "PaddleOCR-VL-1.6",
        "job_id": "job-123",
        "status": "completed",
    }
    post_kwargs = client.posts[0][1]
    assert post_kwargs["headers"]["Authorization"] == "Bearer synthetic-token"
    assert post_kwargs["files"]["file"] == ("scan.png", b"valid image bytes", "image/png")
    assert json.loads(post_kwargs["data"]["optionalPayload"])["useChartRecognition"] is False
    assert "Authorization" not in client.gets[-1][1]


def test_failed_job_remains_unverified_provider_output():
    client = MockClient(
        [response(payload={"data": {"state": "failed", "errorMsg": "private detail"}})]
    )
    provider = PaddleOcrProvider(settings(), client=client, sleep=lambda _: None)

    text, confidence, metadata = asyncio.run(
        provider.extract(b"bytes", "application/pdf", "x.pdf")
    )

    assert text == ""
    assert confidence is None
    assert metadata == {"engine": "paddleocr", "job_id": "job-123", "reason": "job_failed"}


def test_http_error_is_sanitized():
    client = MockClient([response(status=401, payload={"error": "private"})])
    provider = PaddleOcrProvider(settings(), client=client, sleep=lambda _: None)

    text, _, metadata = asyncio.run(provider.extract(b"bytes", "image/jpeg", "x.jpg"))

    assert text == ""
    assert metadata == {"engine": "paddleocr", "reason": "provider_error"}


def test_unsupported_media_type_does_not_call_provider():
    client = MockClient([])
    provider = PaddleOcrProvider(settings(), client=client, sleep=lambda _: None)

    text, _, metadata = asyncio.run(provider.extract(b"bytes", "text/plain", "x.txt"))

    assert text == ""
    assert metadata["reason"] == "unsupported_media_type"
    assert client.posts == []
