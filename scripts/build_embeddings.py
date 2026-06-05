import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import db_path
from rag.embeddings import DEFAULT_DIMENSIONS, DEFAULT_EMBEDDING_MODEL, rebuild_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local metadata embeddings for RAG search.")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    args = parser.parse_args()

    result = rebuild_embeddings(db_path(), model=args.model, dimensions=args.dimensions)
    print(f"Active documents: {result['active_documents']}")
    print(f"Embedding rows: {result['embedding_rows']}")
    print(f"Upserted embeddings: {result['upserted']}")
    print(f"Skipped unchanged: {result['skipped']}")
    print(f"Model: {result['model']}")
    print(f"Dimensions: {result['dimensions']}")


if __name__ == "__main__":
    main()
