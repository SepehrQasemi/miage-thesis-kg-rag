from rag.service import RagService


def document(
    thesis_id: str,
    title: str,
    concepts: str,
    use_case: str,
    *,
    keywords: str | None = None,
    abstract: str = "",
    year: str = "2025",
    master_level: str = "M1",
    track: str = "classique",
) -> dict:
    return {
        "thesis_id": thesis_id,
        "file_name": f"{thesis_id}.pdf",
        "file_path": f"/tmp/{thesis_id}.pdf",
        "sha256": f"sha-{thesis_id}",
        "pages_count": 10,
        "year": year,
        "title": title,
        "master_level": master_level,
        "track": track,
        "abstract": abstract,
        "keywords": keywords or concepts,
        "concepts": concepts,
        "use_case": use_case,
        "methodology": "comparaison experimentale",
        "extraction_confidence": 1.0,
        "status": "active",
    }


def service_for(rows: list[dict]) -> RagService:
    return RagService(rows_provider=lambda: rows)


def test_local_rag_retrieves_relevant_metadata():
    rows = [
        document(
            "thesis_0001",
            "Detection de fraude bancaire avec machine learning",
            "machine learning; detection; fraude",
            "detection de fraude / risque financier",
        ),
        document(
            "thesis_0002",
            "Cloud security monitoring",
            "cybersecurite; cloud computing; detection",
            "cybersecurite / detection d'attaques",
        ),
    ]

    build = service_for(rows).build_embeddings()
    result = service_for(rows).search("fraud detection with machine learning", top_k=1)

    assert build["backend"] == "graph"
    assert build["embedding_rows"] == 2
    assert result["count"] == 1
    assert result["results"][0]["thesis_id"] == "thesis_0001"
    assert result["results"][0]["score"] > 0


def test_local_rag_answer_cites_sources():
    rows = [
        document(
            "thesis_0001",
            "Cybersecurity attack detection",
            "cybersecurite; detection",
            "cybersecurite / detection d'attaques",
        )
    ]

    result = service_for(rows).answer("cybersecurity detection", top_k=1)

    assert result["answer_mode"] == "local"
    assert "thesis_0001" in result["answer"]
    assert result["sources"][0]["thesis_id"] == "thesis_0001"


def test_medical_domain_query_filters_non_medical_fillers():
    rows = [
        document(
            "thesis_0001",
            "Diagnostic mammographique pour la classification du cancer du sein",
            "intelligence artificielle; classification; sante",
            "sante / aide au diagnostic",
        ),
        document(
            "thesis_0002",
            "Anonymisation des donnees personnelles et usage en sante",
            "prediction; sante",
            "cybersecurite / detection d'attaques",
        ),
        document(
            "thesis_0003",
            "Prediction de parties dans un jeu competitif",
            "optimisation; algorithme genetique; prediction",
            "optimisation operationnelle",
        ),
    ]

    result = service_for(rows).search("which thesis treats medical subject", top_k=5)
    answer = service_for(rows).answer("which thesis treats medical subject", top_k=5)

    assert result["domain_filters"] == ["medical"]
    assert result["total"] == 2
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001", "thesis_0002"]
    assert "Applied domain filter: medical" in answer["answer"]
    assert "sante / aide au diagnostic" in answer["answer"]
    assert "cybersecurite / detection d'attaques" not in answer["answer"]


def test_rag_top_k_is_maximum_not_forced_result_count():
    rows = [
        document(
            "thesis_0001",
            "Analyse de parties dans le jeu League of Legends",
            "prediction; jeu video; league of legends",
            "analyse de performances dans le jeu League of Legends",
        ),
        document("thesis_0002", "Optimisation de flux aeroportuaires", "optimisation; graphes; flux", "optimisation operationnelle"),
        document("thesis_0003", "Cloud security monitoring", "cybersecurite; cloud computing; detection", "cybersecurite / detection d'attaques"),
    ]

    result = service_for(rows).search("league of legends", top_k=5)

    assert result["top_k"] == 5
    assert result["min_score"] == 0.3
    assert result["count"] == 1
    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_returns_empty_when_every_candidate_is_below_relevance_threshold():
    rows = [
        document("thesis_0001", "Cloud security monitoring", "cybersecurite; cloud computing; detection", "cybersecurite / detection d'attaques"),
        document("thesis_0002", "Fraud detection", "machine learning; detection; fraude", "detection de fraude / risque financier"),
    ]

    result = service_for(rows).search("xylophone banana", top_k=5)

    assert result["count"] == 0
    assert result["total"] == 0
    assert result["results"] == []


