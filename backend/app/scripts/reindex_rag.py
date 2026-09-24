"""Safe Patient Evidence RAG reindex command.

Examples:
  python -m app.scripts.reindex_rag --patient PATIENT_ID
  python -m app.scripts.reindex_rag --provider nvidia --patient-id PATIENT_ID --dry-run
  python -m app.scripts.reindex_rag --session SESSION_ID
  python -m app.scripts.reindex_rag --document DOCUMENT_ID
  python -m app.scripts.reindex_rag --all --confirm-all
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app import models
from app.database import SessionLocal
from app.services.embedding_provider import configured_provider
from app.services.patient_rag import backfill_patient_embeddings, reindex_patient


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild the patient evidence RAG search index.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--patient", "--patient-id", dest="patient")
    scope.add_argument("--session")
    scope.add_argument("--document")
    scope.add_argument("--all", action="store_true")
    parser.add_argument(
        "--confirm-all",
        action="store_true",
        help="Required with --all to prevent accidental bulk provider usage.",
    )
    parser.add_argument(
        "--confirm-bulk",
        action="store_true",
        help="Additional acknowledgement for provider bulk operations.",
    )
    parser.add_argument("--provider", choices=("mock", "nvidia"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int)
    return parser.parse_args(argv)


def _print_backfill(result) -> None:
    print(f"Provider: {result.provider_name}")
    print(f"Model: {result.provider_model}")
    print(f"Version: {result.provider_version}")
    print(f"Dimension: {result.provider_dimension}")
    print(f"Patient: {result.patient_id}")
    print(f"Canonical chunks: {result.canonical_chunk_count}")
    print(f"Already indexed: {result.already_indexed}")
    print(f"Failed: {result.failed_before_count}")
    print(f"Failed after: {result.failed_count}")
    print(f"Pending: {result.pending_count}")
    print(f"Missing: {result.missing_count}")
    print(f"Stale: {result.stale_count}")
    print(f"Would embed: {result.would_embed}")
    print(f"Estimated batches: {result.estimated_batches}")
    print(f"Coverage before: {result.coverage_before:.2f}%")
    print(f"Coverage after: {result.coverage_after:.2f}%")
    print(f"Ready before: {str(result.ready_before).lower()}")
    print(f"Ready after: {str(result.ready_after).lower()}")


async def run(args: argparse.Namespace) -> int:
    if args.provider == "nvidia" and args.all:
        if not args.confirm_bulk:
            raise SystemExit("NVIDIA bulk mode requires --confirm-bulk")
        raise SystemExit("NVIDIA bulk mode is disabled; use --patient-id")
    if args.provider == "nvidia" and not args.patient:
        raise SystemExit("--provider nvidia requires --patient-id")
    if args.all and not args.confirm_all:
        raise SystemExit("--all requires --confirm-all")
    if args.dry_run and not args.provider:
        raise SystemExit("--dry-run requires --provider")
    provider = configured_provider(args.provider) if args.provider else None
    with SessionLocal() as db:
        if args.patient:
            patient_ids = [args.patient]
        elif args.session:
            session = db.get(models.Session, args.session)
            if session is None:
                raise SystemExit("Session not found")
            patient_ids = [session.patient_id]
        elif args.document:
            document = db.get(models.Document, args.document)
            if document is None:
                raise SystemExit("Document not found")
            session = db.get(models.Session, document.session_id)
            patient_ids = [session.patient_id]
        else:
            patient_ids = list(db.scalars(select(models.Patient.id).order_by(models.Patient.id)))

        for patient_id in patient_ids:
            if provider is not None:
                result = await backfill_patient_embeddings(
                    db,
                    patient_id,
                    provider,
                    dry_run=args.dry_run,
                    batch_size=args.batch_size,
                )
                _print_backfill(result)
            else:
                status = await reindex_patient(db, patient_id)
                print(
                    f"patient={patient_id} chunks={status.chunks_total} "
                    f"embedded={status.chunks_embedded} failed={status.chunks_failed}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(arguments())))
