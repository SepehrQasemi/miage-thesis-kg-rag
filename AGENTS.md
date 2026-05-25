# Project Instructions

The user is a master's student in MIAGE at Universite Paris Nanterre.

This project combines:
- software engineering
- information systems
- data extraction
- NLP
- knowledge graph construction
- RAG
- academic analysis

## Project Goal

Build a reusable system that extracts structured information from MIAGE thesis PDFs, stores one row per thesis in SQLite, creates CSV datasets, and later supports knowledge graph construction and RAG.

## Data Rules

- `data/raw/theses_pdf/` is immutable.
- Do not edit, rename, or delete raw PDFs unless the user explicitly asks.
- Any generated text, JSON, CSV, reports, or intermediate files must go outside `data/raw/`.
- Keep manifests and quality reports updated when data selection changes.

## Extraction Strategy

Use a free-first approach:

1. Rule-based extraction for stable fields.
2. Classical NLP for baseline keyword and concept extraction.
3. Optional local LLM later for semantic fields and fallback cases.

Rule-based alone is not enough because the corpus contains several formats. Paid API usage is not allowed for the current version. Local Ollama models are allowed for fallback review.

## Main CSV Fields

The primary CSV should include:

- `thesis_id`
- `file_name`
- `year`
- `title`
- `master_level`
- `track`
- `abstract`
- `keywords`
- `concepts`
- `use_case`
- `methodology`
- `confidence`
- `needs_review`

## Engineering Preferences

- Keep the project modular.
- Prefer repeatable scripts over one-off notebooks.
- Every pipeline step should be runnable from `scripts/`.
- Every extraction run should produce a quality report.
- Use simple, inspectable outputs first: SQLite and CSV.
- Keep the current database simple: one thesis equals one row in `documents`.
- Use LLM fallback only for rows marked `needs_review`, and prefer filling missing fields over overwriting confident rule-based values.
