import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.pipeline_outputs import rebuild_graph_outputs_from_rows
from extraction.field_extractor import confidence_score
from graph.neo4j_store import Neo4jGraphQueryService


DEFAULT_OVERRIDES = ROOT / "data" / "manual_overrides" / "theses_metadata.csv"


def recompute_review(row: dict) -> tuple[float, int, str]:
    fields = {
        "title": row.get("title"),
        "year": row.get("year"),
        "master_level": row.get("master_level"),
        "track": row.get("track"),
        "abstract": row.get("abstract"),
        "keywords": row.get("keywords"),
        "methodology": row.get("methodology"),
        "use_case": row.get("use_case"),
    }
    notes = []
    for label, value in [
        ("missing_title", row.get("title")),
        ("missing_year", row.get("year")),
        ("missing_master_level", row.get("master_level")),
        ("missing_track", row.get("track")),
        ("missing_use_case", row.get("use_case")),
        ("missing_methodology", row.get("methodology")),
    ]:
        if not value:
            notes.append(label)
    confidence = confidence_score(fields)
    return confidence, 1 if confidence < 0.70 or notes else 0, "; ".join(notes)


def parse_year(value: str) -> int | str | None:
    value = value.strip()
    if value.upper() == "N/A":
        return "N/A"
    return int(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply manually verified metadata overrides to the documents table.")
    parser.add_argument("--file", default=str(DEFAULT_OVERRIDES), help="CSV file containing manual overrides.")
    args = parser.parse_args()

    override_path = Path(args.file)
    graph_service = Neo4jGraphQueryService()
    graph_service.verify_connectivity()
    rows = graph_service.document_rows()
    rows_by_id = {str(row.get("thesis_id")): row for row in rows}

    applied = 0
    with override_path.open(encoding="utf-8-sig", newline="") as f:
        for override in csv.DictReader(f):
            thesis_id = (override.get("thesis_id") or "").strip()
            if not thesis_id:
                continue
            existing = rows_by_id.get(thesis_id)
            if not existing:
                print(f"Skipping unknown thesis_id: {thesis_id}")
                continue
            row = dict(existing)
            updates = {}
            for field in ["title", "master_level", "track"]:
                value = (override.get(field) or "").strip()
                if value:
                    row[field] = value
                    updates[field] = value
            year = parse_year(override.get("year") or "")
            if year:
                row["year"] = year
                updates["year"] = year
            if not updates:
                continue

            confidence, needs_review, missing_notes = recompute_review(row)
            source_note = (override.get("notes") or "manual_override").strip()
            previous_tags = [
                part.strip()
                for part in (existing.get("extraction_notes") or "").split(";")
                if part.strip().startswith(("llm_reviewed:", "title_repaired:", "ocr_pages:"))
            ]
            note_parts = [missing_notes, *previous_tags, source_note]
            row.update(
                {
                    **updates,
                    "extraction_confidence": confidence,
                    "needs_review": needs_review,
                    "extraction_notes": "; ".join(part for part in note_parts if part),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            rows_by_id[thesis_id] = row
            applied += 1

    if applied:
        updated_rows = sorted(rows_by_id.values(), key=lambda item: str(item.get("thesis_id") or ""))
        graph_service.replace_with_documents(updated_rows)
        rebuild_graph_outputs_from_rows(graph_service.document_rows())

    print(f"Manual overrides applied: {applied}")


if __name__ == "__main__":
    main()
