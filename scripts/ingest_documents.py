#!/usr/bin/env python3
"""
scripts/ingest_documents.py

Batch ingest a directory of documents into the NovaMindd knowledge base.

Usage:
    python scripts/ingest_documents.py <documents_dir> [--api-url http://localhost:8000]
"""
import argparse
import sys
from pathlib import Path

import httpx

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def ingest_file(path: Path, api_url: str) -> dict:
    with path.open("rb") as fh:
        content = fh.read()
    files = {"file": (path.name, content, "application/octet-stream")}
    r = httpx.post(f"{api_url}/api/v1/knowledge/ingest", files=files, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch ingest documents into NovaMindd")
    parser.add_argument("documents_dir", help="Directory containing documents to ingest")
    parser.add_argument("--api-url", default="http://localhost:8000", help="NovaMindd API URL")
    args = parser.parse_args()

    docs_dir = Path(args.documents_dir)
    if not docs_dir.is_dir():
        print(f"ERROR: {docs_dir} is not a directory", file=sys.stderr)
        return 1

    files = [f for f in docs_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        print(f"No supported files found in {docs_dir}")
        return 0

    print(f"Ingesting {len(files)} file(s) into {args.api_url}")
    success = 0
    for f in sorted(files):
        try:
            result = ingest_file(f, args.api_url)
            print(f"  ✓ {f.name} → document_id={result['document_id']} chunks={result['chunks_created']}")
            success += 1
        except Exception as exc:
            print(f"  ✗ {f.name} → ERROR: {exc}", file=sys.stderr)

    print(f"\nCompleted: {success}/{len(files)} files ingested successfully.")
    return 0 if success == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
