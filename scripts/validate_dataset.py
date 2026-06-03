import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path, processed_dir, raw_pdf_dir, reports_dir


REQUIRED_FIELDS = [
    "title",
    "year",
    "master_level",
    "track",
    "keywords",
    "concepts",
    "use_case",
    "methodology",
]

ALLOWED_MASTER_LEVELS = {"M1", "M2", "N/A"}
ALLOWED_TRACKS = {"apprentissage", "classique", "N/A"}


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_missing(value: Any) -> bool:
    return text(value) == ""


def valid_year(value: Any) -> bool:
    value_text = text(value)
    if value_text == "N/A":
        return True
    if not re.fullmatch(r"\d{4}", value_text):
        return False
    year = int(value_text)
    return 2000 <= year <= 2035


def boolish(value: Any) -> bool:
    return text(value).lower() in {"1", "true", "yes"}


def issue(thesis_id: str, severity: str, field: str, problem: str, value: Any = "") -> dict[str, str]:
    return {
        "thesis_id": thesis_id,
        "severity": severity,
        "field": field,
        "problem": problem,
        "value": text(value),
    }


def suspicious_title_problems(title: str) -> list[str]:
    problems = []
    if "`" in title:
        problems.append("contains_pdf_backtick_accent_artifact")
    if re.search(r"Ã|Â|â", title):
        problems.append("contains_mojibake_encoding_artifact")
    if re.search(r"\b\w+de\s", title):
        for glued in ["Modelesde", "Processusde", "Integrationde", "Qualitedes", "etevalution"]:
            if glued.lower() in title.lower():
                problems.append("contains_suspicious_glued_word")
                break
    if len(title) > 260:
        problems.append("title_too_long")
    return problems


def read_exported_csv() -> list[dict[str, str]]:
    csv_path = processed_dir() / "theses.csv"
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def validate_rows(rows: list[dict[str, Any]], allow_subset: bool) -> tuple[list[dict[str, str]], dict[str, Any]]:
    issues: list[dict[str, str]] = []

    thesis_ids = [text(row.get("thesis_id")) for row in rows]
    for thesis_id, count in Counter(thesis_ids).items():
        if thesis_id and count > 1:
            issues.append(issue(thesis_id, "ERROR", "thesis_id", "duplicate_thesis_id", count))

    file_names = [text(row.get("file_name")) for row in rows]
    for file_name, count in Counter(file_names).items():
        if file_name and count > 1:
            issues.append(issue("", "ERROR", "file_name", "duplicate_file_name", file_name))

    for row in rows:
        thesis_id = text(row.get("thesis_id"))
        for field in REQUIRED_FIELDS:
            if is_missing(row.get(field)):
                issues.append(issue(thesis_id, "ERROR", field, "missing_required_field", row.get(field)))

        if not is_missing(row.get("year")) and not valid_year(row.get("year")):
            issues.append(issue(thesis_id, "ERROR", "year", "invalid_year", row.get("year")))

        master_level = text(row.get("master_level"))
        if master_level and master_level not in ALLOWED_MASTER_LEVELS:
            issues.append(issue(thesis_id, "ERROR", "master_level", "invalid_master_level", master_level))

        track = text(row.get("track"))
        if track and track not in ALLOWED_TRACKS:
            issues.append(issue(thesis_id, "ERROR", "track", "invalid_track", track))

        if boolish(row.get("needs_review")):
            issues.append(issue(thesis_id, "ERROR", "needs_review", "row_still_marked_needs_review", row.get("needs_review")))

        title = text(row.get("title"))
        for problem in suspicious_title_problems(title):
            issues.append(issue(thesis_id, "WARNING", "title", problem, title))

    raw_count = len(list(raw_pdf_dir().glob("*.pdf")))
    active_count = len(rows)
    if raw_count != active_count:
        severity = "WARNING" if allow_subset else "ERROR"
        issues.append(
            issue(
                "",
                severity,
                "row_count",
                "active_document_count_does_not_match_raw_pdf_count",
                f"active={active_count}; raw_pdf={raw_count}",
            )
        )

    exported_rows = read_exported_csv()
    if exported_rows and len(exported_rows) != active_count:
        issues.append(
            issue(
                "",
                "ERROR",
                "processed_csv",
                "exported_csv_count_does_not_match_database_count",
                f"csv={len(exported_rows)}; db={active_count}",
            )
        )

    summary = {
        "active_documents": active_count,
        "raw_pdfs": raw_count,
        "exported_csv_rows": len(exported_rows),
        "required_fields": REQUIRED_FIELDS,
        "required_missing": {
            field: sum(1 for row in rows if is_missing(row.get(field)))
            for field in REQUIRED_FIELDS
        },
        "missing_abstract_optional": sum(1 for row in rows if is_missing(row.get("abstract"))),
        "needs_review": sum(1 for row in rows if boolish(row.get("needs_review"))),
        "errors": sum(1 for item in issues if item["severity"] == "ERROR"),
        "warnings": sum(1 for item in issues if item["severity"] == "WARNING"),
    }
    return issues, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the extracted thesis dataset before graph/RAG steps.")
    parser.add_argument("--allow-subset", action="store_true", help="Allow DB row count to be smaller than raw PDF count.")
    args = parser.parse_args()

    with connect(db_path()) as conn:
        init_schema(conn)
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM documents
                WHERE status = 'active'
                ORDER BY thesis_id
                """
            ).fetchall()
        ]

    reports_dir().mkdir(parents=True, exist_ok=True)
    issues, summary = validate_rows(rows, allow_subset=args.allow_subset)

    issues_path = reports_dir() / "dataset_validation.csv"
    with issues_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["thesis_id", "severity", "field", "problem", "value"])
        writer.writeheader()
        writer.writerows(issues)

    summary_path = reports_dir() / "dataset_validation_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Validation errors: {summary['errors']}")
    print(f"Validation warnings: {summary['warnings']}")
    print(f"Validation report: {issues_path}")
    print(f"Validation summary: {summary_path}")

    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
