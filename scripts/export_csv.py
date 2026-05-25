import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path, processed_dir


EXPORT_COLUMNS = [
    "thesis_id",
    "file_name",
    "pages_count",
    "year",
    "title",
    "master_level",
    "track",
    "abstract",
    "keywords",
    "concepts",
    "use_case",
    "methodology",
    "extraction_confidence",
    "needs_review",
    "status",
    "extraction_notes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export extracted thesis data to CSV.")
    parser.add_argument("--output", default=None, help="Optional output CSV path.")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else processed_dir() / "theses.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(db_path()) as conn:
        init_schema(conn)
        rows = conn.execute(
            f"""
            SELECT {", ".join(EXPORT_COLUMNS)}
            FROM documents
            WHERE status = 'active'
            ORDER BY thesis_id
            """
        ).fetchall()

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in EXPORT_COLUMNS})

    print(f"Exported rows: {len(rows)}")
    print(f"CSV: {output_path}")


if __name__ == "__main__":
    main()
