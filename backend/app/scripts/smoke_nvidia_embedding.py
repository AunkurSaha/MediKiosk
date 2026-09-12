"""Sanitized smoke test for live NVIDIA embedding provider.

Does NOT print or log any API keys, secrets, or authorization headers.
Reports sanitized metrics:
- Provider name
- Model name
- Vector dimension
- Call latency
- Top retrieved chunk IDs & similarity scores
"""

import asyncio
import math
import os
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from pydantic import SecretStr

from app.services.embedding_provider import (
    NvidiaEmbeddingProvider,
    NvidiaEmbeddingSettings,
)

# Load backend/.env
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


async def run_smoke_test():
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        print("[SMOKE TEST] NVIDIA_API_KEY is not configured in backend/.env; live smoke test skipped.")
        return

    print("==================================================")
    print("LIVE NVIDIA EMBEDDING SMOKE TEST (SANITIZED)")
    print("==================================================")

    model_name = os.getenv("RAG_EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b").strip()
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()

    settings = NvidiaEmbeddingSettings(
        api_key=SecretStr(api_key),
        model=model_name,
        base_url=base_url,
        timeout=15.0,
        dimension=2048,
    )

    provider = NvidiaEmbeddingProvider(settings=settings)
    print(f"1. Provider initialized: name={provider.name}, model={provider.model}")

    # Test single query embedding
    query_text = "Patient feels heavy pressure in the center of the chest with shortness of breath on exertion"
    t0 = perf_counter()
    query_vector = await provider.embed_query(query_text)
    query_latency = (perf_counter() - t0) * 1000

    print(f"2. Query embedding succeeded in {query_latency:.1f}ms")
    print(f"3. Query vector length: {len(query_vector)}")
    print(f"4. Vector is all numeric: {all(isinstance(x, float) for x in query_vector)}")
    assert len(query_vector) == 2048

    # Embed sample knowledge chunks from chest_pain
    sample_chunks = [
        (
            "cp-dyspnea",
            "Dyspnea (shortness of breath) is a critical associated symptom in chest pain history taking.",
        ),
        (
            "cp-exertion",
            "Provocation: Pain worsening with exertion or walking suggests cardiac ischemia.",
        ),
        (
            "cp-radiation",
            "Warning features: Chest discomfort radiating to the left arm, jaw, shoulder, or back.",
        ),
        (
            "cp-swallowing",
            "Non-cardiac warning features: Pain associated with swallowing suggests esophageal pathology.",
        ),
    ]

    t1 = perf_counter()
    chunk_texts = [text for _, text in sample_chunks]
    doc_vectors = await provider.embed_documents(chunk_texts)
    batch_latency = (perf_counter() - t1) * 1000

    print(f"5. Batch embedding of {len(doc_vectors)} chunks succeeded in {batch_latency:.1f}ms")
    assert len(doc_vectors) == len(sample_chunks)
    assert all(len(v) == 2048 for v in doc_vectors)

    # Calculate cosine rankings
    scored = []
    for (chunk_id, chunk_text), doc_v in zip(sample_chunks, doc_vectors):
        sim = cosine_similarity(query_vector, doc_v)
        scored.append((chunk_id, sim, chunk_text[:50]))

    scored.sort(key=lambda x: x[1], reverse=True)

    print("\n6. Retrieval Ranking for Query:")
    print(f"   \"{query_text}\"")
    print("   ------------------------------------------------")
    for rank, (cid, sim, snippet) in enumerate(scored, 1):
        print(f"   #{rank}: [{cid}] similarity={sim:.4f} snippet=\"{snippet}...\"")

    print("\n[SMOKE TEST COMPLETE - ALL CHECKS PASSED]")


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
