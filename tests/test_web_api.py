import io

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from common.db import connect, init_schema
from graph.knowledge_graph import build_knowledge_graph
from graph.query import GraphQueryService
from ingestion import import_workflow
from llm.import_review import LLMUnavailableError
from web import app as web_app


def document(thesis_id: str, title: str, concepts: str) -> dict:
    return {
        "thesis_id": thesis_id,
        "file_name": f"{thesis_id}.pdf",
        "file_path": f"/tmp/{thesis_id}.pdf",
        "sha256": f"sha-{thesis_id}",
        "pages_count": 10,
        "year": "2025",
        "title": title,
        "master_level": "M1",
        "track": "apprentissage",
        "abstract": "",
        "keywords": "machine learning; detection; sante",
        "concepts": concepts,
        "use_case": "sante / aide au diagnostic",
        "methodology": "comparaison experimentale",
        "extraction_confidence": 1.0,
    }


def seed_database(db_file):
    rows = [
        document("thesis_0001", "Cancer detection", "machine learning; detection; sante"),
        document("thesis_0002", "Medical AI", "IA; detection; sante"),
    ]
    graph = build_knowledge_graph(rows, related_min_shared_concepts=2)
    with connect(db_file) as conn:
        init_schema(conn)
        for row in rows:
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
                row,
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


