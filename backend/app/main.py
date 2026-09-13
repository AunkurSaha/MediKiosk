import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.api.v1.routers import api_router
from app.core.config import CORS_ORIGINS, demo_enabled
from app.core.errors import WorkflowError
from app.database import get_db
from app.services.flow_registry import registry
from app.services.normalization_provider import validate_configuration
from app.services.red_flags import get_rule_catalog
from app.services.speech_provider import validate_speech_configuration


@asynccontextmanager
async def lifespan(app):
    registry.cache_clear()
    registry()
    validate_configuration()
    validate_speech_configuration()
    get_rule_catalog()
    yield


app = FastAPI(
    title="MediKiosk",
    version="0.3.0",
    description="Pre-consultation intake demo",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Demo-Doctor", "Authorization", "Cookie"],
)


def error_response(status, code, message, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": details},
        },
    )


@app.exception_handler(WorkflowError)
async def workflow_error(request: Request, exc: WorkflowError):
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo submitted patient values in validation errors.
    return error_response(
        422,
        "INVALID_INPUT",
        "Check the submitted fields.",
        [{"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in exc.errors()],
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(IntegrityError)
async def conflict_error(request: Request, exc: IntegrityError):
    return error_response(409, "CONFLICT", "The record changed. Reload and retry.")


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return error_response(503, "DATABASE_UNAVAILABLE", "Could not save or load data. Please retry.")


logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.error("Unhandled application error: %s", type(exc).__name__)
    return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred. Please retry.")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/config")
def public_config():
    return {
        "demo_mode": demo_enabled(),
        "phase": "12",
        "languages": ["en", "bn", "hi"],
        "normalization_provider": os.getenv("CLINICAL_NORMALIZATION_PROVIDER", "mock"),
        "speech_provider": os.getenv("SPEECH_PROVIDER", "mock"),
        "ocr_provider": os.getenv("OCR_PROVIDER", "mock"),
        "translation_provider": os.getenv("TRANSLATION_PROVIDER", "mock"),
        "rag_generation_provider": os.getenv("RAG_GENERATION_PROVIDER", "template"),
        "rag_generation_model": os.getenv("RAG_GENERATION_MODEL"),
    }


app.include_router(api_router, prefix="/api")
