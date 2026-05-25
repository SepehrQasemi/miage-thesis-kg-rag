import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path, graph_dir, reports_dir
from graph.knowledge_graph import KnowledgeGraph, build_knowledge_graph, graph_summary


NODE_COLUMNS = ["node_id", "node_type", "label", "slug", "source", "properties_json"]
EDGE_COLUMNS = ["edge_id", "source_id", "target_id", "edge_type", "weight", "source", "properties_json"]


def active_documents() -> list[dict]:
    with connect(db_path()) as conn:
        init_schema(conn)
        return [
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


def replace_graph_tables(graph: KnowledgeGraph) -> None:
    with connect(db_path()) as conn:
        init_schema(conn)
        conn.execute("DELETE FROM graph_edges")
        conn.execute("DELETE FROM graph_nodes")
        conn.executemany(
            """
            INSERT INTO graph_nodes (node_id, node_type, label, slug, source, properties_json)
            VALUES (:node_id, :node_type, :label, :slug, :source, :properties_json)
            """,
            [node.to_record() for node in graph.sorted_nodes()],
        )
        conn.executemany(
            """
            INSERT INTO graph_edges (edge_id, source_id, target_id, edge_type, weight, source, properties_json)
            VALUES (:edge_id, :source_id, :target_id, :edge_type, :weight, :source, :properties_json)
            """,
            [edge.to_record() for edge in graph.sorted_edges()],
        )
        conn.commit()


def write_csv_outputs(graph: KnowledgeGraph) -> tuple[Path, Path]:
    graph_dir().mkdir(parents=True, exist_ok=True)
    nodes_path = graph_dir() / "nodes.csv"
    edges_path = graph_dir() / "edges.csv"

    with nodes_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=NODE_COLUMNS)
        writer.writeheader()
        writer.writerows(node.to_record() for node in graph.sorted_nodes())

    with edges_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EDGE_COLUMNS)
        writer.writeheader()
        writer.writerows(edge.to_record() for edge in graph.sorted_edges())

    return nodes_path, edges_path


def write_json_snapshot(graph: KnowledgeGraph) -> Path:
    graph_dir().mkdir(parents=True, exist_ok=True)
    snapshot_path = graph_dir() / "knowledge_graph.json"
    snapshot = {
        "nodes": [node.to_record() for node in graph.sorted_nodes()],
        "edges": [edge.to_record() for edge in graph.sorted_edges()],
    }
    with snapshot_path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return snapshot_path


def write_summary(graph: KnowledgeGraph, document_count: int) -> Path:
    reports_dir().mkdir(parents=True, exist_ok=True)
    summary_path = reports_dir() / "knowledge_graph_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(graph_summary(graph, document_count), f, ensure_ascii=False, indent=2)
        f.write("\n")
    return summary_path


def write_metric_reports(graph: KnowledgeGraph) -> tuple[Path, Path]:
    reports_dir().mkdir(parents=True, exist_ok=True)
    node_metrics_path = reports_dir() / "knowledge_graph_node_metrics.csv"
    related_theses_path = reports_dir() / "knowledge_graph_related_theses.csv"

    incoming_counts = {node_id: 0 for node_id in graph.nodes}
    outgoing_counts = {node_id: 0 for node_id in graph.nodes}
    for edge in graph.edges.values():
        outgoing_counts[edge.source_id] = outgoing_counts.get(edge.source_id, 0) + 1
        incoming_counts[edge.target_id] = incoming_counts.get(edge.target_id, 0) + 1

    with node_metrics_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "node_id",
                "node_type",
                "label",
                "incoming_edges",
                "outgoing_edges",
                "total_degree",
            ],
        )
        writer.writeheader()
        for node in graph.sorted_nodes():
            incoming = incoming_counts.get(node.node_id, 0)
            outgoing = outgoing_counts.get(node.node_id, 0)
            writer.writerow(
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "label": node.label,
                    "incoming_edges": incoming,
                    "outgoing_edges": outgoing,
                    "total_degree": incoming + outgoing,
                }
            )

    with related_theses_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_thesis_id",
                "target_thesis_id",
                "weight",
                "shared_concept_count",
                "shared_concepts",
            ],
        )
        writer.writeheader()
        related_edges = [edge for edge in graph.sorted_edges() if edge.edge_type == "RELATED_TO"]
        related_edges.sort(key=lambda edge: (-edge.weight, edge.source_id, edge.target_id))
        for edge in related_edges:
            writer.writerow(
                {
                    "source_thesis_id": edge.source_id.replace("thesis:", ""),
                    "target_thesis_id": edge.target_id.replace("thesis:", ""),
                    "weight": edge.weight,
                    "shared_concept_count": edge.properties.get("shared_concept_count", ""),
                    "shared_concepts": "; ".join(edge.properties.get("shared_concepts", [])),
                }
            )

    return node_metrics_path, related_theses_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Knowledge Graph from extracted thesis metadata.")
    parser.add_argument(
        "--related-min-shared-concepts",
        type=int,
        default=3,
        help="Create RELATED_TO thesis edges when this many concepts are shared. Use 0 to disable.",
    )
    args = parser.parse_args()

    rows = active_documents()
    graph = build_knowledge_graph(rows, related_min_shared_concepts=args.related_min_shared_concepts)

    replace_graph_tables(graph)
    nodes_path, edges_path = write_csv_outputs(graph)
    snapshot_path = write_json_snapshot(graph)
    summary_path = write_summary(graph, len(rows))
    node_metrics_path, related_theses_path = write_metric_reports(graph)

    print(f"Source documents: {len(rows)}")
    print(f"Graph nodes: {len(graph.nodes)}")
    print(f"Graph edges: {len(graph.edges)}")
    print(f"Nodes CSV: {nodes_path}")
    print(f"Edges CSV: {edges_path}")
    print(f"Graph JSON: {snapshot_path}")
    print(f"Graph summary: {summary_path}")
    print(f"Node metrics: {node_metrics_path}")
    print(f"Related theses: {related_theses_path}")


if __name__ == "__main__":
    main()
