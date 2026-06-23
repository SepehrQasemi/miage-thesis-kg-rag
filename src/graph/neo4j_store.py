from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

from common.paths import load_env_file
from graph.knowledge_graph import build_knowledge_graph
from graph.query_helpers import (
    THESIS_EDGE_TYPES,
    build_search_filters,
    edge_type_for_node_type,
    entity_node_id,
    normalize_thesis_node_id,
    parse_json,
    parse_related_properties,
)


NEO4J_NODE_LABELS = {"Thesis", "Concept", "Keyword", "UseCase", "Methodology", "Year", "MasterLevel", "Track"}
NEO4J_EDGE_TYPES = {*THESIS_EDGE_TYPES, "RELATED_TO"}
DOCUMENT_FIELDS = [
    "thesis_id",
    "file_name",
    "file_path",
    "sha256",
    "pages_count",
    "cover_text",
    "abstract",
    "introduction",
    "conclusion",
    "year",
    "title",
    "master_level",
    "track",
    "keywords",
    "concepts",
    "use_case",
    "methodology",
    "extraction_confidence",
    "needs_review",
    "status",
    "extraction_notes",
    "processed_at",
    "created_at",
    "updated_at",
]


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str | None = None


def neo4j_settings_from_env() -> Neo4jSettings:
    load_env_file()
    return Neo4jSettings(
        uri=os.environ.get("MIAGE_NEO4J_URI", "bolt://127.0.0.1:7687"),
        user=os.environ.get("MIAGE_NEO4J_USER", "neo4j"),
        password=os.environ.get("MIAGE_NEO4J_PASSWORD", "miage-rag-2026"),
        database=os.environ.get("MIAGE_NEO4J_DATABASE") or None,
    )


def create_neo4j_driver(settings: Neo4jSettings | None = None):
    settings = settings or neo4j_settings_from_env()
    try:
        from neo4j import GraphDatabase
    except Exception as exc:  # pragma: no cover - depends on optional dependency installation
        raise RuntimeError("Neo4j Python driver is not installed. Run: pip install -r requirements.txt") from exc
    return GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))


