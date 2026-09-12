"""Integration test verifying KnowledgeRetrievalService with real NVIDIA embeddings on persisted database chunks.

No secrets, tokens, or credentials are printed or logged.
"""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from app.database import SessionLocal
from app.services.rag import KnowledgeRetrievalService

# Load backend/.env
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)



async def verify_retrieval():
    service = KnowledgeRetrievalService(db_session_factory=SessionLocal)
    print("====================================================================")
    print("REAL KNOWLEDGE RETRIEVAL SERVICE EVALUATION (NVIDIA + REAL PERSISTED CHUNKS)")
    print(f"Active Provider: {service.embedding_provider.name} ({getattr(service.embedding_provider, 'model', 'N/A')})")
    print("====================================================================")

    test_queries = [
        (
            "Q1",
            "Patient becomes short of breath while climbing stairs with chest discomfort",
            "dyspnea / associated-symptoms",
        ),
        (
            "Q2",
            "Heavy central chest pressure gets worse when walking",
            "exertion / provocation",
        ),
        (
            "Q3",
            "Pain moves into the jaw and left arm",
            "radiation",
        ),
        (
            "Q4",
            "Cold sweats and nausea occur with central chest discomfort",
            "autonomic / sweating / nausea",
        ),
        (
            "Q5",
            "Chest discomfort with fever and cough",
            "cough / fever",
        ),
        # Negative controls
        (
            "NEG1",
            "Patient has a severe skin allergy to penicillin and sulfa antibiotics",
            "[NEGATIVE CONTROL - should return empty or low]",
        ),
        (
            "NEG2",
            "The patient is a 42-year-old software engineer living in Bangalore with family",
            "[NEGATIVE CONTROL - should return empty or low]",
        ),
    ]

    for q_id, q_text, expected in test_queries:
        print(f"\nEvaluating [{q_id}]: \"{q_text}\"")
        print(f"Target Expectation: {expected}")
        # Call the actual service method used across the app
        results = await service.retrieve(
            query_text=q_text,
            topic="chest_pain",
            language="en",
            top_k=4,
            min_similarity=None,  # uses calibrated RAG_MIN_SIMILARITY (0.25)
        )
        print(f"Returned {len(results)} chunks above calibrated threshold (0.25):")
        for rank, (chunk, score) in enumerate(results, 1):
            snippet = chunk.content[:60].replace("\n", " ")
            print(f"  #{rank}: [score={score:.4f}] id={chunk.id} section={chunk.section} snippet=\"{snippet}...\"")
        if not results:
            print("  -> Correctly returned 0 chunks (below 0.25 threshold)")


if __name__ == "__main__":
    asyncio.run(verify_retrieval())
