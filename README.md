# MIAGE Thesis Knowledge Graph + RAG

This project is a local, free, no-cloud web app for managing MIAGE thesis PDFs. It extracts structured metadata, stores it in SQLite, exports CSV files, builds a Knowledge Graph, and provides a browser UI for search, graph exploration, PDF import, human review, and optional local Ollama suggestions.

## Quick Start

Requirements:

- Python 3.11 or newer
- Git, if cloning from GitHub
- Optional: Ollama with `qwen2.5:7b` for local LLM suggestions

Windows one-time setup:

```bat
setup_windows.cmd
```

During setup, Windows users are asked whether they want to install Ollama and download the local model for LLM suggestions. This is optional because the model download can be several GB.

Start the app:

```bat
run_app_windows.cmd
```

Manual cross-platform setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python scripts/setup_project.py --install-deps --install-playwright
python scripts/run_web_app.py --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Check your installation:

```powershell
python scripts/doctor.py
```

Install or repair the optional local LLM dependency later:

```bat
setup_ollama_windows.cmd
```

Equivalent manual command:

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

Fresh clones work even without bundled PDFs. The setup script creates an empty SQLite database and empty graph exports. Add theses from the `Import PDF` screen, or place PDFs in `data/raw/theses_pdf/` and run:

```powershell
python scripts/setup_project.py --build-data
```

## Data Policy

Thesis PDFs and generated research data are not committed to GitHub.

The local development workspace can contain:

- clean raw PDFs in `data/raw/theses_pdf/`
- local SQLite database `data/app.sqlite`
- generated CSV, graph, report, OCR cache, and staging files under `data/`

Fresh clones start with no thesis PDFs. Run the setup script, then add PDFs from the `Import PDF` screen.

## Current Version

Version 1 is intentionally simple:

- one SQLite database: `data/app.sqlite`
- one main table: `documents`
- two graph tables: `graph_nodes` and `graph_edges`
- one row per thesis
- one local graph export under `data/graph/`
- no paid API
- no cloud dependency
- optional local LLM fallback only for review cases
- local OCR fallback for image-only cover pages

The system stores only useful front-matter text for now:

- cover text from the first pages
- OCR text from image-only front pages when needed
- abstract
- introduction
- conclusion

`abstract` is useful when it exists, but it is not required for quality approval because many theses do not provide a comparable abstract section. The comparable fields are title, year, master level, track, keywords, concepts, use case, and methodology.

Full-text RAG is intentionally postponed.

## Knowledge Graph

The first graph version is built from validated metadata, not from full document chunks.

Graph node types:

- `Thesis`
- `Concept`
- `Keyword`
- `UseCase`
- `Methodology`
- `Year`
- `MasterLevel`
- `Track`

Main graph relations:

- `Thesis -> HAS_CONCEPT -> Concept`
- `Thesis -> HAS_KEYWORD -> Keyword`
- `Thesis -> HAS_USE_CASE -> UseCase`
- `Thesis -> USES_METHODOLOGY -> Methodology`
- `Thesis -> SUBMITTED_IN -> Year`
- `Thesis -> HAS_MASTER_LEVEL -> MasterLevel`
- `Thesis -> HAS_TRACK -> Track`
- `Thesis -> RELATED_TO -> Thesis` for inferred concept overlap

Graph outputs:

- `data/graph/nodes.csv`
- `data/graph/edges.csv`
- `data/graph/knowledge_graph.json`
- `data/reports/knowledge_graph_summary.json`
- `data/reports/knowledge_graph_node_metrics.csv`
- `data/reports/knowledge_graph_related_theses.csv`
- `data/reports/knowledge_graph_validation.csv`
- `data/reports/knowledge_graph_validation_summary.json`

Schema details are documented in `docs/knowledge_graph_schema.md`.
Query examples are documented in `docs/knowledge_graph_queries.md`.

## Local Web App

The first local UI is available as a FastAPI app with static HTML/CSS/JavaScript.

It includes:

- dashboard
- thesis search and filters
- thesis detail panel
- similar theses
- concept explorer
- direct PDF link for each thesis
- PDF import with single-file or multi-file staging, metadata review, approval, CSV export, and graph refresh
- optional local Ollama suggestions for import review

Run it locally:

