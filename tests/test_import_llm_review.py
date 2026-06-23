import pytest

from llm.import_review import (
    LLMUnavailableError,
    call_ollama,
    normalize_suggestions,
    parse_json_content,
    review_reasons,
)
from llm.ollama_client import build_ollama_options


def test_parse_json_content_handles_markdown_fence():
    parsed = parse_json_content('```json\n{"title": "A", "confidence": 0.7}\n```')

    assert parsed["title"] == "A"
    assert parsed["confidence"] == 0.7


def test_normalize_suggestions_accepts_lists_and_valid_choices():
    normalized = normalize_suggestions(
        {
            "title": " Detection de fraude ",
            "year": "2026",
            "master_level": "m2",
            "track": "Apprentissage",
            "keywords": ["machine learning", "fraude"],
            "concepts": ["classification", "detection"],
            "use_case": "detection de fraude / risque financier",
            "methodology": "comparaison experimentale",
            "confidence": 1.4,
            "notes": "supported by cover",
        }
    )

    assert normalized["fields"]["master_level"] == "M2"
    assert normalized["fields"]["track"] == "apprentissage"
    assert normalized["fields"]["keywords"] == "machine learning; fraude"
    assert normalized["confidence"] == 1.0


def test_review_reasons_marks_low_quality_draft():
    reasons = review_reasons({"title": "", "keywords": "machine learning", "concepts": ""}, 0.5)

    assert "missing_title" in reasons
    assert "few_keywords" in reasons
    assert "few_concepts" in reasons
    assert "low_confidence" in reasons


def test_build_ollama_options_defaults_to_cpu(monkeypatch):
    for key in [
        "MIAGE_OLLAMA_NUM_GPU",
        "MIAGE_OLLAMA_NUM_CTX",
        "MIAGE_OLLAMA_TEMPERATURE",
        "MIAGE_OLLAMA_RAG_NUM_PREDICT",
    ]:
        monkeypatch.delenv(key, raising=False)

    options = build_ollama_options("RAG", default_num_predict=320)

    assert options["temperature"] == 0.0
    assert options["num_gpu"] == 0
    assert options["num_ctx"] == 2048
    assert options["num_predict"] == 320


def test_build_ollama_options_allows_task_override(monkeypatch):
    monkeypatch.setenv("MIAGE_OLLAMA_NUM_GPU", "auto")
    monkeypatch.setenv("MIAGE_OLLAMA_IMPORT_NUM_PREDICT", "512")

    options = build_ollama_options("IMPORT", default_num_predict=700)

    assert "num_gpu" not in options
    assert options["num_predict"] == 512


def test_call_ollama_reports_unavailable(monkeypatch):
    def raise_url_error(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)

    with pytest.raises(LLMUnavailableError):
        call_ollama("fake", "prompt", "http://127.0.0.1:9/api/generate", 1)
