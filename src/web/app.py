from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common.paths import db_path, raw_pdf_dir
from common.pipeline_outputs import DOCUMENT_EXPORT_COLUMNS, active_documents, write_document_csv
from graph.query import GraphQueryService
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
_RAG_SERVICES: dict[Path, RagService] = {}


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


def database_path() -> Path:
    db_override = os.environ.get("MIAGE_APP_DB")
    return Path(db_override) if db_override else db_path()


def service() -> GraphQueryService:
    return GraphQueryService(database_path())


def rag_service() -> RagService:
    path = database_path()
    service_instance = _RAG_SERVICES.get(path)
    if service_instance is None:
        service_instance = RagService(path)
        _RAG_SERVICES[path] = service_instance
    return service_instance


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
    rows = active_documents(database_path())
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
    csv_path = write_document_csv(database_path())
    return FileResponse(csv_path, media_type="text/csv", filename="miage_theses.csv")


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
        return create_import_draft(file.filename or "upload.pdf", content, database_path(), enable_ocr=enable_ocr)
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import extraction failed: {exc}") from exc


@app.post("/api/imports/batch")
async def upload_import_batch(files: list[UploadFile] = File(...)) -> dict:
    try:
        file_items = [(file.filename or "upload.pdf", await file.read()) for file in files]
        enable_ocr = os.environ.get("MIAGE_IMPORT_OCR", "1").lower() not in {"0", "false", "no"}
        return create_import_drafts_batch(file_items, database_path(), enable_ocr=enable_ocr)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Batch import failed: {exc}") from exc


@app.get("/api/imports/{draft_id}")
def import_draft(draft_id: str) -> dict:
    try:
        return load_public_draft(draft_id)
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/imports/{draft_id}/approve")
def approve_import_draft(draft_id: str, approval: ImportApproval) -> dict:
    try:
        payload = approval.model_dump() if hasattr(approval, "model_dump") else approval.dict()
        return approve_import(draft_id, payload, database_path())
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import approval failed: {exc}") from exc


@app.post("/api/imports/{draft_id}/llm-suggestions")
def import_llm_suggestions(draft_id: str, request: LLMSuggestionRequest) -> dict:
    try:
        return generate_import_suggestions(draft_id, request.fields, model=request.model)
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
        return discard_import(draft_id)
    except ImportWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def validate_node_type(node_type: str) -> None:
    if node_type not in {"Concept", "Keyword", "UseCase", "Methodology", "Year", "MasterLevel", "Track"}:
        raise HTTPException(status_code=400, detail=f"Unsupported node type: {node_type}")
