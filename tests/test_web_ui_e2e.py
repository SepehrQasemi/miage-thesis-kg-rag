import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import parse_qs, urlparse
from pathlib import Path

import pytest
from pypdf import PdfWriter

playwright = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright.sync_playwright
expect = playwright.expect


def document(thesis_id: str, title: str, concepts: str, year: str = "2025", track: str = "apprentissage") -> dict:
    return {
        "thesis_id": thesis_id,
        "file_name": f"{thesis_id}.pdf",
        "file_path": f"/tmp/{thesis_id}.pdf",
        "sha256": f"sha-{thesis_id}",
        "pages_count": 10,
        "year": year,
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


def seed_rows() -> list[dict]:
    return [
        document("thesis_0001", "Cancer detection", "machine learning; detection; sante"),
        document("thesis_0002", "Medical AI", "IA; detection; sante"),
        document("thesis_0003", "Cloud security", "cybersecurite; cloud computing; detection", year="2024", track="classique"),
    ]


def sample_pdf_file(tmp_path: Path, file_name: str = "renewable_energy_prediction.pdf") -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.add_metadata({"/Title": Path(file_name).stem})
    pdf_path = tmp_path / file_name
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_path.write_bytes(buffer.getvalue())
    return pdf_path


def fill_review_fields(
    page,
    *,
    title: str,
    year: str = "2026",
    master_level: str = "M1",
    track: str = "apprentissage",
    keywords: str = "machine learning; prediction",
    concepts: str = "machine learning; prediction",
    use_case: str = "business analytics",
    methodology: str = "comparaison experimentale",
    abstract: str = "",
) -> None:
    page.locator("#review-title").fill(title)
    page.locator("#review-year").fill(year)
    page.locator("#review-master-level").select_option(master_level)
    page.locator("#review-track").select_option(track)
    page.locator("#review-keywords").fill(keywords)
    page.locator("#review-concepts").fill(concepts)
    page.locator("#review-use-case").fill(use_case)
    page.locator("#review-methodology").fill(methodology)
    page.locator("#review-abstract").fill(abstract)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Server did not start at {url}: {last_error}")


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory):
    temp_root = tmp_path_factory.mktemp("web-ui")
    port = free_port()
    env = os.environ.copy()
    env["MIAGE_TEST_ROWS_JSON"] = json.dumps(seed_rows())
    env["MIAGE_RAW_PDF_DIR"] = str(temp_root / "raw_pdf")
    env["MIAGE_STAGING_DIR"] = str(temp_root / "staging")
    env["MIAGE_PROCESSED_DIR"] = str(temp_root / "processed")
    env["MIAGE_GRAPH_DIR"] = str(temp_root / "graph")
    env["MIAGE_REPORTS_DIR"] = str(temp_root / "reports")
    env["MIAGE_IMPORT_OCR"] = "0"
    repo = Path(__file__).resolve().parents[1]
    server_code = f"""
import json
import os
import sys
import uvicorn
from pathlib import Path

repo = Path(r"{repo}")
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / "src"))

from tests.fake_graph_service import FakeGraphService
from web import app as web_app

graph_service = FakeGraphService(json.loads(os.environ["MIAGE_TEST_ROWS_JSON"]))
web_app.service = lambda: graph_service
web_app._RAG_SERVICES.clear()
uvicorn.run(web_app.app, host="127.0.0.1", port={port}, log_level="warning")
"""
    process = subprocess.Popen(
        [sys.executable, "-c", server_code],
        cwd=repo,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_for_server(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture()
def page(e2e_server):
    with sync_playwright() as manager:
        browser = manager.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        console_errors = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.goto(e2e_server, wait_until="networkidle")
        yield page
        assert console_errors == []
        browser.close()


def test_dashboard_renders_graph_metrics(page):
    assert page.get_by_role("heading", name="Dashboard").is_visible()
    assert page.locator("#metric-grid").get_by_text("Theses").is_visible()
    assert page.locator("#metric-grid").get_by_text("Concepts").is_visible()
    assert page.locator("#top-concepts").get_by_text("machine learning").is_visible()
    assert page.locator(".nav-icon").count() == 0


def test_help_page_documents_main_workflows(page):
    page.get_by_role("button", name="Help").click()

    expect(page.get_by_role("heading", name="Help")).to_be_visible()
    expect(page.locator("#help-view")).to_contain_text("Import PDFs")
    expect(page.locator("#help-view")).to_contain_text("Ask / RAG")
    expect(page.locator("#help-view")).to_contain_text("python scripts/doctor.py")


def open_and_load_knowledge_graph(page, categories=("Concept", "Year")):
    page.get_by_role("button", name="Knowledge Graph").click()
    expect(page.locator("#graph-map-status")).to_contain_text("Select graph categories")
    focus_type = page.locator("#graph-focus-type").input_value()
    for category in ["Thesis", "Concept", "Year", "UseCase", "Methodology", "MasterLevel", "Track", "Keyword"]:
        checkbox = page.locator(f'.graph-category-checkbox[value="{category}"]')
        if category == focus_type or category in categories:
            checkbox.check()
        else:
            checkbox.uncheck()
    page.locator("#graph-load-button").click()
    expect(page.locator("#graph-map-status")).to_contain_text("theses in map", timeout=15000)


def test_knowledge_graph_map_renders_nodes_legend_and_inspector(page):
    page.get_by_role("button", name="Knowledge Graph").click()

    expect(page.locator("#graph-map-status")).to_contain_text("Select graph categories")
    expect(page.locator('.graph-category-checkbox[value="Thesis"]')).to_be_checked()
    expect(page.locator("#knowledge-graph-svg .graph-node")).to_have_count(0)
    page.locator("#graph-load-button").click()

    expect(page.locator("#graph-map-status")).to_contain_text("theses in map", timeout=15000)
    expect(page.locator("#graph-thesis-limit")).to_have_count(0)
    expect(page.locator("#knowledge-graph-svg .graph-node").first).to_be_visible()
    assert page.locator("#knowledge-graph-svg .graph-node").count() >= 8
    assert page.locator("#knowledge-graph-svg .graph-edge").count() >= 6
    expect(page.locator("#graph-legend")).to_contain_text("Thesis")
    expect(page.locator("#graph-legend")).to_contain_text("Concept")

    page.locator("#knowledge-graph-svg .graph-node").first.click()

    expect(page.locator("#graph-inspector")).not_to_contain_text("Select a node")
    expect(page.locator("#graph-inspector .graph-inspector-title strong")).to_be_visible()
    expect(page.locator("#graph-inspector")).to_contain_text("Connections")


def test_knowledge_graph_filters_reduce_visible_graph(page):
    open_and_load_knowledge_graph(page, categories=("Concept", "Year", "UseCase"))

    page.locator("#graph-relation-filter").select_option("UseCase")
    expect(page.locator("#graph-map-status")).to_contain_text("1 active filter")
    expect(page.locator("#graph-legend")).to_contain_text("Use case")
    expect(page.locator("#graph-legend")).not_to_contain_text("Concept")
    assert page.locator("#knowledge-graph-svg .type-usecase").count() >= 1

    page.locator("#graph-clear-filters-button").click()
    page.locator("#graph-concept-filter").select_option("cloud computing")
    expect(page.locator("#graph-map-status")).to_contain_text("1 active filter")
    expect(page.locator("#knowledge-graph-svg .type-thesis")).to_have_count(1)
    expect(page.locator("#knowledge-graph-svg")).to_contain_text("Cloud security")
    expect(page.locator("#knowledge-graph-svg")).not_to_contain_text("thesis_0003")


def test_knowledge_graph_zoom_controls_change_viewport(page):
    open_and_load_knowledge_graph(page)
    expect(page.locator("#knowledge-graph-svg .graph-node").first).to_be_visible(timeout=15000)
    expect(page.locator("#graph-zoom-label")).to_have_text("100%")

    page.locator("#graph-zoom-in").click()
    expect(page.locator("#graph-zoom-label")).to_have_text("120%")
    assert "scale(1.200)" in page.locator("#knowledge-graph-svg .graph-viewport").get_attribute("transform")

    page.locator("#graph-zoom-out").click()
    expect(page.locator("#graph-zoom-label")).to_have_text("100%")

    page.locator("#graph-zoom-in").click()
    page.locator("#graph-zoom-reset").click()
    expect(page.locator("#graph-zoom-label")).to_have_text("100%")
    assert "scale(1.000)" in page.locator("#knowledge-graph-svg .graph-viewport").get_attribute("transform")


def test_knowledge_graph_analysis_links_connect_metadata(page):
    open_and_load_knowledge_graph(page)
    expect(page.locator("#knowledge-graph-svg .graph-node").first).to_be_visible(timeout=15000)
    expect(page.locator("#knowledge-graph-svg .analysis-edge")).to_have_count(0)
    expect(page.locator("#graph-analysis-pair")).to_have_value("Year:Concept")

    page.locator("#graph-analysis-links").check()
    expect(page.locator("#graph-map-status")).to_contain_text("analysis links")
    analysis_edge_count = page.locator("#knowledge-graph-svg .analysis-edge").count()
    assert 1 <= analysis_edge_count <= 180

    has_year_concept_link = page.evaluate(
        """
        () => {
            const labels = new Map(
                [...document.querySelectorAll("#knowledge-graph-svg .graph-node")]
                    .map((node) => [node.dataset.nodeId, node.querySelector("title")?.textContent || ""])
            );
            return [...document.querySelectorAll("#knowledge-graph-svg .analysis-edge")].some((edge) => {
                const endpoints = [labels.get(edge.dataset.source), labels.get(edge.dataset.target)].sort();
                return endpoints.some((label) => label === "Concept: cloud computing")
                    && endpoints.some((label) => label === "Year: 2024");
            });
        }
        """
    )
    assert has_year_concept_link


def test_knowledge_graph_can_use_concept_as_central_node(page):
    page.get_by_role("button", name="Knowledge Graph").click()
    page.locator("#graph-focus-type").select_option("Concept")
    for category in ["Thesis", "Concept", "Year", "UseCase", "Methodology", "MasterLevel", "Track", "Keyword"]:
        checkbox = page.locator(f'.graph-category-checkbox[value="{category}"]')
        if category in {"Concept", "Year", "Keyword"}:
            checkbox.check()
        else:
            checkbox.uncheck()

    page.locator("#graph-load-button").click()

    expect(page.locator("#graph-map-status")).to_contain_text("Concept-centered map", timeout=15000)
    expect(page.locator("#knowledge-graph-svg .graph-node").first).to_be_visible(timeout=15000)
    expect(page.locator("#knowledge-graph-svg .type-thesis")).to_have_count(0)
    assert page.locator("#knowledge-graph-svg .direct-edge").count() >= 1
    expect(page.locator("#graph-legend")).to_contain_text("Concept")
    expect(page.locator("#graph-legend")).to_contain_text("Year")


def test_knowledge_graph_can_show_theses_with_metadata_center(page):
    page.get_by_role("button", name="Knowledge Graph").click()
    page.locator("#graph-focus-type").select_option("Concept")
    for category in ["Thesis", "Concept", "Year", "UseCase", "Methodology", "MasterLevel", "Track", "Keyword"]:
        checkbox = page.locator(f'.graph-category-checkbox[value="{category}"]')
        if category in {"Thesis", "Concept", "Year"}:
            checkbox.check()
        else:
            checkbox.uncheck()

    page.locator("#graph-load-button").click()

    expect(page.locator("#graph-map-status")).to_contain_text("Concept-centered map", timeout=15000)
    expect(page.locator("#graph-map-status")).to_contain_text("thesis links")
    expect(page.locator("#knowledge-graph-svg .type-thesis").first).to_be_visible(timeout=15000)
    expect(page.locator("#graph-legend")).to_contain_text("Thesis")
    expect(page.locator("#graph-relation-filter")).to_contain_text("Theses")


def test_search_filter_and_detail_panel(page):
    page.get_by_role("button", name="Thesis Search").click()
    page.locator("#concept-filter").select_option("machine learning")
    page.locator("#search-button").click()
    page.locator('#thesis-table tr[data-thesis-id="thesis_0001"]').click()

    detail_panel = page.locator("#detail-panel")
    expect(detail_panel.locator(".detail-title")).to_have_text("Cancer detection")
    expect(detail_panel.locator(".detail-section", has_text="Concepts").locator(".tag.accent", has_text="machine learning")).to_be_visible()
    expect(detail_panel.get_by_text("thesis_0002")).to_be_visible()


def test_search_show_all_results_uses_twenty_row_pages(page):
    rows = [
        {
            "thesis_id": f"thesis_{index:04d}",
            "title": f"Paged thesis {index}",
            "year": "2025",
            "master_level": "M1",
            "track": "apprentissage",
            "use_case": "sante / aide au diagnostic",
            "methodology": "comparaison experimentale",
            "extraction_confidence": 1.0,
        }
        for index in range(1, 26)
    ]

    def paged_theses(route):
        query = parse_qs(urlparse(route.request.url).query)
        page_number = int(query.get("page", ["1"])[0])
        page_size = int(query.get("page_size", ["20"])[0])
        start = (page_number - 1) * page_size
        page_rows = rows[start:start + page_size]
        total_pages = (len(rows) + page_size - 1) // page_size
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "rows": page_rows,
                    "total": len(rows),
                    "page": page_number,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_previous": page_number > 1,
                    "has_next": page_number < total_pages,
                }
            ),
        )

    page.route("**/api/theses/page**", paged_theses)

    page.get_by_role("button", name="Thesis Search").click()
    page.get_by_role("button", name="Show all results").click()

    expect(page.locator("#result-count")).to_contain_text("25 results | 1-20 shown")
    expect(page.locator("#pagination-status")).to_contain_text("Page 1 of 2 | 20 per page")
    expect(page.locator("#thesis-table tr")).to_have_count(20)

    page.locator("#next-page-button").click()

    expect(page.locator("#result-count")).to_contain_text("25 results | 21-25 shown")
    expect(page.locator("#pagination-status")).to_contain_text("Page 2 of 2 | 20 per page")
    expect(page.locator("#thesis-table tr")).to_have_count(5)
    expect(page.locator("#thesis-table")).to_contain_text("thesis_0021")


