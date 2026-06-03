import argparse
import csv
from datetime import datetime
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path, raw_pdf_dir, reports_dir
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
from nlp.keyword_extractor import extract_keywords_for_corpus, normalize_concepts


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def thesis_id_from_name(path: Path) -> str:
    stem = path.stem
    if "__" in stem:
        return stem.split("__", 1)[0]
    return stem


def build_record(pdf_path: Path, enable_ocr: bool = True) -> dict:
    pdf_data = read_pdf_text(pdf_path, cover_pages=3, enable_ocr=enable_ocr)
    sections = extract_sections(pdf_data["full_text"])
    cover_text = pdf_data["cover_text"]
    title = extract_title(cover_text)
    year = extract_year(cover_text)
    master_level = extract_master_level(cover_text + "\n" + pdf_path.name)
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
    )
    if not analysis_text:
        analysis_text = cover_text

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
    )
    if not keyword_text:
        keyword_text = "\n\n".join(
            item
            for item in [
                title,
                cover_text,
            ]
            if item
        )

    classifier_text = "\n\n".join(
        item
        for item in [
            analysis_text,
            cover_text,
        ]
        if item
    )

    return {
        "thesis_id": thesis_id_from_name(pdf_path),
        "file_name": pdf_path.name,
        "file_path": str(pdf_path.relative_to(ROOT)),
        "sha256": sha256_file(pdf_path),
        "pages_count": pdf_data["pages_count"],
        "cover_text": cover_text,
        "abstract": sections.get("abstract", ""),
        "introduction": sections.get("introduction", ""),
        "conclusion": sections.get("conclusion", ""),
        "year": year,
        "title": title,
        "master_level": master_level,
        "track": track,
        "keywords": "",
        "concepts": "",
        "use_case": classify_use_case(classifier_text),
        "methodology": classify_methodology(classifier_text),
        "_semantic_text": keyword_text,
        "_source_notes": pdf_data.get("ocr_notes", []),
    }


def upsert_document(conn, record: dict) -> None:
    fields = [
        "thesis_id",
        "file_name",
        "file_path",
        "sha256",
        "pages_count",
        "cover_text",
        "abstract",
        "introduction",
        "conclusion",
        "year",
        "title",
        "master_level",
        "track",
        "keywords",
        "concepts",
        "use_case",
        "methodology",
        "extraction_confidence",
        "needs_review",
        "status",
        "extraction_notes",
        "processed_at",
    ]
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{field}=excluded.{field}" for field in fields if field != "thesis_id")
    sql = f"""
    INSERT INTO documents ({", ".join(fields)})
    VALUES ({placeholders})
    ON CONFLICT(thesis_id) DO UPDATE SET
        {updates},
        updated_at=CURRENT_TIMESTAMP
    """
    conn.execute(sql, [record.get(field) for field in fields])


def write_quality_report(records: list[dict]) -> Path:
    reports_dir().mkdir(parents=True, exist_ok=True)
    path = reports_dir() / "extraction_quality.csv"
    columns = [
        "thesis_id",
        "file_name",
        "pages_count",
        "title_found",
        "year_found",
        "master_level_found",
        "track_found",
        "abstract_found",
        "introduction_found",
        "keywords_found",
        "concepts_found",
        "use_case_found",
        "methodology_found",
        "extraction_confidence",
        "needs_review",
        "extraction_notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "thesis_id": record["thesis_id"],
                    "file_name": record["file_name"],
                    "pages_count": record["pages_count"],
                    "title_found": bool(record["title"]),
                    "year_found": bool(record["year"]),
                    "master_level_found": bool(record["master_level"]),
                    "track_found": bool(record["track"]),
                    "abstract_found": bool(record["abstract"]),
                    "introduction_found": bool(record["introduction"]),
                    "keywords_found": bool(record["keywords"]),
                    "concepts_found": bool(record["concepts"]),
                    "use_case_found": bool(record["use_case"]),
                    "methodology_found": bool(record["methodology"]),
                    "extraction_confidence": record["extraction_confidence"],
                    "needs_review": bool(record["needs_review"]),
                    "extraction_notes": record["extraction_notes"],
                }
            )
    return path


def finalize_record(record: dict, keywords: list[str], concepts: list[str]) -> dict:
    record["keywords"] = "; ".join(keywords)
    record["concepts"] = "; ".join(concepts)
    inferred_na_notes = []
    for field in ["year", "master_level", "track"]:
        if not record.get(field):
            record[field] = "N/A"
            inferred_na_notes.append(f"{field}_not_found_set_na")
    fields_for_score = {
        "title": record["title"],
        "year": record["year"],
        "master_level": record["master_level"],
        "track": record["track"],
        "abstract": record["abstract"],
        "keywords": record["keywords"],
        "methodology": record["methodology"],
        "use_case": record["use_case"],
    }
    record["extraction_confidence"] = confidence_score(fields_for_score)
    notes = []
    for label, value in [
        ("missing_title", record["title"]),
        ("missing_year", record["year"]),
        ("missing_master_level", record["master_level"]),
        ("missing_track", record["track"]),
        ("missing_use_case", record["use_case"]),
        ("missing_methodology", record["methodology"]),
    ]:
        if not value:
            notes.append(label)
    blocking_notes = list(notes)
    notes.extend(inferred_na_notes)
    notes.extend(record.get("_source_notes", []))
    record["needs_review"] = 1 if record["extraction_confidence"] < 0.70 or blocking_notes else 0
    record["status"] = "active"
    record["extraction_notes"] = "; ".join(notes)
    record["processed_at"] = datetime.now().isoformat(timespec="seconds")
    record.pop("_semantic_text", None)
    record.pop("_source_notes", None)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Process raw thesis PDFs into the documents table.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N PDFs.")
    parser.add_argument("--force", action="store_true", help="Reprocess documents already present in the database.")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR fallback for image-only front pages.")
    args = parser.parse_args()

    pdf_files = sorted(raw_pdf_dir().glob("*.pdf"))
    if args.limit:
        pdf_files = pdf_files[: args.limit]

    records = []
    semantic_texts = {}
    with connect(db_path()) as conn:
        init_schema(conn)
        for pdf_path in pdf_files:
            thesis_id = thesis_id_from_name(pdf_path)
            existing = conn.execute("SELECT id FROM documents WHERE thesis_id = ?", (thesis_id,)).fetchone()
            if existing and not args.force:
                continue
            record = build_record(pdf_path, enable_ocr=not args.no_ocr)
            records.append(record)
            semantic_texts[record["thesis_id"]] = record["_semantic_text"]

        keyword_map = extract_keywords_for_corpus(semantic_texts, limit=10)
        final_records = []
        for record in records:
            keywords = keyword_map.get(record["thesis_id"], [])
            concepts = normalize_concepts(record["_semantic_text"], keywords, limit=8)
            final_record = finalize_record(record, keywords, concepts)
            upsert_document(conn, final_record)
            final_records.append(final_record)
        conn.commit()

    report_path = write_quality_report(final_records)
    print(f"PDFs selected: {len(pdf_files)}")
    print(f"Documents processed: {len(records)}")
    print(f"Quality report: {report_path}")


if __name__ == "__main__":
    main()
