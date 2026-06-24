# Knowledge Graph Queries

## Query Layer

The application queries Neo4j through `Neo4jGraphQueryService`.

This same service is used by:

- Dashboard;
- Knowledge Graph map;
- Thesis Search;
- Concepts;
- thesis profiles;
- Dataset export;
- RAG source retrieval;
- CLI query scripts.

## CLI Examples

Summary:

```powershell
python scripts/query_knowledge_graph.py summary
```

Top concepts:

```powershell
python scripts/query_knowledge_graph.py top --type Concept --limit 20
```

Thesis profile:

```powershell
python scripts/query_knowledge_graph.py profile thesis_0010
```

Similar theses:

```powershell
python scripts/query_knowledge_graph.py similar thesis_0010 --limit 10
```

Concept overview:

```powershell
python scripts/query_knowledge_graph.py concept "intelligence artificielle"
```

Filtered search:

```powershell
python scripts/query_knowledge_graph.py search --concept "sante" --methodology "classification" --match all
```

Export query results:

```powershell
python scripts/query_knowledge_graph.py search --concept "cybersecurite" --csv output/cybersecurity.csv
```

## Web API

Main graph-backed endpoints:

- `GET /api/summary`
- `GET /api/graph/map`
- `GET /api/theses`
- `GET /api/theses/{thesis_id}`
- `GET /api/concepts`
- `POST /api/rag/search`
- `POST /api/rag/answer`

## Search Semantics

Graph search supports:

- `concept`
- `keyword`
- `use_case`
- `methodology`
- `year`
- `master_level`
- `track`
- `match=all`
- `match=any`
- `limit`
- `offset`

`match=all` requires all filters to match.

`match=any` requires at least one filter to match and ranks by matched filter count and score.

## Graph Map

`GET /api/graph/map` supports two rendering modes:

- without `node_types`, it returns a small capped compatibility subgraph;
- with `node_types`, it returns all thesis nodes and only the requested metadata node types.

Example:

```text
GET /api/graph/map?node_types=Concept,Year,UseCase
```

Supported `node_types` values are:

- `Concept`
- `Keyword`
- `UseCase`
- `Methodology`
- `Year`
- `MasterLevel`
- `Track`

When `node_types` is present, `stats.thesis_scope` is `all`, `stats.thesis_limit` is `null`, and `stats.selected_node_types` lists the active categories. This is the mode used by the web interface.

This makes the browser view scalable: all theses remain available, while the user decides whether to analyze concepts, years, use cases, methods, levels, tracks, or keywords.

The full graph remains available in Neo4j and through CLI/API queries.

## Dataset Export

Use:

```powershell
python scripts/export_csv.py
```

or download CSV from the `Dataset` page.

Both paths read active thesis rows from Neo4j.
