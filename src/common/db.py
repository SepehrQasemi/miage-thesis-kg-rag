import sqlite3
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    pages_count INTEGER,

    cover_text TEXT,
    abstract TEXT,
    introduction TEXT,
    conclusion TEXT,

    year INTEGER,
    title TEXT,
    master_level TEXT,
    track TEXT,
    keywords TEXT,
    concepts TEXT,
    use_case TEXT,
    methodology TEXT,

    extraction_confidence REAL DEFAULT 0,
    needs_review INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    extraction_notes TEXT,

    processed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_thesis_id ON documents(thesis_id);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);
CREATE INDEX IF NOT EXISTS idx_documents_master_level ON documents(master_level);
CREATE INDEX IF NOT EXISTS idx_documents_needs_review ON documents(needs_review);

CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL,
    slug TEXT NOT NULL,
    source TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_id) REFERENCES graph_nodes(node_id),
    FOREIGN KEY(target_id) REFERENCES graph_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_slug ON graph_nodes(slug);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(edge_type);

CREATE TABLE IF NOT EXISTS document_embeddings (
    thesis_id TEXT PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    embedding_text TEXT NOT NULL,
    embedding_vector_json TEXT NOT NULL,
    embedding_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(thesis_id) REFERENCES documents(thesis_id)
);

CREATE INDEX IF NOT EXISTS idx_document_embeddings_model ON document_embeddings(embedding_model);
"""


def connect(db_file: Path) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
