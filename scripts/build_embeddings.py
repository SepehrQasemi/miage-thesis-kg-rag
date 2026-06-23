import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from graph.neo4j_store import Neo4jGraphQueryService
from rag.embeddings import DEFAULT_DIMENSIONS, DEFAULT_EMBEDDING_MODEL
from rag.service import RagService


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local in-memory RAG embeddings from Neo4j thesis metadata.")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    args = parser.parse_args()

    graph_service = Neo4jGraphQueryService()
    graph_service.verify_connectivity()
    rows = graph_service.document_rows()
    rag_service = RagService(
        model=args.model,
        dimensions=args.dimensions,
        rows_provider=graph_service.document_rows,
    )
    result = rag_service.build_embeddings()

    print(f"Active Neo4j documents: {len(rows)}")
    print(f"In-memory embedding rows: {result['embedding_rows']}")
    print(f"Model: {result['embedding_model']}")
    print(f"Dimensions: {result['embedding_dimensions']}")


if __name__ == "__main__":
    main()
