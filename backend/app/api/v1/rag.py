from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_current_auth_user
from app.database import get_db
from app.services import rag

router = APIRouter()


class RetrieveRequest(BaseModel):
    query: str = Field(..., description="The query text to retrieve relevant knowledge for.")
    topic: Optional[str] = Field(None, description="Filter by topic (e.g., chest_pain).")
    language: str = Field("en", description="Language of the knowledge base.")
    top_k: int = Field(4, description="Number of top results to return.")
    min_similarity: Optional[float] = Field(None, description="Minimum similarity score threshold (defaults to calibrated RAG_MIN_SIMILARITY).")


class RetrieveResult(BaseModel):
    chunk_id: str
    source_id: str
    source_title: str
    section: str
    content: str
    topic: str
    specialty: Optional[str] = None
    language: str
    document_version: str
    source_reference: Optional[str] = None
    similarity_score: float


class RetrieveResponse(BaseModel):
    query: str
    results: List[RetrieveResult]


class SuggestRequest(BaseModel):
    # We'll accept structured facts as a dict for simplicity.
    # In a real implementation, we might use a specific schema.
    structured_facts: dict = Field(..., description="Normalized patient facts.")
    topic: Optional[str] = Field(None, description="Filter knowledge base by topic.")
    language: str = Field("en", description="Language of the knowledge base.")
    top_k: int = Field(4, description="Number of top retrieval results to consider.")


class SuggestedQuestion(BaseModel):
    question: str
    reason: str
    source_chunk_ids: List[str]
    origin: str = "rag"


class SuggestResponse(BaseModel):
    retrieval_query: str
    sources: List[RetrieveResult]
    questions: List[SuggestedQuestion]


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_knowledge(
    payload: RetrieveRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    """Retrieve relevant knowledge chunks for a given query."""
    retrieval_service = rag.get_retrieval_service()
    results = await retrieval_service.retrieve(
        query_text=payload.query,
        topic=payload.topic,
        language=payload.language,
        top_k=payload.top_k,
        min_similarity=payload.min_similarity,
    )

    retrieve_results = []
    for chunk, similarity in results:
        retrieve_results.append(
            RetrieveResult(
                chunk_id=chunk.id,
                source_id=chunk.source_id,
                source_title=chunk.source_title,
                section=chunk.section,
                content=chunk.content,
                topic=chunk.topic,
                specialty=chunk.specialty,
                language=chunk.language,
                document_version=chunk.document_version,
                source_reference=chunk.source_reference,
                similarity_score=similarity,
            )
        )

    return RetrieveResponse(query=payload.query, results=retrieve_results)


@router.post("/suggest-questions", response_model=SuggestResponse)
async def suggest_questions(
    payload: SuggestRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_auth_user),
):
    """Generate grounded follow-up question suggestions based on patient facts and retrieved knowledge."""
    # First, retrieve relevant knowledge based on the structured facts.
    # We'll construct a query from the structured facts.
    # For simplicity, we'll just concatenate the facts into a string.
    # In a real implementation, we might use a more sophisticated method.
    query_parts = []
    for key, value in payload.structured_facts.items():
        if value:
            query_parts.append(f"{key}: {value}")
    query_text = ". ".join(query_parts)

    retrieval_service = rag.get_retrieval_service()
    retrieved = await retrieval_service.retrieve(
        query_text=query_text,
        topic=payload.topic,
        language=payload.language,
        top_k=payload.top_k,
    )

    # Generate suggestions
    generation_service = rag.get_generation_service()
    suggestions = generation_service.suggest_questions(
        structured_facts=payload.structured_facts,
        retrieved_chunks=retrieved,
    )

    # Convert retrieved chunks to RetrieveResult for response
    retrieve_results = []
    for chunk, similarity in retrieved:
        retrieve_results.append(
            RetrieveResult(
                chunk_id=chunk.id,
                source_id=chunk.source_id,
                source_title=chunk.source_title,
                section=chunk.section,
                content=chunk.content,
                topic=chunk.topic,
                specialty=chunk.specialty,
                language=chunk.language,
                document_version=chunk.document_version,
                source_reference=chunk.source_reference,
                similarity_score=similarity,
            )
        )

    # Convert suggestions to SuggestedQuestion
    suggest_questions = []
    for sug in suggestions:
        suggest_questions.append(
            SuggestedQuestion(
                question=sug["question"],
                reason=sug["reason"],
                source_chunk_ids=sug["source_chunk_ids"],
                origin=sug["origin"],
            )
        )

    return SuggestResponse(
        retrieval_query=query_text,
        sources=retrieve_results,
        questions=suggest_questions,
    )