from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from extraction.text_utils import normalize_for_match
from nlp.keyword_extractor import CONCEPT_SYNONYMS


NODE_TYPES = {
    "Thesis",
    "Concept",
    "Keyword",
    "UseCase",
    "Methodology",
    "Year",
    "MasterLevel",
    "Track",
}

EDGE_TYPES = {
    "HAS_CONCEPT",
    "HAS_KEYWORD",
    "HAS_USE_CASE",
    "USES_METHODOLOGY",
    "SUBMITTED_IN",
    "HAS_MASTER_LEVEL",
    "HAS_TRACK",
    "RELATED_TO",
}

REQUIRED_THESIS_EDGE_TYPES = {
    "HAS_CONCEPT",
    "HAS_KEYWORD",
    "HAS_USE_CASE",
    "USES_METHODOLOGY",
    "SUBMITTED_IN",
    "HAS_MASTER_LEVEL",
    "HAS_TRACK",
}


@dataclass(slots=True)
class Node:
    node_id: str
    node_type: str
    label: str
    slug: str
    source: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, str]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "slug": self.slug,
            "source": self.source,
            "properties_json": json.dumps(self.properties, ensure_ascii=False, sort_keys=True),
        }


@dataclass(slots=True)
class Edge:
    edge_id: str
    source_id: str
    target_id: str
    edge_type: str
    weight: float
    source: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, str | float]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "source": self.source,
            "properties_json": json.dumps(self.properties, ensure_ascii=False, sort_keys=True),
        }


@dataclass(slots=True)
class KnowledgeGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)

    def add_node(self, node: Node) -> Node:
        existing = self.nodes.get(node.node_id)
        if existing:
            existing.properties.update({k: v for k, v in node.properties.items() if v not in ("", None, [])})
            return existing
        self.nodes[node.node_id] = node
        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        source: str,
        weight: float = 1.0,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        edge_id = stable_edge_id(source_id, target_id, edge_type)
        existing = self.edges.get(edge_id)
        if existing:
            existing.weight = max(existing.weight, weight)
            if properties:
                existing.properties.update({k: v for k, v in properties.items() if v not in ("", None, [])})
            return existing
        edge = Edge(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=round(float(weight), 4),
            source=source,
            properties=properties or {},
        )
        self.edges[edge.edge_id] = edge
        return edge

    def sorted_nodes(self) -> list[Node]:
        return sorted(self.nodes.values(), key=lambda node: (node.node_type, node.node_id))

    def sorted_edges(self) -> list[Edge]:
        return sorted(self.edges.values(), key=lambda edge: (edge.edge_type, edge.source_id, edge.target_id))


_CANONICAL_BY_NORMALIZED = {
    normalize_for_match(synonym)[0]: canonical
    for synonym, canonical in CONCEPT_SYNONYMS.items()
}

GRAPH_CONCEPT_ALIASES = {
    "apache": "apache spark",
    "bord": "tableaux de bord",
    "cartographie systematique criteres": "cartographie systematique",
    "conception": "conception logicielle",
    "darchitecture dentreprise": "architecture d'entreprise",
    "dentreprise societe generale": "architecture d'entreprise",
    "data profiling": "data profiling",
    "decisionnel": "business intelligence",
    "developpement": "developpement logiciel",
    "digital etablissement public": "transformation digitale",
    "dun projet transformation": "transformation digitale",
    "durabilite": "durabilite",
    "enjeux impacts dun": "transformation digitale",
    "flux temps reel": "data streaming",
    "genie": "genie logiciel",
    "habert modelisation dynamique": "modelisation",
    "illustree cas qualite": "qualite des donnees",
    "impacts": "transformation digitale",
    "impacts dun projet": "transformation digitale",
    "indicateurs": "indicateurs",
    "lea habert modelisation": "modelisation",
    "logiciel": "developpement logiciel",
    "lontologie metier": "ontologie metier",
    "meta modele": "meta-modele",
    "modelisation dynamique darchitecture": "architecture d'entreprise",
    "outils visualisation": "visualisation de donnees",
    "power": "business intelligence",
    "principes": "principes d'architecture",
    "projet transformation digital": "transformation digitale",
    "public quels enjeux": "transformation digitale",
    "qualite referentiels": "qualite des donnees",
    "quels enjeux impacts": "transformation digitale",
    "reel influence outils": "data streaming",
    "referentiels cartographie systematique": "qualite des donnees",
    "selection articles criteres": "cartographie systematique",
    "simulation": "simulation",
    "streaming": "data streaming",
    "systematique criteres methodes": "cartographie systematique",
    "tableaux bord": "tableaux de bord",
    "temps reel influence": "data streaming",
    "transformation digital etablissement": "transformation digitale",
    "transformation exogene modeles": "modelisation",
    "visualisation temps reel": "visualisation de donnees",
}

