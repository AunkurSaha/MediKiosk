"""Explicitly opt-in diagnostic script to evaluate live BHASHINI (ULCA) Speech APIs.

Run from repository root:
    backend/.venv/Scripts/python.exe scripts/evaluate-bhashini-speech.py --run-live

Features:
1. Validates environment configuration and credentials.
2. Discovers ULCA pipeline models for ASR and TTS in EN, BN, HI.
3. Tests live synthesis for localized chief complaint questions.
4. Reports latency, model identifiers, and response statuses.
5. Strict zero-secret leakage: tokens and keys are never printed.
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def evaluate_bhashini(smoke_only: bool, timeout: float):
    from app.services.bhashini_speech import (
        BhashiniSettings,
        BhashiniSpeechProvider,
        SUPPORTED_LANGUAGES,
    )

    settings = BhashiniSettings.from_environment()
    print("=" * 70)
    print("BHASHINI (ULCA) LIVE EVALUATION SUITE")
    print("=" * 70)
    print(f"Endpoint:      {settings.endpoint_url}")
    print(f"Pipeline ID:   {settings.pipeline_id}")
    print(f"Direct Inf:    {settings.inference_url or 'None (dynamic discovery)'}")
    print(f"Timeout:       {settings.timeout}s")
    print(f"API Key:       {'[CONFIGURED]' if settings.api_key.get_secret_value() else '[MISSING]'}")
    print(f"User ID:       {'[CONFIGURED]' if settings.user_id.get_secret_value() else '[MISSING]'}")
    print("-" * 70)

    if not settings.api_key.get_secret_value() or not settings.user_id.get_secret_value():
        print("ERROR: BHASHINI_API_KEY and BHASHINI_USER_ID must be set in environment.")
        return 1

    provider = BhashiniSpeechProvider(settings=settings)

    test_sentences = {
        "en": "Where is your chest pain located?",
        "bn": "আপনার বুকে ব্যথা কোথায় হচ্ছে?",
        "hi": "आपके सीने में दर्द कहाँ हो रहा है?",
    }

    # 1. Evaluate TTS across supported languages
    print("\n[1/2] Evaluating Text-To-Speech (TTS) Synthesis...")
    for lang in sorted(SUPPORTED_LANGUAGES):
        text = test_sentences.get(lang, "Test question")
        t0 = time.perf_counter()
        try:
            res = await provider.synthesize(text=text, language=lang)
            dt = time.perf_counter() - t0
            if res.status == "success":
                audio_len = len(res.audio_base64) if res.audio_base64 else 0
                print(
                    f"  ✓ [{lang.upper()}] TTS SUCCESS in {dt:.2f}s | "
                    f"Format: {res.media_type} | Base64 Bytes: {audio_len}"
                )
            else:
                print(
                    f"  ✗ [{lang.upper()}] TTS UNAVAILABLE in {dt:.2f}s | "
                    f"Reason: {res.reason}"
                )
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f"  ✗ [{lang.upper()}] TTS ERROR in {dt:.2f}s | {type(e).__name__}: {e}")

    if smoke_only:
        print("\nSmoke evaluation completed.")
        return 0

    # 2. Evaluate ASR Discovery & Compute
    print("\n[2/2] Evaluating Speech-To-Text (ASR) Pipeline Discovery...")
    # Minimal 16-bit 8kHz WAV containing silence
    minimal_wav = (
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"@\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )

    for lang in sorted(SUPPORTED_LANGUAGES):
        t0 = time.perf_counter()
        try:
            res = await provider.transcribe(
                audio=minimal_wav,
                language=lang,
                media_type="audio/wav",
            )
            dt = time.perf_counter() - t0
            if res.status == "success":
                print(
                    f"  ✓ [{lang.upper()}] ASR SUCCESS in {dt:.2f}s | "
                    f"Transcript: '{res.transcript}' | Model: {res.model}"
                )
            else:
                print(
                    f"  ✗ [{lang.upper()}] ASR UNAVAILABLE in {dt:.2f}s | "
                    f"Reason: {res.reason}"
                )
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f"  ✗ [{lang.upper()}] ASR ERROR in {dt:.2f}s | {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-live",
        action="store_true",
        help="Authorize live network calls to BHASHINI ULCA endpoints.",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Run only TTS synthesis checks and skip ASR.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=15.0,
        help="Timeout per request in seconds (default: 15.0).",
    )
    args = parser.parse_args()

    if not args.run_live:
        parser.error("Pass --run-live to authorize live calls to BHASHINI.")

    load_dotenv(ROOT / "backend/.env")
    return asyncio.run(evaluate_bhashini(smoke_only=args.smoke_only, timeout=args.timeout_seconds))


if __name__ == "__main__":
    sys.exit(main())
