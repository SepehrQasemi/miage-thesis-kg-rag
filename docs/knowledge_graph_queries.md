# Knowledge Graph Queries

This document explains how to query the local Knowledge Graph after it has been built.

The query layer reads from the SQLite graph tables:

- `graph_nodes`
- `graph_edges`

It is intentionally local and free. It does not require Neo4j, an API key, or a cloud service.

## Basic Commands

Show graph counts:

```powershell
python scripts/query_knowledge_graph.py summary
```

Show the most frequent concepts:

```powershell
python scripts/query_knowledge_graph.py top --type Concept --limit 10
```

Show the most frequent use cases:

```powershell
python scripts/query_knowledge_graph.py top --type UseCase --limit 10
```

## Thesis Profile

Show the graph profile of one thesis:

```powershell
python scripts/query_knowledge_graph.py profile thesis_0004
```

This returns the thesis metadata and its connected concepts and keywords.

## Similar Theses

Find theses related to one thesis:

```powershell
python scripts/query_knowledge_graph.py similar thesis_0006 --limit 10
```

Similarity is based on shared normalized concepts. The `shared_concepts` column explains why two theses are considered related.

## Concept Query

Find theses connected to a concept:

```powershell
python scripts/query_knowledge_graph.py concept "machine learning" --limit 10
```

This also shows other concepts that frequently appear with the selected concept.

## Entity Query

List theses connected to one entity node:

```powershell
python scripts/query_knowledge_graph.py entity --type Year --label 2024 --limit 20
python scripts/query_knowledge_graph.py entity --type MasterLevel --label M2 --limit 20
python scripts/query_knowledge_graph.py entity --type Track --label apprentissage --limit 20
```

Supported entity types:

- `Concept`
- `Keyword`
- `UseCase`
- `Methodology`
- `Year`
- `MasterLevel`
- `Track`

## Multi-Filter Search

Find theses that match all filters:

```powershell
python scripts/query_knowledge_graph.py search --concept "machine learning" --concept sante --match all --limit 20
```

Find theses that match at least one filter:

```powershell
python scripts/query_knowledge_graph.py search --concept "machine learning" --concept blockchain --match any --limit 20
```

Combine structural filters:

```powershell
python scripts/query_knowledge_graph.py search --concept "machine learning" --year 2024 --master-level M2 --track apprentissage --match all
```

## JSON and CSV Output

Most commands support JSON output:

```powershell
python scripts/query_knowledge_graph.py similar thesis_0006 --json
```

Commands returning rows can also write CSV:

```powershell
python scripts/query_knowledge_graph.py similar thesis_0006 --csv data/reports/query_similar_thesis_0006.csv
```

## Why This Matters

The query layer is the bridge between the graph construction phase and the future application.

It already supports the main use cases needed for the next stages:

- thesis recommendation;
- concept-based search;
- filtering by year, level, track, use case, and methodology;
- structured retrieval for a future RAG pipeline;
- backend logic for a future user interface.