IGNORED_CONCEPT_KEYS = {
    "partielle",
    "standardises normalisespour ameliorer",
    "systeme",
    "tout long",
}


def split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    items = []
    for item in str(value).split(";"):
        item = " ".join(item.strip().split())
        if item and item not in items:
            items.append(item)
    return items


def slugify(value: Any) -> str:
    spaced, _ = normalize_for_match(str(value))
    slug = "-".join(spaced.split())
    if slug:
        return slug[:120]
    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]
    return f"unnamed-{digest}"


def canonical_entity_label(value: Any, node_type: str) -> str:
    label = " ".join(str(value or "").strip().split())
    if not label:
        return ""
    if node_type == "Year":
        return label
    if node_type == "MasterLevel":
        return label.upper()
    if node_type == "Track":
        return label.lower()
    if node_type == "Concept":
        return canonical_concept_label(label)
    if node_type == "Keyword":
        normalized = normalize_for_match(label)[0]
        return _CANONICAL_BY_NORMALIZED.get(normalized, label.lower())
    if node_type in {"UseCase", "Methodology"}:
        return label.lower()
    return label


def canonical_concept_label(value: Any) -> str:
    label = " ".join(str(value or "").strip().split())
    normalized = normalize_for_match(label)[0]
    if not normalized or normalized in IGNORED_CONCEPT_KEYS:
        return ""
    if normalized in GRAPH_CONCEPT_ALIASES:
        return GRAPH_CONCEPT_ALIASES[normalized]
    return _CANONICAL_BY_NORMALIZED.get(normalized, label.lower())


def concept_terms(value: Any) -> list[str]:
    labels = []
    for item in split_terms(value):
        label = canonical_concept_label(item)
        if label and label not in labels:
            labels.append(label)
    return labels


def entity_node(node_type: str, label: str, source: str, properties: dict[str, Any] | None = None) -> Node:
    canonical = canonical_entity_label(label, node_type)
    slug = slugify(canonical)
    node_id = f"{node_type.lower()}:{slug}"
    return Node(
        node_id=node_id,
        node_type=node_type,
        label=canonical,
        slug=slug,
        source=source,
        properties=properties or {},
    )


def thesis_node(row: dict[str, Any]) -> Node:
    thesis_id = str(row["thesis_id"])
    label = str(row["title"]).strip()
    return Node(
        node_id=f"thesis:{thesis_id}",
        node_type="Thesis",
        label=label,
        slug=thesis_id,
        source="documents",
        properties={
            "thesis_id": thesis_id,
            "file_name": row.get("file_name"),
            "pages_count": row.get("pages_count"),
            "year": row.get("year"),
            "master_level": row.get("master_level"),
            "track": row.get("track"),
            "title": label,
            "has_abstract": bool(str(row.get("abstract") or "").strip()),
            "extraction_confidence": row.get("extraction_confidence"),
        },
    )


def stable_edge_id(source_id: str, target_id: str, edge_type: str) -> str:
    digest = hashlib.sha1(f"{source_id}|{edge_type}|{target_id}".encode("utf-8")).hexdigest()[:16]
    return f"edge:{digest}"


def _keyword_weight(position: int) -> float:
    return max(0.25, 1.0 - (position - 1) * 0.05)


