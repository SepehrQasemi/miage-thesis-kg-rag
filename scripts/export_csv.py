import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.pipeline_outputs import write_document_csv_rows
from graph.neo4j_store import Neo4jGraphQueryService


def main() -> None:
    parser = argparse.ArgumentParser(description="Export active thesis metadata from Neo4j to CSV.")
    parser.add_argument("--output", default=None, help="Optional output CSV path.")
    args = parser.parse_args()

    service = Neo4jGraphQueryService()
    service.verify_connectivity()
    rows = service.document_rows()
    output_path = write_document_csv_rows(rows, Path(args.output) if args.output else None)

    print(f"Exported rows: {len(rows)}")
    print(f"CSV: {output_path}")


if __name__ == "__main__":
    main()