def test_concept_explorer_shows_connected_theses(page):
    page.get_by_role("button", name="Concepts").click()
    page.locator('button.concept-item[data-concept="machine learning"]').click()

    concept_detail = page.locator("#concept-detail")
    expect(concept_detail.locator(".detail-title")).to_have_text("machine learning")
    expect(concept_detail.get_by_text("Cancer detection")).to_be_visible()
    expect(concept_detail.locator(".tag", has_text="detection")).to_be_visible()


def test_dataset_view_shows_complete_csv_table(page):
    page.get_by_role("button", name="Dataset").click()

    expect(page.locator("#dataset-count")).to_contain_text("3 rows")
    expect(page.locator("#dataset-head")).to_contain_text("thesis_id")
    expect(page.locator("#dataset-head")).to_contain_text("methodology")
    expect(page.locator("#dataset-body")).to_contain_text("thesis_0001")
    expect(page.locator("#dataset-body")).to_contain_text("Cancer detection")
    expect(page.locator("a.download-button")).to_have_attribute("href", "/api/dataset.csv")


def test_rag_view_retrieves_answer_and_sources(page):
    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("health detection with machine learning")
    page.locator("#rag-top-k").fill("2")
    page.locator("#rag-ask-button").click()

    expect(page.locator("#rag-status")).to_contain_text("Retrieved", timeout=15000)
    expect(page.locator("#rag-answer")).to_contain_text("thesis_000")
    expect(page.locator("#rag-meta")).to_contain_text("min score 0.300")
    expect(page.locator("#rag-results")).to_contain_text("Cancer detection")
    expect(page.locator("#rag-source-count")).to_contain_text("2 sources")
    expect(page.locator(".rag-score")).to_have_count(2)
    expect(page.locator(".rag-score").first).to_contain_text(".")


