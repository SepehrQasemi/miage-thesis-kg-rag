from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common.paths import processed_dir, raw_pdf_dir
from common.pipeline_outputs import DOCUMENT_EXPORT_COLUMNS
from graph.knowledge_graph import build_knowledge_graph
from graph.neo4j_store import Neo4jGraphQueryService, neo4j_settings_from_env
from ingestion.import_workflow import (
    ImportWorkflowError,
    approve_import,
    create_import_draft,
    create_import_drafts_batch,
    discard_import,
    load_public_draft,
)
from llm.import_review import LLMUnavailableError, generate_import_suggestions
from rag.service import RagService


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="MIAGE Thesis Knowledge Graph", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
_GRAPH_SERVICE: Any | None = None
_GRAPH_SERVICE_KEY: tuple[Any, ...] | None = None
_RAG_SERVICES: dict[tuple[Any, ...], RagService] = {}


class ImportApproval(BaseModel):
    thesis_id: str
    title: str
    year: str
    master_level: str
    track: str
    abstract: str = ""
    keywords: str
    concepts: str
    use_case: str
    methodology: str


class LLMSuggestionRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None


class RagRequest(BaseModel):
    question: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float | None = Field(default=None, ge=0, le=10)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=20)
    all_results: bool = False
    use_llm: bool = False
    model: str | None = None


GRAPH_MAP_ENTITY_LIMITS = {
    "Concept": 24,
    "Keyword": 10,
    "UseCase": 12,
    "Methodology": 10,
    "Year": 12,
    "MasterLevel": 4,
    "Track": 4,
}
GRAPH_MAP_NODE_ORDER = {
    "Thesis": 0,
    "Concept": 1,
    "UseCase": 2,
    "Methodology": 3,
    "Keyword": 4,
    "Year": 5,
    "MasterLevel": 6,
    "Track": 7,
}
GRAPH_MAP_EDGE_TYPES = {
    "HAS_CONCEPT",
    "HAS_KEYWORD",
    "HAS_USE_CASE",
    "USES_METHODOLOGY",
    "SUBMITTED_IN",
    "HAS_MASTER_LEVEL",
    "HAS_TRACK",
}


def graph_backend() -> str:
    return "neo4j"


def service() -> Neo4jGraphQueryService:
    global _GRAPH_SERVICE, _GRAPH_SERVICE_KEY
    settings = neo4j_settings_from_env()
    key = ("neo4j", settings.uri, settings.user, settings.database)
    if _GRAPH_SERVICE is None or _GRAPH_SERVICE_KEY != key:
        _GRAPH_SERVICE = Neo4jGraphQueryService(settings=settings)
        _GRAPH_SERVICE_KEY = key
    return _GRAPH_SERVICE


def rag_service() -> RagService:
    settings = neo4j_settings_from_env()
    key = ("neo4j", settings.uri, settings.user, settings.database)
    service_instance = _RAG_SERVICES.get(key)
    if service_instance is None:
        graph_service = service()
        service_instance = RagService(rows_provider=graph_service.document_rows)
        _RAG_SERVICES[key] = service_instance
    return service_instance


