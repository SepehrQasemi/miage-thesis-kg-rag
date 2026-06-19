# MIAGE Thesis Knowledge Graph + RAG

## English

### Overview

This project is a local, free, no-cloud web application for managing MIAGE thesis PDFs.

It can:

- import one or many thesis PDFs from the web interface;
- extract and review structured thesis metadata;
- store one validated row per thesis in SQLite;
- export the complete dataset as CSV;
- build a local Knowledge Graph;
- build local metadata embeddings for RAG search;
- answer questions over thesis metadata with cited sources;
- show relevant RAG sources with scores and pagination;
- open an in-app thesis profile and then open the source PDF;
- optionally use a local Ollama model for review suggestions.

No paid API is required. Ollama is optional and runs locally.

### Main Stack

- Python 3.11+
- FastAPI
- SQLite
- static HTML, CSS, and JavaScript
- pypdf / PyMuPDF / pytesseract for PDF extraction and OCR fallback
- local deterministic embeddings for the first RAG version
- optional Ollama model: `qwen2.5:7b`

### Quick Start On Windows

Clone the repository, then run:

```bat
setup_windows.cmd
```

The setup script installs Python dependencies, installs Playwright browsers, initializes the local database, creates empty graph/RAG outputs, and asks whether you want to install the optional local Ollama model.

Start the app:

```bat
run_app_windows.cmd
```

Open:

```text
http://127.0.0.1:8000
```