def test_rag_view_treats_requested_results_as_maximum(page):
    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("cloud security")
    page.locator("#rag-top-k").fill("5")
    page.locator("#rag-ask-button").click()

    expect(page.locator("#rag-status")).to_contain_text("Retrieved 1 relevant source", timeout=15000)
    expect(page.locator("#rag-source-count")).to_contain_text("1 sources")
    expect(page.locator("#rag-results")).to_contain_text("Cloud security")
    expect(page.locator("#rag-results")).not_to_contain_text("Cancer detection")
    expect(page.locator(".rag-score")).to_have_count(1)


def test_rag_show_all_sources_paginates_twenty_at_a_time(page):
    rows = [
        {
            "thesis_id": f"thesis_{index:04d}",
            "title": f"RAG paged thesis {index}",
            "year": "2025",
            "master_level": "M1",
            "track": "apprentissage" if index % 2 else "classique",
            "concepts": "machine learning; detection; health",
            "keywords": "machine learning; detection",
            "use_case": "sante / aide au diagnostic",
            "methodology": "comparaison experimentale",
            "abstract": "",
            "score": round(1 - (index / 1000), 4),
            "matched_terms": ["detection"],
            "pdf_url": f"/api/files/thesis_{index:04d}",
        }
        for index in range(1, 26)
    ]

    def rag_answer(route):
        payload = json.loads(route.request.post_data or "{}")
        assert payload["question"] == "show all health detection theses"
        assert payload["top_k"] == 5
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "question": "show all health detection theses",
                    "top_k": 5,
                    "embedding_model": "local-hash-v1",
                    "embedding_dimensions": 384,
                    "count": 5,
                    "total": len(rows),
                    "offset": 0,
                    "page": 1,
                    "page_size": 5,
                    "total_pages": 5,
                    "has_previous": False,
                    "has_next": True,
                    "results": rows[:5],
                    "answer": "Closest theses are thesis_0001, thesis_0002, thesis_0003, thesis_0004, thesis_0005.",
                    "answer_mode": "local",
                    "llm_error": "",
                    "sources": rows[:5],
                }
            ),
        )

    def rag_search(route):
        payload = json.loads(route.request.post_data or "{}")
        assert payload["question"] == "show all health detection theses"
        assert payload["page_size"] == 20
        page_number = int(payload.get("page", 1))
        page_size = int(payload.get("page_size", 20))
        start = (page_number - 1) * page_size
        page_rows = rows[start:start + page_size]
        total_pages = (len(rows) + page_size - 1) // page_size
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "question": payload.get("question", ""),
                    "top_k": page_size,
                    "embedding_model": "local-hash-v1",
                    "embedding_dimensions": 384,
                    "count": len(page_rows),
                    "total": len(rows),
                    "offset": start,
                    "page": page_number,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_previous": page_number > 1,
                    "has_next": page_number < total_pages,
                    "results": page_rows,
                }
            ),
        )

    page.route("**/api/rag/answer", rag_answer)
    page.route("**/api/rag/search", rag_search)

    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("show all health detection theses")
    page.locator("#rag-top-k").fill("999")
    page.locator("#rag-show-all").check()
    expect(page.locator("#rag-top-k")).to_be_hidden()
    expect(page.locator("#rag-page-size-display")).to_contain_text("20 per page")
    page.locator("#rag-ask-button").click()

    expect(page.locator("#rag-question")).to_have_value("show all health detection theses")
    expect(page.locator("#rag-source-count")).to_contain_text("1-20 of 25 sources")
    expect(page.locator("#rag-pagination-status")).to_contain_text("Page 1 of 2 | 20 per page")
    expect(page.locator(".rag-source-card")).to_have_count(20)
    expect(page.locator("#rag-results")).to_contain_text("thesis_0020")

    page.locator("#rag-next-page-button").click()

    expect(page.locator("#rag-source-count")).to_contain_text("21-25 of 25 sources")
    expect(page.locator("#rag-pagination-status")).to_contain_text("Page 2 of 2 | 20 per page")
    expect(page.locator(".rag-source-card")).to_have_count(5)
    expect(page.locator("#rag-results")).to_contain_text("thesis_0021")
    expect(page.locator("#rag-next-page-button")).to_be_disabled()


