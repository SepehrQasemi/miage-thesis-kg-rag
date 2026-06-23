import argparse
import csv
from datetime import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import reports_dir
from common.pipeline_outputs import rebuild_graph_outputs_from_rows
from extraction.field_extractor import confidence_score, extract_title_candidates, is_valid_title
from extraction.text_utils import normalize_for_match
from graph.neo4j_store import Neo4jGraphQueryService


OLLAMA_URL = "http://localhost:11434/api/chat"

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "year": {"type": "integer"},
        "master_level": {"type": "string", "enum": ["M1", "M2", "unknown"]},
        "track": {"type": "string", "enum": ["apprentissage", "classique", "unknown"]},
        "abstract": {"type": "string"},
        "concepts": {"type": "array", "items": {"type": "string"}},
        "use_case": {"type": "string"},
        "methodology": {"type": "string"},
        "confidence": {"type": "number"},
        "needs_review": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": [
        "title",
        "year",
        "master_level",
        "track",
        "abstract",
        "concepts",
        "use_case",
        "methodology",
        "confidence",
        "needs_review",
        "notes",
    ],
}


def compact(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text[:max_chars]


def build_prompt(row) -> str:
    notes = row["extraction_notes"] or ""
    title_candidates = extract_title_candidates(row["cover_text"] or "")
    missing_metadata = (
        any(token in notes for token in ["missing_title", "missing_year", "missing_master_level", "missing_track"])
        or not is_valid_title(row["title"] or "")
        or not normalize_master_level(row["master_level"])
        or not normalize_track(row["track"])
    )
    current = {
        "title": row["title"] or "",
        "year": row["year"] or "",
        "master_level": row["master_level"] or "",
        "track": row["track"] or "",
        "abstract": row["abstract"] or "",
        "concepts": row["concepts"] or "",
        "use_case": row["use_case"] or "",
        "methodology": row["methodology"] or "",
        "missing": notes,
    }
    if notes.strip() == "missing_use_case":
        text_blocks = {
            "title": compact(row["title"], 350),
            "abstract": compact(row["abstract"], 550),
            "concepts": compact(row["concepts"], 350),
        }
    elif "missing_abstract" in notes and not missing_metadata:
        text_blocks = {
            "title_candidates": title_candidates,
            "cover_text": compact(row["cover_text"], 800),
            "introduction": compact(row["introduction"], 700),
            "conclusion": compact(row["conclusion"], 350),
        }
    else:
        text_blocks = {
            "title_candidates": title_candidates,
            "cover_text": compact(row["cover_text"], 1800),
            "introduction": compact(row["introduction"], 500),
        }
    if notes.strip() == "missing_use_case":
        task = "Main task: fill use_case from title/abstract. Infer the practical application domain when it is clearly indicated. Copy existing correct fields."
    elif missing_metadata:
        task = (
            "Main task: fix missing title/year/master_level/track FIRST from cover_text and title_candidates. "
            "If title_candidates contains the thesis subject, use the best candidate as title. "
            "title is the research subject only; it is never a table of contents, author name, university name, program name, or acknowledgements. "
            "master_level must be exactly M1, M2, or unknown. Convert Master 2, 2eme annee, MASTER M2 to M2. "
            "track must be exactly apprentissage, classique, or unknown. If the student is not in apprentissage, use classique. Never put the title in track. "
            "Also fill abstract only if a real Resume/Abstract appears in the text."
        )
    elif "missing_abstract" in notes:
        task = "Main task: find an abstract only if a real Résumé/Abstract appears in the text. Otherwise keep abstract empty. Copy existing correct fields."
    else:
        task = "Main task: fill missing title/year/master_level/track from cover text. Copy existing correct fields."

    return f"""
Extract metadata from a French MIAGE master's thesis.

Use ONLY the provided text. Do not invent information.
If a value is not supported by the text, return:
- empty string for text fields
- 0 for year
- "unknown" for master_level or track

Return ONLY compact JSON with keys:
title, year, master_level, track, abstract, concepts, use_case, methodology, confidence, needs_review, notes.
concepts must be a JSON array of strings. confidence must be a number.
{task}

Current extraction: {json.dumps(current, ensure_ascii=False)}

Text: {json.dumps(text_blocks, ensure_ascii=False)}
""".strip()


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
    return parse_json_content(completed.stdout)


def parse_json_content(content: str) -> dict[str, Any]:
    # Remove ANSI control sequences emitted by the CLI spinner.
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", content).strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def valid_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    if 2000 <= year <= 2035:
        return year
    return None


def value_or_empty(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "unknown" else text


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def normalize_master_level(value: Any) -> str:
    spaced, compact = normalize_for_match(value_or_empty(value))
    if compact in {"m1", "master1", "mastermiage1"} or "master1" in compact or "1ereannee" in compact or "1reannee" in compact:
        return "M1"
    if compact in {"m2", "master2", "mastermiage2", "masterm2"} or "master2" in compact or "2emeannee" in compact or "2eannee" in compact or "m2" in compact:
        return "M2"
    return ""


def normalize_track(value: Any) -> str:
    spaced, _ = normalize_for_match(value_or_empty(value))
    if "apprentissage" in spaced:
        return "apprentissage"
    if "mixte" in spaced or "classique" in spaced:
        return "classique"
    return ""


def normalized_review_value(field: str, value: Any) -> str:
    if field == "master_level":
        return normalize_master_level(value)
    if field == "track":
        return normalize_track(value)
    text = value_or_empty(value)
    if field == "title":
        return text if is_valid_title(text) else ""
    return text


def confidence_value(value: Any) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    if conf < 0:
        return 0.0
    if conf > 1:
        return 1.0
    return conf


def concepts_text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        return value.strip()
    return ""


def should_update(current: Any, proposed: Any, field: str, min_confidence: float, llm_confidence: float) -> bool:
    if llm_confidence < min_confidence:
        return False
    proposed_text = normalized_review_value(field, proposed)
    current_text = normalized_review_value(field, current)
    if field == "abstract":
        return not current_text and len(proposed_text) >= 80
    if field == "title":
        return (not current_text or len(current_text) < 12) and bool(proposed_text)
    if field in {"master_level", "track"}:
        return not current_text and bool(proposed_text)
    if field == "year":
        return not current_text and valid_year(proposed) is not None
    if field in {"use_case", "methodology"}:
        return not current_text and len(proposed_text) >= 4
    if field == "concepts":
        return bool(proposed_text)
    return False


def recompute_review(row: dict[str, Any]) -> tuple[float, int, str]:
    fields = {
        "title": normalized_review_value("title", row.get("title")),
        "year": row.get("year"),
        "master_level": normalized_review_value("master_level", row.get("master_level")),
        "track": normalized_review_value("track", row.get("track")),
        "abstract": row.get("abstract"),
        "keywords": row.get("keywords"),
        "methodology": row.get("methodology"),
        "use_case": row.get("use_case"),
    }
    confidence = confidence_score(fields)
    notes = []
    for label, value in [
        ("missing_title", normalized_review_value("title", row.get("title"))),
        ("missing_year", row.get("year")),
        ("missing_master_level", normalized_review_value("master_level", row.get("master_level"))),
        ("missing_track", normalized_review_value("track", row.get("track"))),
        ("missing_use_case", row.get("use_case")),
        ("missing_methodology", row.get("methodology")),
    ]:
        if not value:
            notes.append(label)
    return confidence, 1 if confidence < 0.70 or notes else 0, "; ".join(notes)


def apply_review(row, review: dict[str, Any], model: str, min_confidence: float) -> dict[str, Any]:
    llm_confidence = confidence_value(review.get("confidence"))
    updated = dict(row)
    updates: dict[str, Any] = {}

    for field in ["title", "master_level", "track", "abstract", "use_case", "methodology"]:
        proposed = normalized_review_value(field, review.get(field))
        if should_update(updated.get(field), proposed, field, min_confidence, llm_confidence):
            updated[field] = proposed
            updates[field] = proposed

    year = valid_year(review.get("year"))
    if should_update(updated.get("year"), year, "year", min_confidence, llm_confidence):
        updated["year"] = year
        updates["year"] = year

    concept_text = concepts_text(review.get("concepts"))
    if concept_text and llm_confidence >= min_confidence:
        updated["concepts"] = concept_text
        updates["concepts"] = concept_text

    new_confidence, needs_review, notes = recompute_review(updated)
    notes = "; ".join(part for part in [notes, f"llm_reviewed:{model}"] if part)
    updates.update(
        {
            "extraction_confidence": new_confidence,
            "needs_review": needs_review,
            "extraction_notes": notes,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    updated.update(updates)
    return updated


def write_report(rows: list[dict[str, Any]], model: str) -> Path:
    reports_dir().mkdir(parents=True, exist_ok=True)
    safe_model = model.replace(":", "_").replace("/", "_")
    path = reports_dir() / f"llm_review_{safe_model}.csv"
    columns = [
        "thesis_id",
        "file_name",
        "old_title",
        "new_title",
        "old_year",
        "new_year",
        "old_master_level",
        "new_master_level",
        "old_track",
        "new_track",
        "old_has_abstract",
        "new_has_abstract",
        "old_use_case",
        "new_use_case",
        "old_methodology",
        "new_methodology",
        "old_concepts",
        "new_concepts",
        "llm_confidence",
        "llm_needs_review",
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
    parser = argparse.ArgumentParser(description="Use local Ollama LLM to review needs_review documents.")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="Apply confident LLM fixes to the database.")
    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    graph_service = Neo4jGraphQueryService()
    graph_service.verify_connectivity()
    all_rows = graph_service.document_rows()
    rows_by_id = {str(row.get("thesis_id")): dict(row) for row in all_rows}
    rows = [dict(row) for row in all_rows if is_truthy(row.get("needs_review"))]
    if args.limit:
        rows = rows[: args.limit]

    report_rows = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] reviewing {row['thesis_id']} {row['file_name']}")
        report = {
            "thesis_id": row["thesis_id"],
            "file_name": row["file_name"],
            "old_title": row["title"] or "",
            "old_year": row["year"] or "",
            "old_master_level": row["master_level"] or "",
            "old_track": row["track"] or "",
            "old_has_abstract": bool(row["abstract"]),
            "old_use_case": row["use_case"] or "",
            "old_methodology": row["methodology"] or "",
            "old_concepts": row["concepts"] or "",
            "applied": False,
            "error": "",
        }
        try:
            review = call_ollama(args.model, build_prompt(row), args.timeout)
            if args.apply:
                updated = apply_review(row, review, args.model, args.min_confidence)
                rows_by_id[str(updated["thesis_id"])] = updated
                report["applied"] = True
                report["new_title"] = updated.get("title") or ""
                report["new_year"] = updated.get("year") or ""
                report["new_master_level"] = updated.get("master_level") or ""
                report["new_track"] = updated.get("track") or ""
                report["new_has_abstract"] = bool(updated.get("abstract"))
                report["new_use_case"] = updated.get("use_case") or ""
                report["new_methodology"] = updated.get("methodology") or ""
                report["new_concepts"] = updated.get("concepts") or ""
            else:
                report["new_title"] = review.get("title", "")
                report["new_year"] = review.get("year", "")
                report["new_master_level"] = review.get("master_level", "")
                report["new_track"] = review.get("track", "")
                report["new_has_abstract"] = bool(review.get("abstract"))
                report["new_use_case"] = review.get("use_case", "")
                report["new_methodology"] = review.get("methodology", "")
                report["new_concepts"] = concepts_text(review.get("concepts"))
            report["llm_confidence"] = review.get("confidence", "")
            report["llm_needs_review"] = review.get("needs_review", "")
            report["llm_notes"] = review.get("notes", "")
        except (urllib.error.URLError, TimeoutError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            report["error"] = repr(exc)
        report_rows.append(report)
    if args.apply and report_rows:
        updated_rows = sorted(rows_by_id.values(), key=lambda item: str(item.get("thesis_id") or ""))
        graph_service.replace_with_documents(updated_rows)
        rebuild_graph_outputs_from_rows(graph_service.document_rows())

    report_path = write_report(report_rows, args.model)
    print(f"Reviewed rows: {len(report_rows)}")
    print(f"Applied: {args.apply}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
