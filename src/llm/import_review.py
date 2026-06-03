from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from ingestion.import_workflow import load_draft, save_draft


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
) -> dict[str, Any]:
    draft = load_draft(draft_id)
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
    save_draft(draft)
    return result


def call_ollama(model: str, prompt: str, url: str, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
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
        "front_pages_text": compact(draft.get("cover_text_preview", ""), 3200),
    }
    return f"""
You are reviewing metadata extracted from a French MIAGE master's thesis PDF.

Use only the provided front-pages text and current extraction. Do not invent unsupported facts.
Return only compact JSON. No markdown.

Required JSON shape:
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
- title is the thesis subject, not the author, university, program name, table of contents, or acknowledgements.
- year must be the defense/submission year when visible; otherwise N/A.
- master_level must be exactly M1, M2, or N/A.
- track must be exactly apprentissage, classique, or N/A.
- If the student is not in apprentissage, use classique.
- keywords and concepts must be short comparable terms separated as JSON arrays.
- use_case must be a practical application domain, for example "sante / aide au diagnostic" or "cybersecurite / detection d'attaques".
- methodology must be a short method label, for example "comparaison experimentale", "revue de litterature / etat de l'art", or "analyse de donnees".
- abstract must stay empty unless the provided text contains a real Resume/Abstract or enough explicit summary text.
- confidence is your confidence that the suggested fields are supported by the text, from 0 to 1.

Input:
{json.dumps(source, ensure_ascii=False)}
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
