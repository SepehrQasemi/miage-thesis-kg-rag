from __future__ import annotations

import json
from typing import Any, Iterable

from graph.knowledge_graph import canonical_entity_label, slugify


THESIS_EDGE_TYPES = {
    "HAS_CONCEPT": "concepts",
    "HAS_KEYWORD": "keywords",
    "HAS_USE_CASE": "use_case",
    "USES_METHODOLOGY": "methodology",
    "SUBMITTED_IN": "year",
    "HAS_MASTER_LEVEL": "master_level",
    "HAS_TRACK": "track",
}


def normalize_thesis_node_id(thesis_id: str) -> str:
    thesis_id = thesis_id.strip()
    if thesis_id.startswith("thesis:"):
        return thesis_id
    return f"thesis:{thesis_id}"


def entity_node_id(node_type: str, label: str) -> str:
    canonical = canonical_entity_label(label, node_type)
    return f"{node_type.lower()}:{slugify(canonical)}"


def build_search_filters(
    concepts: Iterable[str] | None = None,
    keywords: Iterable[str] | None = None,
    use_case: str | None = None,
    methodology: str | None = None,
    year: str | None = None,
    master_level: str | None = None,
    track: str | None = None,
) -> list[tuple[str, str, str]]:
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
    return filters


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
