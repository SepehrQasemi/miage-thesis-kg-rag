import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.pipeline_outputs import rebuild_graph_outputs_from_rows
from extraction.field_extractor import (
    confidence_score,
    extract_master_level,
    extract_title,
    extract_track,
    is_valid_title,
)
from graph.neo4j_store import Neo4jGraphQueryService


def valid_master_level(value: str | None) -> str:
    value = (value or "").strip()
    return value if value in {"M1", "M2", "N/A"} else ""


def valid_track(value: str | None) -> str:
    value = (value or "").strip().lower()
    if value == "mixte":
        return "classique"
    return value if value in {"apprentissage", "classique", "N/A"} else ""


def recompute(row: dict) -> tuple[float, int, str]:
    fields = {
        "title": row["title"] if is_valid_title(row.get("title") or "") else "",
        "year": row.get("year"),
        "master_level": valid_master_level(row.get("master_level")),
        "track": valid_track(row.get("track")),
        "abstract": row.get("abstract"),
        "keywords": row.get("keywords"),
        "methodology": row.get("methodology"),
        "use_case": row.get("use_case"),
    }
    missing = []
    for label, value in [
        ("missing_title", fields["title"]),
        ("missing_year", fields["year"]),
        ("missing_master_level", fields["master_level"]),
        ("missing_track", fields["track"]),
        ("missing_use_case", fields["use_case"]),
        ("missing_methodology", fields["methodology"]),
    ]:
        if not value:
            missing.append(label)

    confidence = confidence_score(fields)
    return confidence, 1 if confidence < 0.70 or missing else 0, "; ".join(missing)


def preserved_tags(notes: str | None) -> list[str]:
    tags = []
    for part in (notes or "").split(";"):
        part = part.strip()
        if part.startswith("llm_reviewed:"):
            tags.append(part)
    return tags


def main() -> None:
    changed = 0
    graph_service = Neo4jGraphQueryService()
    graph_service.verify_connectivity()
    rows = graph_service.document_rows()
    repaired_rows = []
    for original in rows:
        row = dict(original)
        updates = {}

        candidate_title = extract_title(row.get("cover_text") or "")
        if candidate_title and not is_valid_title(row.get("title") or ""):
            row["title"] = candidate_title
            updates["title"] = candidate_title
        elif candidate_title and "title_repaired:rules" in (row.get("extraction_notes") or "") and candidate_title != (row.get("title") or ""):
            row["title"] = candidate_title
            updates["title"] = candidate_title
        elif row.get("title") and not is_valid_title(row.get("title") or ""):
            row["title"] = ""
            updates["title"] = ""

        current_master = valid_master_level(row.get("master_level"))
        if not current_master:
            detected_master = extract_master_level((row.get("cover_text") or "") + "\n" + (row.get("file_name") or ""))
            row["master_level"] = detected_master
            if detected_master != (original.get("master_level") or ""):
                updates["master_level"] = detected_master

        current_track = valid_track(row.get("track"))
        if not current_track:
            detected_track = extract_track(row.get("cover_text") or "")
            row["track"] = detected_track
            if detected_track != (original.get("track") or ""):
                updates["track"] = detected_track

        if updates:
            confidence, needs_review, missing_notes = recompute(row)
            tags = preserved_tags(original.get("extraction_notes"))
            if "title_repaired:rules" not in tags:
                tags.append("title_repaired:rules")
            row.update(
                {
                    **updates,
                    "extraction_confidence": confidence,
                    "needs_review": needs_review,
                    "extraction_notes": "; ".join(part for part in [missing_notes, *tags] if part),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            changed += 1
        repaired_rows.append(row)

    if changed:
        graph_service.replace_with_documents(repaired_rows)
        rebuild_graph_outputs_from_rows(graph_service.document_rows())

    print(f"Rows repaired: {changed}")


if __name__ == "__main__":
    main()
