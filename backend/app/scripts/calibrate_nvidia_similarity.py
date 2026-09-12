"""Calibration script for NVIDIA nemotron-3-embed-1b semantic retrieval on MediKiosk chest-pain corpus.

Evaluates:
- 5 clinically relevant paraphrased queries
- 4 negative control / unrelated queries
Computes:
- Top matching chunk similarity
- Second-best matching chunk similarity
- Irrelevant chunk similarities
- Optimal min_similarity threshold
"""

import asyncio
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr

from app.services.embedding_provider import (
    NvidiaEmbeddingProvider,
    NvidiaEmbeddingSettings,
)
from app.services.rag import KnowledgeIngestionService

# Load backend/.env
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)



def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


async def calibrate():
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        print("ERROR: NVIDIA_API_KEY is not set in backend/.env")
        return

    model_name = os.getenv("RAG_EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b").strip()
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()

    settings = NvidiaEmbeddingSettings(
        api_key=SecretStr(api_key),
        model=model_name,
        base_url=base_url,
        timeout=20.0,
        dimension=2048,
    )
    provider = NvidiaEmbeddingProvider(settings=settings)

    # Load and chunk all 3 knowledge base files from ai/knowledge_base/chest_pain
    kb_dir = Path(__file__).resolve().parents[3] / "ai" / "knowledge_base" / "chest_pain"
    files = [
        ("associated_symptoms.md", "associated_symptoms", "Associated Symptoms"),
        ("history_taking.md", "history_taking", "History Taking"),
        ("warning_features.md", "warning_features", "Warning Features"),
    ]

    ingestion_service = KnowledgeIngestionService()
    all_chunks = []
    for fname, sec, title in files:
        fpath = kb_dir / fname
        text = fpath.read_text(encoding="utf-8")
        chunks = ingestion_service._chunk_markdown(text, f"chest_pain-{sec}", title, sec)
        all_chunks.extend(chunks)

    print(f"Total knowledge base chunks created: {len(all_chunks)}")

    # Batch embed all chunks as passages
    chunk_texts = [c["content"] for c in all_chunks]
    doc_vectors = await provider.embed_documents(chunk_texts)
    print(f"Successfully embedded {len(doc_vectors)} chunks (dim={len(doc_vectors[0])})")

    # Evaluation Set
    clinical_queries = [
        (
            "Q1_dyspnea",
            "Patient becomes short of breath while climbing stairs with chest discomfort",
            "dyspnea",
        ),
        (
            "Q2_exertion",
            "Heavy central chest pressure gets worse when walking",
            "exertion / provocation",
        ),
        (
            "Q3_radiation",
            "Pain moves into the jaw and left arm",
            "radiation",
        ),
        (
            "Q4_autonomic",
            "Cold sweats and nausea occur with central chest discomfort",
            "diaphoresis / sweating / nausea",
        ),
        (
            "Q5_cough_fever",
            "Chest discomfort with fever and cough",
            "cough / fever",
        ),
    ]

    negative_controls = [
        (
            "NEG1_allergy",
            "Patient has a severe skin allergy to penicillin and sulfa antibiotics",
        ),
        (
            "NEG2_dermatology",
            "Dry red itchy scaling rash observed on bilateral forearms for two weeks",
        ),
        (
            "NEG3_demographics",
            "The patient is a 42-year-old software engineer living in Bangalore with family",
        ),
        (
            "NEG4_diet_lifestyle",
            "Patient follows a vegetarian diet with regular morning walks and meditation",
        ),
    ]

    print("\n=======================================================")
    print("EVALUATING CLINICAL QUERIES (RELEVANT INTENT)")
    print("=======================================================")

    clinical_top_scores = []
    clinical_second_scores = []

    for q_id, q_text, expected in clinical_queries:
        q_vec = await provider.embed_query(q_text)
        scores = []
        for c, d_vec in zip(all_chunks, doc_vectors):
            sim = cosine_similarity(q_vec, d_vec)
            scores.append((sim, c["id"], c["metadata"]["section"], c["content"][:60].replace("\n", " ")))
        scores.sort(key=lambda x: x[0], reverse=True)

        top1 = scores[0]
        top2 = scores[1]
        clinical_top_scores.append(top1[0])
        clinical_second_scores.append(top2[0])

        print(f"\nQuery [{q_id}]: \"{q_text}\"")
        print(f"Target Concept: {expected}")
        print(f"  #1: score={top1[0]:.4f} id={top1[1]} snippet=\"{top1[3]}...\"")
        print(f"  #2: score={top2[0]:.4f} id={top2[1]} snippet=\"{top2[3]}...\"")
        print(f"  #3: score={scores[2][0]:.4f} id={scores[2][1]} snippet=\"{scores[2][3]}...\"")

    print("\n=======================================================")
    print("EVALUATING NEGATIVE CONTROLS (UNRELATED INTENT)")
    print("=======================================================")

    negative_top_scores = []

    for neg_id, neg_text in negative_controls:
        q_vec = await provider.embed_query(neg_text)
        scores = []
        for c, d_vec in zip(all_chunks, doc_vectors):
            sim = cosine_similarity(q_vec, d_vec)
            scores.append((sim, c["id"], c["metadata"]["section"], c["content"][:60].replace("\n", " ")))
        scores.sort(key=lambda x: x[0], reverse=True)

        top1 = scores[0]
        negative_top_scores.append(top1[0])

        print(f"\nNegative Control [{neg_id}]: \"{neg_text}\"")
        print(f"  Max Similarity: score={top1[0]:.4f} id={top1[1]} snippet=\"{top1[3]}...\"")

    print("\n=======================================================")
    print("STATISTICAL DISTRIBUTION SUMMARY")
    print("=======================================================")
    print(f"Clinical Relevant Top-1 Mean:     {sum(clinical_top_scores)/len(clinical_top_scores):.4f} (range: {min(clinical_top_scores):.4f} - {max(clinical_top_scores):.4f})")
    print(f"Clinical Relevant Top-2 Mean:     {sum(clinical_second_scores)/len(clinical_second_scores):.4f} (range: {min(clinical_second_scores):.4f} - {max(clinical_second_scores):.4f})")
    print(f"Negative Control Max Mean:        {sum(negative_top_scores)/len(negative_top_scores):.4f} (range: {min(negative_top_scores):.4f} - {max(negative_top_scores):.4f})")

    # Determine optimal threshold
    # Must be <= min(clinical_top_scores) so all relevant queries pass
    # Must be > max(negative_top_scores) so negative queries are rejected
    rec_threshold = round((min(clinical_top_scores) + max(negative_top_scores)) / 2, 2)
    print(f"\nRecommended Calibrated min_similarity: {rec_threshold}")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(calibrate())
