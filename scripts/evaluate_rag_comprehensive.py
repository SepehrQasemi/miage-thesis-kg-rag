import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import reports_dir
from graph.neo4j_store import Neo4jGraphQueryService
from rag.embeddings import normalize_text, split_terms
from rag.service import RagService


@dataclass(frozen=True)
class ComprehensiveCase:
    case_id: str
    category: str
    question: str
    expected_id: str = ""
    expected_title: str = ""
    expected_use_case: str = ""
    expected_concept: str = ""
    expected_year: str = ""
    expected_master_level: str = ""
    expected_track: str = ""
    top_k: int = 10
    min_matches: int = 1


def concept_terms(value: Any) -> set[str]:
    return {normalize_text(item) for item in split_terms(value) if normalize_text(item)}


def has_concept(row: dict[str, Any], concept: str) -> bool:
    return normalize_text(concept) in concept_terms(row.get("concepts"))


def row_matches_case(row: dict[str, Any], case: ComprehensiveCase) -> bool:
    if case.expected_id and row.get("thesis_id") == case.expected_id:
        return True
    if case.expected_use_case and row.get("use_case") != case.expected_use_case:
        return False
    if case.expected_concept and not has_concept(row, case.expected_concept):
        return False
    if case.expected_year and str(row.get("year") or "") != case.expected_year:
        return False
    if case.expected_master_level and row.get("master_level") != case.expected_master_level:
        return False
    if case.expected_track and row.get("track") != case.expected_track:
        return False
    if case.expected_title:
        return normalize_text(row.get("title")) == normalize_text(case.expected_title)
    return bool(case.expected_use_case or case.expected_concept)


def exact_hit_rank(results: list[dict[str, Any]], expected_id: str) -> str:
    if not expected_id:
        return ""
    for index, row in enumerate(results, start=1):
        if row["thesis_id"] == expected_id:
            return str(index)
    return ""


def top_result_matches(results: list[dict[str, Any]], case: ComprehensiveCase) -> bool:
    return bool(results and row_matches_case(results[0], case))


def evaluate_case(service: RagService, case: ComprehensiveCase) -> dict[str, Any]:
    response = service.search(case.question, top_k=case.top_k)
    results = response["results"]
    retrieved_ids = [row["thesis_id"] for row in results]
    match_count = sum(1 for row in results if row_matches_case(row, case))
    rank = exact_hit_rank(results, case.expected_id)

    if case.category == "title":
        passed = bool(rank) or top_result_matches(results, case)
    elif case.category in {"topic", "concept"}:
        passed = top_result_matches(results, case) and match_count >= case.min_matches
    else:
        passed = bool(rank) or match_count >= case.min_matches

    return {
        "case_id": case.case_id,
        "category": case.category,
        "passed": passed,
        "match_count": match_count,
        "min_matches": case.min_matches,
        "exact_hit_rank": rank,
        "expected_id": case.expected_id,
        "expected_title": case.expected_title,
        "expected_use_case": case.expected_use_case,
        "expected_concept": case.expected_concept,
        "expected_year": case.expected_year,
        "expected_master_level": case.expected_master_level,
        "expected_track": case.expected_track,
        "retrieved_ids": "; ".join(retrieved_ids),
        "top_result": f"{results[0]['thesis_id']} | {results[0]['score']} | {results[0]['title']}" if results else "",
        "question": case.question,
    }


def build_title_cases(rows: list[dict[str, Any]]) -> list[ComprehensiveCase]:
    cases = []
    for index, row in enumerate(rows, start=1):
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        cases.append(
            ComprehensiveCase(
                case_id=f"title_{index:03d}",
                category="title",
                question=f"Find the thesis titled: {title}",
                expected_id=row["thesis_id"],
                expected_title=title,
                top_k=5,
            )
        )
    return cases


def build_topic_cases(rows: list[dict[str, Any]]) -> list[ComprehensiveCase]:
    counts: dict[str, int] = {}
    for row in rows:
        use_case = str(row.get("use_case") or "").strip()
        if use_case:
            counts[use_case] = counts.get(use_case, 0) + 1
    cases = []
    for index, (use_case, count) in enumerate(sorted(counts.items()), start=1):
        min_matches = min(count, 5)
        cases.append(
            ComprehensiveCase(
                case_id=f"topic_{index:03d}",
                category="topic",
                question=f"Show theses about this use case: {use_case}",
                expected_use_case=use_case,
                top_k=10,
                min_matches=min_matches,
            )
        )
    return cases