def build_knowledge_graph(
    rows: list[dict[str, Any]],
    related_min_shared_concepts: int = 3,
) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    thesis_concepts: dict[str, set[str]] = {}

    for row in rows:
        thesis = thesis_node(row)
        graph.add_node(thesis)

        year = entity_node("Year", row.get("year"), "documents.year")
        graph.add_node(year)
        graph.add_edge(thesis.node_id, year.node_id, "SUBMITTED_IN", "documents.year")

        master_level = entity_node("MasterLevel", row.get("master_level"), "documents.master_level")
        graph.add_node(master_level)
        graph.add_edge(thesis.node_id, master_level.node_id, "HAS_MASTER_LEVEL", "documents.master_level")

        track = entity_node("Track", row.get("track"), "documents.track")
        graph.add_node(track)
        graph.add_edge(thesis.node_id, track.node_id, "HAS_TRACK", "documents.track")

        use_case = entity_node("UseCase", row.get("use_case"), "documents.use_case")
        graph.add_node(use_case)
        graph.add_edge(thesis.node_id, use_case.node_id, "HAS_USE_CASE", "documents.use_case")

        methodology = entity_node("Methodology", row.get("methodology"), "documents.methodology")
        graph.add_node(methodology)
        graph.add_edge(thesis.node_id, methodology.node_id, "USES_METHODOLOGY", "documents.methodology")

        thesis_concepts[thesis.node_id] = set()
        for position, concept_label in enumerate(concept_terms(row.get("concepts")), start=1):
            concept = entity_node("Concept", concept_label, "documents.concepts")
            graph.add_node(concept)
            thesis_concepts[thesis.node_id].add(concept.node_id)
            graph.add_edge(
                thesis.node_id,
                concept.node_id,
                "HAS_CONCEPT",
                "documents.concepts",
                weight=1.0,
                properties={"position": position},
            )

        for position, keyword_label in enumerate(split_terms(row.get("keywords")), start=1):
            keyword = entity_node("Keyword", keyword_label, "documents.keywords")
            graph.add_node(keyword)
            graph.add_edge(
                thesis.node_id,
                keyword.node_id,
                "HAS_KEYWORD",
                "documents.keywords",
                weight=_keyword_weight(position),
                properties={"position": position},
            )

    if related_min_shared_concepts > 0:
        _add_related_thesis_edges(graph, thesis_concepts, related_min_shared_concepts)

    return graph


def _add_related_thesis_edges(
    graph: KnowledgeGraph,
    thesis_concepts: dict[str, set[str]],
    min_shared_concepts: int,
) -> None:
    thesis_ids = sorted(thesis_concepts)
    concept_labels = {
        node_id: graph.nodes[node_id].label
        for concepts in thesis_concepts.values()
        for node_id in concepts
        if node_id in graph.nodes
    }
    concept_document_counts: dict[str, int] = defaultdict(int)
    for concepts in thesis_concepts.values():
        for concept_id in concepts:
            concept_document_counts[concept_id] += 1

    for left_index, left_id in enumerate(thesis_ids):
        for right_id in thesis_ids[left_index + 1 :]:
            shared = sorted(thesis_concepts[left_id] & thesis_concepts[right_id])
            if len(shared) < min_shared_concepts:
                continue
            # Generic concepts are useful, but less discriminating. This keeps the
            # edge weight interpretable without discarding broad themes.
            specificity_weight = sum(1 / max(1, concept_document_counts[concept_id]) for concept_id in shared)
            graph.add_edge(
                left_id,
                right_id,
                "RELATED_TO",
                "inferred.shared_concepts",
                weight=len(shared) + specificity_weight,
                properties={
                    "shared_concept_count": len(shared),
                    "shared_concepts": [concept_labels[concept_id] for concept_id in shared],
                    "direction": "undirected",
                },
            )


def graph_summary(graph: KnowledgeGraph, thesis_count: int) -> dict[str, Any]:
    node_counts: dict[str, int] = defaultdict(int)
    edge_counts: dict[str, int] = defaultdict(int)
    incoming_counts: dict[str, int] = defaultdict(int)

    for node in graph.nodes.values():
        node_counts[node.node_type] += 1
    for edge in graph.edges.values():
        edge_counts[edge.edge_type] += 1
        incoming_counts[edge.target_id] += 1

    top_nodes_by_type: dict[str, list[dict[str, Any]]] = {}
    for node_type in ["Concept", "Keyword", "UseCase", "Methodology", "Year", "MasterLevel", "Track"]:
        nodes = [
            {
                "node_id": node.node_id,
                "label": node.label,
                "incoming_edges": incoming_counts[node.node_id],
            }
            for node in graph.nodes.values()
            if node.node_type == node_type
        ]
        nodes.sort(key=lambda item: (-item["incoming_edges"], item["label"]))
        top_nodes_by_type[node_type] = nodes[:20]

    return {
        "source_documents": thesis_count,
        "nodes_total": len(graph.nodes),
        "edges_total": len(graph.edges),
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "top_nodes_by_type": top_nodes_by_type,
    }
