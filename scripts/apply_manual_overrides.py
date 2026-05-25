import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path
from extraction.field_extractor import confidence_score


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
    applied = 0
    with connect(db_path()) as conn:
        init_schema(conn)
        with override_path.open(encoding="utf-8-sig", newline="") as f:
            for override in csv.DictReader(f):
                thesis_id = (override.get("thesis_id") or "").strip()
                if not thesis_id:
                    continue
                existing = conn.execute("SELECT * FROM documents WHERE thesis_id=?", (thesis_id,)).fetchone()
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
                    for part in (existing["extraction_notes"] or "").split(";")
                    if part.strip().startswith(("llm_reviewed:", "title_repaired:", "ocr_pages:"))
                ]
                note_parts = [missing_notes, *previous_tags, source_note]
                updates.update(
                    {
                        "extraction_confidence": confidence,
                        "needs_review": needs_review,
                        "extraction_notes": "; ".join(part for part in note_parts if part),
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                set_clause = ", ".join(f"{key}=?" for key in updates)
                conn.execute(f"UPDATE documents SET {set_clause} WHERE thesis_id=?", [*updates.values(), thesis_id])
                applied += 1
        conn.commit()

    print(f"Manual overrides applied: {applied}")


if __name__ == "__main__":
    main()
