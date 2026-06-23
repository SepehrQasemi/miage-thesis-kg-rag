from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from graph.neo4j_store import Neo4jGraphQueryService
from ingestion.import_workflow import load_draft, save_draft
from llm.ollama_client import build_ollama_options


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"


class LLMUnavailableError(RuntimeError):
    pass


class LLMSuggestionError(ValueError):
    pass


def generate_import_suggestions(
    draft_id: str,
    current_fields: dict[str, Any] | None = None,
    model: str | None = None,
    ollama_url: str | None = None,
    timeout: int | None = None,
    graph_service: Neo4jGraphQueryService | None = None,
) -> dict[str, Any]:
    graph_service = graph_service or Neo4jGraphQueryService()
    draft = load_draft(draft_id, graph_service)
    if draft.get("status") != "draft":
        raise LLMSuggestionError("LLM suggestions are only available for open drafts.")

    selected_model = model or os.environ.get("MIAGE_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    url = ollama_url or os.environ.get("MIAGE_OLLAMA_URL", DEFAULT_OLLAMA_URL)
    request_timeout = timeout or int(os.environ.get("MIAGE_OLLAMA_TIMEOUT", "90"))
    fields = {**draft.get("fields", {}), **(current_fields or {})}

    raw = call_ollama(selected_model, build_prompt(draft, fields), url, request_timeout)
    suggestions = normalize_suggestions(raw)
    result = {
        "status": "suggested",
        "model": selected_model,
        "suggestions": suggestions["fields"],
        "confidence": suggestions["confidence"],
        "notes": suggestions["notes"],
        "review_reasons": review_reasons(fields, draft.get("extraction_confidence", 0)),
    }
    draft["llm_suggestions"] = result
    save_draft(draft, graph_service)
    return result


def call_ollama(model: str, prompt: str, url: str, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "raw": True,
        "stream": False,
        "options": build_ollama_options("IMPORT", default_num_predict=260),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMUnavailableError(f"Ollama unavailable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LLMSuggestionError(f"Ollama returned invalid JSON: {exc}") from exc

    content = data.get("response") or data.get("message", {}).get("content")
    if not content:
        raise LLMSuggestionError("Ollama returned an empty response.")
    return parse_json_content(str(content))


def build_prompt(draft: dict[str, Any], fields: dict[str, Any]) -> str:
    source = {
        "file_name": draft.get("original_file_name", ""),
        "pages_count": draft.get("pages_count", ""),
        "current_extraction": compact_fields(fields),
        "current_confidence": draft.get("extraction_confidence", 0),
        "current_notes": draft.get("extraction_notes", ""),
        "front_pages_text": compact(draft.get("cover_text_preview", ""), 800),
    }
    return f"""
Review metadata from a French MIAGE master's thesis PDF.
Use only Input. Do not invent unsupported facts.
Return only this compact JSON shape, with no markdown and no extra keys:
{{
  "title": "string",
  "year": "YYYY or N/A",
  "master_level": "M1 or M2 or N/A",
  "track": "apprentissage or classique or N/A",
  "keywords": ["string"],
  "concepts": ["string"],
  "use_case": "string",
  "methodology": "string",
  "abstract": "string",
  "confidence": 0.0,
  "notes": "short explanation"
}}

Rules:
- title: thesis subject only, not author/university/program/table of contents.
- year: visible defense/submission year, else N/A.
- master_level: exactly M1, M2, or N/A.
- track: exactly apprentissage, classique, or N/A. If no apprentissage/alternance evidence, use classique. MIAGE/university names are not track.
- keywords/concepts: short comparable JSON arrays.
- use_case: derive mainly from title, Resume/Abstract, and front_pages_text. Do not copy a label from current_extraction if it conflicts with the visible subject.
- methodology: short method label such as "comparaison experimentale", "revue de litterature / etat de l'art", or "analyse de donnees".
- abstract: empty unless a real Resume/Abstract or explicit summary is visible.
- confidence: number from 0 to 1.
- Preserve current_extraction values when supported by front_pages_text.

Domain hints for use_case:
- inondations, hydrologie, climat, catastrophe naturelle -> environnement / prediction des risques naturels
- fraude, transaction bancaire, risque financier -> finance / detection de fraude
- cybersecurite, attaque, intrusion -> cybersecurite / detection d'attaques
- medical, sante, diagnostic, patient, cancer -> sante / aide au diagnostic
- jeu video, League of Legends, joueur -> jeux video / analyse de parties

Input:
{json.dumps(source, ensure_ascii=False)}
JSON:
""".strip()


def parse_json_content(content: str) -> dict[str, Any]:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise LLMSuggestionError("LLM response must be a JSON object.")
    return parsed


def normalize_suggestions(raw: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "title": clean_text(raw.get("title")),
        "year": clean_year(raw.get("year")),
        "master_level": clean_choice(raw.get("master_level"), {"M1", "M2", "N/A"}, uppercase=True),
        "track": clean_choice(str(raw.get("track") or "").lower().replace("mixte", "classique"), {"apprentissage", "classique", "N/A"}, uppercase=False),
        "keywords": clean_terms(raw.get("keywords")),
        "concepts": clean_terms(raw.get("concepts")),
        "use_case": clean_text(raw.get("use_case")),
        "methodology": clean_text(raw.get("methodology")),
        "abstract": clean_text(raw.get("abstract")),
    }
    return {
        "fields": fields,
        "confidence": clamp_confidence(raw.get("confidence")),
        "notes": clean_text(raw.get("notes")),
    }


def review_reasons(fields: dict[str, Any], confidence: Any) -> list[str]:
    reasons = []
    for key in ["title", "year", "master_level", "track", "keywords", "concepts", "use_case", "methodology"]:
        if not clean_text(fields.get(key)):
            reasons.append(f"missing_{key}")
    if len(split_terms(fields.get("keywords"))) < 2:
        reasons.append("few_keywords")
    if len(split_terms(fields.get("concepts"))) < 2:
        reasons.append("few_concepts")
    try:
        score = float(confidence or 0)
    except (TypeError, ValueError):
        score = 0
    if score < 0.80:
        reasons.append("low_confidence")
    return list(dict.fromkeys(reasons))


def compact_fields(fields: dict[str, Any]) -> dict[str, str]:
    return {
        key: compact(fields.get(key), 700 if key == "abstract" else 240)
        for key in [
            "thesis_id",
            "title",
            "year",
            "master_level",
            "track",
            "keywords",
            "concepts",
            "use_case",
            "methodology",
            "abstract",
        ]
    }


def compact(value: Any, max_chars: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_chars]


def clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return "" if text.lower() in {"unknown", "null", "none"} else text


def clean_year(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if text.upper() == "N/A":
        return "N/A"
    match = re.search(r"\b(20[0-3][0-9])\b", text)
    return match.group(1) if match else ""


def clean_choice(value: Any, allowed: set[str], uppercase: bool) -> str:
    text = clean_text(value)
    if text.upper() == "N/A" and "N/A" in allowed:
        return "N/A"
    text = text.upper() if uppercase else text.lower()
    return text if text in allowed else ""


def clean_terms(value: Any) -> str:
    if isinstance(value, list):
        raw_terms = value
    else:
        raw_terms = re.split(r"[;\n,]+", str(value or ""))
    terms = []
    for item in raw_terms:
        term = clean_text(item)
        if term and term not in terms:
            terms.append(term)
    return "; ".join(terms[:12])


def split_terms(value: Any) -> list[str]:
    return [term.strip() for term in str(value or "").split(";") if term.strip()]


def clamp_confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, score)), 3)
