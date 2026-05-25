from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from common.db import connect, init_schema
from common.paths import db_path
from graph.knowledge_graph import canonical_concept_label, canonical_entity_label, slugify


THESIS_EDGE_TYPES = {
    "HAS_CONCEPT": "concepts",
    "HAS_KEYWORD": "keywords",
    "HAS_USE_CASE": "use_case",
    "USES_METHODOLOGY": "methodology",
    "SUBMITTED_IN": "year",
    "HAS_MASTER_LEVEL": "master_level",
    "HAS_TRACK": "track",
}


@dataclass(slots=True)
class GraphQueryService:
    database_path: Any = None

    def __post_init__(self) -> None:
        if self.database_path is None:
            self.database_path = db_path()

    def summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            node_counts = {
                row["node_type"]: row["count"]
                for row in conn.execute(
                    """
                    SELECT node_type, COUNT(*) AS count
                    FROM graph_nodes
                    GROUP BY node_type
                    ORDER BY node_type
                    """
                )
            }
            edge_counts = {
                row["edge_type"]: row["count"]
                for row in conn.execute(
                    """
                    SELECT edge_type, COUNT(*) AS count
                    FROM graph_edges
                    GROUP BY edge_type
                    ORDER BY edge_type
                    """
                )
            }
            return {
                "nodes_total": sum(node_counts.values()),
                "edges_total": sum(edge_counts.values()),
                "node_counts": node_counts,
                "edge_counts": edge_counts,
            }

    def top_nodes(self, node_type: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    n.node_id,
                    n.node_type,
                    n.label,
                    COUNT(e.edge_id) AS incoming_edges
                FROM graph_nodes n
                LEFT JOIN graph_edges e ON e.target_id = n.node_id
                WHERE n.node_type = ?
                GROUP BY n.node_id, n.node_type, n.label
                ORDER BY incoming_edges DESC, n.label ASC
                LIMIT ?
                """,
                (node_type, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_theses(self, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        search_text = f"%{query.strip()}%" if query and query.strip() else None
        where_clause = "WHERE status = 'active'"
        params: list[Any] = []
        if search_text:
            where_clause += """
                AND (
                    title LIKE ?
                    OR concepts LIKE ?
                    OR keywords LIKE ?
                    OR use_case LIKE ?
                    OR methodology LIKE ?
                )
            """
            params.extend([search_text] * 5)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT thesis_id, title, year, master_level, track, use_case,
                       methodology, extraction_confidence
                FROM documents
                {where_clause}
                ORDER BY
                    CASE WHEN year = 'N/A' THEN 0 ELSE CAST(year AS INTEGER) END DESC,
                    thesis_id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def facets(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "years": self.top_nodes("Year", limit=50),
            "master_levels": self.top_nodes("MasterLevel", limit=10),
            "tracks": self.top_nodes("Track", limit=10),
            "use_cases": self.top_nodes("UseCase", limit=30),
            "methodologies": self.top_nodes("Methodology", limit=20),
            "concepts": self.top_nodes("Concept", limit=60),
        }

    def thesis_profile(self, thesis_id: str) -> dict[str, Any]:
        thesis_node_id = normalize_thesis_node_id(thesis_id)
        with self._connect() as conn:
            thesis = conn.execute(
                """
                SELECT n.*, d.file_name, d.pages_count, d.year, d.master_level, d.track,
                       d.title, d.abstract, d.keywords, d.concepts, d.use_case, d.methodology,
                       d.extraction_confidence
                FROM graph_nodes n
                LEFT JOIN documents d ON d.thesis_id = REPLACE(n.node_id, 'thesis:', '')
                WHERE n.node_id = ? AND n.node_type = 'Thesis'
                """,
                (thesis_node_id,),
            ).fetchone()
            if thesis is None:
                raise LookupError(f"Unknown thesis: {thesis_id}")

            edges = conn.execute(
                """
                SELECT e.edge_type, e.weight, e.properties_json, n.node_id, n.node_type, n.label
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.target_id
                WHERE e.source_id = ? AND e.edge_type <> 'RELATED_TO'
                ORDER BY e.edge_type, e.weight DESC, n.label
                """,
                (thesis_node_id,),
            ).fetchall()

        grouped: dict[str, list[dict[str, Any]]] = {label: [] for label in THESIS_EDGE_TYPES.values()}
        for row in edges:
            group = THESIS_EDGE_TYPES.get(row["edge_type"], row["edge_type"].lower())
            grouped.setdefault(group, []).append(
                {
                    "node_id": row["node_id"],
                    "node_type": row["node_type"],
                    "label": row["label"],
                    "weight": row["weight"],
                    "properties": parse_json(row["properties_json"]),
                }
            )

        thesis_dict = dict(thesis)
        return {
            "thesis_id": thesis_node_id.replace("thesis:", ""),
            "title": thesis_dict.get("title") or thesis_dict.get("label"),
            "file_name": thesis_dict.get("file_name"),
            "pages_count": thesis_dict.get("pages_count"),
            "year": thesis_dict.get("year"),
            "master_level": thesis_dict.get("master_level"),
            "track": thesis_dict.get("track"),
            "use_case": thesis_dict.get("use_case"),
            "methodology": thesis_dict.get("methodology"),
            "extraction_confidence": thesis_dict.get("extraction_confidence"),
            "graph": grouped,
        }

    def similar_theses(self, thesis_id: str, limit: int = 10) -> list[dict[str, Any]]:
        thesis_node_id = normalize_thesis_node_id(thesis_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END AS related_node_id,
                    e.weight,
                    e.properties_json,
                    n.label AS related_title,
                    d.year,
                    d.master_level,
                    d.track,
                    d.use_case,
                    d.methodology
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END
                LEFT JOIN documents d ON d.thesis_id = REPLACE(n.node_id, 'thesis:', '')
                WHERE e.edge_type = 'RELATED_TO'
                  AND (e.source_id = ? OR e.target_id = ?)
                ORDER BY e.weight DESC, related_node_id ASC
                LIMIT ?
                """,
                (thesis_node_id, thesis_node_id, thesis_node_id, thesis_node_id, limit),
            ).fetchall()
        return [
            {
                "thesis_id": row["related_node_id"].replace("thesis:", ""),
                "title": row["related_title"],
                "year": row["year"],
                "master_level": row["master_level"],
                "track": row["track"],
                "use_case": row["use_case"],
                "methodology": row["methodology"],
                "weight": row["weight"],
                **parse_related_properties(row["properties_json"]),
            }
            for row in rows
        ]

    def theses_by_entity(
        self,
        node_type: str,
        label: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        node_id = entity_node_id(node_type, label)
        edge_type = edge_type_for_node_type(node_type)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.thesis_id, d.title, d.year, d.master_level, d.track, d.use_case,
                       d.methodology, e.weight
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.source_id AND n.node_type = 'Thesis'
                JOIN documents d ON d.thesis_id = REPLACE(n.node_id, 'thesis:', '')
                WHERE e.target_id = ? AND e.edge_type = ?
                ORDER BY
                    e.weight DESC,
                    CASE WHEN d.year = 'N/A' THEN 0 ELSE CAST(d.year AS INTEGER) END DESC,
                    d.thesis_id ASC
                LIMIT ?
                """,
                (node_id, edge_type, limit),
            ).fetchall()
        return [dict(row) for row in rows]

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
    ) -> list[dict[str, Any]]:
        filters: list[tuple[str, str, str]] = []
        for concept in concepts or []:
            filters.append(("HAS_CONCEPT", entity_node_id("Concept", concept), concept))
        for keyword in keywords or []:
            filters.append(("HAS_KEYWORD", entity_node_id("Keyword", keyword), keyword))
        if use_case:
            filters.append(("HAS_USE_CASE", entity_node_id("UseCase", use_case), use_case))
        if methodology:
            filters.append(("USES_METHODOLOGY", entity_node_id("Methodology", methodology), methodology))
        if year:
            filters.append(("SUBMITTED_IN", entity_node_id("Year", year), year))
        if master_level:
            filters.append(("HAS_MASTER_LEVEL", entity_node_id("MasterLevel", master_level), master_level))
        if track:
            filters.append(("HAS_TRACK", entity_node_id("Track", track), track))
        if not filters:
            return []

        conditions = " OR ".join("(e.edge_type = ? AND e.target_id = ?)" for _ in filters)
        params: list[Any] = []
        for edge_type, target_id, _ in filters:
            params.extend([edge_type, target_id])

        required_count = len(filters) if match.lower() == "all" else 1
        params.extend([required_count, limit])

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT d.thesis_id, d.title, d.year, d.master_level, d.track,
                       d.use_case, d.methodology,
                       COUNT(DISTINCT e.edge_type || ':' || e.target_id) AS matched_filters,
                       SUM(e.weight) AS score
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.source_id AND n.node_type = 'Thesis'
                JOIN documents d ON d.thesis_id = REPLACE(n.node_id, 'thesis:', '')
                WHERE {conditions}
                GROUP BY d.thesis_id, d.title, d.year, d.master_level, d.track, d.use_case, d.methodology
                HAVING matched_filters >= ?
                ORDER BY
                    matched_filters DESC,
                    score DESC,
                    CASE WHEN d.year = 'N/A' THEN 0 ELSE CAST(d.year AS INTEGER) END DESC,
                    d.thesis_id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def concept_overview(self, concept: str, limit: int = 10) -> dict[str, Any]:
        concept_node_id = entity_node_id("Concept", concept)
        with self._connect() as conn:
            node = conn.execute("SELECT * FROM graph_nodes WHERE node_id = ?", (concept_node_id,)).fetchone()
            if node is None:
                raise LookupError(f"Unknown concept: {concept}")

            theses = self.theses_by_entity("Concept", concept, limit=limit)
            related_concepts = conn.execute(
                """
                SELECT c.node_id, c.label, COUNT(*) AS shared_theses
                FROM graph_edges base
                JOIN graph_edges other
                  ON other.source_id = base.source_id
                 AND other.edge_type = 'HAS_CONCEPT'
                 AND other.target_id <> base.target_id
                JOIN graph_nodes c ON c.node_id = other.target_id
                WHERE base.edge_type = 'HAS_CONCEPT'
                  AND base.target_id = ?
                GROUP BY c.node_id, c.label
                ORDER BY shared_theses DESC, c.label ASC
                LIMIT ?
                """,
                (concept_node_id, limit),
            ).fetchall()

        return {
            "concept": dict(node),
            "theses": theses,
            "related_concepts": [dict(row) for row in related_concepts],
        }

    def _connect(self):
        conn = connect(self.database_path)
        init_schema(conn)
        return conn


def normalize_thesis_node_id(thesis_id: str) -> str:
    thesis_id = thesis_id.strip()
    if thesis_id.startswith("thesis:"):
        return thesis_id
    return f"thesis:{thesis_id}"


def entity_node_id(node_type: str, label: str) -> str:
    canonical = canonical_entity_label(label, node_type)
    return f"{node_type.lower()}:{slugify(canonical)}"


def edge_type_for_node_type(node_type: str) -> str:
    edge_types = {
        "Concept": "HAS_CONCEPT",
        "Keyword": "HAS_KEYWORD",
        "UseCase": "HAS_USE_CASE",
        "Methodology": "USES_METHODOLOGY",
        "Year": "SUBMITTED_IN",
        "MasterLevel": "HAS_MASTER_LEVEL",
        "Track": "HAS_TRACK",
    }
    try:
        return edge_types[node_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported query node type: {node_type}") from exc


def parse_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_related_properties(value: Any) -> dict[str, Any]:
    props = parse_json(value)
    return {
        "shared_concept_count": props.get("shared_concept_count", 0),
        "shared_concepts": props.get("shared_concepts", []),
    }
