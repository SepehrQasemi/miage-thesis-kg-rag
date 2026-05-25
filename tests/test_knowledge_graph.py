from graph.knowledge_graph import build_knowledge_graph, canonical_entity_label, concept_terms, slugify


def sample_row(thesis_id: str, title: str, concepts: str) -> dict:
    return {
        "thesis_id": thesis_id,
        "file_name": f"{thesis_id}.pdf",
        "pages_count": 10,
        "year": "2025",
        "title": title,
        "master_level": "M1",
        "track": "apprentissage",
        "abstract": "",
        "keywords": "IA; machine learning; detection",
        "concepts": concepts,
        "use_case": "sante / aide au diagnostic",
        "methodology": "revue de litterature / etat de l'art",
        "extraction_confidence": 1.0,
    }


def test_slugify_is_stable_ascii_identifier():
    assert slugify("Intelligence Artificielle") == "intelligence-artificielle"
    assert slugify("santé / aide au diagnostic") == "sante-aide-au-diagnostic"


def test_concept_and_keyword_aliases_are_canonicalized():
    assert canonical_entity_label("IA", "Concept") == "intelligence artificielle"
    assert canonical_entity_label("Machine Learning", "Keyword") == "machine learning"
    assert canonical_entity_label("M1", "MasterLevel") == "M1"


def test_graph_concept_cleanup_maps_extraction_fragments():
    assert concept_terms("bord; power; standardises normalisespour ameliorer") == [
        "tableaux de bord",
        "business intelligence",
    ]


def test_build_graph_creates_required_thesis_edges():
    graph = build_knowledge_graph(
        [
            sample_row("thesis_0001", "First thesis", "intelligence artificielle; machine learning; detection"),
        ],
        related_min_shared_concepts=0,
    )

    thesis_id = "thesis:thesis_0001"
    outgoing_edge_types = {
        edge.edge_type
        for edge in graph.edges.values()
        if edge.source_id == thesis_id
    }

    assert "HAS_CONCEPT" in outgoing_edge_types
    assert "HAS_KEYWORD" in outgoing_edge_types
    assert "HAS_USE_CASE" in outgoing_edge_types
    assert "USES_METHODOLOGY" in outgoing_edge_types
    assert "SUBMITTED_IN" in outgoing_edge_types
    assert "HAS_MASTER_LEVEL" in outgoing_edge_types
    assert "HAS_TRACK" in outgoing_edge_types


def test_build_graph_adds_related_thesis_edges_when_concepts_overlap():
    graph = build_knowledge_graph(
        [
            sample_row("thesis_0001", "First thesis", "intelligence artificielle; machine learning; detection"),
            sample_row("thesis_0002", "Second thesis", "IA; machine learning; detection"),
        ],
        related_min_shared_concepts=3,
    )

    related_edges = [edge for edge in graph.edges.values() if edge.edge_type == "RELATED_TO"]

    assert len(related_edges) == 1
    assert related_edges[0].properties["shared_concept_count"] == 3
