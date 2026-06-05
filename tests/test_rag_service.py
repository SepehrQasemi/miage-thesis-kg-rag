from common.db import connect, init_schema
from rag.embeddings import rebuild_embeddings
from rag.service import RagService


def insert_document(conn, thesis_id: str, title: str, concepts: str, use_case: str) -> None:
    conn.execute(
        """
        INSERT INTO documents (
            thesis_id, file_name, file_path, sha256, pages_count, year, title,
            master_level, track, abstract, keywords, concepts, use_case,
            methodology, extraction_confidence, status
        )
        VALUES (?, ?, ?, ?, 10, '2025', ?, 'M1', 'classique', '', ?, ?, ?, 'comparaison experimentale', 1.0, 'active')
        """,
        (
            thesis_id,
            f"{thesis_id}.pdf",
            f"/tmp/{thesis_id}.pdf",
            f"sha-{thesis_id}",
            title,
            concepts,
            concepts,
            use_case,
        ),
    )


def test_local_rag_retrieves_relevant_metadata(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Detection de fraude bancaire avec machine learning",
            "machine learning; detection; fraude",
            "detection de fraude / risque financier",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Cloud security monitoring",
            "cybersecurite; cloud computing; detection",
            "cybersecurite / detection d'attaques",
        )
        conn.commit()

    build = rebuild_embeddings(db_file)
    assert build["embedding_rows"] == 2

    result = RagService(db_file).search("fraud detection with machine learning", top_k=1)

    assert result["count"] == 1
    assert result["results"][0]["thesis_id"] == "thesis_0001"
    assert result["results"][0]["score"] > 0


def test_local_rag_answer_cites_sources(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Cybersecurity attack detection",
            "cybersecurite; detection",
            "cybersecurite / detection d'attaques",
        )
        conn.commit()

    result = RagService(db_file).answer("cybersecurity detection", top_k=1)

    assert result["answer_mode"] == "local"
    assert "thesis_0001" in result["answer"]
    assert result["sources"][0]["thesis_id"] == "thesis_0001"


def test_rag_service_reloads_cached_rows_after_embedding_rebuild(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Fraud detection",
            "machine learning; detection; fraude",
            "detection de fraude / risque financier",
        )
        conn.commit()

    service = RagService(db_file)
    first_result = service.search("fraud detection", top_k=1)
    assert first_result["results"][0]["thesis_id"] == "thesis_0001"

    with connect(db_file) as conn:
        insert_document(
            conn,
            "thesis_0002",
            "Healthcare chatbot",
            "chatbot; NLP; sante",
            "sante / aide aux patients",
        )
        conn.commit()
    rebuild_embeddings(db_file)

    second_result = service.search("healthcare chatbot NLP", top_k=1)
    assert second_result["total"] == 2
    assert second_result["results"][0]["thesis_id"] == "thesis_0002"
