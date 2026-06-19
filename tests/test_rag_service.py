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


def test_medical_domain_query_filters_non_medical_fillers(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Diagnostic mammographique pour la classification du cancer du sein",
            "intelligence artificielle; classification; sante",
            "sante / aide au diagnostic",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Anonymisation des donnees personnelles et usage en sante",
            "prediction; sante",
            "cybersecurite / detection d'attaques",
        )
        insert_document(
            conn,
            "thesis_0003",
            "Prediction de parties dans un jeu competitif",
            "optimisation; algorithme genetique; prediction",
            "optimisation operationnelle",
        )
        conn.commit()

    rebuild_embeddings(db_file)

    result = RagService(db_file).search("which thesis treats medical subject", top_k=5)

    assert result["domain_filters"] == ["medical"]
    assert result["total"] == 2
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001", "thesis_0002"]

    answer = RagService(db_file).answer("which thesis treats medical subject", top_k=5)
    assert "Applied domain filter: medical" in answer["answer"]
    assert "sante / aide au diagnostic" in answer["answer"]
    assert "cybersecurite / detection d'attaques" not in answer["answer"]


def test_rag_top_k_is_maximum_not_forced_result_count(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Analyse de parties dans le jeu League of Legends",
            "prediction; jeu video; league of legends",
            "analyse de performances dans le jeu League of Legends",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Optimisation de flux aeroportuaires",
            "optimisation; graphes; flux",
            "optimisation operationnelle",
        )
        insert_document(
            conn,
            "thesis_0003",
            "Cloud security monitoring",
            "cybersecurite; cloud computing; detection",
            "cybersecurite / detection d'attaques",
        )
        conn.commit()

    rebuild_embeddings(db_file)

    result = RagService(db_file).search("league of legends", top_k=5)

    assert result["top_k"] == 5
    assert result["min_score"] == 0.3
    assert result["count"] == 1
    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_returns_empty_when_every_candidate_is_below_relevance_threshold(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Cloud security monitoring",
            "cybersecurite; cloud computing; detection",
            "cybersecurite / detection d'attaques",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Fraud detection",
            "machine learning; detection; fraude",
            "detection de fraude / risque financier",
        )
        conn.commit()

    rebuild_embeddings(db_file)

    result = RagService(db_file).search("xylophone banana", top_k=5)

    assert result["count"] == 0
    assert result["total"] == 0
    assert result["results"] == []


def test_rag_ignores_user_request_words_when_filtering_anchors(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Detection de fake news avec BERT",
            "fake news; detection de desinformation; NLP",
            "medias / detection de desinformation",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Prediction du diabete avec apprentissage federe",
            "sante; federated learning; prediction",
            "sante / aide au diagnostic",
        )
        conn.execute(
            """
            UPDATE documents
            SET abstract = 'This work needs a robust medical prediction model.'
            WHERE thesis_id = 'thesis_0002'
            """
        )
        conn.commit()

    rebuild_embeddings(db_file)

    result = RagService(db_file).search("I need theses about fake news detection", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_french_ddos_query_uses_ddos_as_anchor_not_filler_words(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Detection des attaques par deni de service DDoS",
            "cybersecurite; ddos; detection",
            "cybersecurite / detection d'attaques",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Cybersecurite des systemes industriels",
            "cybersecurite; detection",
            "cybersecurite / detection d'attaques",
        )
        conn.execute(
            """
            UPDATE documents
            SET abstract = 'Je cherche des memoires et des exemples generaux de securite.'
            WHERE thesis_id = 'thesis_0002'
            """
        )
        conn.commit()

    rebuild_embeddings(db_file)

    result = RagService(db_file).search(
        "Je cherche des mémoires sur les attaques DDoS et la cybersécurité",
        top_k=5,
    )

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_quantum_computing_requires_quantum_anchor_not_generic_computing(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Loi de Moore a l'epreuve de l'informatique quantique",
            "informatique quantique; algorithmes quantiques",
            "informatique quantique / analyse technologique",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Cloud computing security monitoring",
            "cloud computing; cybersecurite; detection",
            "cybersecurite / detection d'attaques",
        )
        conn.commit()

    rebuild_embeddings(db_file)

    result = RagService(db_file).search("I am looking for theses about quantum computing", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_software_quality_control_keeps_software_context(tmp_path):
    db_file = tmp_path / "rag.sqlite"
    with connect(db_file) as conn:
        init_schema(conn)
        insert_document(
            conn,
            "thesis_0001",
            "Controle de qualite des logiciels",
            "qualite logiciels; controle qualite logiciels",
            "developpement logiciel / controle qualite",
        )
        insert_document(
            conn,
            "thesis_0002",
            "Qualite des referentiels de donnees",
            "qualite referentiels; data profiling; indicateurs",
            "gestion des donnees / controle qualite",
        )
        conn.commit()

    rebuild_embeddings(db_file)

    result = RagService(db_file).search("Which theses are about software quality control?", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


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
    assert second_result["total"] == 1
    assert second_result["results"][0]["thesis_id"] == "thesis_0002"
