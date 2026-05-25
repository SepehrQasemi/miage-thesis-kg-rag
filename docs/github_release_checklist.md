# GitHub Release Checklist

Use this checklist before publishing or sharing the repository.

## Required

- Run the setup script on a clean checkout:

```powershell
python scripts/setup_project.py --install-deps --install-playwright
```

- Run the environment doctor:

```powershell
python scripts/doctor.py
```

- Run tests:

```powershell
python -m pytest
```

- Validate the current dataset and graph if data is included locally:

```powershell
python scripts/validate_dataset.py
python scripts/validate_knowledge_graph.py
```

## Data Policy

Do not commit private thesis PDFs unless you are explicitly allowed to publish them.

The repository is configured to ignore:

- all local runtime data under `data/`, except `data/README.md`
- all runtime logs and local output files under `output/`
- local environment files such as `.env`

Fresh users can still run the app with an empty local database and add PDFs through the UI.

## User-Facing Entry Points

- `setup_windows.cmd`
- `run_app_windows.cmd`
- `scripts/setup_project.py`
- `scripts/doctor.py`
- `scripts/run_web_app.py`
- `docs/quickstart.md`

## Optional Local LLM

LLM suggestions use local Ollama only. No paid API is required.

Recommended model:

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

If Ollama is not running, the app keeps manual import review available.

Windows users can also run:

```bat
setup_ollama_windows.cmd
```