def test_rag_source_profile_modal_opens_inside_app(page):
    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("health detection with machine learning")
    page.locator("#rag-top-k").fill("3")
    page.locator("#rag-ask-button").click()

    profile_button = page.locator('.profile-button[data-thesis-id="thesis_0001"]')
    expect(profile_button).to_be_visible(timeout=15000)
    profile_button.click()

    modal = page.locator("#profile-modal")
    expect(modal).to_be_visible()
    expect(modal.locator("#profile-title")).to_have_text("Cancer detection")
    expect(modal.locator("#profile-meta")).to_contain_text("thesis_0001")
    expect(modal.locator("#profile-body")).to_contain_text("Use case")
    expect(modal.locator("#profile-body")).to_contain_text("Methodology")
    expect(modal.locator("#profile-body")).to_contain_text("machine learning")
    expect(modal.locator("a.pdf-link")).to_have_attribute("href", "/api/files/thesis_0001")

    page.locator("#profile-close-button").click()
    expect(modal).to_be_hidden()


def test_rag_view_validates_empty_and_short_questions(page):
    page.get_by_role("button", name="Ask / RAG").click()

    page.locator("#rag-ask-button").click()
    expect(page.locator("#rag-status")).to_contain_text("Enter a question first.")

    page.locator("#rag-question").fill("a")
    page.locator("#rag-ask-button").click()
    expect(page.locator("#rag-status")).to_contain_text("Question must be at least 2 characters.")
    expect(page.locator("#rag-answer")).to_contain_text("Ask a question to retrieve thesis sources.")