def test_rag_ignores_user_request_words_when_filtering_anchors():
    rows = [
        document("thesis_0001", "Detection de fake news avec BERT", "fake news; detection de desinformation; NLP", "medias / detection de desinformation"),
        document(
            "thesis_0002",
            "Prediction du diabete avec apprentissage federe",
            "sante; federated learning; prediction",
            "sante / aide au diagnostic",
            abstract="This work needs a robust medical prediction model.",
        ),
    ]

    result = service_for(rows).search("I need theses about fake news detection", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_french_ddos_query_uses_ddos_as_anchor_not_filler_words():
    rows = [
        document("thesis_0001", "Detection des attaques par deni de service DDoS", "cybersecurite; ddos; detection", "cybersecurite / detection d'attaques"),
        document(
            "thesis_0002",
            "Cybersecurite des systemes industriels",
            "cybersecurite; detection",
            "cybersecurite / detection d'attaques",
            abstract="Je cherche des memoires et des exemples generaux de securite.",
        ),
    ]

    result = service_for(rows).search("Je cherche des memoires sur les attaques DDoS et la cybersecurite", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_quantum_computing_requires_quantum_anchor_not_generic_computing():
    rows = [
        document("thesis_0001", "Loi de Moore a l'epreuve de l'informatique quantique", "informatique quantique; algorithmes quantiques", "informatique quantique / analyse technologique"),
        document("thesis_0002", "Cloud computing security monitoring", "cloud computing; cybersecurite; detection", "cybersecurite / detection d'attaques"),
    ]

    result = service_for(rows).search("I am looking for theses about quantum computing", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_league_of_legends_does_not_match_language_models_by_substring():
    rows = [
        document("thesis_0001", "Prediction de parties dans le jeu League of Legends", "prediction; league legends; game analytics", "optimisation operationnelle"),
        document("thesis_0002", "Vision Language Models pour les mammographies", "prediction; sante; vision language models", "sante / aide au diagnostic"),
    ]

    result = service_for(rows).search("league of legends game prediction", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_finance_query_filters_quantum_crypto_false_positive():
    rows = [
        document("thesis_0001", "Online automatic trading of crypto currency", "finance; crypto; trading", "finance / marche crypto"),
        document("thesis_0002", "Loi de Moore a l'epreuve de l'informatique quantique", "informatique quantique; cryptographie quantique", "informatique quantique / calcul"),
    ]

    result = service_for(rows).search("finance crypto market", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_software_quality_control_keeps_software_context():
    rows = [
        document("thesis_0001", "Controle de qualite des logiciels", "qualite logiciels; controle qualite logiciels", "developpement logiciel / controle qualite"),
        document("thesis_0002", "Qualite des referentiels de donnees", "qualite referentiels; data profiling; indicateurs", "gestion des donnees / controle qualite"),
    ]

    result = service_for(rows).search("Which theses are about software quality control?", top_k=5)

    assert result["total"] == 1
    assert [row["thesis_id"] for row in result["results"]] == ["thesis_0001"]


def test_rag_service_reloads_cached_rows_after_graph_rows_change():
    rows = [
        document("thesis_0001", "Fraud detection", "machine learning; detection; fraude", "detection de fraude / risque financier")
    ]
    service = service_for(rows)
    first_result = service.search("fraud detection", top_k=1)
    assert first_result["results"][0]["thesis_id"] == "thesis_0001"

    rows.append(document("thesis_0002", "Healthcare chatbot", "chatbot; NLP; sante", "sante / aide aux patients"))

    second_result = service.search("healthcare chatbot NLP", top_k=1)
    assert second_result["total"] == 1
    assert second_result["results"][0]["thesis_id"] == "thesis_0002"
