import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.pipeline_outputs import rebuild_graph_outputs_from_rows
from graph.neo4j_store import Neo4jGraphQueryService


def main() -> None:
    service = Neo4jGraphQueryService()
    service.verify_connectivity()
    service.ensure_schema()
    rows = service.document_rows()
    outputs = rebuild_graph_outputs_from_rows(rows)
    print("Neo4j is the source of truth; no external synchronization step is required.")
    print(f"Active theses: {len(rows)}")
    print(f"CSV: {outputs['csv_path']}")
    print(f"Graph JSON: {outputs['snapshot_path']}")


if __name__ == "__main__":
    main()
