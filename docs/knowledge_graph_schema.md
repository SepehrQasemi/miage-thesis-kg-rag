# Knowledge Graph Schema

This document describes the first permanent Knowledge Graph layer built from the extracted MIAGE thesis metadata.

The graph is intentionally local and simple. It does not require a paid API, a cloud database, or a Neo4j server. The canonical graph is stored in SQLite and exported as CSV/JSON so it can later be imported into NetworkX, Neo4j, a web UI, or a RAG pipeline.

## Source

The graph is built from active rows in:

`data/app.sqlite`

Main source table:

`documents`

The exported graph files are:

- `data/graph/nodes.csv`
- `data/graph/edges.csv`
- `data/graph/knowledge_graph.json`

The graph is also stored in SQLite tables:

- `graph_nodes`
- `graph_edges`

## Node Types

| Node type | Meaning | Stable ID example |
|---|---|---|
| `Thesis` | One thesis PDF/document | `thesis:thesis_0001` |
| `Concept` | Normalized technical/business concept | `concept:machine-learning` |
| `Keyword` | Extracted keyword or key phrase | `keyword:business-intelligence` |
| `UseCase` | Use-case category | `usecase:sante-aide-au-diagnostic` |
| `Methodology` | Methodology category | `methodology:revue-de-litterature-etat-de-l-art` |
| `Year` | Thesis year | `year:2025` |
| `MasterLevel` | `M1`, `M2`, or `N/A` | `masterlevel:m1` |
| `Track` | `apprentissage`, `classique`, or `N/A` | `track:apprentissage` |

Each node has:

- `node_id`
- `node_type`
- `label`
- `slug`
- `source`
- `properties_json`

## Edge Types

| Edge type | Source | Target | Meaning |
|---|---|---|---|
| `HAS_CONCEPT` | `Thesis` | `Concept` | Thesis contains a normalized concept |
| `HAS_KEYWORD` | `Thesis` | `Keyword` | Thesis contains an extracted keyword |
| `HAS_USE_CASE` | `Thesis` | `UseCase` | Thesis belongs to a use-case category |
| `USES_METHODOLOGY` | `Thesis` | `Methodology` | Thesis uses a methodology category |
| `SUBMITTED_IN` | `Thesis` | `Year` | Thesis was submitted in a given year |
| `HAS_MASTER_LEVEL` | `Thesis` | `MasterLevel` | Thesis belongs to M1/M2 |
| `HAS_TRACK` | `Thesis` | `Track` | Thesis belongs to apprenticeship/classical track |
| `RELATED_TO` | `Thesis` | `Thesis` | Inferred relation based on shared concepts |

`RELATED_TO` edges are inferred and undirected by interpretation. They are stored once, from the lower thesis ID to the higher thesis ID, to avoid duplicates.

## Normalization Rules

The first version uses deterministic local normalization:

- labels are stripped and whitespace-normalized;
- entity IDs are ASCII slugs;
- known concept aliases are canonicalized, for example `IA` becomes `intelligence artificielle`;
- track labels are normalized to `apprentissage` or `classique`; legacy/source labels such as `mixte` are represented as `classique`;
- raw PDF files are never modified;
- manual corrections remain traceable in `data/manual_overrides/theses_metadata.csv`.

## Validation

The graph validation step checks:

- one `Thesis` node per active document;
- unique node IDs and edge IDs;
- no dangling edges;
- valid node types and edge types;
- valid JSON properties;
- every thesis has the required metadata edges;
- graph CSV row counts match the SQLite graph tables.

Validation outputs:

- `data/reports/knowledge_graph_validation.csv`
- `data/reports/knowledge_graph_validation_summary.json`

Analysis outputs:

- `data/reports/knowledge_graph_summary.json`
- `data/reports/knowledge_graph_node_metrics.csv`
- `data/reports/knowledge_graph_related_theses.csv`

## Commands

Build the graph:

```powershell
python scripts/build_knowledge_graph.py
```

Validate the graph:

```powershell
python scripts/validate_knowledge_graph.py
```

Run the full extraction and graph pipeline:

```powershell
python scripts/run_pipeline.py
```
