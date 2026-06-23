from graph.neo4j_store import Neo4jGraphQueryService, Neo4jSettings, document_from_props


class FakeResult:
    def data(self):
        return []

    def consume(self):
        return None


class FakeSession:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        return FakeResult()


class FakeDriver:
    def __init__(self):
        self.calls = []

    def session(self, database=None):
        self.calls.append(("SESSION", {"database": database}))
        return FakeSession(self.calls)

    def verify_connectivity(self):
        self.calls.append(("VERIFY", {}))

    def close(self):
        self.calls.append(("CLOSE", {}))


def thesis_row(thesis_id: str, title: str, concepts: str) -> dict:
    return {
        "thesis_id": thesis_id,
        "file_name": f"{thesis_id}.pdf",
        "file_path": f"/tmp/{thesis_id}.pdf",
        "sha256": f"sha-{thesis_id}",
        "pages_count": 10,
        "year": "2026",
        "title": title,
        "master_level": "M2",
        "track": "classique",
        "abstract": "",
        "keywords": "machine learning; detection",
        "concepts": concepts,
        "use_case": "sante / aide au diagnostic",
        "methodology": "comparaison experimentale",
        "extraction_confidence": 1.0,
        "status": "active",
    }


def test_replace_with_documents_writes_miage_graph_to_neo4j():
    driver = FakeDriver()
    service = Neo4jGraphQueryService(
        driver=driver,
        settings=Neo4jSettings(uri="bolt://test", user="neo4j", password="password", database="neo4j"),
    )

    result = service.replace_with_documents(
        [
            thesis_row("thesis_0001", "Cancer detection", "machine learning; detection; sante"),
            thesis_row("thesis_0002", "Medical classification", "machine learning; classification; sante"),
        ],
        related_min_shared_concepts=2,
    )

    queries = [call[0] for call in driver.calls if call[0] != "SESSION"]
    assert result["backend"] == "neo4j"
    assert result["source_documents"] == 2
    assert any("CREATE CONSTRAINT miage_node_id" in query for query in queries)
    assert any("MATCH (n:MiageNode) DETACH DELETE n" in query for query in queries)
    assert any("MERGE (n:MiageNode:`Thesis`" in query for query in queries)
    assert any("MERGE (source)-[r:`HAS_CONCEPT`]->(target)" in query for query in queries)
    assert any("MERGE (source)-[r:`RELATED_TO`]->(target)" in query for query in queries)


def test_document_from_props_keeps_thesis_fields_for_rag():
    row = document_from_props(
        {
            "node_id": "thesis:thesis_0001",
            "title": "Cancer detection",
            "concepts": "machine learning; sante",
            "status": "active",
        }
    )

    assert row["thesis_id"] == "thesis_0001"
    assert row["title"] == "Cancer detection"
    assert row["concepts"] == "machine learning; sante"
    assert row["status"] == "active"
