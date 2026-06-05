# Quick Start

This guide is for someone who downloads the project from GitHub and wants to run it locally.

## 1. Install Requirements

Install Python 3.11 or newer.

Optional:

- Install Ollama if you want local LLM suggestions during PDF import review.
- Pull the recommended model:

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

The model can be several GB. The app still works without Ollama; only LLM suggestions are disabled.

## 2. Setup

On Windows, run:

```bat
setup_windows.cmd
```

The Windows setup asks whether to install Ollama and pull `qwen2.5:7b`.

To install the LLM dependency later:

```bat
setup_ollama_windows.cmd
```

Manual setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python scripts/setup_project.py --install-deps --install-playwright
```

The setup script:

- creates the local data folders;
- creates `.env` from `.env.example` when missing;
- initializes `data/app.sqlite`;
- creates empty graph, CSV, and RAG embedding outputs so the UI can start immediately.

## 3. Start The App

On Windows:

```bat
run_app_windows.cmd
```

Manual:

```powershell
python scripts/run_web_app.py --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## 4. Add PDFs

Preferred workflow:

1. Open the `Import PDF` screen.
2. Upload one thesis PDF, or select several PDFs at once.
3. Review the extracted metadata for each draft in the import queue.
4. Optionally generate local LLM suggestions.
5. Apply suggestions only if they look correct.
6. Click `Approve`.

Approve updates the SQLite database, CSV export, Knowledge Graph, and RAG embeddings together.

Alternative batch workflow:

```powershell
python scripts/setup_project.py --build-data
```

Use this only after placing PDFs in:

```text
data/raw/theses_pdf/
```

## 5. Check The Installation

```powershell
python scripts/doctor.py
python -m pytest
```

`doctor.py` checks Python, dependencies, database, graph outputs, RAG embeddings, raw PDFs, and optional Ollama availability.

## 6. Common Problems

If Playwright tests fail because Chromium is missing:

```powershell
python -m playwright install chromium
```

If LLM suggestions show Ollama as unavailable:

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

Manual review and approval still work without Ollama.