def test_rag_view_clamps_result_count_inputs(page):
    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("health detection")

    page.locator("#rag-top-k").fill("0")
    page.locator("#rag-ask-button").click()
    expect(page.locator("#rag-top-k")).to_have_value("1")
    expect(page.locator("#rag-source-count")).to_contain_text("1 sources", timeout=15000)

    page.locator("#rag-top-k").fill("999")
    page.locator("#rag-ask-button").click()
    expect(page.locator("#rag-top-k")).to_have_value("20")
    expect(page.locator("#rag-source-count")).to_contain_text("3 sources", timeout=15000)


def test_rag_view_handles_html_like_user_question(page):
    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("<script>alert('bad')</script> health detection")
    page.locator("#rag-top-k").fill("2")
    page.locator("#rag-ask-button").click()

    expect(page.locator("#rag-status")).to_contain_text("Retrieved", timeout=15000)
    expect(page.locator("#rag-results")).to_contain_text("Cancer detection")
    assert page.locator("#rag-answer script").count() == 0
    assert page.locator("#rag-results script").count() == 0


def test_import_single_pdf_from_ui_updates_dataset_search_and_rag(page, tmp_path):
    pdf_path = sample_pdf_file(tmp_path, "customer_analytics_segmentation.pdf")

    page.get_by_role("button", name="Import PDF").click()
    page.locator("#pdf-file").set_input_files(str(pdf_path))
    expect(page.locator("#file-label")).to_contain_text("customer_analytics_segmentation.pdf")
    page.locator("#process-upload-button").click()

    expect(page.locator("#review-form")).to_be_visible(timeout=15000)
    expect(page.locator("#batch-list")).to_contain_text("customer_analytics_segmentation.pdf")
    expect(page.locator("#draft-meta")).to_contain_text("customer_analytics_segmentation.pdf")
    thesis_id = page.locator("#review-thesis-id").input_value()
    assert thesis_id.startswith("thesis_")

    fill_review_fields(
        page,
        title="Customer analytics segmentation with machine learning",
        keywords="machine learning; segmentation; client",
        concepts="machine learning; segmentation; client",
        use_case="analyse client / commerce",
        methodology="comparaison experimentale",
    )
    page.locator("#approve-import-button").click()

    expect(page.locator("#import-status")).to_contain_text(f"Approved {thesis_id}", timeout=30000)
    expect(page.locator("#review-empty")).to_be_visible()
    expect(page.locator("#file-label")).to_contain_text("Select one or more PDF files")

    page.get_by_role("button", name="Thesis Search").click()
    page.locator("#text-query").fill("segmentation")
    page.locator("#search-button").click()
    expect(page.locator(f'#thesis-table tr[data-thesis-id="{thesis_id}"]')).to_be_visible()

    page.get_by_role("button", name="Dataset").click()
    expect(page.locator("#dataset-body")).to_contain_text(thesis_id)
    expect(page.locator("#dataset-body")).to_contain_text("Customer analytics segmentation")

    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("customer segmentation machine learning")
    page.locator("#rag-top-k").fill("5")
    page.locator("#rag-ask-button").click()
    expect(page.locator("#rag-results")).to_contain_text(thesis_id, timeout=15000)


