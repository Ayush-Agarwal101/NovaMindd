#!/usr/bin/env python3
"""
scripts/download_models.py

Download all retrieval models (embedding + reranker) from HuggingFace and save
them to the local ``models/embeddings/`` directory so the application can run
fully offline afterwards.

Run this once before starting the server (or during Docker build):

    python scripts/download_models.py

Both models are resolved using the same slug-first path logic used at runtime:
  1. bare slug  ->  models/embeddings/<slug>          (preferred)
  2. escaped    ->  models/embeddings/<org>--<slug>    (fallback)

If a model directory already exists it is skipped (use --force to re-download).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── project root on sys.path so core.config is importable ────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402 — must come after sys.path tweak


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_save_path(model_name: str, base: Path) -> Path:
    """
    Return the path where the model should be saved.

    Prefers the bare slug directory if it already exists (matching models
    that were saved manually or by older tooling).  For a fresh download the
    bare slug is always used — it is the shortest, most readable name.
    """
    slug = model_name.split("/")[-1]
    slug_path = base / slug
    if slug_path.exists():
        return slug_path          # already there under the short name
    escaped_path = base / model_name.replace("/", "--")
    if escaped_path.exists():
        return escaped_path       # already there under the escaped name
    return slug_path              # new download → use short name


def _download_sentence_transformer(model_name: str, save_path: Path, force: bool) -> None:
    """Download a SentenceTransformer (bi-encoder / embedding) model."""
    if save_path.exists() and not force:
        print(f"  [skip] {save_path.name} already exists at {save_path}")
        return

    print(f"  [download] {model_name}  ->  {save_path}")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("  [error] sentence-transformers is not installed.  Run: pip install sentence-transformers")
        sys.exit(1)

    model = SentenceTransformer(model_name)
    save_path.mkdir(parents=True, exist_ok=True)
    model.save(str(save_path))
    print(f"  [saved]  {save_path}")


def _download_cross_encoder(model_name: str, save_path: Path, force: bool) -> None:
    """Download a CrossEncoder (reranker) model."""
    if save_path.exists() and not force:
        print(f"  [skip] {save_path.name} already exists at {save_path}")
        return

    print(f"  [download] {model_name}  ->  {save_path}")
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        print("  [error] sentence-transformers is not installed.  Run: pip install sentence-transformers")
        sys.exit(1)

    model = CrossEncoder(model_name)
    save_path.mkdir(parents=True, exist_ok=True)
    model.save(str(save_path))
    print(f"  [saved]  {save_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Download retrieval models for offline use.")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if the model directory already exists.",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config YAML (default: configs/config.yaml).",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    retrieval = cfg.retrieval

    base = ROOT / retrieval.models_dir
    base.mkdir(parents=True, exist_ok=True)

    print(f"\nModels directory : {base}")
    print(f"Embedding model  : {retrieval.embedding_model}")
    print(f"Reranker model   : {retrieval.reranker_model}")
    print()

    # 1. Embedding model
    print("-- Embedding model --------------------------------------------------")
    emb_path = _resolve_save_path(retrieval.embedding_model, base)
    _download_sentence_transformer(retrieval.embedding_model, emb_path, args.force)

    # 2. Reranker model
    print("-- Reranker model ---------------------------------------------------")
    rnk_path = _resolve_save_path(retrieval.reranker_model, base)
    _download_cross_encoder(retrieval.reranker_model, rnk_path, args.force)

    print()
    print("All models ready. The server will now start fully offline.")


if __name__ == "__main__":
    main()
