"""Opt-in, synthetic-only hosted capability probe. Never emits request/error bodies."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import httpx2 as httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


async def main():
    load_dotenv(ROOT / "backend/.env")
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        raise SystemExit("NVIDIA_API_KEY is missing; no request sent.")
    model = os.getenv("CLINICAL_NORMALIZATION_MODEL", "google/gemma-4-31b-it")
    base = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip(
        "/"
    )
    if base != "https://integrate.api.nvidia.com/v1":
        raise SystemExit(
            "Capability probe is restricted to the requested NVIDIA hosted endpoint."
        )
    schema = {
        "type": "object",
        "properties": {"probe": {"type": "string", "enum": ["schema_enforced"]}},
        "required": ["probe"],
        "additionalProperties": False,
    }
    cases = [
        (
            "strict_json_schema",
            {
                "type": "json_schema",
                "json_schema": {"name": "probe", "strict": True, "schema": schema},
            },
            'Return JSON {"probe":"prompt_value"}.',
        ),
        ("json_object", {"type": "json_object"}, 'Return JSON {"probe":"json_ok"}.'),
        (
            "json_object_enforcement",
            {"type": "json_object"},
            "Return only the plain text hello, without JSON.",
        ),
        ("prompt_only", None, 'Return only JSON {"probe":"prompt_ok"}, no markdown.'),
        (
            "invalid_format_control",
            {"type": "unsupported_probe_format"},
            'Return only JSON {"probe":"control"}.',
        ),
    ]
    results = []
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=False, trust_env=False
    ) as client:
        for name, response_format, instruction in cases:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Follow the output contract."},
                    {"role": "user", "content": instruction},
                ],
                "temperature": 0,
                "stream": False,
                "max_tokens": 128,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            if response_format:
                payload["response_format"] = response_format
            started = perf_counter()
            result = {"case": name}
            try:
                response = await client.post(
                    base + "/chat/completions",
                    headers={"Authorization": "Bearer " + key},
                    json=payload,
                )
                result["http_status"] = response.status_code
                if response.status_code == 200:
                    data = response.json()
                    choice = data["choices"][0]
                    message = choice["message"]
                    result["finish_reason"] = choice.get("finish_reason")
                    result["reasoning_content_present"] = bool(
                        message.get("reasoning_content")
                    )
                    # Only whitelist synthetic probe values, never print arbitrary model output.
                    try:
                        parsed = json.loads(message["content"])
                        result["valid_json_object"] = isinstance(parsed, dict)
                        result["schema_enforced"] = parsed == {
                            "probe": "schema_enforced"
                        }
                    except (ValueError, TypeError):
                        result["valid_json_object"] = False
                    usage = data.get("usage") or {}
                    result["usage"] = {
                        k: v
                        for k, v in usage.items()
                        if k in ("prompt_tokens", "completion_tokens", "total_tokens")
                        and type(v) is int
                    }
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                result["error_category"] = type(exc).__name__
            result["latency_ms"] = round((perf_counter() - started) * 1000)
            results.append(result)
            print(json.dumps(result), flush=True)
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "endpoint": base + "/chat/completions",
        "model": model,
        "settings": {
            "temperature": 0,
            "stream": False,
            "max_tokens": 128,
            "enable_thinking": False,
        },
        "cases": results,
    }
    (ROOT / ".runtime").mkdir(exist_ok=True)
    (ROOT / ".runtime/nvidia-capabilities.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
