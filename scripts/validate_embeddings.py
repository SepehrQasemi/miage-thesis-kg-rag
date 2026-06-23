import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import reports_dir
from graph.neo4j_store import Neo4jGraphQueryService
from rag.embeddings import DEFAULT_DIMENSIONS, DEFAULT_EMBEDDING_MODEL
from rag.service import RagService


def issue(severity: str, item: str, problem: str, value: str = "") -> dict[str, str]:
    return {
        "severity": severity,
        "item": item,
        "problem": problem,
        "value": value,
    }


def validate(model: str, dimensions: int) -> tuple[list[dict[str, str]], dict]:
    issues = []
    graph_service = Neo4jGraphQueryService()
    graph_service.verify_connectivity()
    rows = graph_service.document_rows()
    service = RagService(model=model, dimensions=dimensions, rows_provider=graph_service.document_rows)
    build = service.build_embeddings()

    if build["embedding_rows"] != len(rows):
        issues.append(issue("ERROR", "graph_embeddings", "embedding_count_mismatch", f"rows={len(rows)}; embeddings={build['embedding_rows']}"))

    search_result = service.search("machine learning detection", top_k=3)
    if rows and not search_result["results"]:
        issues.append(issue("ERROR", "rag_search", "no_results_for_smoke_query"))

    summary = {
        "backend": "neo4j",
        "active_documents": len(rows),
        "embedding_rows": build["embedding_rows"],
        "errors": sum(1 for item in issues if item["severity"] == "ERROR"),
        "warnings": sum(1 for item in issues if item["severity"] == "WARNING"),
        "model": model,
        "dimensions": dimensions,
        "smoke_query_results": len(search_result["results"]),
    }
    return issues, summary


def write_reports(issues: list[dict[str, str]], summary: dict) -> tuple[Path, Path]:
    reports_dir().mkdir(parents=True, exist_ok=True)
    issues_path = reports_dir() / "embedding_validation.csv"
    summary_path = reports_dir() / "embedding_validation_summary.json"
    with issues_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["severity", "item", "problem", "value"])
        writer.writeheader()
        writer.writerows(issues)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return issues_path, summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate graph-backed local RAG embeddings.")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    args = parser.parse_args()

    issues, summary = validate(args.model, args.dimensions)
    issues_path, summary_path = write_reports(issues, summary)
    print(f"Embedding validation errors: {summary['errors']}")
    print(f"Active Neo4j documents: {summary['active_documents']}")
    print(f"Graph-backed embedding rows: {summary['embedding_rows']}")
    print(f"Smoke query results: {summary['smoke_query_results']}")
    print(f"Report: {issues_path}")
    print(f"Summary: {summary_path}")
    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
