import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path, reports_dir


QUALITY_COLUMNS = [
    "thesis_id",
    "file_name",
    "pages_count",
    "required_fields_complete",
    "title_found",
    "year_found",
    "master_level_found",
    "track_found",
    "abstract_required",
    "abstract_found",
    "keywords_found",
    "concepts_found",
    "use_case_found",
    "methodology_found",
    "extraction_confidence",
    "needs_review",
    "extraction_notes",
]


def main() -> None:
    reports_dir().mkdir(parents=True, exist_ok=True)
    output = reports_dir() / "extraction_quality.csv"
    with connect(db_path()) as conn:
        init_schema(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM documents
            WHERE status = 'active'
            ORDER BY thesis_id
            """
        ).fetchall()

    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUALITY_COLUMNS)
        writer.writeheader()
        for row in rows:
            required_fields_complete = all(
                bool(row[field])
                for field in [
                    "title",
                    "year",
                    "master_level",
                    "track",
                    "keywords",
                    "concepts",
                    "use_case",
                    "methodology",
                ]
            )
            writer.writerow(
                {
                    "thesis_id": row["thesis_id"],
                    "file_name": row["file_name"],
                    "pages_count": row["pages_count"],
                    "required_fields_complete": required_fields_complete,
                    "title_found": bool(row["title"]),
                    "year_found": bool(row["year"]),
                    "master_level_found": bool(row["master_level"]),
                    "track_found": bool(row["track"]),
                    "abstract_required": False,
                    "abstract_found": bool(row["abstract"]),
                    "keywords_found": bool(row["keywords"]),
                    "concepts_found": bool(row["concepts"]),
                    "use_case_found": bool(row["use_case"]),
                    "methodology_found": bool(row["methodology"]),
                    "extraction_confidence": row["extraction_confidence"],
                    "needs_review": bool(row["needs_review"]),
                    "extraction_notes": row["extraction_notes"],
                }
            )
    print(f"Quality rows: {len(rows)}")
    print(f"Quality report: {output}")


if __name__ == "__main__":
    main()
