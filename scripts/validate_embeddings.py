import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path, reports_dir
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
    database = db_path()
    with connect(database) as conn:
        init_schema(conn)
        active_count = conn.execute("SELECT COUNT(*) AS count FROM documents WHERE status = 'active'").fetchone()["count"]
        embedding_rows = conn.execute(
            "SELECT * FROM document_embeddings WHERE embedding_model = ? ORDER BY thesis_id",
            (model,),
        ).fetchall()
        embedding_count = len(embedding_rows)
        if active_count != embedding_count:
            issues.append(issue("ERROR", "document_embeddings", "embedding_count_mismatch", f"active={active_count}; embeddings={embedding_count}"))
        for row in embedding_rows:
            if int(row["embedding_dimensions"]) != dimensions:
                issues.append(issue("ERROR", row["thesis_id"], "invalid_embedding_dimensions", row["embedding_dimensions"]))
            try:
                vector = json.loads(row["embedding_vector_json"])
            except json.JSONDecodeError:
                issues.append(issue("ERROR", row["thesis_id"], "invalid_embedding_json"))
                continue
            if len(vector) != dimensions:
                issues.append(issue("ERROR", row["thesis_id"], "embedding_vector_length_mismatch", str(len(vector))))
            if not row["embedding_text"].strip():
                issues.append(issue("ERROR", row["thesis_id"], "empty_embedding_text"))

    search_result = RagService(database, model=model, dimensions=dimensions).search("machine learning detection", top_k=3)
    if not search_result["results"]:
        issues.append(issue("ERROR", "rag_search", "no_results_for_smoke_query"))

    summary = {
        "active_documents": active_count,
        "embedding_rows": embedding_count,
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
    parser = argparse.ArgumentParser(description="Validate local RAG embeddings.")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    args = parser.parse_args()

    issues, summary = validate(args.model, args.dimensions)
    issues_path, summary_path = write_reports(issues, summary)
    print(f"Embedding validation errors: {summary['errors']}")
    print(f"Embedding validation warnings: {summary['warnings']}")
    print(f"Embedding validation report: {issues_path}")
    print(f"Embedding validation summary: {summary_path}")
    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
