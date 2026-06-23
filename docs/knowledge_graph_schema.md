# Knowledge Graph Schema

## Source Of Truth

Neo4j is the source of truth for the Knowledge Graph.

Generated CSV and JSON files in `data/graph` are exports for inspection, reporting, and backup. They are not the runtime database.

## Node Labels

All graph nodes have the shared label `MiageNode`.

Specific labels:

- `Thesis`
- `Concept`
- `Keyword`
- `UseCase`
- `Methodology`
- `Year`
- `MasterLevel`
- `Track`
- `ImportDraft`

`ImportDraft` is used for pending upload review. It is not part of the public thesis graph map.

## Thesis Properties

`Thesis` nodes store the approved metadata:

- `thesis_id`
- `file_name`
- `file_path`
- `sha256`
- `pages_count`
- `cover_text`
- `abstract`
- `introduction`
- `conclusion`
- `year`
- `title`
- `master_level`
- `track`
- `keywords`
- `concepts`
- `use_case`
- `methodology`
- `extraction_confidence`
- `needs_review`
- `status`
- `extraction_notes`
- `processed_at`
- `created_at`
- `updated_at`

## Entity Properties

Entity nodes use:

- `node_id`
- `node_type`
- `label`
- `slug`
- `source`
- `properties_json`

## Relationship Types

From `Thesis` to entity nodes:

- `HAS_CONCEPT`
- `HAS_KEYWORD`
- `HAS_USE_CASE`
- `USES_METHODOLOGY`
- `SUBMITTED_IN`
- `HAS_MASTER_LEVEL`
- `HAS_TRACK`

Between theses:

- `RELATED_TO`

`RELATED_TO` is inferred when theses share enough concepts. The default threshold is 3 shared concepts.

## Relationship Properties

Relationships store:

- `edge_id`
- `source_id`
- `target_id`
- `edge_type`
- `weight`
- `source`
- `properties_json`

For `RELATED_TO`, `properties_json` includes:

- `shared_concept_count`
- `shared_concepts`
- `direction`

## Constraints And Indexes

The setup/doctor scripts create:

- unique `MiageNode.node_id`;
- unique `Thesis.thesis_id`;
- unique `ImportDraft.draft_id`;
- index on `Thesis.sha256`;
- index on `ImportDraft.sha256`;
- index on `ImportDraft.status`;
- index on `MiageNode.node_type`;
- index on `MiageNode.slug`.

## Rebuild Strategy

When a thesis is approved or when graph maintenance scripts run:

1. Approved thesis rows are read from Neo4j.
2. The in-memory graph model is rebuilt.
3. Neo4j `MiageNode` nodes and relationships are replaced.
4. Import drafts are preserved.
5. CSV, JSON, and report outputs are regenerated.

This keeps the graph deterministic and avoids partial relationship drift.

## Validation

Use:

```powershell
python scripts/validate_knowledge_graph.py
```

The validator reads nodes and relationships directly from Neo4j and checks:

- valid node types;
- valid relationship types;
- unique node IDs;
- unique edge IDs;
- dangling relationship endpoints;
- required thesis relationships;
- CSV export row counts.
