# Local Metadata RAG

The first RAG layer is intentionally local, free, and metadata-based.

It does not send data to a paid API and it does not chunk full PDFs yet. Each thesis is represented by one retrieval text built from validated metadata:

- title
- year
- master level
- track
- keywords
- concepts
- use case
- methodology
- abstract, introduction, and conclusion when available

## Storage

Embeddings are stored in SQLite table:

`document_embeddings`

Each row contains:

- `thesis_id`
- `embedding_model`
- `embedding_dimensions`
- `embedding_text`
- `embedding_vector_json`
- `embedding_hash`

The current default model is `local-hash-v1`. It is a deterministic local hashing embedder, so fresh GitHub clones can run RAG search without downloading a large model.

## Ranking And Relevance Threshold

`top_k` is a maximum, not a required result count.

The service first scores candidate theses, then keeps only sources that are relevant enough. This avoids filling the answer with weak matches when the requested subject is rare.

The default relevance threshold is:

```text
MIAGE_RAG_MIN_SCORE=0.30
```

If the variable is not set, the backend uses `0.30`. A lower value returns more sources but can include weak matches. A higher value returns fewer sources but is stricter.

The final RAG score combines:

- deterministic local embedding similarity;
- sparse lexical overlap;
- title, concept, keyword, use case, year, level, and track metadata signals;
- domain filters such as the medical/health domain;
- specific evidence from non-generic query terms.

Generic terms such as `AI`, `machine learning`, `model`, `classification`, and `detection` are useful for ranking but are not enough by themselves when the question also contains a more specific clue. For example, a question about `League of Legends` should not return unrelated machine-learning theses only to reach `top_k=5`.

The final filter also extracts anchor clues from the original question. For example, `blockchain security` keeps `blockchain` as the anchor and does not accept a thesis only because it mentions general security. Concepts and keywords still help ranking, but when an abstract is available the final evidence check prefers stronger fields: title, use case, and abstract.

For domain questions, the domain filter uses stronger evidence than the general ranking text. When an abstract exists, domain evidence comes from title plus abstract. When the abstract is missing, it falls back to title plus reviewed use case. This reduces the impact of noisy concepts or keywords in older extracted rows.

## Build

```powershell
python scripts/build_embeddings.py
python scripts/validate_embeddings.py
```

The full pipeline also builds and validates embeddings:

```powershell
python scripts/run_pipeline.py
```

## API

Semantic retrieval:

```text
POST /api/rag/search
```

Answer with cited sources:

```text
POST /api/rag/answer
```

Example body:

```json
{
  "question": "Which theses are related to fraud detection with machine learning?",
  "top_k": 5,
  "min_score": 0.3,
  "use_llm": false
}
```

`min_score` is optional. When omitted, the backend uses `MIAGE_RAG_MIN_SCORE` or the built-in default `0.30`.

The response includes the score and threshold:

```json
{
  "top_k": 5,
  "min_score": 0.3,
  "count": 2,
  "total": 2,
  "results": [
    {
      "thesis_id": "thesis_0001",
      "title": "Example title",
      "score": 0.8421
    }
  ]
}
```

If `use_llm` is false, the backend returns a deterministic local answer from the retrieved sources. If `use_llm` is true, the backend tries Ollama and falls back to the local answer when Ollama is unavailable.

When `all_results` is true, the endpoint returns all relevant sources above the threshold with server-side pagination. Each page is capped at 20 sources.

## Import Integration

When a new PDF is approved from the Import PDFs screen, the app updates:

- SQLite `documents`
- `data/processed/theses.csv`
- Knowledge Graph tables and exports
- `document_embeddings`

This keeps RAG search aligned with the current approved dataset.

## Current Limitation

This version retrieves at thesis level, not page or paragraph level. That is deliberate because the validated comparable information is mostly in the first pages and metadata fields. Full-text chunking can be added later when the project needs precise passage-level answers.

The score is a local ranking signal, not an academic confidence score. It is useful for comparing sources inside the same RAG answer, but it should not be interpreted as an absolute quality grade for a thesis.
