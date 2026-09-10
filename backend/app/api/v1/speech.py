from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.speech import SpeechSynthesisRequest, SpeechSynthesisResult, TranscriptionResult
from app.services import speech

router = APIRouter()


@router.post("/{session_id}/interview/speech/transcribe", response_model=TranscriptionResult)
async def transcribe(
    session_id: UUID,
    audio: UploadFile = File(...),
    question_id: str = Form(...),
    fixture_id: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        return await speech.transcribe_audio(
            db=db,
            session_id=str(session_id),
            audio_file=audio,
            question_id=question_id,
            fixture_id=fixture_id,
        )
    finally:
        await audio.close()


@router.post("/{session_id}/interview/speech/synthesize", response_model=SpeechSynthesisResult)
async def synthesize(
    session_id: UUID,
    payload: SpeechSynthesisRequest,
    db: Session = Depends(get_db),
):
    return await speech.synthesize_question(
        db=db,
        session_id=str(session_id),
        question_id=payload.question_id,
    )