def graph_map_payload(
    rows: list[dict[str, Any]],
    *,
    backend: str,
    thesis_limit: int = 60,
    concept_limit: int = 24,
) -> dict[str, Any]:
    graph = build_knowledge_graph(rows, related_min_shared_concepts=0)
    incoming_counts: Counter[str] = Counter()
    thesis_targets: dict[str, list[str]] = defaultdict(list)

    for edge in graph.edges.values():
        if edge.edge_type not in GRAPH_MAP_EDGE_TYPES:
            continue
        incoming_counts[edge.target_id] += 1
        if edge.source_id.startswith("thesis:"):
            thesis_targets[edge.source_id].append(edge.target_id)

    entity_limits = {**GRAPH_MAP_ENTITY_LIMITS, "Concept": concept_limit}
    selected_entities: set[str] = set()
    for node_type, limit in entity_limits.items():
        candidates = [
            node
            for node in graph.nodes.values()
            if node.node_type == node_type and incoming_counts[node.node_id] > 0
        ]
        candidates.sort(key=lambda node: (-incoming_counts[node.node_id], node.label.lower()))
        selected_entities.update(node.node_id for node in candidates[:limit])

    selected_theses = select_graph_map_theses(rows, thesis_targets, selected_entities, thesis_limit)
    selected_node_ids = set(selected_entities) | set(selected_theses)

    visible_edges = [
        edge
        for edge in graph.sorted_edges()
        if edge.edge_type in GRAPH_MAP_EDGE_TYPES
        and edge.source_id in selected_node_ids
        and edge.target_id in selected_node_ids
    ]
    visible_degree: Counter[str] = Counter()
    for edge in visible_edges:
        visible_degree[edge.source_id] += 1
        visible_degree[edge.target_id] += 1

    visible_nodes = [graph.nodes[node_id] for node_id in selected_node_ids if node_id in graph.nodes]
    visible_nodes.sort(
        key=lambda node: (
            GRAPH_MAP_NODE_ORDER.get(node.node_type, 99),
            -visible_degree[node.node_id],
            node.label.lower(),
        )
    )

    node_type_counts: Counter[str] = Counter(node.node_type for node in graph.nodes.values())
    edge_type_counts: Counter[str] = Counter(edge.edge_type for edge in graph.edges.values())
    visible_type_counts: Counter[str] = Counter(node.node_type for node in visible_nodes)

    return {
        "backend": backend,
        "nodes": [graph_map_node(node, incoming_counts, visible_degree) for node in visible_nodes],
        "edges": [
            {
                "id": edge.edge_id,
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.edge_type,
                "weight": edge.weight,
            }
            for edge in visible_edges
        ],
        "stats": {
            "source_documents": len(rows),
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "visible_nodes": len(visible_nodes),
            "visible_edges": len(visible_edges),
            "visible_node_counts": dict(sorted(visible_type_counts.items())),
            "node_counts": dict(sorted(node_type_counts.items())),
            "edge_counts": dict(sorted(edge_type_counts.items())),
            "thesis_limit": thesis_limit,
            "concept_limit": concept_limit,
        },
    }


def select_graph_map_theses(
    rows: list[dict[str, Any]],
    thesis_targets: dict[str, list[str]],
    selected_entities: set[str],
    thesis_limit: int,
) -> list[str]:
    candidates: list[tuple[int, int, str, str]] = []
    for row in rows:
        thesis_id = str(row.get("thesis_id") or "")
        if not thesis_id:
            continue
        node_id = f"thesis:{thesis_id}"
        selected_connection_count = sum(1 for target in thesis_targets.get(node_id, []) if target in selected_entities)
        if selected_connection_count <= 0:
            continue
        candidates.append((selected_connection_count, parse_year(row.get("year")), thesis_id, node_id))

    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    selected = [node_id for *_unused, node_id in candidates[:thesis_limit]]

    if len(selected) < thesis_limit:
        selected_set = set(selected)
        remaining = [
            (parse_year(row.get("year")), str(row.get("thesis_id") or ""), f"thesis:{row.get('thesis_id')}")
            for row in rows
            if row.get("thesis_id") and f"thesis:{row.get('thesis_id')}" not in selected_set
        ]
        remaining.sort(key=lambda item: (-item[0], item[1]))
        selected.extend(node_id for *_unused, node_id in remaining[: thesis_limit - len(selected)])

    return selected


def graph_map_node(node: Any, incoming_counts: Counter[str], visible_degree: Counter[str]) -> dict[str, Any]:
    properties = node.properties or {}
    if node.node_type == "Thesis":
        metadata = {
            "thesis_id": properties.get("thesis_id") or node.slug,
            "title": properties.get("title") or node.label,
            "year": properties.get("year") or "",
            "master_level": properties.get("master_level") or "",
            "track": properties.get("track") or "",
            "file_name": properties.get("file_name") or "",
        }
        subtitle = " | ".join(str(metadata[key]) for key in ["thesis_id", "year", "master_level", "track"] if metadata[key])
        return {
            "id": node.node_id,
            "type": node.node_type,
            "label": node.label,
            "subtitle": subtitle,
            "weight": max(1, visible_degree[node.node_id]),
            "incoming_edges": incoming_counts[node.node_id],
            "metadata": metadata,
        }

    return {
        "id": node.node_id,
        "type": node.node_type,
        "label": node.label,
        "subtitle": f"{incoming_counts[node.node_id]} connected thesis{'es' if incoming_counts[node.node_id] != 1 else ''}",
        "weight": max(1, incoming_counts[node.node_id]),
        "incoming_edges": incoming_counts[node.node_id],
        "metadata": {},
    }


