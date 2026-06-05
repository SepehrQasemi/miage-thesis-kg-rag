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
  "use_llm": false
}
```

If `use_llm` is false, the backend returns a deterministic local answer from the retrieved sources. If `use_llm` is true, the backend tries Ollama and falls back to the local answer when Ollama is unavailable.

## Import Integration

When a new PDF is approved from the Import PDF screen, the app updates:

- SQLite `documents`
- `data/processed/theses.csv`
- Knowledge Graph tables and exports
- `document_embeddings`

This keeps RAG search aligned with the current approved dataset.

## Current Limitation

This version retrieves at thesis level, not page or paragraph level. That is deliberate because the validated comparable information is mostly in the first pages and metadata fields. Full-text chunking can be added later when the project needs precise passage-level answers.
