from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable

from graph.knowledge_graph import build_knowledge_graph, graph_summary, split_terms
from graph.query_helpers import build_search_filters, entity_node_id


class FakeGraphService:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = [dict(row) for row in rows]
        self.drafts: dict[str, dict[str, Any]] = {}

    def document_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in sorted(self.rows, key=lambda item: str(item.get("thesis_id") or ""))]

    def replace_with_documents(self, rows: list[dict[str, Any]], related_min_shared_concepts: int = 3) -> dict[str, Any]:
        self.rows = [dict(row) for row in rows if str(row.get("status") or "active") == "active"]
        graph = build_knowledge_graph(self.rows, related_min_shared_concepts=related_min_shared_concepts)
        return {
            "backend": "neo4j",
            "source_documents": len(self.rows),
            "nodes_total": len(graph.nodes),
            "edges_total": len(graph.edges),
        }

    def add_document(self, row: dict[str, Any], related_min_shared_concepts: int = 3) -> dict[str, Any]:
        self.rows = [item for item in self.rows if item.get("thesis_id") != row.get("thesis_id")]
        self.rows.append(dict(row))
        return self.replace_with_documents(self.rows, related_min_shared_concepts=related_min_shared_concepts)

    def summary(self) -> dict[str, Any]:
        graph = build_knowledge_graph(self.rows)
        result = graph_summary(graph, len(self.rows))
        result["backend"] = "neo4j"
        return result

    def top_nodes(self, node_type: str, limit: int = 20) -> list[dict[str, Any]]:
        graph = build_knowledge_graph(self.rows)
        incoming = {node_id: 0 for node_id in graph.nodes}
        for edge in graph.edges.values():
            incoming[edge.target_id] = incoming.get(edge.target_id, 0) + 1
        rows = [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "label": node.label,
                "incoming_edges": incoming.get(node.node_id, 0),
            }
            for node in graph.nodes.values()
            if node.node_type == node_type
        ]
        rows.sort(key=lambda item: (-item["incoming_edges"], item["label"]))
        return rows[:limit]

    def facets(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "years": self.top_nodes("Year", limit=50),
            "master_levels": self.top_nodes("MasterLevel", limit=10),
            "tracks": self.top_nodes("Track", limit=10),
            "use_cases": self.top_nodes("UseCase", limit=30),
            "methodologies": self.top_nodes("Methodology", limit=20),
            "concepts": self.top_nodes("Concept", limit=60),
        }

    def list_theses(self, query: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        query_norm = str(query or "").strip().lower()
        rows = self.document_rows()
        if query_norm:
            rows = [
                row for row in rows
                if any(query_norm in str(row.get(field, "")).lower() for field in ["title", "concepts", "keywords", "use_case", "methodology"])
            ]
        rows.sort(key=lambda item: (-_year(item.get("year")), str(item.get("thesis_id") or "")))
        return [dict(row) for row in rows[offset:offset + limit]]

    def count_theses(self, query: str | None = None) -> int:
        return len(self.list_theses(query=query, limit=10_000, offset=0))

    def search_theses(
        self,
        concepts: Iterable[str] | None = None,
        keywords: Iterable[str] | None = None,
        use_case: str | None = None,
        methodology: str | None = None,
        year: str | None = None,
        master_level: str | None = None,
        track: str | None = None,
        match: str = "all",
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters = build_search_filters(concepts, keywords, use_case, methodology, year, master_level, track)
        rows = []
        required = len(filters) if str(match).lower() == "all" else 1
        for row in self.document_rows():
            matched = sum(1 for edge_type, target_id, _label in filters if _row_matches_filter(row, edge_type, target_id))
            if filters and matched >= required:
                item = dict(row)
                item["matched_filters"] = matched
                item["score"] = matched
                rows.append(item)
        rows.sort(key=lambda item: (-item.get("matched_filters", 0), -_year(item.get("year")), item.get("thesis_id", "")))
        return rows[offset:offset + limit]

    def count_search_theses(self, **kwargs) -> int:
        kwargs["limit"] = 10_000
        kwargs["offset"] = 0
        return len(self.search_theses(**kwargs))

    def thesis_profile(self, thesis_id: str) -> dict[str, Any]:
        row = self._row(thesis_id)
        return {
            **row,
            "graph": {
                "concepts": _nodes("Concept", row.get("concepts")),
                "keywords": _nodes("Keyword", row.get("keywords")),
                "use_cases": _nodes("UseCase", row.get("use_case")),
                "methodologies": _nodes("Methodology", row.get("methodology")),
                "years": _nodes("Year", row.get("year")),
                "master_levels": _nodes("MasterLevel", row.get("master_level")),
                "tracks": _nodes("Track", row.get("track")),
            },
        }

    def similar_theses(self, thesis_id: str, limit: int = 10) -> list[dict[str, Any]]:
        row = self._row(thesis_id)
        row_concepts = set(split_terms(row.get("concepts")))
        similar = []
        for other in self.document_rows():
            if other.get("thesis_id") == row.get("thesis_id"):
                continue
            shared = sorted(row_concepts & set(split_terms(other.get("concepts"))))
            if shared:
                similar.append({
                    "thesis_id": other.get("thesis_id"),
                    "title": other.get("title"),
                    "year": other.get("year"),
                    "master_level": other.get("master_level"),
                    "track": other.get("track"),
                    "use_case": other.get("use_case"),
                    "methodology": other.get("methodology"),
                    "weight": len(shared),
                    "shared_concepts": shared,
                    "shared_concept_count": len(shared),
                })
        similar.sort(key=lambda item: (-item["weight"], item["thesis_id"]))
        return similar[:limit]

    def concept_overview(self, concept: str, limit: int = 10) -> dict[str, Any]:
        concept_norm = str(concept).lower()
        theses = [
            row for row in self.document_rows()
            if concept_norm in [term.lower() for term in split_terms(row.get("concepts"))]
        ][:limit]
        if not theses:
            raise LookupError(f"Unknown concept: {concept}")
        related: dict[str, int] = {}
        for row in theses:
            for term in split_terms(row.get("concepts")):
                if term.lower() != concept_norm:
                    related[term] = related.get(term, 0) + 1
        return {
            "concept": {"node_id": entity_node_id("Concept", concept), "node_type": "Concept", "label": concept},
            "theses": theses,
            "related_concepts": [
                {"node_id": entity_node_id("Concept", label), "node_type": "Concept", "label": label, "shared_theses": count}
                for label, count in sorted(related.items(), key=lambda item: (-item[1], item[0]))[:limit]
            ],
        }

    def thesis_id_exists(self, thesis_id: str) -> bool:
        return any(row.get("thesis_id") == thesis_id for row in self.rows)

    def find_duplicate_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        for row in self.rows:
            if row.get("sha256") == sha256 and str(row.get("status") or "active") == "active":
                return {key: row.get(key) for key in ["thesis_id", "title", "file_name", "year", "master_level"]}
        return None

    def save_import_draft(self, draft: dict[str, Any]) -> None:
        self.drafts[draft["draft_id"]] = deepcopy(draft)

    def load_import_draft(self, draft_id: str) -> dict[str, Any]:
        if draft_id not in self.drafts:
            raise LookupError(f"Unknown import draft: {draft_id}")
        return deepcopy(self.drafts[draft_id])

    def delete_import_draft(self, draft_id: str) -> None:
        self.drafts.pop(draft_id, None)

    def open_import_draft_thesis_ids(self) -> set[str]:
        return {
            str(draft.get("fields", {}).get("thesis_id"))
            for draft in self.drafts.values()
            if draft.get("status") == "draft" and draft.get("fields", {}).get("thesis_id")
        }

    def _row(self, thesis_id: str) -> dict[str, Any]:
        normalized = str(thesis_id).replace("thesis:", "")
        for row in self.rows:
            if row.get("thesis_id") == normalized:
                return dict(row)
        raise LookupError(f"Unknown thesis: {thesis_id}")


def _nodes(node_type: str, value: Any) -> list[dict[str, Any]]:
    return [
        {
            "node_id": entity_node_id(node_type, term),
            "node_type": node_type,
            "label": term,
            "weight": 1,
            "properties": {},
        }
        for term in split_terms(value)
    ]


def _row_matches_filter(row: dict[str, Any], edge_type: str, target_id: str) -> bool:
    field_by_edge = {
        "HAS_CONCEPT": ("Concept", "concepts"),
        "HAS_KEYWORD": ("Keyword", "keywords"),
        "HAS_USE_CASE": ("UseCase", "use_case"),
        "USES_METHODOLOGY": ("Methodology", "methodology"),
        "SUBMITTED_IN": ("Year", "year"),
        "HAS_MASTER_LEVEL": ("MasterLevel", "master_level"),
        "HAS_TRACK": ("Track", "track"),
    }
    node_type, field = field_by_edge[edge_type]
    return target_id in {entity_node_id(node_type, term) for term in split_terms(row.get(field))}


def _year(value: Any) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0