def build_concept_cases(rows: list[dict[str, Any]]) -> list[ComprehensiveCase]:
    counts: dict[str, int] = {}
    original_values: dict[str, str] = {}
    for row in rows:
        for concept in split_terms(row.get("concepts")):
            normalized = normalize_text(concept)
            if not normalized:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
            original_values.setdefault(normalized, concept)
    cases = []
    for index, normalized in enumerate(sorted(counts), start=1):
        concept = original_values[normalized]
        min_matches = min(counts[normalized], 5)
        cases.append(
            ComprehensiveCase(
                case_id=f"concept_{index:03d}",
                category="concept",
                question=f"Find theses related to the concept: {concept}",
                expected_concept=concept,
                top_k=10,
                min_matches=min_matches,
            )
        )
    return cases


def build_mixed_cases(rows: list[dict[str, Any]]) -> list[ComprehensiveCase]:
    cases = []
    for index, row in enumerate(rows, start=1):
        concepts = split_terms(row.get("concepts"))
        if not concepts:
            continue
        concept = concepts[0]
        use_case = str(row.get("use_case") or "").strip()
        question = (
            f"Find a {row.get('master_level')} {row.get('track')} thesis from {row.get('year')} "
            f"about {concept} for the use case {use_case}."
        )
        cases.append(
            ComprehensiveCase(
                case_id=f"mixed_{index:03d}",
                category="mixed",
                question=question,
                expected_id=row["thesis_id"],
                expected_use_case=use_case,
                expected_concept=concept,
                expected_year=str(row.get("year") or ""),
                expected_master_level=str(row.get("master_level") or ""),
                expected_track=str(row.get("track") or ""),
                top_k=20,
                min_matches=1,
            )
        )
    return cases


def build_cases(rows: list[dict[str, Any]]) -> list[ComprehensiveCase]:
    return [
        *build_title_cases(rows),
        *build_topic_cases(rows),
        *build_concept_cases(rows),
        *build_mixed_cases(rows),
    ]


def summarize(rows: list[dict[str, Any]], min_pass_rate: float) -> dict[str, Any]:
    categories: dict[str, dict[str, Any]] = {}
    for row in rows:
        category = row["category"]
        item = categories.setdefault(category, {"cases": 0, "passed": 0, "failed": 0, "pass_rate": 0.0})
        item["cases"] += 1
        if row["passed"]:
            item["passed"] += 1
        else:
            item["failed"] += 1
    for item in categories.values():
        item["pass_rate"] = round(item["passed"] / max(1, item["cases"]), 4)
    passed = sum(1 for row in rows if row["passed"])
    failed_rows = [row for row in rows if not row["passed"]]
    return {
        "cases": len(rows),
        "passed": passed,
        "failed": len(failed_rows),
        "pass_rate": round(passed / max(1, len(rows)), 4),
        "min_pass_rate": min_pass_rate,
        "categories": categories,
        "failed_case_ids": [row["case_id"] for row in failed_rows],
    }


def write_reports(rows: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    reports_dir().mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir() / "rag_comprehensive_benchmark.csv"
    summary_path = reports_dir() / "rag_comprehensive_benchmark_summary.json"
    columns = [
        "case_id",
        "category",
        "passed",
        "match_count",
        "min_matches",
        "exact_hit_rank",
        "expected_id",
        "expected_title",
        "expected_use_case",
        "expected_concept",
        "expected_year",
        "expected_master_level",
        "expected_track",
        "retrieved_ids",
        "top_result",
        "question",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return csv_path, summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run comprehensive RAG tests by title, topic, concept, and mixed metadata.")
    parser.add_argument("--min-pass-rate", type=float, default=0.90)
    parser.add_argument("--no-fail", action="store_true", help="Always exit 0 after writing reports.")
    args = parser.parse_args()

    graph_service = Neo4jGraphQueryService()
    rows = graph_service.document_rows()
    service = RagService(rows_provider=graph_service.document_rows)
    cases = build_cases(rows)
    results = [evaluate_case(service, case) for case in cases]
    summary = summarize(results, args.min_pass_rate)
    csv_path, summary_path = write_reports(results, summary)

    print(f"Comprehensive RAG cases: {summary['cases']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Pass rate: {summary['pass_rate']:.2%}")
    for category, item in sorted(summary["categories"].items()):
        print(
            f"- {category}: {item['passed']}/{item['cases']} "
            f"passed ({item['pass_rate']:.2%})"
        )
    print(f"Report: {csv_path}")
    print(f"Summary: {summary_path}")

    failed_rows = [row for row in results if not row["passed"]]
    if failed_rows:
        print("\nFailed cases:")
        for row in failed_rows[:25]:
            print(f"- {row['case_id']} [{row['category']}]: {row['question']}")
            print(f"  expected_id={row['expected_id']} expected_use_case={row['expected_use_case']} expected_concept={row['expected_concept']}")
            print(f"  retrieved={row['retrieved_ids']}")
        if len(failed_rows) > 25:
            print(f"... {len(failed_rows) - 25} more failed cases in the CSV report.")
    if not args.no_fail and summary["pass_rate"] < args.min_pass_rate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
