import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path, graph_dir, reports_dir
from graph.knowledge_graph import EDGE_TYPES, NODE_TYPES, REQUIRED_THESIS_EDGE_TYPES


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def issue(severity: str, item_type: str, item_id: str, problem: str, value: Any = "") -> dict[str, str]:
    return {
        "severity": severity,
        "item_type": item_type,
        "item_id": item_id,
        "problem": problem,
        "value": text(value),
    }


def load_graph_tables() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    with connect(db_path()) as conn:
        init_schema(conn)
        documents = [
            dict(row)
            for row in conn.execute(
                """
                SELECT thesis_id, title
                FROM documents
                WHERE status = 'active'
                ORDER BY thesis_id
                """
            ).fetchall()
        ]
        nodes = [dict(row) for row in conn.execute("SELECT * FROM graph_nodes ORDER BY node_id").fetchall()]
        edges = [dict(row) for row in conn.execute("SELECT * FROM graph_edges ORDER BY edge_id").fetchall()]
    return documents, nodes, edges


def read_csv_count(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def validate_graph(
    documents: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    issues: list[dict[str, str]] = []

    node_ids = [text(node.get("node_id")) for node in nodes]
    edge_ids = [text(edge.get("edge_id")) for edge in edges]
    node_id_set = set(node_ids)

    for node_id, count in Counter(node_ids).items():
        if not node_id:
            issues.append(issue("ERROR", "node", "", "missing_node_id"))
        elif count > 1:
            issues.append(issue("ERROR", "node", node_id, "duplicate_node_id", count))

    for edge_id, count in Counter(edge_ids).items():
        if not edge_id:
            issues.append(issue("ERROR", "edge", "", "missing_edge_id"))
        elif count > 1:
            issues.append(issue("ERROR", "edge", edge_id, "duplicate_edge_id", count))

    for node in nodes:
        node_type = text(node.get("node_type"))
        if node_type not in NODE_TYPES:
            issues.append(issue("ERROR", "node", node.get("node_id"), "invalid_node_type", node_type))
        if not text(node.get("label")):
            issues.append(issue("ERROR", "node", node.get("node_id"), "missing_label"))
        try:
            json.loads(text(node.get("properties_json")) or "{}")
        except json.JSONDecodeError as exc:
            issues.append(issue("ERROR", "node", node.get("node_id"), "invalid_properties_json", exc))

    edge_types_by_source: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        edge_type = text(edge.get("edge_type"))
        source_id = text(edge.get("source_id"))
        target_id = text(edge.get("target_id"))
        if edge_type not in EDGE_TYPES:
            issues.append(issue("ERROR", "edge", edge.get("edge_id"), "invalid_edge_type", edge_type))
        if source_id not in node_id_set:
            issues.append(issue("ERROR", "edge", edge.get("edge_id"), "dangling_source_id", source_id))
        if target_id not in node_id_set:
            issues.append(issue("ERROR", "edge", edge.get("edge_id"), "dangling_target_id", target_id))
        try:
            weight = float(edge.get("weight"))
            if weight <= 0:
                issues.append(issue("ERROR", "edge", edge.get("edge_id"), "non_positive_weight", weight))
        except (TypeError, ValueError):
            issues.append(issue("ERROR", "edge", edge.get("edge_id"), "invalid_weight", edge.get("weight")))
        try:
            json.loads(text(edge.get("properties_json")) or "{}")
        except json.JSONDecodeError as exc:
            issues.append(issue("ERROR", "edge", edge.get("edge_id"), "invalid_properties_json", exc))
        edge_types_by_source[source_id].add(edge_type)

    thesis_nodes = [node for node in nodes if text(node.get("node_type")) == "Thesis"]
    expected_thesis_ids = {f"thesis:{doc['thesis_id']}" for doc in documents}
    actual_thesis_ids = {text(node.get("node_id")) for node in thesis_nodes}
    missing_thesis_nodes = sorted(expected_thesis_ids - actual_thesis_ids)
    extra_thesis_nodes = sorted(actual_thesis_ids - expected_thesis_ids)

    for node_id in missing_thesis_nodes:
        issues.append(issue("ERROR", "node", node_id, "missing_thesis_node"))
    for node_id in extra_thesis_nodes:
        issues.append(issue("ERROR", "node", node_id, "extra_thesis_node"))

    for thesis_id in sorted(expected_thesis_ids & actual_thesis_ids):
        missing_edges = REQUIRED_THESIS_EDGE_TYPES - edge_types_by_source.get(thesis_id, set())
        for edge_type in sorted(missing_edges):
            issues.append(issue("ERROR", "edge", thesis_id, "missing_required_thesis_edge", edge_type))

    nodes_csv_count = read_csv_count(graph_dir() / "nodes.csv")
    edges_csv_count = read_csv_count(graph_dir() / "edges.csv")
    if nodes_csv_count is None:
        issues.append(issue("ERROR", "file", str(graph_dir() / "nodes.csv"), "missing_nodes_csv"))
    elif nodes_csv_count != len(nodes):
        issues.append(issue("ERROR", "file", str(graph_dir() / "nodes.csv"), "nodes_csv_count_mismatch", f"csv={nodes_csv_count}; db={len(nodes)}"))
    if edges_csv_count is None:
        issues.append(issue("ERROR", "file", str(graph_dir() / "edges.csv"), "missing_edges_csv"))
    elif edges_csv_count != len(edges):
        issues.append(issue("ERROR", "file", str(graph_dir() / "edges.csv"), "edges_csv_count_mismatch", f"csv={edges_csv_count}; db={len(edges)}"))

    node_counts = Counter(text(node.get("node_type")) for node in nodes)
    edge_counts = Counter(text(edge.get("edge_type")) for edge in edges)
    summary = {
        "source_documents": len(documents),
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "nodes_csv_rows": nodes_csv_count,
        "edges_csv_rows": edges_csv_count,
        "errors": sum(1 for item in issues if item["severity"] == "ERROR"),
        "warnings": sum(1 for item in issues if item["severity"] == "WARNING"),
    }
    return issues, summary


def main() -> None:
    documents, nodes, edges = load_graph_tables()
    issues, summary = validate_graph(documents, nodes, edges)

    reports_dir().mkdir(parents=True, exist_ok=True)
    issues_path = reports_dir() / "knowledge_graph_validation.csv"
    with issues_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["severity", "item_type", "item_id", "problem", "value"])
        writer.writeheader()
        writer.writerows(issues)

    summary_path = reports_dir() / "knowledge_graph_validation_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Graph validation errors: {summary['errors']}")
    print(f"Graph validation warnings: {summary['warnings']}")
    print(f"Graph validation report: {issues_path}")
    print(f"Graph validation summary: {summary_path}")

    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
