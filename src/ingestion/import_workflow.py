from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from secrets import token_hex
from typing import Any

from common.paths import project_root, raw_pdf_dir, staging_dir
from common.pipeline_outputs import rebuild_graph_outputs_from_rows
from extraction.field_extractor import (
    classify_methodology,
    classify_use_case,
    confidence_score,
    extract_master_level,
    extract_title,
    extract_track,
    extract_year,
)
from extraction.pdf_reader import read_pdf_text
from extraction.section_detector import extract_sections
from graph.neo4j_store import Neo4jGraphQueryService
from nlp.keyword_extractor import extract_keywords_for_corpus, normalize_concepts


ALLOWED_MASTER_LEVELS = {"M1", "M2", "N/A"}
ALLOWED_TRACKS = {"apprentissage", "classique", "N/A"}
DEFAULT_MAX_UPLOAD_MB = 100


class ImportWorkflowError(ValueError):
    pass


def create_import_draft(
    file_name: str,
    content: bytes,
    graph_service: Neo4jGraphQueryService | None = None,
    enable_ocr: bool = True,
    reserved_ids: set[str] | None = None,
) -> dict[str, Any]:
    graph_service = graph_service or Neo4jGraphQueryService()
    clean_name = safe_filename(file_name)
    if not clean_name.lower().endswith(".pdf"):
        raise ImportWorkflowError("Only PDF files can be imported.")
    validate_pdf_content(content)

    digest = hashlib.sha256(content).hexdigest()
    duplicate = graph_service.find_duplicate_by_sha256(digest)
    if duplicate:
        return {
            "status": "duplicate",
            "duplicate": duplicate,
            "draft": None,
        }

    draft_id = new_draft_id()
    upload_dir = staging_dir() / "imports" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    staged_path = upload_dir / f"{draft_id}__{clean_name}"
    staged_path.write_bytes(content)

    try:
        draft = extract_draft_metadata(
            draft_id=draft_id,
            staged_path=staged_path,
            original_file_name=clean_name,
            sha256=digest,
            graph_service=graph_service,
            enable_ocr=enable_ocr,
            reserved_ids=reserved_ids,
        )
        save_draft(draft, graph_service)
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise

    return {
        "status": "draft",
        "duplicate": None,
        "draft": public_draft(draft),
    }


def create_import_drafts_batch(
    file_items: list[tuple[str, bytes]],
    graph_service: Neo4jGraphQueryService | None = None,
    enable_ocr: bool = True,
) -> dict[str, Any]:
    graph_service = graph_service or Neo4jGraphQueryService()
    reserved_ids = set(open_draft_thesis_ids(graph_service))
    seen_hashes: dict[str, dict[str, Any]] = {}
    results = []

    for file_name, content in file_items:
        clean_name = safe_filename(file_name)
        try:
            if not clean_name.lower().endswith(".pdf"):
                raise ImportWorkflowError("Only PDF files can be imported.")
            validate_pdf_content(content)

            digest = hashlib.sha256(content).hexdigest()
            if digest in seen_hashes:
                results.append(
                    {
                        "file_name": clean_name,
                        "status": "duplicate",
                        "duplicate": seen_hashes[digest],
                        "draft": None,
                        "error": None,
                    }
                )
                continue

            result = create_import_draft(
                clean_name,
                content,
                graph_service,
                enable_ocr=enable_ocr,
                reserved_ids=reserved_ids,
            )
            item = {"file_name": clean_name, "error": None, **result}
            if result["status"] == "draft":
                draft = result["draft"]
                fields = draft.get("fields", {})
                reserved_ids.add(str(fields.get("thesis_id", "")))
                seen_hashes[digest] = {
                    "thesis_id": fields.get("thesis_id"),
                    "title": fields.get("title"),
                    "file_name": clean_name,
                    "draft_id": draft.get("draft_id"),
                    "source": "current_batch",
                }
            elif result["status"] == "duplicate" and result.get("duplicate"):
                seen_hashes[digest] = result["duplicate"]
            results.append(item)
        except Exception as exc:
            results.append(
                {
                    "file_name": clean_name,
                    "status": "error",
                    "duplicate": None,
                    "draft": None,
                    "error": str(exc),
                }
            )

    return {
        "status": "completed",
        "total": len(results),
        "drafts_count": sum(1 for item in results if item["status"] == "draft"),
        "duplicates_count": sum(1 for item in results if item["status"] == "duplicate"),
        "errors_count": sum(1 for item in results if item["status"] == "error"),
        "results": results,
    }