def test_import_review_approval_workflow(page, tmp_path):
    pdf_path = sample_pdf_file(tmp_path, "renewable_energy_prediction.pdf")
    second_pdf_path = sample_pdf_file(tmp_path, "student_services_chatbot.pdf")
    page.route(
        "**/api/imports/*/llm-suggestions",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "suggested",
                    "model": "fake-local-model",
                    "suggestions": {
                        "title": "Renewable energy forecasting with machine learning",
                        "year": "2026",
                        "master_level": "M1",
                        "track": "apprentissage",
                        "keywords": "machine learning; prediction; energie",
                        "concepts": "machine learning; prediction; energie",
                        "use_case": "energie / environnement",
                        "methodology": "comparaison experimentale",
                        "abstract": "",
                    },
                    "confidence": 0.91,
                    "notes": "fake browser suggestion",
                    "review_reasons": ["low_confidence"],
                }
            ),
        ),
    )

    page.get_by_role("button", name="Import PDF").click()
    page.locator("#pdf-file").set_input_files([str(pdf_path), str(second_pdf_path)])
    page.locator("#process-upload-button").click()

    expect(page.locator("#review-form")).to_be_visible(timeout=15000)
    expect(page.locator("#batch-list")).to_contain_text("renewable_energy_prediction.pdf")
    expect(page.locator("#batch-list")).to_contain_text("student_services_chatbot.pdf")
    first_id = page.locator("#review-thesis-id").input_value()
    assert first_id.startswith("thesis_")
    page.locator("#generate-llm-button").click()
    expect(page.locator("#llm-suggestion-panel")).to_be_visible()
    expect(page.locator("#llm-suggestion-content")).to_contain_text("Renewable energy forecasting")
    page.locator("#apply-llm-button").click()
    expect(page.locator("#review-title")).to_have_value("Renewable energy forecasting with machine learning")
    page.locator("#approve-import-button").click()

    expect(page.locator("#import-status")).to_contain_text(f"Approved {first_id}", timeout=30000)
    expect(page.locator("#draft-meta")).to_contain_text("student_services_chatbot.pdf")
    second_id = page.locator("#review-thesis-id").input_value()
    assert second_id.startswith("thesis_")
    assert second_id != first_id

    fill_review_fields(
        page,
        title="Student services chatbot with NLP",
        keywords="chatbot; NLP; student services",
        concepts="chatbot; NLP; student services",
        use_case="services etudiants",
        methodology="prototype applicatif",
    )
    page.locator("#approve-import-button").click()

    expect(page.locator("#import-status")).to_contain_text(f"Approved {second_id}", timeout=30000)
    expect(page.locator("#review-empty")).to_be_visible()
    page.get_by_role("button", name="Thesis Search").click()
    page.locator("#text-query").fill("forecasting")
    page.locator("#search-button").click()
    expect(page.locator(f'#thesis-table tr[data-thesis-id="{first_id}"]')).to_be_visible()

    page.locator("#text-query").fill("chatbot")
    page.locator("#search-button").click()
    expect(page.locator(f'#thesis-table tr[data-thesis-id="{second_id}"]')).to_be_visible()


