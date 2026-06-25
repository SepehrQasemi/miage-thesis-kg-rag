# Quickstart

This application is Neo4j-first. Neo4j stores thesis metadata, import drafts, graph nodes, and graph relationships.

The filesystem stores PDFs and generated artifacts:

- `data/raw/theses_pdf`: approved PDFs;
- `data/staging`: temporary uploaded PDFs;
- `data/processed/theses.csv`: exported dataset;
- `data/graph`: graph CSV/JSON snapshots;
- `data/reports`: validation and quality reports.

## Windows Setup

Make sure Docker Desktop is installed and running.

Install and initialize. This command creates the Python virtual environment, installs dependencies, starts Neo4j with Docker Compose, creates `.env` when missing, and checks the installation:

```bat
setup_windows.cmd
```

Start the app:

```bat
run_app_windows.cmd
```

Open:

```text
http://127.0.0.1:8000
```

## Manual Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
docker compose up -d neo4j
python scripts/setup_project.py
python scripts/doctor.py
python scripts/run_web_app.py --port 8000
```

## Environment

Use `.env.example` as the template:

```text
MIAGE_NEO4J_URI=bolt://127.0.0.1:7687
MIAGE_NEO4J_USER=neo4j
MIAGE_NEO4J_PASSWORD=miage-rag-2026
MIAGE_NEO4J_DATABASE=
MIAGE_MAX_UPLOAD_MB=100
```

Neo4j Browser:

```text
http://127.0.0.1:7474
```

## Add Theses

Use the web UI:

1. Open `Import PDFs`.
2. Select one PDF or multiple PDFs.
3. Review extracted metadata.
4. Approve valid drafts.
5. The app copies approved PDFs to `data/raw/theses_pdf`.
6. Neo4j is rebuilt with the new thesis metadata and graph relationships.
7. CSV exports, graph snapshots, and reports are regenerated.

## Check The Installation

```powershell
python scripts/doctor.py
python scripts/export_csv.py
python scripts/validate_dataset.py
python scripts/build_knowledge_graph.py
python scripts/validate_knowledge_graph.py
python scripts/validate_embeddings.py
```

## Run Tests

```powershell
python -m pytest -q
```

For UI tests, install Playwright Chromium first:

```powershell
python -m playwright install chromium
```

## Optional Ollama

Ollama is optional. The app works without it. If installed, it can provide local extraction review suggestions.

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

For low-VRAM laptops, keep the default CPU-only settings from `.env.example`:

```env
MIAGE_OLLAMA_NUM_GPU=0
MIAGE_OLLAMA_NUM_CTX=2048
MIAGE_OLLAMA_TIMEOUT=300
```

This makes local LLM suggestions slower but more reliable. Use `MIAGE_OLLAMA_NUM_GPU=auto` only if the machine has enough GPU memory.