def extract_draft_metadata(
    draft_id: str,
    staged_path: Path,
    original_file_name: str,
    sha256: str,
    graph_service: Neo4jGraphQueryService,
    enable_ocr: bool = True,
    reserved_ids: set[str] | None = None,
) -> dict[str, Any]:
    pdf_data = read_pdf_text(staged_path, cover_pages=3, enable_ocr=enable_ocr)
    sections = extract_sections(pdf_data["full_text"])
    cover_text = pdf_data["cover_text"]
    title = extract_title(cover_text) or title_from_filename(original_file_name)
    year = extract_year(cover_text)
    master_level = extract_master_level(cover_text + "\n" + original_file_name)
    track = extract_track(cover_text)

    analysis_text = "\n\n".join(
        item
        for item in [
            title,
            sections.get("abstract", ""),
            sections.get("introduction", ""),
            sections.get("conclusion", ""),
        ]
        if item
    ) or cover_text
    keyword_text = "\n\n".join(
        item
        for item in [
            title,
            title,
            sections.get("abstract", ""),
            sections.get("introduction", ""),
            sections.get("conclusion", ""),
        ]
        if item
    ) or "\n\n".join(item for item in [title, cover_text] if item)
    classifier_text = "\n\n".join(item for item in [analysis_text, cover_text] if item)

    semantic_key = draft_id
    keyword_map = extract_keywords_for_corpus({semantic_key: keyword_text}, limit=10)
    keywords = keyword_map.get(semantic_key, [])
    concepts = normalize_concepts(keyword_text, keywords, limit=8)

    fields = {
        "thesis_id": next_thesis_id(graph_service, reserved_ids=reserved_ids),
        "title": title,
        "year": str(year) if year else "",
        "master_level": master_level,
        "track": track,
        "abstract": sections.get("abstract", ""),
        "keywords": "; ".join(keywords),
        "concepts": "; ".join(concepts),
        "use_case": classify_use_case(classifier_text),
        "methodology": classify_methodology(classifier_text),
    }
    score = confidence_score(fields)
    missing = missing_review_fields(fields)
    notes = missing + list(pdf_data.get("ocr_notes", []))

    return {
        "draft_id": draft_id,
        "status": "draft",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "original_file_name": original_file_name,
        "staged_file_path": str(staged_path),
        "sha256": sha256,
        "pages_count": pdf_data["pages_count"],
        "fields": fields,
        "extraction_confidence": score,
        "needs_review": bool(missing or score < 0.70),
        "extraction_notes": "; ".join(notes),
        "cover_text_preview": cover_text[:3000],
    }


def approve_import(
    draft_id: str,
    fields: dict[str, Any],
    graph_service: Neo4jGraphQueryService | None = None,
) -> dict[str, Any]:
    graph_service = graph_service or Neo4jGraphQueryService()
    draft = load_draft(draft_id, graph_service)
    if draft.get("status") != "draft":
        raise ImportWorkflowError("This draft is not available for approval.")

    reviewed = normalize_review_fields({**draft.get("fields", {}), **fields})
    staged_path = Path(str(draft["staged_file_path"]))
    if not staged_path.exists():
        raise ImportWorkflowError("The staged PDF file is missing.")

    final_file_name = final_pdf_filename(reviewed["thesis_id"], draft["original_file_name"])
    destination = raw_pdf_dir() / final_file_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ImportWorkflowError(f"Target PDF already exists: {final_file_name}")

    if graph_service.thesis_id_exists(reviewed["thesis_id"]):
        raise ImportWorkflowError(f"Thesis ID already exists: {reviewed['thesis_id']}")
    duplicate = graph_service.find_duplicate_by_sha256(draft["sha256"])
    if duplicate:
        raise ImportWorkflowError(f"Duplicate PDF already exists as {duplicate['thesis_id']}.")

    previous_rows = graph_service.document_rows()
    shutil.copy2(staged_path, destination)
    record = approved_record(draft, reviewed, destination, final_file_name)
    try:
        graph_outputs = graph_service.add_document(record)
        output_files = rebuild_graph_outputs_from_rows(graph_service.document_rows())
    except Exception:
        try:
            graph_service.replace_with_documents(previous_rows)
            rebuild_graph_outputs_from_rows(previous_rows)
        except Exception:
            pass
        destination.unlink(missing_ok=True)
        raise

    draft["status"] = "approved"
    draft["approved_at"] = datetime.now().isoformat(timespec="seconds")
    draft["approved_thesis_id"] = reviewed["thesis_id"]
    save_draft(draft, graph_service)
    staged_path.unlink(missing_ok=True)

    return {
        "status": "approved",
        "thesis_id": reviewed["thesis_id"],
        "file_name": final_file_name,
        "title": reviewed["title"],
        "outputs": {**graph_outputs, **output_files},
        "embedding_outputs": {
            "backend": "neo4j",
            "embedding_source": "in_memory_graph_rows",
            "active_documents": len(graph_service.document_rows()),
        },
    }


