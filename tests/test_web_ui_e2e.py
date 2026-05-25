import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from pypdf import PdfWriter

from common.db import connect, init_schema
from graph.knowledge_graph import build_knowledge_graph

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


def seed_database(db_file: Path) -> None:
    rows = [
        document("thesis_0001", "Cancer detection", "machine learning; detection; sante"),
        document("thesis_0002", "Medical AI", "IA; detection; sante"),
        document("thesis_0003", "Cloud security", "cybersecurite; cloud computing; detection", year="2024", track="mixte"),
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


def sample_pdf_file(tmp_path: Path, file_name: str = "renewable_energy_prediction.pdf") -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.add_metadata({"/Title": Path(file_name).stem})
    pdf_path = tmp_path / file_name
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_path.write_bytes(buffer.getvalue())
    return pdf_path


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
    db_file = temp_root / "app.sqlite"
    seed_database(db_file)
    port = free_port()
    env = os.environ.copy()
    env["MIAGE_APP_DB"] = str(db_file)
    env["MIAGE_RAW_PDF_DIR"] = str(temp_root / "raw_pdf")
    env["MIAGE_STAGING_DIR"] = str(temp_root / "staging")
    env["MIAGE_PROCESSED_DIR"] = str(temp_root / "processed")
    env["MIAGE_GRAPH_DIR"] = str(temp_root / "graph")
    env["MIAGE_REPORTS_DIR"] = str(temp_root / "reports")
    env["MIAGE_IMPORT_OCR"] = "0"
    process = subprocess.Popen(
        [
            sys.executable,
            "scripts/run_web_app.py",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
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


def test_search_filter_and_detail_panel(page):
    page.get_by_role("button", name="Thesis Search").click()
    page.locator("#concept-filter").select_option("machine learning")
    page.locator("#search-button").click()
    page.locator('#thesis-table tr[data-thesis-id="thesis_0001"]').click()

    detail_panel = page.locator("#detail-panel")
    expect(detail_panel.locator(".detail-title")).to_have_text("Cancer detection")
    expect(detail_panel.locator(".detail-section", has_text="Concepts").locator(".tag.accent", has_text="machine learning")).to_be_visible()
    expect(detail_panel.get_by_text("thesis_0002")).to_be_visible()


def test_concept_explorer_shows_connected_theses(page):
    page.get_by_role("button", name="Concepts").click()
    page.locator('button.concept-item[data-concept="machine learning"]').click()

    concept_detail = page.locator("#concept-detail")
    expect(concept_detail.locator(".detail-title")).to_have_text("machine learning")
    expect(concept_detail.get_by_text("Cancer detection")).to_be_visible()
    expect(concept_detail.locator(".tag", has_text="detection")).to_be_visible()


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
    expect(page.locator("#review-thesis-id")).to_have_value("thesis_0004")
    page.locator("#generate-llm-button").click()
    expect(page.locator("#llm-suggestion-panel")).to_be_visible()
    expect(page.locator("#llm-suggestion-content")).to_contain_text("Renewable energy forecasting")
    page.locator("#apply-llm-button").click()
    expect(page.locator("#review-title")).to_have_value("Renewable energy forecasting with machine learning")
    page.locator("#approve-import-button").click()

    expect(page.locator("#import-status")).to_contain_text("Approved thesis_0004", timeout=30000)
    expect(page.locator("#review-thesis-id")).to_have_value("thesis_0005")
    page.get_by_role("button", name="Thesis Search").click()
    page.locator("#text-query").fill("forecasting")
    page.locator("#search-button").click()
    expect(page.locator('#thesis-table tr[data-thesis-id="thesis_0004"]')).to_be_visible()


def test_responsive_views_have_no_horizontal_overflow(page):
    view_buttons = ["Dashboard", "Thesis Search", "Concepts", "Import PDF"]
    viewports = [
        {"width": 390, "height": 800},
        {"width": 768, "height": 900},
        {"width": 1440, "height": 900},
    ]
    for viewport in viewports:
        page.set_viewport_size(viewport)
        for button_name in view_buttons:
            page.get_by_role("button", name=button_name).click()
            metrics = page.evaluate(
                """
                () => ({
                    innerWidth: globalThis.innerWidth,
                    scrollWidth: document.documentElement.scrollWidth
                })
                """
            )
            assert metrics["scrollWidth"] <= metrics["innerWidth"] + 1
