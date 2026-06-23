# RAG

## Goal

The RAG layer answers questions about the thesis dataset using structured metadata stored in Neo4j.

It is intentionally local and free:

- no paid API;
- no cloud embedding service;
- deterministic local embeddings;
- Neo4j thesis rows as the source of truth.

## Source Data

For each thesis, RAG uses fields such as:

- title;
- year;
- master level;
- track;
- abstract when available;
- keywords;
- concepts;
- use case;
- methodology;
- introduction and conclusion when available.

The full PDF text is not the default RAG source. This keeps the first version focused on the structured metadata that was extracted and reviewed.

## Retrieval

The retrieval service builds weighted local text features:

- title and concepts have high weight;
- keywords and use case have high weight;
- methodology has medium weight;
- year, master level, and track have lower weight;
- abstract/introduction/conclusion provide additional context.

The feature vector is hashed into a fixed-size deterministic vector. Query vectors are produced with the same local method.

## Threshold Behavior

The system does not force an exact number of source theses.

Example:

- user asks for 10 results;
- only 3 theses are above the relevance threshold;
- the UI shows 3 theses, not 10 weak matches.

This matters for rare topics such as medicine, fraud, quantum computing, or a specific methodology.

## UI Behavior

The RAG page shows:

- answer text;
- source theses;
- relevance score;
- thesis profile button;
- PDF open button;
- pagination;
- maximum 20 sources per page.

The `Show all results` option means "show all relevant results above the threshold", not "show every thesis in the database".

## Scripts

```powershell
python scripts/build_embeddings.py
python scripts/validate_embeddings.py
python scripts/evaluate_rag_benchmark.py
python scripts/evaluate_rag_comprehensive.py
```

`build_embeddings.py` is a sanity command. Embeddings are built in memory from Neo4j rows and are not persisted to a separate database table.

## Limitations

The current RAG version is metadata-first. It is accurate for questions that can be answered from extracted thesis metadata. It is not designed to answer detailed questions that require reading every page of a PDF.

Future improvements can add:

- optional chunk-level PDF retrieval;
- hybrid graph + text retrieval;
- stronger local embedding models;
- local LLM answer synthesis through Ollama.

When `Use Ollama` is enabled in the web UI, retrieval still happens first through the local metadata search. Ollama only rewrites/synthesizes the answer from the retrieved thesis metadata and must cite thesis IDs. The default generation options are CPU-only (`MIAGE_OLLAMA_NUM_GPU=0`) to avoid CUDA failures on low-VRAM laptops.
