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

`GET /api/graph/map` supports three rendering modes:

- without `node_types`, it returns a small capped compatibility subgraph;
- with `node_types`, it returns the requested visual categories. Include `Thesis` when thesis nodes should be drawn.
- with `node_types` and a metadata `focus_type`, it returns direct metadata-to-metadata relations. If `Thesis` is also selected, it also draws the thesis evidence nodes and their original thesis-to-metadata edges.

Example:

```text
GET /api/graph/map?node_types=Concept,Year,UseCase
```

Metadata-centered direct relation example:

```text
GET /api/graph/map?node_types=Concept,Year,Keyword&focus_type=Concept
```

Supported `node_types` values are:

- `Concept`
- `Thesis`
- `Keyword`
- `UseCase`
- `Methodology`
- `Year`
- `MasterLevel`
- `Track`

When `node_types` is present and `focus_type=Thesis`, `stats.thesis_scope` is `all`, `stats.thesis_limit` is `null`, and `stats.selected_node_types` lists the active categories.

When `focus_type` is a metadata type such as `Concept`, `stats.graph_mode` is `metadata_focus`. If `Thesis` is not selected, `stats.thesis_scope` is `hidden` and the graph only draws `DIRECT_RELATION` edges. If `Thesis` is selected, `stats.thesis_scope` is `included` and the response also contains the original thesis-to-metadata edges, such as `HAS_CONCEPT` and `SUBMITTED_IN`. Direct edges are derived from thesis evidence. For example, a Concept -> Year edge with weight 4 means four theses connect that concept to that year.

This makes the browser view scalable: all theses remain available, while the user decides whether to analyze concepts, years, use cases, methods, levels, tracks, or keywords.

The full graph remains available in Neo4j and through CLI/API queries.

## Dataset Export

Use:

```powershell
python scripts/export_csv.py
```

or download CSV from the `Dataset` page.

Both paths read active thesis rows from Neo4j.
