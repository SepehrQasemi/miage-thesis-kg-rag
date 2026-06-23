import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import reports_dir
from graph.neo4j_store import Neo4jGraphQueryService


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
    service = Neo4jGraphQueryService()
    service.verify_connectivity()
    rows = service.document_rows()

    reports_dir().mkdir(parents=True, exist_ok=True)
    output = reports_dir() / "extraction_quality.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUALITY_COLUMNS)
        writer.writeheader()
        for row in rows:
            required_fields_complete = all(
                bool(row.get(field))
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
                    "thesis_id": row.get("thesis_id", ""),
                    "file_name": row.get("file_name", ""),
                    "pages_count": row.get("pages_count", ""),
                    "required_fields_complete": required_fields_complete,
                    "title_found": bool(row.get("title")),
                    "year_found": bool(row.get("year")),
                    "master_level_found": bool(row.get("master_level")),
                    "track_found": bool(row.get("track")),
                    "abstract_required": False,
                    "abstract_found": bool(row.get("abstract")),
                    "keywords_found": bool(row.get("keywords")),
                    "concepts_found": bool(row.get("concepts")),
                    "use_case_found": bool(row.get("use_case")),
                    "methodology_found": bool(row.get("methodology")),
                    "extraction_confidence": row.get("extraction_confidence", ""),
                    "needs_review": bool(row.get("needs_review")),
                    "extraction_notes": row.get("extraction_notes", ""),
                }
            )
    print(f"Quality rows: {len(rows)}")
    print(f"Quality report: {output}")


if __name__ == "__main__":
    main()