def discard_import(draft_id: str, graph_service: Neo4jGraphQueryService | None = None) -> dict[str, str]:
    graph_service = graph_service or Neo4jGraphQueryService()
    draft = load_draft(draft_id, graph_service)
    staged_path = Path(str(draft.get("staged_file_path", "")))
    if staged_path.exists():
        staged_path.unlink()
    graph_service.delete_import_draft(draft_id)
    return {"status": "discarded", "draft_id": draft_id}


def public_draft(draft: dict[str, Any]) -> dict[str, Any]:
    llm_reasons = llm_review_reasons(draft.get("fields", {}), draft.get("extraction_confidence", 0))
    return {
        "draft_id": draft["draft_id"],
        "status": draft["status"],
        "created_at": draft["created_at"],
        "original_file_name": draft["original_file_name"],
        "sha256": draft["sha256"],
        "pages_count": draft["pages_count"],
        "fields": draft["fields"],
        "extraction_confidence": draft["extraction_confidence"],
        "needs_review": draft["needs_review"],
        "extraction_notes": draft["extraction_notes"],
        "cover_text_preview": draft.get("cover_text_preview", ""),
        "llm_review": {
            "recommended": bool(llm_reasons),
            "reasons": llm_reasons,
            "suggestions": draft.get("llm_suggestions"),
        },
    }


def load_public_draft(draft_id: str, graph_service: Neo4jGraphQueryService | None = None) -> dict[str, Any]:
    graph_service = graph_service or Neo4jGraphQueryService()
    return public_draft(load_draft(draft_id, graph_service))


def approved_record(draft: dict[str, Any], fields: dict[str, str], pdf_path: Path, file_name: str) -> dict[str, Any]:
    root = project_root()
    try:
        file_path = str(pdf_path.relative_to(root))
    except ValueError:
        file_path = str(pdf_path)
    return {
        "thesis_id": fields["thesis_id"],
        "file_name": file_name,
        "file_path": file_path,
        "sha256": draft["sha256"],
        "pages_count": draft["pages_count"],
        "cover_text": draft.get("cover_text_preview", ""),
        "abstract": fields["abstract"],
        "introduction": "",
        "conclusion": "",
        "year": fields["year"],
        "title": fields["title"],
        "master_level": fields["master_level"],
        "track": fields["track"],
        "keywords": fields["keywords"],
        "concepts": fields["concepts"],
        "use_case": fields["use_case"],
        "methodology": fields["methodology"],
        "extraction_confidence": confidence_score(fields),
        "needs_review": 0,
        "status": "active",
        "extraction_notes": f"approved_from_ui; draft_id:{draft['draft_id']}",
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    }


def normalize_review_fields(fields: dict[str, Any]) -> dict[str, str]:
    normalized = {
        "thesis_id": clean_thesis_id(fields.get("thesis_id")),
        "title": clean_text(fields.get("title")),
        "year": clean_year(fields.get("year")),
        "master_level": clean_master_level(fields.get("master_level")),
        "track": clean_track(fields.get("track")),
        "abstract": clean_text(fields.get("abstract")),
        "keywords": clean_semicolon_list(fields.get("keywords")),
        "concepts": clean_semicolon_list(fields.get("concepts")),
        "use_case": clean_text(fields.get("use_case")) or "N/A",
        "methodology": clean_text(fields.get("methodology")) or "N/A",
    }
    if not normalized["thesis_id"]:
        raise ImportWorkflowError("Thesis ID is required.")
    if not normalized["title"]:
        raise ImportWorkflowError("Title is required.")
    if not normalized["keywords"]:
        normalized["keywords"] = "N/A"
    if not normalized["concepts"]:
        normalized["concepts"] = "N/A"
    return normalized


def next_thesis_id(graph_service: Neo4jGraphQueryService, reserved_ids: set[str] | None = None) -> str:
    max_number = 0
    for row in graph_service.document_rows():
        match = re.fullmatch(r"thesis_(\d+)", str(row.get("thesis_id") or ""))
        if match:
            max_number = max(max_number, int(match.group(1)))
    for pdf_path in raw_pdf_dir().glob("thesis_*.pdf"):
        match = re.match(r"thesis_(\d+)", pdf_path.stem)
        if match:
            max_number = max(max_number, int(match.group(1)))
    for thesis_id in set(open_draft_thesis_ids(graph_service)) | set(reserved_ids or set()):
        match = re.fullmatch(r"thesis_(\d+)", str(thesis_id))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"thesis_{max_number + 1:04d}"


