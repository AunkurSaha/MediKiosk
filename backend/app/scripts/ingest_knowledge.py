#!/usr/bin/env python
"""Script to ingest knowledge base files into the RAG store."""

import argparse
import asyncio
import os
from pathlib import Path

from app.services.rag import get_ingestion_service


def main():
    parser = argparse.ArgumentParser(description="Ingest knowledge base for RAG.")
    parser.add_argument(
        "--knowledge-base",
        type=str,
        default=str(Path(__file__).parents[3] / "ai" / "knowledge_base"),
        help="Path to the knowledge base directory.",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="chest_pain",
        help="Topic to assign to the ingested knowledge.",
    )
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="Force re-embedding of existing knowledge chunks with the current provider.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Alias for --reembed.",
    )
    args = parser.parse_args()

    kb_path = Path(args.knowledge_base)
    if not kb_path.exists():
        print(f"Knowledge base path does not exist: {kb_path}")
        return

    ingestion_service = get_ingestion_service()
    force_reembed = bool(args.reembed or args.force)

    # Walk through the knowledge base directory
    for root, dirs, files in os.walk(kb_path):
        for file in files:
            if file.endswith(".md") or file.endswith(".txt"):
                file_path = Path(root) / file
                # Determine section from filename (without extension)
                section = Path(file).stem
                # Determine source_id from relative path
                relative_path = file_path.relative_to(kb_path)
                source_id = str(relative_path.with_suffix("")).replace(os.sep, "-")
                # Source title: make it nice
                source_title = section.replace("_", " ").title()

                print(f"Ingesting {file_path} as source_id='{source_id}', section='{section}' (reembed={force_reembed})")
                asyncio.run(
                    ingestion_service.ingest_file(
                        file_path=str(file_path),
                        source_id=source_id,
                        source_title=source_title,
                        section=section,
                        topic=args.topic,
                        language="en",
                        document_version="1.0-demo",
                        source_reference="Internally generated for MediKiosk demo",
                        force_reembed=force_reembed,
                    )
                )
    print("Ingestion complete.")


if __name__ == "__main__":
    main()