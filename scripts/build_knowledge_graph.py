import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.pipeline_outputs import rebuild_graph_outputs_from_rows
from graph.neo4j_store import Neo4jGraphQueryService


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the Neo4j Knowledge Graph and export graph files.")
    parser.add_argument(
        "--related-min-shared-concepts",
        type=int,
        default=3,
        help="Create RELATED_TO thesis edges when this many concepts are shared. Use 0 to disable.",
    )
    args = parser.parse_args()

    service = Neo4jGraphQueryService()
    service.verify_connectivity()
    rows = service.document_rows()
    graph_result = service.replace_with_documents(
        rows,
        related_min_shared_concepts=args.related_min_shared_concepts,
    )
    output_result = rebuild_graph_outputs_from_rows(
        service.document_rows(),
        related_min_shared_concepts=args.related_min_shared_concepts,
    )

    print(f"Source documents: {graph_result['source_documents']}")
    print(f"Neo4j graph nodes: {graph_result['nodes_total']}")
    print(f"Neo4j graph relationships: {graph_result['edges_total']}")
    print(f"CSV: {output_result['csv_path']}")
    print(f"Nodes CSV: {output_result['nodes_path']}")
    print(f"Edges CSV: {output_result['edges_path']}")
    print(f"Graph JSON: {output_result['snapshot_path']}")
    print(f"Graph summary: {output_result['summary_path']}")
    print(f"Node metrics: {output_result['node_metrics_path']}")
    print(f"Related theses: {output_result['related_theses_path']}")


if __name__ == "__main__":
    main()