def parse_year(value: Any) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return 0


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/summary")
def summary() -> dict:
    graph_service = service()
    result = graph_service.summary()
    result["top_concepts"] = graph_service.top_nodes("Concept", limit=10)
    result["top_use_cases"] = graph_service.top_nodes("UseCase", limit=10)
    result["top_methodologies"] = graph_service.top_nodes("Methodology", limit=10)
    return result


@app.get("/api/facets")
def facets() -> dict:
    return service().facets()


@app.get("/api/dataset")
def dataset() -> dict:
    rows = service().document_rows()
    export_rows = [
        {column: row.get(column, "") for column in DOCUMENT_EXPORT_COLUMNS}
        for row in rows
    ]
    return {
        "columns": DOCUMENT_EXPORT_COLUMNS,
        "count": len(export_rows),
        "rows": export_rows,
    }


@app.get("/api/dataset.csv")
def dataset_csv() -> FileResponse:
    csv_path = write_dataset_csv(service().document_rows())
    return FileResponse(csv_path, media_type="text/csv", filename="miage_theses.csv")


@app.get("/api/graph/map")
def graph_map(
    thesis_limit: Annotated[int, Query(ge=10, le=120)] = 60,
    concept_limit: Annotated[int, Query(ge=5, le=50)] = 24,
) -> dict[str, Any]:
    rows = service().document_rows()
    return graph_map_payload(rows, backend=graph_backend(), thesis_limit=thesis_limit, concept_limit=concept_limit)


@app.post("/api/rag/search")
def rag_search(request: RagRequest) -> dict:
    try:
        if request.all_results:
            return rag_service().search(
                request.question,
                top_k=request.page_size,
                offset=(request.page - 1) * request.page_size,
                min_score=request.min_score,
            )
        return rag_service().search(request.question, top_k=request.top_k, min_score=request.min_score)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/rag/answer")
def rag_answer(request: RagRequest) -> dict:
    try:
        return rag_service().answer(
            request.question,
            top_k=request.top_k,
            use_llm=request.use_llm,
            model=request.model,
            min_score=request.min_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/top/{node_type}")
def top_nodes(node_type: str, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict]:
    validate_node_type(node_type)
    return service().top_nodes(node_type, limit=limit)


@app.get("/api/theses")
def theses(
    q: str | None = None,
    concept: Annotated[list[str] | None, Query()] = None,
    keyword: Annotated[list[str] | None, Query()] = None,
    use_case: str | None = None,
    methodology: str | None = None,
    year: str | None = None,
    master_level: str | None = None,
    track: str | None = None,
    match: str = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict]:
    graph_service = service()
    has_graph_filters = any([concept, keyword, use_case, methodology, year, master_level, track])
    if has_graph_filters:
        return graph_service.search_theses(
            concepts=concept or [],
            keywords=keyword or [],
            use_case=use_case,
            methodology=methodology,
            year=year,
            master_level=master_level,
            track=track,
            match=match,
            limit=limit,
        )
    return graph_service.list_theses(query=q, limit=limit)


@app.get("/api/theses/page")
def theses_page(
    q: str | None = None,
    concept: Annotated[list[str] | None, Query()] = None,
    keyword: Annotated[list[str] | None, Query()] = None,
    use_case: str | None = None,
    methodology: str | None = None,
    year: str | None = None,
    master_level: str | None = None,
    track: str | None = None,
    match: str = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=20)] = 20,
) -> dict:
    graph_service = service()
    offset = (page - 1) * page_size
    has_graph_filters = any([concept, keyword, use_case, methodology, year, master_level, track])
    if has_graph_filters:
        total = graph_service.count_search_theses(
            concepts=concept or [],
            keywords=keyword or [],
            use_case=use_case,
            methodology=methodology,
            year=year,
            master_level=master_level,
            track=track,
            match=match,
        )
        rows = graph_service.search_theses(
            concepts=concept or [],
            keywords=keyword or [],
            use_case=use_case,
            methodology=methodology,
            year=year,
            master_level=master_level,
            track=track,
            match=match,
            limit=page_size,
            offset=offset,
        )
    else:
        total = graph_service.count_theses(query=q)
        rows = graph_service.list_theses(query=q, limit=page_size, offset=offset)
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_previous": page > 1 and total_pages > 0,
        "has_next": page < total_pages,
    }


