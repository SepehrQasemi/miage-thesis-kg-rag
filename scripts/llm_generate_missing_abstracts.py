import argparse
import csv
from datetime import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import reports_dir
from common.pipeline_outputs import rebuild_graph_outputs_from_rows
from extraction.field_extractor import classify_methodology, classify_use_case, confidence_score
from graph.neo4j_store import Neo4jGraphQueryService


def compact(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    return " ".join(str(text).split())[:max_chars]


def call_ollama(model: str, prompt: str, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"ollama exited with {completed.returncode}")
    text = completed.stdout.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def build_prompt(row: dict[str, Any]) -> str:
    source = {
        "title": row.get("title") or "",
        "year": row.get("year") or "",
        "master_level": row.get("master_level") or "",
        "track": row.get("track") or "",
        "concepts": row.get("concepts") or "",
        "keywords": row.get("keywords") or "",
        "cover_text": compact(row.get("cover_text"), 900),
        "introduction": compact(row.get("introduction"), 2600),
        "conclusion": compact(row.get("conclusion"), 900),
    }
    return f"""
You are helping build a structured dataset of French MIAGE master's theses.

The original document has no explicit Resume/Abstract extracted.
Generate a short French abstract ONLY from the provided text.
Do not invent company names, methods, or results that are not supported by the text.
If the text is insufficient, return an empty abstract.

Return ONLY compact JSON with keys:
abstract, use_case, methodology, confidence, notes.

Rules:
- abstract: 3 to 5 sentences, neutral academic style, 80 to 900 characters.
- use_case: short practical domain label, or empty string.
- methodology: short method label, or empty string.
- confidence: number from 0 to 1.
- notes: mention that the abstract is generated from introduction/available text.

Text: {json.dumps(source, ensure_ascii=False)}
""".strip()


def confidence_value(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, score))


def recompute_review(row: dict[str, Any]) -> tuple[float, int, str]:
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


def apply_review(row: dict[str, Any], review: dict[str, Any], model: str, min_confidence: float) -> dict[str, Any]:
    llm_confidence = confidence_value(review.get("confidence"))
    updated = dict(row)
    updates: dict[str, Any] = {}
    proposed_abstract = str(review.get("abstract") or "").strip()
    if llm_confidence >= min_confidence and not updated.get("abstract") and len(proposed_abstract) >= 80:
        updated["abstract"] = proposed_abstract
        updates["abstract"] = proposed_abstract

    semantic_text = "\n".join(
        str(updated.get(key) or "")
        for key in ["title", "abstract", "introduction", "conclusion", "cover_text"]
    )
    proposed_use_case = str(review.get("use_case") or "").strip() or classify_use_case(semantic_text)
    proposed_methodology = str(review.get("methodology") or "").strip() or classify_methodology(semantic_text)
    if proposed_use_case and not updated.get("use_case"):
        updated["use_case"] = proposed_use_case
        updates["use_case"] = proposed_use_case
    if proposed_methodology and not updated.get("methodology"):
        updated["methodology"] = proposed_methodology
        updates["methodology"] = proposed_methodology

    confidence, needs_review, missing_notes = recompute_review(updated)
    previous_tags = [
        part.strip()
        for part in (row.get("extraction_notes") or "").split(";")
        if part.strip().startswith(("llm_reviewed:", "title_repaired:", "ocr_pages:", "manual_"))
    ]
    tags = previous_tags + [f"abstract_generated:{model}"]
    updates.update(
        {
            "extraction_confidence": confidence,
            "needs_review": needs_review,
            "extraction_notes": "; ".join(part for part in [missing_notes, *tags] if part),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    updated.update(updates)
    return updated


def write_report(rows: list[dict[str, Any]], model: str) -> Path:
    reports_dir().mkdir(parents=True, exist_ok=True)
    safe_model = model.replace(":", "_").replace("/", "_")
    path = reports_dir() / f"generated_abstracts_{safe_model}.csv"
    columns = [
        "thesis_id",
        "file_name",
        "old_has_abstract",
        "new_has_abstract",
        "generated_abstract",
        "llm_confidence",
        "llm_notes",
        "applied",
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate clearly marked abstracts for rows without extracted abstracts.")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    graph_service = Neo4jGraphQueryService()
    graph_service.verify_connectivity()
    all_rows = graph_service.document_rows()
    rows_by_id = {str(row.get("thesis_id")): dict(row) for row in all_rows}
    rows = [
        dict(row)
        for row in all_rows
        if not str(row.get("abstract") or "").strip()
        and (
            str(row.get("introduction") or "").strip()
            or str(row.get("cover_text") or "").strip()
        )
    ]
    if args.limit:
        rows = rows[: args.limit]

    report_rows = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] generating abstract {row['thesis_id']} {row['file_name']}")
        report = {
            "thesis_id": row["thesis_id"],
            "file_name": row["file_name"],
            "old_has_abstract": bool(row.get("abstract")),
            "applied": False,
            "error": "",
        }
        try:
            review = call_ollama(args.model, build_prompt(row), args.timeout)
            report["generated_abstract"] = review.get("abstract", "")
            report["llm_confidence"] = review.get("confidence", "")
            report["llm_notes"] = review.get("notes", "")
            if args.apply:
                updated = apply_review(row, review, args.model, args.min_confidence)
                rows_by_id[str(updated["thesis_id"])] = updated
                report["applied"] = True
                report["new_has_abstract"] = bool(updated.get("abstract"))
            else:
                report["new_has_abstract"] = bool(review.get("abstract"))
        except Exception as exc:
            report["error"] = repr(exc)
        report_rows.append(report)
    if args.apply and report_rows:
        updated_rows = sorted(rows_by_id.values(), key=lambda item: str(item.get("thesis_id") or ""))
        graph_service.replace_with_documents(updated_rows)
        rebuild_graph_outputs_from_rows(graph_service.document_rows())

    report_path = write_report(report_rows, args.model)
    print(f"Rows reviewed: {len(report_rows)}")
    print(f"Applied: {args.apply}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
