from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from common.db import connect, init_schema
from common.paths import db_path, graph_dir, processed_dir, reports_dir
from graph.knowledge_graph import KnowledgeGraph, build_knowledge_graph, graph_summary


DOCUMENT_EXPORT_COLUMNS = [
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

NODE_COLUMNS = ["node_id", "node_type", "label", "slug", "source", "properties_json"]
EDGE_COLUMNS = ["edge_id", "source_id", "target_id", "edge_type", "weight", "source", "properties_json"]


def active_documents(database_path: Path | None = None) -> list[dict[str, Any]]:
    with connect(database_path or db_path()) as conn:
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


def replace_graph_tables(graph: KnowledgeGraph, database_path: Path | None = None) -> None:
    with connect(database_path or db_path()) as conn:
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


def write_document_csv(database_path: Path | None = None, output_path: Path | None = None) -> Path:
    path = output_path or processed_dir() / "theses.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path or db_path()) as conn:
        init_schema(conn)
        rows = conn.execute(
            f"""
            SELECT {", ".join(DOCUMENT_EXPORT_COLUMNS)}
            FROM documents
            WHERE status = 'active'
            ORDER BY thesis_id
            """
        ).fetchall()

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DOCUMENT_EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in DOCUMENT_EXPORT_COLUMNS})
    return path


def write_graph_csv_outputs(graph: KnowledgeGraph) -> tuple[Path, Path]:
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


def write_graph_json_snapshot(graph: KnowledgeGraph) -> Path:
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


def write_graph_summary(graph: KnowledgeGraph, document_count: int) -> Path:
    reports_dir().mkdir(parents=True, exist_ok=True)
    summary_path = reports_dir() / "knowledge_graph_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(graph_summary(graph, document_count), f, ensure_ascii=False, indent=2)
        f.write("\n")
    return summary_path


def write_graph_metric_reports(graph: KnowledgeGraph) -> tuple[Path, Path]:
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


def rebuild_graph_outputs(
    database_path: Path | None = None,
    related_min_shared_concepts: int = 3,
) -> dict[str, Any]:
    rows = active_documents(database_path)
    graph = build_knowledge_graph(rows, related_min_shared_concepts=related_min_shared_concepts)
    replace_graph_tables(graph, database_path)
    nodes_path, edges_path = write_graph_csv_outputs(graph)
    snapshot_path = write_graph_json_snapshot(graph)
    summary_path = write_graph_summary(graph, len(rows))
    node_metrics_path, related_theses_path = write_graph_metric_reports(graph)
    csv_path = write_document_csv(database_path)
    return {
        "source_documents": len(rows),
        "nodes_total": len(graph.nodes),
        "edges_total": len(graph.edges),
        "csv_path": str(csv_path),
        "nodes_path": str(nodes_path),
        "edges_path": str(edges_path),
        "snapshot_path": str(snapshot_path),
        "summary_path": str(summary_path),
        "node_metrics_path": str(node_metrics_path),
        "related_theses_path": str(related_theses_path),
        "node_counts": dict(sorted(Counter(node.node_type for node in graph.nodes.values()).items())),
        "edge_counts": dict(sorted(Counter(edge.edge_type for edge in graph.edges.values()).items())),
    }