def test_responsive_views_use_mobile_and_tablet_layouts(page):
    view_buttons = ["Dashboard", "Knowledge Graph", "Thesis Search", "Concepts", "Dataset", "Ask / RAG", "Import PDFs"]
    viewports = [
        {"width": 320, "height": 720},
        {"width": 360, "height": 760},
        {"width": 390, "height": 800},
        {"width": 768, "height": 900},
        {"width": 1024, "height": 900},
        {"width": 1440, "height": 900},
    ]
    for viewport in viewports:
        page.set_viewport_size(viewport)
        for button_name in view_buttons:
            page.get_by_role("button", name=button_name).click()
            metrics = page.evaluate(
                """
                (buttonName) => {
                    const nav = document.querySelector(".nav-list");
                    const navButton = document.querySelector(".nav-item");
                    const activeView = document.querySelector(".view.active");
                    const activeRect = activeView.getBoundingClientRect();
                    const mainRect = document.querySelector(".main").getBoundingClientRect();
                    const toolbar = document.querySelector("#search-view.active .toolbar");
                    const ragControls = document.querySelector("#rag-view.active .rag-controls");
                    const graphControls = document.querySelector("#graph-view.active .graph-controls");
                    const graphLayout = document.querySelector("#graph-view.active .graph-layout");
                    const metricGrid = document.querySelector("#dashboard-view.active .metric-grid");
                    const pagination = document.querySelector(".view.active .pagination-controls");

                    function columnCount(element) {
                        if (!element) return 0;
                        const columns = getComputedStyle(element).gridTemplateColumns;
                        if (!columns || columns === "none") return 0;
                        return columns.split(" ").filter(Boolean).length;
                    }

                    return {
                        buttonName,
                        innerWidth: globalThis.innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        bodyScrollWidth: document.body.scrollWidth,
                        activeLeft: activeRect.left,
                        activeRight: activeRect.right,
                        mainLeft: mainRect.left,
                        mainRight: mainRect.right,
                        navDisplay: getComputedStyle(nav).display,
                        navOverflowX: getComputedStyle(nav).overflowX,
                        navButtonHeight: navButton.getBoundingClientRect().height,
                        toolbarColumns: columnCount(toolbar),
                        ragColumns: columnCount(ragControls),
                        graphControlColumns: columnCount(graphControls),
                        graphLayoutColumns: columnCount(graphLayout),
                        metricColumns: columnCount(metricGrid),
                        paginationWraps: pagination ? getComputedStyle(pagination).flexWrap : "",
                    };
                }
                """,
                button_name,
            )
            assert metrics["scrollWidth"] <= metrics["innerWidth"] + 1
            assert metrics["bodyScrollWidth"] <= metrics["innerWidth"] + 1
            assert metrics["activeLeft"] >= -1
            assert metrics["activeRight"] <= metrics["innerWidth"] + 1
            assert metrics["mainLeft"] >= -1
            assert metrics["mainRight"] <= metrics["innerWidth"] + 1

            if viewport["width"] <= 680:
                assert metrics["navDisplay"] == "flex"
                assert metrics["navOverflowX"] in {"auto", "scroll"}
                assert metrics["navButtonHeight"] >= 44
                assert metrics["paginationWraps"] in {"wrap", ""}
                if button_name == "Dashboard":
                    assert metrics["metricColumns"] == 1
                if button_name == "Thesis Search":
                    assert metrics["toolbarColumns"] == 1
                if button_name == "Ask / RAG":
                    assert metrics["ragColumns"] == 1
                if button_name == "Knowledge Graph":
                    assert metrics["graphControlColumns"] == 1
                    assert metrics["graphLayoutColumns"] == 1
            elif viewport["width"] <= 1100:
                assert metrics["navDisplay"] == "grid"
                assert metrics["navButtonHeight"] >= 42
                if button_name == "Dashboard":
                    assert metrics["metricColumns"] == 2
                if button_name == "Thesis Search":
                    assert metrics["toolbarColumns"] == 2
                if button_name == "Ask / RAG":
                    assert metrics["ragColumns"] == 2
                if button_name == "Knowledge Graph":
                    assert metrics["graphLayoutColumns"] == 1