class Neo4jGraphQueryService:
    def __init__(
        self,
        driver: Any | None = None,
        settings: Neo4jSettings | None = None,
    ):
        self.settings = settings or neo4j_settings_from_env()
        self._driver = driver or create_neo4j_driver(self.settings)
        self.database = self.settings.database

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def close(self) -> None:
        self._driver.close()

    def ensure_schema(self) -> None:
        self._write("CREATE CONSTRAINT miage_node_id IF NOT EXISTS FOR (n:MiageNode) REQUIRE n.node_id IS UNIQUE")
        self._write("CREATE CONSTRAINT miage_thesis_id IF NOT EXISTS FOR (t:Thesis) REQUIRE t.thesis_id IS UNIQUE")
        self._write("CREATE CONSTRAINT miage_import_draft_id IF NOT EXISTS FOR (d:ImportDraft) REQUIRE d.draft_id IS UNIQUE")
        self._write("CREATE INDEX miage_thesis_sha256 IF NOT EXISTS FOR (t:Thesis) ON (t.sha256)")
        self._write("CREATE INDEX miage_import_draft_sha256 IF NOT EXISTS FOR (d:ImportDraft) ON (d.sha256)")
        self._write("CREATE INDEX miage_import_draft_status IF NOT EXISTS FOR (d:ImportDraft) ON (d.status)")
        self._write("CREATE INDEX miage_node_type IF NOT EXISTS FOR (n:MiageNode) ON (n.node_type)")
        self._write("CREATE INDEX miage_node_slug IF NOT EXISTS FOR (n:MiageNode) ON (n.slug)")

    def replace_with_documents(
        self,
        rows: list[dict[str, Any]],
        related_min_shared_concepts: int = 3,
    ) -> dict[str, Any]:
        self.ensure_schema()
        graph = build_knowledge_graph(rows, related_min_shared_concepts=related_min_shared_concepts)
        row_by_id = {str(row.get("thesis_id")): row for row in rows}
        self._write("MATCH (n:MiageNode) DETACH DELETE n")

        for node in graph.sorted_nodes():
            record = node.to_record()
            props = dict(record)
            if record["node_type"] == "Thesis":
                thesis_id = str(record["node_id"]).replace("thesis:", "")
                props.update({field: row_by_id.get(thesis_id, {}).get(field) for field in DOCUMENT_FIELDS})
                props["thesis_id"] = thesis_id
                props["title"] = props.get("title") or record["label"]
                props["status"] = props.get("status") or "active"
            self._merge_node(record["node_type"], props)

        for edge in graph.sorted_edges():
            record = edge.to_record()
            self._merge_relationship(record["edge_type"], record)

        return {
            "backend": "neo4j",
            "source_documents": len(rows),
            "nodes_total": len(graph.nodes),
            "edges_total": len(graph.edges),
        }

    def document_rows(self) -> list[dict[str, Any]]:
        records = self._run(
            """
            MATCH (t:Thesis)
            WHERE coalesce(t.status, 'active') = 'active'
            RETURN t { .* } AS thesis
            ORDER BY t.thesis_id ASC
            """
        )
        return [document_from_props(record["thesis"]) for record in records]

    def add_document(self, row: dict[str, Any], related_min_shared_concepts: int = 3) -> dict[str, Any]:
        rows = [existing for existing in self.document_rows() if existing.get("thesis_id") != row.get("thesis_id")]
        rows.append(row)
        rows.sort(key=lambda item: str(item.get("thesis_id") or ""))
        return self.replace_with_documents(rows, related_min_shared_concepts=related_min_shared_concepts)

    def thesis_id_exists(self, thesis_id: str) -> bool:
        records = self._run(
            """
            MATCH (t:Thesis {thesis_id: $thesis_id})
            WHERE coalesce(t.status, 'active') = 'active'
            RETURN count(t) AS count
            """,
            {"thesis_id": str(thesis_id)},
        )
        return bool(records and records[0]["count"])

    def find_duplicate_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        records = self._run(
            """
            MATCH (t:Thesis {sha256: $sha256})
            WHERE coalesce(t.status, 'active') = 'active'
            RETURN t.thesis_id AS thesis_id,
                   t.title AS title,
                   t.file_name AS file_name,
                   t.year AS year,
                   t.master_level AS master_level
            LIMIT 1
            """,
            {"sha256": sha256},
        )
        return dict(records[0]) if records else None

    def save_import_draft(self, draft: dict[str, Any]) -> None:
        self.ensure_schema()
        props = encode_import_draft(draft)
        self._write(
            """
            MERGE (d:ImportDraft {draft_id: $draft_id})
            SET d += $props
            """,
            {"draft_id": props["draft_id"], "props": props},
        )

    def load_import_draft(self, draft_id: str) -> dict[str, Any]:
        records = self._run(
            """
            MATCH (d:ImportDraft {draft_id: $draft_id})
            RETURN d { .* } AS draft
            LIMIT 1
            """,
            {"draft_id": draft_id},
        )
        if not records:
            raise LookupError(f"Unknown import draft: {draft_id}")
        return decode_import_draft(records[0]["draft"])

    def delete_import_draft(self, draft_id: str) -> None:
        self._write(
            """
            MATCH (d:ImportDraft {draft_id: $draft_id})
            DETACH DELETE d
            """,
            {"draft_id": draft_id},
        )

    def open_import_draft_thesis_ids(self) -> set[str]:
        records = self._run(
            """
            MATCH (d:ImportDraft)
            WHERE coalesce(d.status, 'draft') = 'draft'
            RETURN d.fields_json AS fields_json
            """
        )
        thesis_ids: set[str] = set()
        for record in records:
            fields = parse_json(record.get("fields_json"))
            thesis_id = str(fields.get("thesis_id") or "")
            if thesis_id:
                thesis_ids.add(thesis_id)
        return thesis_ids

    def next_thesis_id(self, reserved_ids: set[str] | None = None) -> str:
        max_number = 0
        thesis_ids = [str(row.get("thesis_id") or "") for row in self.document_rows()]
        thesis_ids.extend(self.open_import_draft_thesis_ids())
        thesis_ids.extend(str(item) for item in reserved_ids or set())
        for thesis_id in thesis_ids:
            match = re.fullmatch(r"thesis_(\d+)", thesis_id)
            if match:
                max_number = max(max_number, int(match.group(1)))
        return f"thesis_{max_number + 1:04d}"

    def summary(self) -> dict[str, Any]:
        node_counts = {
            record["node_type"]: record["count"]
            for record in self._run(
                """
                MATCH (n:MiageNode)
                RETURN n.node_type AS node_type, count(n) AS count
                ORDER BY node_type
                """
            )
        }
        edge_counts = {
            record["edge_type"]: record["count"]
            for record in self._run(
                """
                MATCH (:MiageNode)-[r]->(:MiageNode)
                RETURN type(r) AS edge_type, count(r) AS count
                ORDER BY edge_type
                """
            )
        }
        return {
            "backend": "neo4j",
            "nodes_total": sum(node_counts.values()),
            "edges_total": sum(edge_counts.values()),
            "node_counts": node_counts,
            "edge_counts": edge_counts,
        }

    def node_records(self) -> list[dict[str, Any]]:
        records = self._run(
            """
            MATCH (n:MiageNode)
            RETURN n { .* } AS node
            ORDER BY n.node_type ASC, n.node_id ASC
            """
        )
        return [dict(record["node"]) for record in records]

    def edge_records(self) -> list[dict[str, Any]]:
        records = self._run(
            """
            MATCH (:MiageNode)-[r]->(:MiageNode)
            RETURN r { .* } AS relationship
            ORDER BY type(r) ASC, r.source_id ASC, r.target_id ASC
            """
        )
        return [dict(record["relationship"]) for record in records]

    def graph_records(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return self.node_records(), self.edge_records()

    def top_nodes(self, node_type: str, limit: int = 20) -> list[dict[str, Any]]:
        label = neo4j_label(node_type)
        records = self._run(
            f"""
            MATCH (n:MiageNode:{label})
            OPTIONAL MATCH (:Thesis)-[e]->(n)
            RETURN n.node_id AS node_id,
                   n.node_type AS node_type,
                   n.label AS label,
                   count(e) AS incoming_edges
            ORDER BY incoming_edges DESC, label ASC
            LIMIT $limit
            """,
            {"limit": int(limit)},
        )
        return [dict(record) for record in records]

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
        search = query.strip().lower() if query and query.strip() else ""
        records = self._run(
            """
            MATCH (t:Thesis)
            WHERE coalesce(t.status, 'active') = 'active'
              AND (
                $search = ''
                OR toLower(coalesce(t.title, '')) CONTAINS $search
                OR toLower(coalesce(t.concepts, '')) CONTAINS $search
                OR toLower(coalesce(t.keywords, '')) CONTAINS $search
                OR toLower(coalesce(t.use_case, '')) CONTAINS $search
                OR toLower(coalesce(t.methodology, '')) CONTAINS $search
              )
            RETURN t { .* } AS thesis
            ORDER BY coalesce(toInteger(t.year), 0) DESC, t.thesis_id ASC
            SKIP $offset
            LIMIT $limit
            """,
            {"search": search, "limit": int(limit), "offset": int(offset)},
        )
        return [document_from_props(record["thesis"]) for record in records]

    def count_theses(self, query: str | None = None) -> int:
        search = query.strip().lower() if query and query.strip() else ""
        records = self._run(
            """
            MATCH (t:Thesis)
            WHERE coalesce(t.status, 'active') = 'active'
              AND (
                $search = ''
                OR toLower(coalesce(t.title, '')) CONTAINS $search
                OR toLower(coalesce(t.concepts, '')) CONTAINS $search
                OR toLower(coalesce(t.keywords, '')) CONTAINS $search
                OR toLower(coalesce(t.use_case, '')) CONTAINS $search
                OR toLower(coalesce(t.methodology, '')) CONTAINS $search
              )
            RETURN count(t) AS count
            """,
            {"search": search},
        )
        return int(records[0]["count"]) if records else 0

    def thesis_profile(self, thesis_id: str) -> dict[str, Any]:
        normalized_id = normalize_thesis_node_id(thesis_id).replace("thesis:", "")
        records = self._run(
            """
            MATCH (t:Thesis {thesis_id: $thesis_id})
            WHERE coalesce(t.status, 'active') = 'active'
            OPTIONAL MATCH (t)-[e]->(n:MiageNode)
            WHERE type(e) <> 'RELATED_TO'
            RETURN t { .* } AS thesis,
                   collect({
                     edge_type: type(e),
                     weight: e.weight,
                     properties_json: e.properties_json,
                     node: n { .* }
                   }) AS connections
            """,
            {"thesis_id": normalized_id},
        )
        if not records:
            raise LookupError(f"Unknown thesis: {thesis_id}")
        thesis = document_from_props(records[0]["thesis"])
        grouped: dict[str, list[dict[str, Any]]] = {label: [] for label in THESIS_EDGE_TYPES.values()}
        for connection in records[0]["connections"]:
            node = connection.get("node")
            edge_type = connection.get("edge_type")
            if not node or not edge_type:
                continue
            group = THESIS_EDGE_TYPES.get(edge_type, edge_type.lower())
            grouped.setdefault(group, []).append(
                {
                    "node_id": node.get("node_id"),
                    "node_type": node.get("node_type"),
                    "label": node.get("label"),
                    "weight": connection.get("weight"),
                    "properties": parse_json(connection.get("properties_json")),
                }
            )
        for items in grouped.values():
            items.sort(key=lambda item: (str(item["label"])))
        return {
            "thesis_id": thesis["thesis_id"],
            "title": thesis.get("title"),
            "file_name": thesis.get("file_name"),
            "pages_count": thesis.get("pages_count"),
            "year": thesis.get("year"),
            "master_level": thesis.get("master_level"),
            "track": thesis.get("track"),
            "abstract": thesis.get("abstract"),
            "keywords": thesis.get("keywords"),
            "concepts": thesis.get("concepts"),
            "use_case": thesis.get("use_case"),
            "methodology": thesis.get("methodology"),
            "extraction_confidence": thesis.get("extraction_confidence"),
            "graph": grouped,
        }

    def similar_theses(self, thesis_id: str, limit: int = 10) -> list[dict[str, Any]]:
        normalized_id = normalize_thesis_node_id(thesis_id).replace("thesis:", "")
        records = self._run(
            """
            MATCH (t:Thesis {thesis_id: $thesis_id})-[r:RELATED_TO]-(other:Thesis)
            WHERE coalesce(other.status, 'active') = 'active'
            RETURN other { .* } AS thesis,
                   r.weight AS weight,
                   r.properties_json AS properties_json
            ORDER BY weight DESC, other.thesis_id ASC
            LIMIT $limit
            """,
            {"thesis_id": normalized_id, "limit": int(limit)},
        )
        rows = []
        for record in records:
            thesis = document_from_props(record["thesis"])
            rows.append(
                {
                    "thesis_id": thesis["thesis_id"],
                    "title": thesis.get("title"),
                    "year": thesis.get("year"),
                    "master_level": thesis.get("master_level"),
                    "track": thesis.get("track"),
                    "use_case": thesis.get("use_case"),
                    "methodology": thesis.get("methodology"),
                    "weight": record["weight"],
                    **parse_related_properties(record.get("properties_json")),
                }
            )
        return rows

    def theses_by_entity(self, node_type: str, label: str, limit: int = 20) -> list[dict[str, Any]]:
        edge_type = edge_type_for_node_type(node_type)
        records = self._run_theses_for_filters(
            [{"edge_type": edge_type, "target_id": entity_node_id(node_type, label)}],
            required_count=1,
            limit=limit,
            offset=0,
        )
        return records

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
        filters = cypher_filters(build_search_filters(concepts, keywords, use_case, methodology, year, master_level, track))
        if not filters:
            return []
        required_count = len(filters) if match.lower() == "all" else 1
        return self._run_theses_for_filters(filters, required_count=required_count, limit=limit, offset=offset)

    def count_search_theses(
        self,
        concepts: Iterable[str] | None = None,
        keywords: Iterable[str] | None = None,
        use_case: str | None = None,
        methodology: str | None = None,
        year: str | None = None,
        master_level: str | None = None,
        track: str | None = None,
        match: str = "all",
    ) -> int:
        filters = cypher_filters(build_search_filters(concepts, keywords, use_case, methodology, year, master_level, track))
        if not filters:
            return 0
        required_count = len(filters) if match.lower() == "all" else 1
        records = self._run(
            """
            MATCH (t:Thesis)-[e]->(n:MiageNode)
            WHERE coalesce(t.status, 'active') = 'active'
              AND any(filter IN $filters WHERE type(e) = filter.edge_type AND n.node_id = filter.target_id)
            WITH t, count(DISTINCT type(e) + ':' + n.node_id) AS matched_filters
            WHERE matched_filters >= $required_count
            RETURN count(t) AS count
            """,
            {"filters": filters, "required_count": required_count},
        )
        return int(records[0]["count"]) if records else 0

    def concept_overview(self, concept: str, limit: int = 10) -> dict[str, Any]:
        concept_node_id = entity_node_id("Concept", concept)
        records = self._run(
            """
            MATCH (c:Concept {node_id: $node_id})
            RETURN c { .* } AS concept
            """,
            {"node_id": concept_node_id},
        )
        if not records:
            raise LookupError(f"Unknown concept: {concept}")
        related = self._run(
            """
            MATCH (base:Concept {node_id: $node_id})<-[:HAS_CONCEPT]-(t:Thesis)-[:HAS_CONCEPT]->(other:Concept)
            WHERE other.node_id <> base.node_id
              AND coalesce(t.status, 'active') = 'active'
            RETURN other.node_id AS node_id,
                   other.node_type AS node_type,
                   other.label AS label,
                   count(DISTINCT t) AS shared_theses
            ORDER BY shared_theses DESC, label ASC
            LIMIT $limit
            """,
            {"node_id": concept_node_id, "limit": int(limit)},
        )
        return {
            "concept": records[0]["concept"],
            "theses": self.theses_by_entity("Concept", concept, limit=limit),
            "related_concepts": [dict(record) for record in related],
        }

    def _run_theses_for_filters(
        self,
        filters: list[dict[str, str]],
        required_count: int,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        records = self._run(
            """
            MATCH (t:Thesis)-[e]->(n:MiageNode)
            WHERE coalesce(t.status, 'active') = 'active'
              AND any(filter IN $filters WHERE type(e) = filter.edge_type AND n.node_id = filter.target_id)
            WITH t,
                 count(DISTINCT type(e) + ':' + n.node_id) AS matched_filters,
                 sum(coalesce(e.weight, 1.0)) AS score
            WHERE matched_filters >= $required_count
            RETURN t { .* } AS thesis,
                   matched_filters,
                   score
            ORDER BY matched_filters DESC,
                     score DESC,
                     coalesce(toInteger(t.year), 0) DESC,
                     t.thesis_id ASC
            SKIP $offset
            LIMIT $limit
            """,
            {
                "filters": filters,
                "required_count": int(required_count),
                "limit": int(limit),
                "offset": int(offset),
            },
        )
        rows = []
        for record in records:
            thesis = document_from_props(record["thesis"])
            thesis["matched_filters"] = record.get("matched_filters")
            thesis["score"] = record.get("score")
            rows.append(thesis)
        return rows

    def _merge_node(self, node_type: str, props: dict[str, Any]) -> None:
        label = neo4j_label(node_type)
        self._write(
            f"""
            MERGE (n:MiageNode:{label} {{node_id: $node_id}})
            SET n += $props
            """,
            {"node_id": props["node_id"], "props": props},
        )

    def _merge_relationship(self, edge_type: str, props: dict[str, Any]) -> None:
        relationship_type = neo4j_relationship(edge_type)
        self._write(
            f"""
            MATCH (source:MiageNode {{node_id: $source_id}})
            MATCH (target:MiageNode {{node_id: $target_id}})
            MERGE (source)-[r:{relationship_type}]->(target)
            SET r += $props
            """,
            {
                "source_id": props["source_id"],
                "target_id": props["target_id"],
                "props": props,
            },
        )

    def _run(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._driver.session(database=self.database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def _write(self, query: str, parameters: dict[str, Any] | None = None) -> None:
        with self._driver.session(database=self.database) as session:
            session.run(query, parameters or {}).consume()


def neo4j_label(label: str) -> str:
    if label not in NEO4J_NODE_LABELS:
        raise ValueError(f"Unsupported Neo4j node label: {label}")
    return f"`{label}`"


def neo4j_relationship(edge_type: str) -> str:
    if edge_type not in NEO4J_EDGE_TYPES:
        raise ValueError(f"Unsupported Neo4j relationship type: {edge_type}")
    return f"`{edge_type}`"


def cypher_filters(filters: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [{"edge_type": edge_type, "target_id": target_id, "label": label} for edge_type, target_id, label in filters]


def document_from_props(props: dict[str, Any]) -> dict[str, Any]:
    row = {field: props.get(field, "") for field in DOCUMENT_FIELDS}
    row["thesis_id"] = props.get("thesis_id") or str(props.get("node_id", "")).replace("thesis:", "")
    row["title"] = props.get("title") or props.get("label") or ""
    row["file_name"] = props.get("file_name") or ""
    row["status"] = props.get("status") or "active"
    return row


def encode_import_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_id": draft["draft_id"],
        "status": draft.get("status", "draft"),
        "created_at": draft.get("created_at", ""),
        "approved_at": draft.get("approved_at", ""),
        "approved_thesis_id": draft.get("approved_thesis_id", ""),
        "original_file_name": draft.get("original_file_name", ""),
        "staged_file_path": draft.get("staged_file_path", ""),
        "sha256": draft.get("sha256", ""),
        "pages_count": draft.get("pages_count", 0),
        "fields_json": json.dumps(draft.get("fields", {}), ensure_ascii=False, sort_keys=True),
        "extraction_confidence": draft.get("extraction_confidence", 0),
        "needs_review": bool(draft.get("needs_review")),
        "extraction_notes": draft.get("extraction_notes", ""),
        "cover_text_preview": draft.get("cover_text_preview", ""),
        "llm_suggestions_json": json.dumps(draft.get("llm_suggestions") or {}, ensure_ascii=False, sort_keys=True),
    }


def decode_import_draft(props: dict[str, Any]) -> dict[str, Any]:
    draft = dict(props)
    draft["fields"] = parse_json(draft.pop("fields_json", "{}"))
    suggestions = parse_json(draft.pop("llm_suggestions_json", "{}"))
    if suggestions:
        draft["llm_suggestions"] = suggestions
    draft["pages_count"] = int(draft.get("pages_count") or 0)
    draft["extraction_confidence"] = float(draft.get("extraction_confidence") or 0)
    draft["needs_review"] = bool(draft.get("needs_review"))
    return draft
