from common.db import connect, init_schema
from graph.knowledge_graph import build_knowledge_graph
from graph.query import GraphQueryService


def row(thesis_id: str, title: str, concepts: str, track: str = "apprentissage") -> dict:
    return {
        "thesis_id": thesis_id,
        "file_name": f"{thesis_id}.pdf",
        "file_path": f"/tmp/{thesis_id}.pdf",
        "sha256": thesis_id,
        "pages_count": 12,
        "year": "2025",
        "title": title,
        "master_level": "M1",
        "track": track,
        "abstract": "",
        "keywords": "machine learning; detection; sante",
        "concepts": concepts,
        "use_case": "sante / aide au diagnostic",
        "methodology": "comparaison experimentale",
        "extraction_confidence": 1.0,
    }


def make_service(tmp_path):
    db_file = tmp_path / "test.sqlite"
    rows = [
        row("thesis_0001", "Cancer detection", "machine learning; detection; sante"),
        row("thesis_0002", "Medical classification", "IA; detection; sante"),
        row("thesis_0003", "Cloud security", "cybersecurite; cloud computing; detection", track="mixte"),
    ]
    graph = build_knowledge_graph(rows, related_min_shared_concepts=2)
    with connect(db_file) as conn:
        init_schema(conn)
        for item in rows:
            conn.execute(
                """
                INSERT INTO documents (
                    thesis_id, file_name, file_path, sha256, pages_count, year, title,
                    master_level, track, abstract, keywords, concepts, use_case,
                    methodology, extraction_confidence, status
                )
                VALUES (
                    :thesis_id, :file_name, :file_path, :sha256, :pages_count, :year, :title,
                    :master_level, :track, :abstract, :keywords, :concepts, :use_case,
                    :methodology, :extraction_confidence, 'active'
                )
                """,
                item,
            )
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
    return GraphQueryService(db_file)


def test_summary_counts_graph_tables(tmp_path):
    service = make_service(tmp_path)
    summary = service.summary()

    assert summary["node_counts"]["Thesis"] == 3
    assert summary["edge_counts"]["HAS_CONCEPT"] >= 9


def test_search_theses_matches_all_filters(tmp_path):
    service = make_service(tmp_path)
    results = service.search_theses(
        concepts=["machine learning", "sante"],
        track="apprentissage",
        match="all",
    )

    assert [item["thesis_id"] for item in results] == ["thesis_0001"]


def test_similar_theses_uses_related_edges(tmp_path):
    service = make_service(tmp_path)
    results = service.similar_theses("thesis_0001", limit=5)

    assert results[0]["thesis_id"] == "thesis_0002"
    assert results[0]["shared_concept_count"] >= 2


def test_thesis_profile_groups_connected_nodes(tmp_path):
    service = make_service(tmp_path)
    profile = service.thesis_profile("thesis_0001")

    concept_labels = {item["label"] for item in profile["graph"]["concepts"]}
    assert profile["title"] == "Cancer detection"
    assert "machine learning" in concept_labels
    assert "sante" in concept_labels


def test_list_theses_keeps_missing_years_last(tmp_path):
    service = make_service(tmp_path)
    with connect(tmp_path / "test.sqlite") as conn:
        conn.execute(
            """
            INSERT INTO documents (
                thesis_id, file_name, file_path, sha256, pages_count, year, title,
                master_level, track, abstract, keywords, concepts, use_case,
                methodology, extraction_confidence, status
            )
            VALUES (
                'thesis_0999', 'thesis_0999.pdf', '/tmp/thesis_0999.pdf', 'missing-year',
                10, 'N/A', 'Missing year', 'M1', 'mixte', '', 'cloud', 'cloud computing',
                'developpement logiciel / devops', 'comparaison experimentale', 1.0, 'active'
            )
            """
        )
        conn.commit()

    results = service.list_theses(limit=10)

    assert str(results[0]["year"]) == "2025"
    assert results[-1]["thesis_id"] == "thesis_0999"
