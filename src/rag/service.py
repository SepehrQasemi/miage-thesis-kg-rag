from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from common.db import connect, init_schema
from common.paths import db_path
from nlp.keyword_extractor import STOPWORDS
from rag.embeddings import (
    DEFAULT_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    embed_text,
    feature_counts,
    load_embedding_rows,
    normalize_text,
    rebuild_embeddings,
    row_feature_counts,
    semantic_expansions,
    split_terms,
)


QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "are",
    "as",
    "at",
    "by",
    "can",
    "discuss",
    "discusses",
    "find",
    "for",
    "from",
    "give",
    "in",
    "into",
    "is",
    "me",
    "of",
    "on",
    "or",
    "related",
    "research",
    "show",
    "study",
    "studies",
    "technique",
    "techniques",
    "the",
    "thesis",
    "theses",
    "to",
    "uses",
    "using",
    "which",
    "with",
    "work",
    "works",
}

FIELD_WEIGHTS = (
    ("title", 0.22),
    ("concepts", 0.16),
    ("keywords", 0.14),
    ("use_case", 0.12),
    ("methodology", 0.04),
    ("abstract", 0.08),
    ("embedding_text", 0.03),
)

BROAD_DOMAIN_TOKENS = {
    "ai",
    "algorithm",
    "algorithme",
    "algorithmes",
    "algorithms",
    "analysis",
    "analyse",
    "artificial",
    "artificielle",
    "classification",
    "data",
    "deep",
    "detection",
    "donnees",
    "ia",
    "intelligence",
    "learning",
    "machine",
    "method",
    "methode",
    "methodes",
    "methods",
    "model",
    "modele",
    "modeles",
    "models",
    "optimisation",
    "optimization",
    "prediction",
    "process",
    "processus",
    "research",
    "system",
    "systeme",
    "systems",
}


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def parse_vector(value: str) -> list[float]:
    parsed = json.loads(value or "[]")
    return [float(item) for item in parsed]


def expanded_question_text(question: str) -> str:
    parts = [question]
    for expansion in semantic_expansions(question):
        if expansion not in parts:
            parts.append(expansion)
    return " ".join(parts)


def meaningful_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in normalize_text(text).split()
        if len(token) >= 2 and token not in STOPWORDS and token not in QUERY_STOPWORDS
    }
    variants = set(tokens)
    for token in tokens:
        if len(token) > 4 and token.endswith("s"):
            variants.add(token[:-1])
        if len(token) > 5 and token.endswith("ies"):
            variants.add(f"{token[:-3]}y")
    return variants


def question_clues(question: str) -> list[str]:
    clues: list[str] = []
    for value in [question, *semantic_expansions(question)]:
        normalized = normalize_text(value)
        if normalized and normalized not in clues:
            clues.append(normalized)
        tokens = [
            token
            for token in normalized.split()
            if token not in STOPWORDS and token not in QUERY_STOPWORDS
        ]
        for size in (2, 3, 4, 5):
            for index in range(0, max(0, len(tokens) - size + 1)):
                phrase = " ".join(tokens[index:index + size])
                if phrase and phrase not in clues:
                    clues.append(phrase)
    return clues


