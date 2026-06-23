# User Guide

## 1. Start The Application

Start Neo4j first:

```powershell
docker compose up -d neo4j
```

Start the web app:

```powershell
python scripts/run_web_app.py --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## 2. Check The System

Run:

```powershell
python scripts/doctor.py
```

Expected result:

- Python dependencies are available;
- Neo4j is reachable;
- graph output files exist;
- Ollama may be unavailable, but that is not blocking.

## 3. Import PDFs

Open `Import PDFs`.

You can select one PDF or multiple PDFs together.

The application checks:

- file extension must be `.pdf`;
- file content must look like a PDF;
- file must not be empty;
- file size must be below `MIAGE_MAX_UPLOAD_MB`;
- duplicate PDFs are detected by SHA-256 hash.

After upload:

1. Review the extracted fields.
2. Correct the fields when needed.
3. Approve valid drafts.
4. Discard invalid drafts.

Approved PDFs are copied to `data/raw/theses_pdf`.

Approved metadata is stored in Neo4j.

## 4. Search Theses

Open `Thesis Search`.

You can:

- search by title, concept, keyword, use case, or methodology;
- filter by concept, year, level, and track;
- view results with pagination;
- click a thesis to open its graph profile;
- open the PDF from the profile.

## 5. Explore The Knowledge Graph

Open `Knowledge Graph`.

The graph shows:

- thesis nodes;
- concept nodes;
- keyword nodes;
- use case nodes;
- methodology nodes;
- year, level, and track nodes.

Click a node to inspect its metadata and direct connections.

## 6. Use RAG

Open `Ask / RAG`.

Ask a question such as:

```text
Which theses are related to medical diagnosis?
```

The system returns only sources above the relevance threshold. It does not force weak results just to reach the requested maximum.

Use `Show all results` when you want every relevant source above the threshold, with pagination.

## 7. View Or Export The Dataset

Open `Dataset`.

You can:

- view all thesis rows;
- copy CSV;
- download CSV.

The CSV is generated from Neo4j thesis rows.

## 8. Optional LLM Review

Ollama is optional.

If Ollama is installed, the import screen can generate local review suggestions. If Ollama is unavailable, manual review still works.

The default configuration runs Ollama on CPU:

```env
MIAGE_OLLAMA_NUM_GPU=0
MIAGE_OLLAMA_TIMEOUT=300
```

This is slower, but it is safer on low-VRAM laptops. On a stronger GPU, this can be changed in `.env`.

## 9. Useful Maintenance Commands

```powershell
python scripts/export_csv.py
python scripts/build_knowledge_graph.py
python scripts/validate_dataset.py
python scripts/validate_knowledge_graph.py
python scripts/validate_embeddings.py
python scripts/query_knowledge_graph.py summary
```

## 10. Common Problems

### Neo4j Is Not Reachable

Run:

```powershell
docker compose up -d neo4j
```

Then:

```powershell
python scripts/doctor.py
```

### PDF Is Rejected

Possible reasons:

- file is not really a PDF;
- file is empty;
- file is larger than `MIAGE_MAX_UPLOAD_MB`;
- file is a duplicate of an approved thesis.

### RAG Shows Few Results

This is expected when the topic is rare. The system filters weak matches instead of filling the result list with unrelated theses.