### Manual Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python scripts/setup_project.py --install-deps --install-playwright
python scripts/run_web_app.py --port 8000
```

Check the installation:

```powershell
python scripts/doctor.py
```

### Optional Local LLM Setup

Ollama is optional. The application still works without it; only LLM suggestions are disabled.

Windows helper:

```bat
setup_ollama_windows.cmd
```

Manual command:

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

### Web App Features

The web interface contains:

- `Dashboard`: dataset and graph overview;
- `Thesis Search`: search, filters, paginated results, thesis detail profile;
- `Concepts`: concept index and connected theses;
- `Dataset`: complete extracted dataset, CSV copy, CSV download;
- `Ask / RAG`: local question answering, cited sources, visible relevance scores, show-all relevant-source pagination, source profiles, PDF links;
- `Import PDFs`: upload one PDF or several PDFs together, review extracted metadata, approve or discard drafts.

### Import Workflow

New PDFs should be added through the web UI, not by manually editing the database.

Workflow:

1. Open `Import PDFs`.
2. Select one PDF or multiple PDFs in the same file picker.
3. The system stages each file and creates one review draft per new PDF.
4. The system checks duplicates by PDF hash.
5. The user reviews title, year, master level, track, keywords, concepts, use case, methodology, and abstract.
6. Optional: ask local Ollama for suggestions.
7. `Apply LLM suggestions` only fills the review form.
8. `Approve` inserts the thesis into SQLite.
9. The CSV export, Knowledge Graph, and RAG embeddings are rebuilt together.
10. `Discard` removes the draft without changing the main dataset.

### Data Model

The project stores one row per thesis.

Main fields:

```text
thesis_id
file_name
pages_count
year
title
master_level
track
abstract
keywords
concepts
use_case
methodology
extraction_confidence
needs_review
extraction_notes
```

The `abstract` field is useful when present, but it is not mandatory because many theses do not contain a comparable abstract section.

Track normalization:

- `apprentissage` means apprenticeship track;
- every non-apprenticeship thesis is treated as `classique`.

### Knowledge Graph

The graph is built from validated metadata.

Node types:

- `Thesis`
- `Concept`
- `Keyword`
- `UseCase`
- `Methodology`
- `Year`
- `MasterLevel`
- `Track`

Main relations:

- `Thesis -> HAS_CONCEPT -> Concept`
- `Thesis -> HAS_KEYWORD -> Keyword`
- `Thesis -> HAS_USE_CASE -> UseCase`
- `Thesis -> USES_METHODOLOGY -> Methodology`
- `Thesis -> SUBMITTED_IN -> Year`
- `Thesis -> HAS_MASTER_LEVEL -> MasterLevel`
- `Thesis -> HAS_TRACK -> Track`
- `Thesis -> RELATED_TO -> Thesis`

Graph files are generated locally under `data/graph/`.

### RAG

The first RAG version is metadata-based, not full-PDF chunk-based.

For each thesis, the system builds one retrieval text from:

- title;
- concepts;
- keywords;
- use case;
- methodology;
- abstract / introduction / conclusion when available.

The web app can:

- answer with local retrieval only;
- optionally use Ollama for answer generation;
- show cited thesis sources with relevance scores;
- treat `Max results` / `top_k` as a maximum, not a required result count;
- filter weak matches with a default relevance threshold of `MIAGE_RAG_MIN_SCORE=0.30`;
- show all relevant ranked sources above the threshold with 20 results per page;
- open each source as an in-app thesis profile;
- open the associated PDF from the profile.

This means rare questions can return fewer sources than requested. For example, if the user asks for 5 sources but only 1 thesis is relevant enough, the UI shows only that one thesis instead of filling the answer with weak matches. The score shown in the UI is a ranking signal, not a thesis quality grade.

For domain questions such as medical/health queries, the backend uses stronger evidence from title plus abstract when possible, so noisy old concepts or keywords are not enough by themselves.

### Data Policy

Private thesis PDFs and generated local data are not committed to GitHub.

Ignored by Git:

- `data/*`, except `data/README.md`;
- `output/`;
- `.env`;
- `.venv/`;
- caches and Python bytecode.

A fresh clone starts with an empty local database. Add PDFs through the UI.

### Tests And Validation

Run all tests:

```powershell
python -m pytest
```

Validate local data, graph, and embeddings:

```powershell
python scripts/validate_dataset.py
python scripts/validate_knowledge_graph.py
python scripts/validate_embeddings.py
```

Run RAG benchmarks:

```powershell
python scripts/evaluate_rag_benchmark.py
python scripts/evaluate_rag_comprehensive.py
```

### Important Commands

```powershell
python scripts/setup_project.py
python scripts/run_web_app.py --port 8000
python scripts/doctor.py
python scripts/run_pipeline.py
python scripts/build_knowledge_graph.py
python scripts/build_embeddings.py
python scripts/query_knowledge_graph.py summary
```

### Documentation

- `docs/quickstart.md`
- `docs/web_app.md`
- `docs/knowledge_graph_schema.md`
- `docs/knowledge_graph_queries.md`
- `docs/rag.md`

---

## Francais

### Vue D'ensemble

Ce projet est une application web locale, gratuite et sans cloud pour gerer des memoires MIAGE au format PDF.

Elle permet de:

- importer un ou plusieurs PDF depuis l'interface web;
- extraire et verifier des metadonnees structurees;
- stocker une ligne validee par memoire dans SQLite;
- exporter le jeu de donnees complet en CSV;
- construire un graphe de connaissances local;
- construire des embeddings locaux pour la recherche RAG;
- poser des questions sur les metadonnees des memoires avec des sources citees;
- afficher les sources RAG pertinentes avec score et pagination;
- ouvrir un profil de memoire dans l'application, puis ouvrir le PDF source;
- utiliser optionnellement un modele Ollama local pour proposer des corrections.

Aucune API payante n'est necessaire. Ollama est optionnel et fonctionne localement.

### Stack Technique

- Python 3.11+
- FastAPI
- SQLite
- HTML, CSS et JavaScript statiques
- pypdf / PyMuPDF / pytesseract pour l'extraction PDF et l'OCR de secours
- embeddings locaux deterministes pour la premiere version RAG
- modele Ollama optionnel: `qwen2.5:7b`

### Demarrage Rapide Sous Windows

Apres avoir clone le depot, lancer:

```bat
setup_windows.cmd
```

Ce script installe les dependances Python, installe les navigateurs Playwright, initialise la base locale, cree les sorties vides du graphe/RAG, puis propose d'installer le modele Ollama optionnel.

Demarrer l'application:

```bat
run_app_windows.cmd
```

Ouvrir:

```text
http://127.0.0.1:8000
```

### Installation Manuelle

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python scripts/setup_project.py --install-deps --install-playwright
python scripts/run_web_app.py --port 8000
```

Verifier l'installation:

```powershell
python scripts/doctor.py
```

### Installation Optionnelle Du LLM Local

Ollama est optionnel. L'application fonctionne sans Ollama; seules les suggestions LLM sont indisponibles.

Script Windows:

```bat
setup_ollama_windows.cmd
```

Commande manuelle:

```powershell
python scripts/setup_ollama.py --install --pull --model qwen2.5:7b
```

### Fonctionnalites De L'interface Web

L'interface contient:

- `Dashboard`: vue d'ensemble du jeu de donnees et du graphe;
- `Thesis Search`: recherche, filtres, resultats pagines, profil de memoire;
- `Concepts`: index des concepts et memoires connectes;
- `Dataset`: table complete, copie CSV, telechargement CSV;
- `Ask / RAG`: questions locales, sources citees, scores de pertinence visibles, pagination des sources pertinentes, profils des sources, liens PDF;
- `Import PDFs`: import d'un PDF ou de plusieurs PDF ensemble, verification des metadonnees, validation ou suppression des brouillons.

### Workflow D'import

Les nouveaux PDF doivent etre ajoutes depuis l'interface web.

Workflow:

1. Ouvrir `Import PDFs`.
2. Selectionner un PDF ou plusieurs PDF dans la meme fenetre de selection.
3. Le systeme place chaque fichier en staging et cree un brouillon de verification.
4. Le systeme detecte les doublons avec le hash du PDF.
5. L'utilisateur verifie le titre, l'annee, le niveau, le parcours, les mots-cles, les concepts, le cas d'usage, la methodologie et le resume.
6. Optionnel: demander des suggestions a Ollama local.
7. `Apply LLM suggestions` remplit seulement le formulaire.
8. `Approve` insere le memoire dans SQLite.
9. Le CSV, le graphe de connaissances et les embeddings RAG sont reconstruits ensemble.
10. `Discard` supprime le brouillon sans modifier le jeu de donnees principal.

### Modele De Donnees

Le projet stocke une ligne par memoire.

Champs principaux:

```text
thesis_id
file_name
pages_count
year
title
master_level
track
abstract
keywords
concepts
use_case
methodology
extraction_confidence
needs_review
extraction_notes
```

Le champ `abstract` est utile lorsqu'il existe, mais il n'est pas obligatoire car beaucoup de memoires n'ont pas de section resume comparable.

Normalisation du parcours:

- `apprentissage` correspond au parcours en apprentissage;
- tout memoire qui n'est pas en apprentissage est considere comme `classique`.

### Graphe De Connaissances

Le graphe est construit a partir des metadonnees validees.

Types de noeuds:

- `Thesis`
- `Concept`
- `Keyword`
- `UseCase`
- `Methodology`
- `Year`
- `MasterLevel`
- `Track`

Relations principales:

- `Thesis -> HAS_CONCEPT -> Concept`
- `Thesis -> HAS_KEYWORD -> Keyword`
- `Thesis -> HAS_USE_CASE -> UseCase`
- `Thesis -> USES_METHODOLOGY -> Methodology`
- `Thesis -> SUBMITTED_IN -> Year`
- `Thesis -> HAS_MASTER_LEVEL -> MasterLevel`
- `Thesis -> HAS_TRACK -> Track`
- `Thesis -> RELATED_TO -> Thesis`

Les fichiers du graphe sont generes localement dans `data/graph/`.

### RAG

La premiere version RAG utilise les metadonnees, pas des chunks du PDF complet.

Pour chaque memoire, le systeme construit un texte de recherche avec:

- le titre;
- les concepts;
- les mots-cles;
- le cas d'usage;
- la methodologie;
- le resume / l'introduction / la conclusion lorsqu'ils existent.

L'application peut:

- repondre avec la recherche locale;
- utiliser Ollama de maniere optionnelle;
- citer les memoires sources avec un score de pertinence;
- traiter `Max results` / `top_k` comme un maximum, pas comme un nombre obligatoire;
- filtrer les correspondances faibles avec le seuil par defaut `MIAGE_RAG_MIN_SCORE=0.30`;
- afficher toutes les sources pertinentes au-dessus du seuil avec 20 resultats par page;
- ouvrir chaque source dans un profil integre a l'application;
- ouvrir le PDF associe depuis le profil.

Ainsi, une question rare peut retourner moins de sources que le nombre demande. Si l'utilisateur demande 5 sources mais qu'un seul memoire est suffisamment pertinent, l'interface affiche seulement ce memoire au lieu d'ajouter des correspondances faibles. Le score affiche est un signal de classement, pas une note de qualite du memoire.

Pour les questions de domaine, par exemple medical/sante, le backend utilise si possible des preuves plus fortes venant du titre et du resume. Des anciens concepts ou mots-cles bruites ne suffisent donc pas a eux seuls.

### Politique Des Donnees

Les PDF prives et les donnees locales generees ne sont pas envoyes sur GitHub.

Ignores par Git:

- `data/*`, sauf `data/README.md`;
- `output/`;
- `.env`;
- `.venv/`;
- caches et bytecode Python.

Un clone propre demarre avec une base locale vide. Les PDF doivent etre ajoutes depuis l'interface.

### Tests Et Validation

Lancer tous les tests:

```powershell
python -m pytest
```

Valider les donnees locales, le graphe et les embeddings:

```powershell
python scripts/validate_dataset.py
python scripts/validate_knowledge_graph.py
python scripts/validate_embeddings.py
```

Lancer les benchmarks RAG:

```powershell
python scripts/evaluate_rag_benchmark.py
python scripts/evaluate_rag_comprehensive.py
```

### Commandes Importantes

```powershell
python scripts/setup_project.py
python scripts/run_web_app.py --port 8000
python scripts/doctor.py
python scripts/run_pipeline.py
python scripts/build_knowledge_graph.py
python scripts/build_embeddings.py
python scripts/query_knowledge_graph.py summary
```

### Documentation

- `docs/quickstart.md`
- `docs/web_app.md`
- `docs/knowledge_graph_schema.md`
- `docs/knowledge_graph_queries.md`
- `docs/rag.md`