def sparse_cosine(left: dict[str, float], right: dict[str, float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    numerator = sum(value * right.get(feature, 0.0) for feature, value in left.items())
    return numerator / (left_norm * right_norm)


def question_profile(question: str) -> dict[str, Any]:
    query_text = expanded_question_text(question)
    clues_by_text = {}
    for clue in question_clues(question):
        clue_tokens = meaningful_tokens(clue)
        if clue_tokens:
            clues_by_text.setdefault(clue, clue_tokens)
    clues = sorted(
        clues_by_text.items(),
        key=lambda item: (-len(item[1]), -len(item[0]), item[0]),
    )
    return {
        "text": query_text,
        "normalized": normalize_text(query_text),
        "tokens": meaningful_tokens(query_text),
        "clues": clues,
    }


def phrase_matches(clue: str, clue_tokens: set[str], field_norm: str, field_tokens: set[str]) -> bool:
    if not clue_tokens:
        return False
    if clue in field_norm:
        return True
    clue_compact = clue.replace(" ", "")
    field_compact = field_norm.replace(" ", "")
    if clue_compact and len(clue_compact) >= 3 and clue_compact in field_compact:
        return True
    if len(clue_tokens) == 1:
        return next(iter(clue_tokens)) in field_tokens
    return clue_tokens.issubset(field_tokens)


def row_search_profile(row: dict[str, Any]) -> dict[str, Any]:
    fields = []
    row_tokens = set()
    for field, weight in FIELD_WEIGHTS:
        value = str(row.get(field) or "")
        field_norm = normalize_text(value)
        field_tokens = meaningful_tokens(value)
        row_tokens.update(field_tokens)
        fields.append((field, weight, field_norm, field_tokens))

    concepts = []
    for concept in split_terms(row.get("concepts")):
        concept_norm = normalize_text(concept)
        concepts.append(
            {
                "label": concept,
                "norm": concept_norm,
                "compact": concept_norm.replace(" ", ""),
                "tokens": meaningful_tokens(concept_norm),
            }
        )

    keywords = []
    for keyword in split_terms(row.get("keywords")):
        keyword_norm = normalize_text(keyword)
        keywords.append(
            {
                "label": keyword,
                "norm": keyword_norm,
                "tokens": meaningful_tokens(keyword_norm),
            }
        )

    title_norm = normalize_text(row.get("title"))
    use_case_norm = normalize_text(row.get("use_case"))
    return {
        "fields": fields,
        "row_tokens": row_tokens,
        "title_norm": title_norm,
        "title_compact": title_norm.replace(" ", ""),
        "use_case_norm": use_case_norm,
        "use_case_tokens": meaningful_tokens(use_case_norm),
        "concepts": concepts,
        "keywords": keywords,
        "terms": [*concepts, *keywords],
    }


def lexical_score(
    question: str,
    row: dict[str, Any],
    profile: dict[str, Any] | None = None,
    row_profile: dict[str, Any] | None = None,
) -> float:
    profile = profile or question_profile(question)
    query_tokens = profile["tokens"]
    clues = profile["clues"]
    score = 0.0
    if row_profile:
        fields = row_profile["fields"]
        row_tokens = row_profile["row_tokens"]
    else:
        fields = []
        row_tokens = set()
        for field, weight in FIELD_WEIGHTS:
            value = str(row.get(field) or "")
            field_norm = normalize_text(value)
            field_tokens = meaningful_tokens(value)
            row_tokens.update(field_tokens)
            fields.append((field, weight, field_norm, field_tokens))
    for _field, weight, field_norm, field_tokens in fields:
        overlap = query_tokens & field_tokens
        if overlap:
            score += min(weight * 0.35, weight * 0.04 * len(overlap))
        phrase_hits = 0
        for clue, clue_tokens in clues:
            if phrase_matches(clue, clue_tokens, field_norm, field_tokens):
                phrase_hits += 1
                clue_len = len(clue_tokens)
                score += weight * (0.55 if clue_len >= 2 else 0.12)
                if phrase_hits >= 4:
                    break
    specific_query_tokens = query_tokens - BROAD_DOMAIN_TOKENS
    specific_overlap = specific_query_tokens & row_tokens
    if specific_overlap:
        score += min(0.22, 0.035 * len(specific_overlap))
    return min(score, 0.85)


def metadata_score(
    question: str,
    row: dict[str, Any],
    profile: dict[str, Any] | None = None,
    row_profile: dict[str, Any] | None = None,
) -> float:
    profile = profile or question_profile(question)
    question_norm = profile["normalized"]
    question_compact = question_norm.replace(" ", "")
    score = 0.0

    title_norm = row_profile["title_norm"] if row_profile else normalize_text(row.get("title"))
    title_compact = title_norm.replace(" ", "")
    if title_norm and (title_norm in question_norm or title_compact in question_compact):
        score += 0.9

    use_case_norm = row_profile["use_case_norm"] if row_profile else normalize_text(row.get("use_case"))
    if use_case_norm and use_case_norm in question_norm:
        score += 0.85 if "use case" in question_norm else 0.35
    elif "use case" in question_norm and use_case_norm:
        use_case_tokens = (row_profile["use_case_tokens"] if row_profile else meaningful_tokens(use_case_norm)) - BROAD_DOMAIN_TOKENS
        overlap = use_case_tokens & profile["tokens"]
        if overlap:
            score += min(0.35, 0.08 * len(overlap))

    concepts = row_profile["concepts"] if row_profile else [
        {
            "norm": normalize_text(concept),
            "compact": normalize_text(concept).replace(" ", ""),
        }
        for concept in split_terms(row.get("concepts"))
    ]
    for concept in concepts:
        concept_norm = concept["norm"]
        if not concept_norm:
            continue
        concept_compact = concept["compact"]
        if concept_norm in question_norm or (
            len(concept_compact) >= 4 and concept_compact in question_compact
        ):
            score += 0.85 if "concept" in question_norm else 0.28
            break

    keywords = row_profile["keywords"] if row_profile else [
        {"norm": normalize_text(keyword)}
        for keyword in split_terms(row.get("keywords"))
    ]
    for keyword in keywords:
        keyword_norm = keyword["norm"]
        if keyword_norm and len(keyword_norm) >= 4 and keyword_norm in question_norm:
            score += 0.08
            break

    requested_years = set(re.findall(r"\b20\d{2}\b", question_norm))
    if requested_years:
        if str(row.get("year") or "") in requested_years:
            score += 0.22
        else:
            score -= 0.08

    tokens = profile["tokens"]
    if "m1" in tokens:
        score += 0.14 if row.get("master_level") == "M1" else -0.06
    if "m2" in tokens:
        score += 0.14 if row.get("master_level") == "M2" else -0.06
    if "apprentissage" in tokens:
        score += 0.14 if row.get("track") == "apprentissage" else -0.06
    if "classique" in tokens:
        score += 0.14 if row.get("track") == "classique" else -0.06

    return score


def shared_terms(
    question: str,
    row: dict[str, Any],
    profile: dict[str, Any] | None = None,
    row_profile: dict[str, Any] | None = None,
) -> list[str]:
    profile = profile or question_profile(question)
    question_norm = profile["normalized"]
    question_tokens = profile["tokens"]
    if row_profile:
        terms = row_profile["terms"]
    else:
        terms = [
            {
                "label": term,
                "norm": normalize_text(term),
                "tokens": meaningful_tokens(normalize_text(term)),
            }
            for term in split_terms(row.get("concepts")) + split_terms(row.get("keywords"))
        ]
    matches = []
    for term in terms:
        term_norm = term["norm"]
        term_tokens = term["tokens"]
        label = term["label"]
        if (
            term_norm
            and (term_norm in question_norm or (term_tokens and term_tokens.issubset(question_tokens)))
            and label not in matches
        ):
            matches.append(label)
    return matches[:8]


def ensure_embedding_count(database: Path, model: str, dimensions: int) -> None:
    with connect(database) as conn:
        init_schema(conn)
        counts = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM documents WHERE status = 'active') AS active_count,
                (SELECT COUNT(*) FROM document_embeddings WHERE embedding_model = ?) AS embedding_count
            """,
            (model,),
        ).fetchone()
    if counts["active_count"] != counts["embedding_count"]:
        rebuild_embeddings(database, model=model, dimensions=dimensions)


class RagService:
    def __init__(
        self,
        database_path: Path | None = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
    ):
        self.database_path = database_path or db_path()
        self.model = model
        self.dimensions = dimensions
        self._rows_cache: list[dict[str, Any]] | None = None
        self._rows_signature: tuple[int, str, str, str, str] | None = None
        self._feature_cache: dict[str, dict[str, float]] = {}
        self._vector_cache: dict[str, list[float]] = {}
        self._search_profile_cache: dict[str, dict[str, Any]] = {}

    def build_embeddings(self) -> dict[str, Any]:
        result = rebuild_embeddings(self.database_path, model=self.model, dimensions=self.dimensions)
        self._rows_cache = None
        self._rows_signature = None
        self._feature_cache = {}
        self._vector_cache = {}
        self._search_profile_cache = {}
        return result

    def _embedding_signature(self) -> tuple[int, str, str, str, str]:
        with connect(self.database_path) as conn:
            init_schema(conn)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS count,
                    COALESCE(MAX(e.updated_at), '') AS max_embedding_updated_at,
                    COALESCE(MAX(d.updated_at), '') AS max_document_updated_at,
                    COALESCE(MIN(e.embedding_hash), '') AS min_embedding_hash,
                    COALESCE(MAX(e.embedding_hash), '') AS max_embedding_hash
                FROM documents d
                JOIN document_embeddings e ON e.thesis_id = d.thesis_id
                WHERE d.status = 'active'
                  AND e.embedding_model = ?
                  AND e.embedding_dimensions = ?
                """,
                (self.model, self.dimensions),
            ).fetchone()
        return (
            int(row["count"] or 0),
            row["max_embedding_updated_at"] or "",
            row["max_document_updated_at"] or "",
            row["min_embedding_hash"] or "",
            row["max_embedding_hash"] or "",
        )

    def _embedding_rows(self) -> list[dict[str, Any]]:
        signature = self._embedding_signature()
        if self._rows_cache is None or signature != self._rows_signature:
            self._rows_cache = load_embedding_rows(self.database_path, model=self.model)
            self._rows_signature = signature
            self._feature_cache = {}
            self._vector_cache = {}
            self._search_profile_cache = {}
        return self._rows_cache

    def _row_features(self, row: dict[str, Any]) -> dict[str, float]:
        thesis_id = row["thesis_id"]
        if thesis_id not in self._feature_cache:
            self._feature_cache[thesis_id] = row_feature_counts(row)
        return self._feature_cache[thesis_id]

    def _row_vector(self, row: dict[str, Any]) -> list[float]:
        thesis_id = row["thesis_id"]
        if thesis_id not in self._vector_cache:
            self._vector_cache[thesis_id] = parse_vector(row["embedding_vector_json"])
        return self._vector_cache[thesis_id]

    def _row_search_profile(self, row: dict[str, Any]) -> dict[str, Any]:
        thesis_id = row["thesis_id"]
        if thesis_id not in self._search_profile_cache:
            self._search_profile_cache[thesis_id] = row_search_profile(row)
        return self._search_profile_cache[thesis_id]

    def search(self, question: str, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise ValueError("Question is required.")
        top_k = max(1, min(int(top_k or 5), 20))
        offset = max(0, int(offset or 0))
        ensure_embedding_count(self.database_path, self.model, self.dimensions)
        profile = question_profile(question)
        query_vector = embed_text(question, dimensions=self.dimensions)
        query_features = feature_counts(profile["text"], weight=1.0)
        rows = self._embedding_rows()
        results = []
        for row in rows:
            search_profile = self._row_search_profile(row)
            vector = self._row_vector(row)
            dense_score = dot(query_vector, vector)
            if math.isnan(dense_score):
                dense_score = 0.0
            sparse_score = sparse_cosine(query_features, self._row_features(row))
            matches = shared_terms(question, row, profile=profile, row_profile=search_profile)
            score = (
                (0.25 * max(dense_score, 0.0))
                + (0.55 * sparse_score)
                + lexical_score(question, row, profile=profile, row_profile=search_profile)
                + metadata_score(question, row, profile=profile, row_profile=search_profile)
            )
            if matches:
                score += min(0.08, 0.02 * len(matches))
            results.append(self._result_row(row, score, matches))
        results.sort(key=lambda item: (-item["score"], item["thesis_id"]))
        page_results = results[offset:offset + top_k]
        page = (offset // top_k) + 1
        total_pages = (len(results) + top_k - 1) // top_k if results else 0
        return {
            "question": question,
            "top_k": top_k,
            "embedding_model": self.model,
            "embedding_dimensions": self.dimensions,
            "count": len(page_results),
            "total": len(results),
            "offset": offset,
            "page": page,
            "page_size": top_k,
            "total_pages": total_pages,
            "has_previous": page > 1 and total_pages > 0,
            "has_next": page < total_pages,
            "results": page_results,
        }

    def answer(self, question: str, top_k: int = 5, use_llm: bool = False, model: str | None = None) -> dict[str, Any]:
        search_result = self.search(question, top_k=top_k)
        results = search_result["results"]
        local_answer = local_rag_answer(question, results)
        answer_text = local_answer
        answer_mode = "local"
        llm_error = ""
        if use_llm:
            try:
                answer_text = ollama_answer(question, results, model=model)
                answer_mode = "ollama"
            except Exception as exc:  # pragma: no cover - depends on local Ollama runtime
                answer_text = local_answer
                answer_mode = "ollama_unavailable"
                llm_error = str(exc)
        return {
            **search_result,
            "answer": answer_text,
            "answer_mode": answer_mode,
            "llm_error": llm_error,
            "sources": [
                {
                    "thesis_id": row["thesis_id"],
                    "title": row["title"],
                    "score": row["score"],
                    "pdf_url": row["pdf_url"],
                }
                for row in results
            ],
        }

    def _result_row(self, row: dict[str, Any], score: float, matches: list[str]) -> dict[str, Any]:
        return {
            "thesis_id": row["thesis_id"],
            "title": row["title"],
            "year": row["year"],
            "master_level": row["master_level"],
            "track": row["track"],
            "concepts": row.get("concepts") or "",
            "keywords": row.get("keywords") or "",
            "use_case": row.get("use_case") or "",
            "methodology": row.get("methodology") or "",
            "abstract": row.get("abstract") or "",
            "score": round(float(score), 4),
            "matched_terms": matches,
            "pdf_url": f"/api/files/{row['thesis_id']}",
        }


def local_rag_answer(question: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return "No matching thesis metadata was found."
    top = results[: min(5, len(results))]
    source_ids = ", ".join(row["thesis_id"] for row in top)
    use_cases = []
    concepts = []
    for row in top:
        if row.get("use_case") and row["use_case"] not in use_cases:
            use_cases.append(row["use_case"])
        for concept in split_terms(row.get("concepts")):
            if concept not in concepts:
                concepts.append(concept)
    lines = [
        f"Closest theses for the question are {source_ids}.",
        "Main use cases: " + "; ".join(use_cases[:4]) + ".",
        "Relevant concepts: " + "; ".join(concepts[:8]) + ".",
        "Use the listed thesis IDs as sources before opening the PDFs.",
    ]
    return " ".join(line for line in lines if line.strip())


def ollama_answer(question: str, results: list[dict[str, Any]], model: str | None = None) -> str:
    model = model or os.environ.get("MIAGE_OLLAMA_MODEL", "qwen2.5:7b")
    url = os.environ.get("MIAGE_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
    timeout = float(os.environ.get("MIAGE_OLLAMA_TIMEOUT", "90"))
    context = [
        {
            "thesis_id": row["thesis_id"],
            "title": row["title"],
            "year": row["year"],
            "master_level": row["master_level"],
            "track": row["track"],
            "concepts": row["concepts"],
            "keywords": row["keywords"],
            "use_case": row["use_case"],
            "methodology": row["methodology"],
            "abstract": row["abstract"][:900],
            "score": row["score"],
        }
        for row in results
    ]
    prompt = f"""
You answer questions about MIAGE master's theses.
Use only the retrieved metadata below. Do not invent sources.
Answer in the same language as the question when possible.
Cite thesis IDs in the answer.

Question:
{question}

Retrieved theses:
{json.dumps(context, ensure_ascii=False, indent=2)}
""".strip()
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama unavailable: {exc}") from exc
    answer = str(payload.get("response") or "").strip()
    if not answer:
        raise RuntimeError("Ollama returned an empty answer.")
    return answer