def test_mobile_rag_profile_modal_fits_viewport(page):
    page.set_viewport_size({"width": 320, "height": 720})
    page.get_by_role("button", name="Ask / RAG").click()
    page.locator("#rag-question").fill("health detection with machine learning")
    page.locator("#rag-top-k").fill("3")
    page.locator("#rag-ask-button").click()

    profile_button = page.locator('.profile-button[data-thesis-id="thesis_0001"]')
    expect(profile_button).to_be_visible(timeout=15000)
    profile_button.click()
    modal = page.locator("#profile-modal")
    expect(modal).to_be_visible()

    metrics = page.evaluate(
        """
        () => {
            const panel = document.querySelector(".modal-panel").getBoundingClientRect();
            const close = document.querySelector("#profile-close-button").getBoundingClientRect();
            return {
                innerWidth: globalThis.innerWidth,
                innerHeight: globalThis.innerHeight,
                scrollWidth: document.documentElement.scrollWidth,
                panelLeft: panel.left,
                panelRight: panel.right,
                panelTop: panel.top,
                panelBottom: panel.bottom,
                closeHeight: close.height,
                bodyModalOpen: document.body.classList.contains("modal-open"),
            };
        }
        """
    )
    assert metrics["scrollWidth"] <= metrics["innerWidth"] + 1
    assert metrics["panelLeft"] >= -1
    assert metrics["panelRight"] <= metrics["innerWidth"] + 1
    assert metrics["panelTop"] >= -1
    assert metrics["panelBottom"] <= metrics["innerHeight"] + 1
    assert metrics["closeHeight"] >= 44
    assert metrics["bodyModalOpen"] is True
