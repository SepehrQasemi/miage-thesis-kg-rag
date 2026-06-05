# Local Web App

The local web app provides a first user interface for the extracted thesis dataset and the Knowledge Graph.

It is intentionally simple and local:

- backend: FastAPI
- database: the existing SQLite database
- frontend: static HTML/CSS/JavaScript
- no paid API
- no cloud dependency

## Run

Build and validate the data first:

```powershell
python scripts/validate_dataset.py
python scripts/build_knowledge_graph.py
python scripts/validate_knowledge_graph.py
python scripts/build_embeddings.py
python scripts/validate_embeddings.py
```

Start the app:

```powershell
python scripts/run_web_app.py --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Screens

The first version contains:

- Dashboard: graph counts, top concepts, use cases, methodologies
- Thesis Search: search, filters, show-all results, and a paginated thesis table limited to 20 rows per page
- Thesis Detail: metadata, concepts, keywords, similar theses, PDF link
- Concepts: concept index, connected theses, related concepts
- Dataset: complete extracted dataset table with CSV copy and download actions
- Ask / RAG: ask questions over local metadata embeddings, optionally show all ranked sources with 20 results per page, open each source profile inside the app, and open the PDF from that profile
- Import PDF: upload one or more PDFs, extract, review each draft, approve, and refresh the local graph and RAG index

## API

Main endpoints:

```text
GET /api/summary
GET /api/facets
GET /api/dataset
GET /api/dataset.csv
POST /api/rag/search
POST /api/rag/answer
GET /api/theses
GET /api/theses/{thesis_id}
GET /api/theses/{thesis_id}/similar
GET /api/concepts/{concept_label}
GET /api/top/{node_type}
GET /api/files/{thesis_id}
POST /api/imports
POST /api/imports/batch
GET /api/imports/{draft_id}
POST /api/imports/{draft_id}/approve
DELETE /api/imports/{draft_id}
```

Example:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/theses?concept=machine%20learning&year=2024"
```

## Import Workflow

New PDFs are not inserted directly into the main dataset.

The app uses this workflow:

1. Upload one PDF or select several PDFs from the Import PDF screen.
2. Store it in `data/staging/imports`.
3. Check the PDF hash against active documents to prevent duplicates.
4. Extract first-page metadata with the local NLP pipeline.
5. Create one review draft per new PDF with title, year, level, track, keywords, concepts, use case, methodology, and abstract.
6. Optionally request local Ollama LLM suggestions from the Review screen.
7. Apply LLM suggestions to the form only if they look correct.
8. Review the draft queue one item at a time.
9. Wait for manual approval from the UI.
10. Copy the approved PDF into `data/raw/theses_pdf`.
11. Insert one row into `documents`.
12. Rebuild the Knowledge Graph tables and graph export files.
13. Export `data/processed/theses.csv`.
14. Rebuild local metadata embeddings for RAG search.

This keeps incomplete imports out of the main database until the metadata has been reviewed.

## Optional LLM Review

The Import PDF screen can ask a local Ollama model for metadata suggestions.

Default settings:

```text
MIAGE_OLLAMA_MODEL=qwen2.5:7b
MIAGE_OLLAMA_URL=http://127.0.0.1:11434/api/generate
MIAGE_OLLAMA_TIMEOUT=90
```

The LLM result is intentionally non-authoritative:

- it is generated only from the staged draft and front-pages text;
- it is returned as validated JSON;
- it appears in a separate `LLM suggestions` panel;
- `Apply LLM suggestions` only fills the Review form;
- the database, CSV, graph, and RAG embeddings are updated only after `Approve`;
- if Ollama is unavailable, manual review still works.

## Ask / RAG Workflow

The first RAG version is local and metadata-based. It does not chunk the full PDFs.

1. Build one retrieval text per active thesis from title, concepts, keywords, use case, methodology, abstract, introduction, and conclusion.
2. Store a deterministic local embedding in SQLite table `document_embeddings`.
3. Embed the user question with the same local model.
4. Rank theses by cosine similarity.
5. Return an answer plus cited thesis IDs and PDF links.
6. When `Show all results` is enabled in the Ask/RAG screen, return the ranked source list through server-side pagination with a maximum of 20 theses per page.
7. Each RAG source can be opened as an in-app thesis profile containing metadata, concepts, keywords, similar theses, and a PDF link.

`POST /api/rag/answer` works without Ollama by returning a local source-grounded answer. If `use_llm` is true, the backend tries Ollama and falls back to the local answer if Ollama is unavailable.

## Responsive QA

The UI must stay usable on:

- mobile: around 390px width
- tablet: around 768px width
- desktop: around 1440px width

The current layout has been checked on dashboard, thesis search, dataset, Ask/RAG, import, and concept explorer views. The checks confirmed:

- no horizontal page overflow
- sidebar collapses above the main content on smaller screens
- filters stack on mobile
- the complete dataset table stays inside its own horizontal scroll area
- thesis table remains scrollable inside its panel
- detail panels move below the main content on smaller screens

## Automated UI Tests

The UI has browser-level tests in:

`tests/test_web_ui_e2e.py`

These tests start the FastAPI app with a temporary SQLite database and verify:

- dashboard metrics render;
- thesis search filters work;
- thesis search can show the full result set through server-side pagination;
- selecting a thesis opens the detail panel;
- similar theses are shown;
- concept explorer loads connected theses and related concepts;
- complete dataset rows are shown with a CSV download link;
- Ask/RAG retrieves an answer and cited sources;
- Ask/RAG can show all ranked sources in 20-result pages;
- Ask/RAG source profiles open inside the app and expose the PDF link;
- PDF import creates a review draft;
- local LLM suggestions are non-blocking and do not update the database by themselves;
- approving an import updates the database, CSV, graph tables, RAG embeddings, and search UI;
- mobile, tablet, and desktop layouts do not create horizontal overflow;
- browser console errors are treated as test failures.

Run all tests:

```powershell
python -m pytest
```

If Playwright browsers are not installed on a new machine, install Chromium once:

```powershell
python -m playwright install chromium
```