def client_for(tmp_path, monkeypatch):
    db_file = tmp_path / "web.sqlite"
    seed_database(db_file)
    monkeypatch.setenv("MIAGE_APP_DB", str(db_file))
    monkeypatch.setenv("MIAGE_RAW_PDF_DIR", str(tmp_path / "raw_pdf"))
    monkeypatch.setenv("MIAGE_STAGING_DIR", str(tmp_path / "staging"))
    monkeypatch.setenv("MIAGE_PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("MIAGE_GRAPH_DIR", str(tmp_path / "graph"))
    monkeypatch.setenv("MIAGE_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(web_app, "service", lambda: GraphQueryService(db_file))
    return TestClient(web_app.app)


def sample_pdf_bytes(title: str = "Sample thesis") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.add_metadata({"/Title": title})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def stub_pdf_text(monkeypatch):
    monkeypatch.setattr(
        import_workflow,
        "read_pdf_text",
        lambda *_args, **_kwargs: {
            "pages_count": 3,
            "cover_text": "Memoire de M1 Master MIAGE apprentissage 2026 Cancer detection",
            "full_text": "Resume Machine learning detection sante. Introduction benchmark classification prediction.",
            "ocr_notes": [],
        },
    )


def test_summary_endpoint_returns_graph_counts(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.get("/api/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["node_counts"]["Thesis"] == 2
    assert data["top_concepts"]


def test_thesis_detail_endpoint_includes_similar_theses(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.get("/api/theses/thesis_0001")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Cancer detection"
    assert data["similar_theses"][0]["thesis_id"] == "thesis_0002"


def test_filtered_thesis_search_uses_graph_filters(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.get("/api/theses", params={"concept": "machine learning", "track": "apprentissage"})

    assert response.status_code == 200
    assert [row["thesis_id"] for row in response.json()] == ["thesis_0001"]


def test_paginated_thesis_search_returns_total_and_page_size(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.get("/api/theses/page", params={"page": 1, "page_size": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total_pages"] == 2
    assert data["has_next"] is True
    assert len(data["rows"]) == 1

    second_page = client.get("/api/theses/page", params={"page": 2, "page_size": 1}).json()
    assert second_page["has_previous"] is True
    assert second_page["has_next"] is False
    assert len(second_page["rows"]) == 1


def test_paginated_thesis_search_limits_page_size_to_twenty(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.get("/api/theses/page", params={"page_size": 21})

    assert response.status_code == 422


def test_dataset_endpoint_returns_complete_csv_rows(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.get("/api/dataset")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["columns"][:4] == ["thesis_id", "file_name", "pages_count", "year"]
    assert [row["thesis_id"] for row in data["rows"]] == ["thesis_0001", "thesis_0002"]
    assert data["rows"][0]["title"] == "Cancer detection"


def test_dataset_csv_download_returns_export_file(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.get("/api/dataset.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.content.decode("utf-8-sig")
    assert "thesis_id,file_name,pages_count,year,title" in body
    assert "thesis_0001" in body


def test_rag_search_endpoint_returns_semantic_sources(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.post("/api/rag/search", json={"question": "health detection with machine learning", "top_k": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["embedding_model"] == "local-hash-v1"
    assert data["results"][0]["thesis_id"] == "thesis_0001"
    assert data["results"][0]["pdf_url"] == "/api/files/thesis_0001"


def test_rag_search_endpoint_uses_result_count_as_maximum(tmp_path, monkeypatch):
    db_file = tmp_path / "web.sqlite"
    seed_database(db_file)
    with connect(db_file) as conn:
        conn.execute(
            """
            UPDATE documents
            SET title = 'Cloud security',
                keywords = 'cybersecurite; cloud computing; detection',
                concepts = 'cybersecurite; cloud computing; detection',
                use_case = 'cybersecurite / detection d''attaques'
            WHERE thesis_id = 'thesis_0002'
            """
        )
        conn.commit()
    monkeypatch.setenv("MIAGE_APP_DB", str(db_file))
    monkeypatch.setenv("MIAGE_RAW_PDF_DIR", str(tmp_path / "raw_pdf"))
    monkeypatch.setattr(web_app, "service", lambda: GraphQueryService(db_file))
    web_app._RAG_SERVICES.clear()
    client = TestClient(web_app.app)

    response = client.post("/api/rag/search", json={"question": "cloud security", "top_k": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["top_k"] == 5
    assert data["min_score"] == 0.3
    assert data["count"] == 1
    assert data["total"] == 1
    assert data["results"][0]["thesis_id"] == "thesis_0002"


def test_rag_search_all_results_is_paginated_to_twenty_max(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.post(
        "/api/rag/search",
        json={"question": "health detection", "all_results": True, "page": 1, "page_size": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["count"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total_pages"] == 2
    assert data["has_previous"] is False
    assert data["has_next"] is True

    second_page = client.post(
        "/api/rag/search",
        json={"question": "health detection", "all_results": True, "page": 2, "page_size": 1},
    ).json()
    assert second_page["count"] == 1
    assert second_page["page"] == 2
    assert second_page["has_previous"] is True
    assert second_page["has_next"] is False


def test_rag_search_all_results_rejects_page_size_above_twenty(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.post(
        "/api/rag/search",
        json={"question": "health detection", "all_results": True, "page": 1, "page_size": 21},
    )

    assert response.status_code == 422


def test_rag_answer_endpoint_uses_local_answer_by_default(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.post("/api/rag/answer", json={"question": "medical AI detection", "top_k": 2})

    assert response.status_code == 200
    data = response.json()
    assert data["answer_mode"] == "local"
    assert "thesis_000" in data["answer"]
    assert len(data["sources"]) == 2


def test_rag_endpoint_rejects_invalid_user_input(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    response = client.post("/api/rag/search", json={"question": "a", "top_k": 0})

    assert response.status_code == 422


def test_rag_answer_falls_back_when_ollama_unavailable(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("Ollama offline")

    monkeypatch.setattr("rag.service.ollama_answer", unavailable)

    response = client.post(
        "/api/rag/answer",
        json={"question": "medical AI detection", "top_k": 1, "use_llm": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer_mode"] == "ollama_unavailable"
    assert "Ollama offline" in data["llm_error"]
    assert len(data["sources"]) == 1


def test_import_upload_creates_review_draft(tmp_path, monkeypatch):
    stub_pdf_text(monkeypatch)
    client = client_for(tmp_path, monkeypatch)

    response = client.post(
        "/api/imports",
        files={"file": ("new_thesis.pdf", sample_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["draft"]["fields"]["thesis_id"] == "thesis_0003"
    assert data["draft"]["fields"]["year"] == "2026"


def test_batch_import_creates_unique_review_drafts(tmp_path, monkeypatch):
    stub_pdf_text(monkeypatch)
    client = client_for(tmp_path, monkeypatch)

    response = client.post(
        "/api/imports/batch",
        files=[
            ("files", ("first_thesis.pdf", sample_pdf_bytes("First thesis"), "application/pdf")),
            ("files", ("second_thesis.pdf", sample_pdf_bytes("Second thesis"), "application/pdf")),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["total"] == 2
    assert data["drafts_count"] == 2
    assert data["duplicates_count"] == 0
    assert data["errors_count"] == 0
    drafts = [item["draft"] for item in data["results"]]
    assert [draft["fields"]["thesis_id"] for draft in drafts] == ["thesis_0003", "thesis_0004"]
    assert {draft["draft_id"] for draft in drafts}


def test_import_approval_updates_database_csv_and_graph(tmp_path, monkeypatch):
    stub_pdf_text(monkeypatch)
    client = client_for(tmp_path, monkeypatch)
    upload = client.post(
        "/api/imports",
        files={"file": ("new_thesis.pdf", sample_pdf_bytes(), "application/pdf")},
    )
    draft = upload.json()["draft"]
    fields = draft["fields"]
    fields.update(
        {
            "title": "Cancer detection with machine learning",
            "keywords": "machine learning; detection; sante",
            "concepts": "machine learning; detection; sante",
            "use_case": "sante / aide au diagnostic",
            "methodology": "comparaison experimentale",
        }
    )

    response = client.post(f"/api/imports/{draft['draft_id']}/approve", json=fields)

    assert response.status_code == 200
    assert response.json()["thesis_id"] == "thesis_0003"
    assert (tmp_path / "raw_pdf" / "thesis_0003__new_thesis.pdf").exists()
    assert (tmp_path / "processed" / "theses.csv").exists()
    assert (tmp_path / "graph" / "nodes.csv").exists()
    assert (tmp_path / "graph" / "edges.csv").exists()
    with connect(tmp_path / "web.sqlite") as conn:
        row = conn.execute("SELECT title FROM documents WHERE thesis_id = 'thesis_0003'").fetchone()
        node_count = conn.execute("SELECT COUNT(*) AS count FROM graph_nodes WHERE node_type = 'Thesis'").fetchone()
        embedding_count = conn.execute("SELECT COUNT(*) AS count FROM document_embeddings").fetchone()
    assert row["title"] == "Cancer detection with machine learning"
    assert node_count["count"] == 3
    assert embedding_count["count"] == 3

    duplicate = client.post(
        "/api/imports",
        files={"file": ("new_thesis.pdf", sample_pdf_bytes(), "application/pdf")},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["duplicate"]["thesis_id"] == "thesis_0003"


def test_import_llm_suggestions_do_not_update_database(tmp_path, monkeypatch):
    stub_pdf_text(monkeypatch)
    client = client_for(tmp_path, monkeypatch)
    upload = client.post(
        "/api/imports",
        files={"file": ("new_thesis.pdf", sample_pdf_bytes(), "application/pdf")},
    )
    draft = upload.json()["draft"]

    def fake_suggestions(draft_id, fields, model=None):
        assert draft_id == draft["draft_id"]
        assert fields["title"] == draft["fields"]["title"]
        return {
            "status": "suggested",
            "model": model or "fake-local-model",
            "suggestions": {
                "title": "Cancer detection with local LLM",
                "year": "2026",
                "master_level": "M1",
                "track": "apprentissage",
                "keywords": "machine learning; detection",
                "concepts": "machine learning; detection",
                "use_case": "sante / aide au diagnostic",
                "methodology": "comparaison experimentale",
                "abstract": "",
            },
            "confidence": 0.82,
            "notes": "fake suggestion",
            "review_reasons": ["low_confidence"],
        }

    monkeypatch.setattr(web_app, "generate_import_suggestions", fake_suggestions)

    response = client.post(
        f"/api/imports/{draft['draft_id']}/llm-suggestions",
        json={"fields": draft["fields"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "suggested"
    assert data["suggestions"]["title"] == "Cancer detection with local LLM"
    with connect(tmp_path / "web.sqlite") as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()
    assert count["count"] == 2


def test_import_llm_unavailable_is_non_blocking(tmp_path, monkeypatch):
    stub_pdf_text(monkeypatch)
    client = client_for(tmp_path, monkeypatch)
    upload = client.post(
        "/api/imports",
        files={"file": ("new_thesis.pdf", sample_pdf_bytes(), "application/pdf")},
    )
    draft = upload.json()["draft"]

    def unavailable(*_args, **_kwargs):
        raise LLMUnavailableError("Ollama unavailable")

    monkeypatch.setattr(web_app, "generate_import_suggestions", unavailable)

    response = client.post(
        f"/api/imports/{draft['draft_id']}/llm-suggestions",
        json={"fields": draft["fields"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
