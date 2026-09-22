"""Localhost-only line recognition service for the isolated OCR runtime."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.recognizer import ROOT, FlorLineRecognizer

recognizer: FlorLineRecognizer | None = None
load_error: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global recognizer, load_error
    checkpoint = Path(
        os.getenv("MEDIKIOSK_OCR_CHECKPOINT", ROOT / "models" / "tiny_flor.weights.h5")
    )
    try:
        recognizer = FlorLineRecognizer(checkpoint)
        load_error = None
    except Exception as error:
        recognizer = None
        load_error = type(error).__name__
    yield


app = FastAPI(title="MediKiosk Local Line OCR", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok" if recognizer else "not_ready",
        "recognizer_loaded": recognizer is not None,
        "device": "cpu",
        "model": recognizer.model_version if recognizer else None,
        "checkpoint": "configured" if recognizer else None,
        "error": load_error,
    }


@app.post("/recognize-line")
async def recognize_line(image: Annotated[UploadFile, File()]):
    if recognizer is None:
        raise HTTPException(status_code=503, detail={"code": "OCR_MODEL_NOT_READY"})
    content = await image.read()
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail={"code": "OCR_RECOGNITION_FAILED"})
    try:
        text, processing_ms = recognizer.recognize(content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": str(error)}) from error
    if not text.strip():
        raise HTTPException(status_code=422, detail={"code": "OCR_EMPTY_RESULT"})
    return {
        "text": text,
        "processing_ms": round(processing_ms, 2),
        "model_version": recognizer.model_version,
        "uncertain": True,
    }