```powershell
python scripts/setup_project.py
python scripts/run_web_app.py --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Details are documented in `docs/web_app.md`.

Approved imports are the only workflow that should add new PDFs to `data/raw/theses_pdf/`. The Import PDF screen can accept one PDF or several PDFs at once. Each uploaded PDF becomes a separate review draft, and each draft must be approved or discarded individually. Manual changes to the raw folder should still be avoided because they bypass duplicate checks, review, CSV export, and graph rebuilds.

LLM suggestions are optional and local. They fill only the Review form and never update SQLite, CSV, or the graph until the user clicks `Approve`.

## Optional Local LLM Fallback

For documents marked `needs_review`, and for Import PDF review suggestions, the project can use a free local Ollama model.

Recommended model:

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

Or manually:

```powershell
ollama pull qwen2.5:7b
```

Ollama is not a Python package, so it is not installed through `requirements.txt`. On Windows, the project setup can install it with `winget` using the package ID `Ollama.Ollama`, then pull the model.

Run local LLM review without applying changes:

```powershell
python scripts/llm_review_needs_review.py --model qwen2.5:7b
```

Run and apply confident fixes:

```powershell
python scripts/llm_review_needs_review.py --model qwen2.5:7b --apply
python scripts/export_csv.py
python scripts/export_quality_report.py
```

The LLM is used only as a fallback. It should fill missing fields when supported by the text, not invent missing abstracts.

If a document does not contain an explicit abstract, the system can optionally generate a clearly marked abstract from the available introduction/conclusion text:

```powershell
python scripts/llm_generate_missing_abstracts.py --model qwen2.5:7b --apply
```

Generated abstracts are tagged in `extraction_notes` as `abstract_generated:<model>` so they are not confused with abstracts extracted from the original PDF.

## Target CSV Fields

The main extraction goal is to create `data/processed/theses.csv` with one row per thesis:

```text
thesis_id
file_name
year
title
master_level
track
abstract
keywords
concepts
use_case
methodology
confidence
needs_review
```

`abstract` may be empty. Missing abstracts do not make a row `needs_review`.

## Scripts

Initialize or reset the database:

```powershell
python scripts/init_db.py --reset
```

Process all raw PDFs into SQLite:

```powershell
python scripts/process_pdfs.py --force
```

Run the full local pipeline with OCR, rule repair, manual verified overrides if present, and exports:

```powershell
python scripts/run_pipeline.py
```

Run the same pipeline with local Ollama review and generated abstracts:

```powershell
python scripts/run_pipeline.py --with-llm-review --generate-abstracts --model qwen2.5:7b
```

Export the final CSV:

```powershell
python scripts/export_csv.py
```

Validate that the dataset is ready for the next stage:

```powershell
python scripts/validate_dataset.py
```

Build the Knowledge Graph:

```powershell
python scripts/build_knowledge_graph.py
```

Validate the Knowledge Graph:

```powershell
python scripts/validate_knowledge_graph.py
```

Query the Knowledge Graph:

```powershell
python scripts/query_knowledge_graph.py summary
python scripts/query_knowledge_graph.py similar thesis_0006 --limit 10
python scripts/query_knowledge_graph.py search --concept "machine learning" --concept sante --match all
```

Run the local web app:

```powershell
python scripts/run_web_app.py --port 8000
```

Test only the first 5 PDFs:

```powershell
python scripts/init_db.py --reset
python scripts/process_pdfs.py --limit 5 --force
python scripts/export_csv.py --output data/processed/theses_sample.csv
```

## Pipeline

1. Read each PDF from `data/raw/theses_pdf/`.
2. Extract cover text and scan the document in memory for useful sections.
3. If an early page has no text layer but contains images, render it and run local OCR.
4. Use rule-based extraction for stable fields:
   - year
   - title
   - M1/M2
   - apprentissage/mixte
   - abstract/introduction when headings are clear
5. Use local NLP rules for keywords and concepts.
6. Use rule-based classifiers for use case and methodology.
7. Store one row per thesis in SQLite.
8. Optionally run local LLM fallback on `needs_review` documents.
9. Optionally generate clearly marked abstracts for theses that have no explicit abstract.
10. Export `data/processed/theses.csv`.
11. Write `data/reports/extraction_quality.csv`.
12. Validate required fields and write:
    - `data/reports/dataset_validation.csv`
    - `data/reports/dataset_validation_summary.json`
13. Build the local Knowledge Graph:
    - SQLite tables: `graph_nodes`, `graph_edges`
    - CSV files: `data/graph/nodes.csv`, `data/graph/edges.csv`
    - JSON snapshot: `data/graph/knowledge_graph.json`
14. Validate the Knowledge Graph.

## Current Validation Target

The dataset is considered ready for the graph/RAG stage when:

- active database rows match the raw PDF count
- required fields are complete: title, year, master level, track, keywords, concepts, use case, methodology
- no active row is marked `needs_review`
- exported CSV row count matches the database
- suspicious title artifacts such as PDF backticks or encoding mojibake are absent

Missing abstracts are reported separately but do not block validation.

## Current Graph Validation Target

The graph is considered ready for the first graph/RAG experiments when:

- every active thesis has one `Thesis` node
- every graph edge points to existing nodes
- node IDs and edge IDs are unique
- every thesis has required relations to year, master level, track, use case, methodology, concepts, and keywords
- graph CSV row counts match SQLite graph tables

## Important Rule

Do not modify files in `data/raw/theses_pdf/` manually. Add new PDFs through the Import PDF workflow so duplicate checks, metadata review, database insert, CSV export, and graph rebuild happen together.