@app.get("/api/theses/{thesis_id}")
def thesis_detail(thesis_id: str, similar_limit: Annotated[int, Query(ge=1, le=50)] = 8) -> dict:
    graph_service = service()
    try:
        profile = graph_service.thesis_profile(thesis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    profile["similar_theses"] = graph_service.similar_theses(thesis_id, limit=similar_limit)
    return profile


@app.get("/api/theses/{thesis_id}/similar")
def similar_theses(thesis_id: str, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[dict]:
    try:
        return service().similar_theses(thesis_id, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/concepts/{concept_label}")
def concept_detail(concept_label: str, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict:
    try:
        return service().concept_overview(concept_label, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/files/{thesis_id}")
def thesis_pdf(thesis_id: str) -> FileResponse:
    try:
        profile = service().thesis_profile(thesis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    file_name = profile.get("file_name")
    pdf_path = raw_pdf_dir() / file_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=file_name)


@app.post("/api/imports")
async def upload_import(file: UploadFile = File(...)) -> dict:
    try:
        content = await file.read()
        enable_ocr = os.environ.get("MIAGE_IMPORT_OCR", "1").lower() not in {"0", "false", "no"}
        return create_import_draft(file.filename or "upload.pdf", content, graph_service=service(), enable_ocr=enable_ocr)
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import extraction failed: {exc}") from exc


@app.post("/api/imports/batch")
async def upload_import_batch(files: list[UploadFile] = File(...)) -> dict:
    try:
        file_items = [(file.filename or "upload.pdf", await file.read()) for file in files]
        enable_ocr = os.environ.get("MIAGE_IMPORT_OCR", "1").lower() not in {"0", "false", "no"}
        return create_import_drafts_batch(file_items, graph_service=service(), enable_ocr=enable_ocr)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Batch import failed: {exc}") from exc


@app.get("/api/imports/{draft_id}")
def import_draft(draft_id: str) -> dict:
    try:
        return load_public_draft(draft_id, graph_service=service())
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/imports/{draft_id}/approve")
def approve_import_draft(draft_id: str, approval: ImportApproval) -> dict:
    try:
        payload = approval.model_dump() if hasattr(approval, "model_dump") else approval.dict()
        result = approve_import(draft_id, payload, graph_service=service())
        _RAG_SERVICES.clear()
        return result
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import approval failed: {exc}") from exc


@app.post("/api/imports/{draft_id}/llm-suggestions")
def import_llm_suggestions(draft_id: str, request: LLMSuggestionRequest) -> dict:
    try:
        return generate_import_suggestions(draft_id, request.fields, model=request.model, graph_service=service())
    except LLMUnavailableError as exc:
        return {
            "status": "unavailable",
            "message": str(exc),
            "suggestions": {},
            "confidence": 0,
            "notes": "",
        }
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"LLM suggestions failed: {exc}") from exc


@app.delete("/api/imports/{draft_id}")
def delete_import_draft(draft_id: str) -> dict:
    try:
        return discard_import(draft_id, graph_service=service())
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def validate_node_type(node_type: str) -> None:
    if node_type not in {"Concept", "Keyword", "UseCase", "Methodology", "Year", "MasterLevel", "Track"}:
        raise HTTPException(status_code=400, detail=f"Unsupported node type: {node_type}")


def write_dataset_csv(rows: list[dict[str, Any]]) -> Path:
    csv_path = processed_dir() / "theses.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DOCUMENT_EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in DOCUMENT_EXPORT_COLUMNS})
    return csv_path