def open_draft_thesis_ids(graph_service: Neo4jGraphQueryService) -> set[str]:
    return graph_service.open_import_draft_thesis_ids()


def save_draft(draft: dict[str, Any], graph_service: Neo4jGraphQueryService) -> None:
    graph_service.save_import_draft(draft)


def load_draft(draft_id: str, graph_service: Neo4jGraphQueryService) -> dict[str, Any]:
    if not re.fullmatch(r"import_[A-Za-z0-9_]+", draft_id):
        raise ImportWorkflowError("Invalid draft ID.")
    try:
        return graph_service.load_import_draft(draft_id)
    except LookupError as exc:
        raise ImportWorkflowError(str(exc)) from exc


def new_draft_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"import_{timestamp}_{token_hex(4)}"


def safe_filename(file_name: str) -> str:
    name = Path(file_name or "upload.pdf").name.strip() or "upload.pdf"
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    stem = re.sub(r"\s+", "_", stem).strip("._- ")
    return stem or "upload.pdf"


def max_upload_bytes() -> int:
    raw_value = os.environ.get("MIAGE_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        megabytes = int(str(raw_value).strip())
    except ValueError:
        megabytes = DEFAULT_MAX_UPLOAD_MB
    return max(1, megabytes) * 1024 * 1024


def validate_pdf_content(content: bytes) -> None:
    if not content:
        raise ImportWorkflowError("The uploaded PDF is empty.")
    if len(content) > max_upload_bytes():
        raise ImportWorkflowError(f"The uploaded PDF is larger than {max_upload_bytes() // (1024 * 1024)} MB.")
    if not content.lstrip().startswith(b"%PDF-"):
        raise ImportWorkflowError("The uploaded file is not a valid PDF document.")


def final_pdf_filename(thesis_id: str, original_file_name: str) -> str:
    original = safe_filename(original_file_name)
    stem = Path(original).stem
    return f"{thesis_id}__{stem}.pdf"


def title_from_filename(file_name: str) -> str:
    stem = Path(file_name).stem
    if "__" in stem:
        stem = stem.split("__", 1)[1]
    stem = re.sub(r"[_-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or "Untitled thesis"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_semicolon_list(value: Any) -> str:
    items = []
    for item in re.split(r"[;\n,]+", str(value or "")):
        cleaned = clean_text(item)
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return "; ".join(items)


def clean_thesis_id(value: Any) -> str:
    thesis_id = clean_text(value)
    if not re.fullmatch(r"thesis_\d{4,}", thesis_id):
        raise ImportWorkflowError("Thesis ID must follow the format thesis_0000.")
    return thesis_id


def clean_year(value: Any) -> str:
    year = clean_text(value)
    if not year:
        return "N/A"
    if year == "N/A":
        return year
    if not re.fullmatch(r"\d{4}", year):
        raise ImportWorkflowError("Year must be a four-digit value or N/A.")
    if not 2000 <= int(year) <= 2035:
        raise ImportWorkflowError("Year must be between 2000 and 2035, or N/A.")
    return year


def clean_master_level(value: Any) -> str:
    level = clean_text(value).upper() or "N/A"
    if level not in ALLOWED_MASTER_LEVELS:
        raise ImportWorkflowError("Master level must be M1, M2, or N/A.")
    return level


def clean_track(value: Any) -> str:
    track = clean_text(value).lower() or "N/A"
    if track == "mixte":
        track = "classique"
    if track not in ALLOWED_TRACKS:
        raise ImportWorkflowError("Track must be apprentissage, classique, or N/A.")
    return track


def missing_review_fields(fields: dict[str, Any]) -> list[str]:
    missing = []
    for label in ["title", "year", "master_level", "track", "keywords", "concepts", "use_case", "methodology"]:
        if not clean_text(fields.get(label)):
            missing.append(f"missing_{label}")
    return missing


def llm_review_reasons(fields: dict[str, Any], confidence: Any) -> list[str]:
    reasons = []
    for label in ["title", "year", "master_level", "track", "keywords", "concepts", "use_case", "methodology"]:
        if not clean_text(fields.get(label)):
            reasons.append(f"missing_{label}")
    if len([item for item in str(fields.get("keywords") or "").split(";") if item.strip()]) < 2:
        reasons.append("few_keywords")
    if len([item for item in str(fields.get("concepts") or "").split(";") if item.strip()]) < 2:
        reasons.append("few_concepts")
    try:
        score = float(confidence or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score < 0.80:
        reasons.append("low_confidence")
    return list(dict.fromkeys(reasons))
