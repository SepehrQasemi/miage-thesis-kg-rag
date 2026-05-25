import importlib.util
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from common.paths import db_path, graph_dir, load_env_file, raw_pdf_dir


REQUIRED_IMPORTS = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pypdf": "pypdf",
    "fitz": "PyMuPDF",
    "rapidocr_onnxruntime": "rapidocr-onnxruntime",
    "cv2": "opencv-python",
    "numpy": "numpy",
    "yaml": "PyYAML",
    "playwright": "playwright",
    "multipart": "python-multipart",
}


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def check_python() -> bool:
    version = sys.version_info
    if version >= (3, 11):
        ok(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    fail(f"Python 3.11+ required, found {version.major}.{version.minor}.{version.micro}")
    return False


def check_imports() -> bool:
    good = True
    for module, package in REQUIRED_IMPORTS.items():
        if importlib.util.find_spec(module):
            ok(f"Dependency import works: {module}")
        else:
            fail(f"Missing dependency: {package}")
            good = False
    return good


def check_database() -> bool:
    database = db_path()
    if not database.exists():
        fail(f"Database missing: {database}")
        return False
    try:
        with sqlite3.connect(database) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            required = {"documents", "graph_nodes", "graph_edges"}
            missing = required - tables
            if missing:
                fail(f"Database schema missing tables: {', '.join(sorted(missing))}")
                return False
            doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE status = 'active'").fetchone()[0]
        ok(f"Database schema ready; active documents: {doc_count}")
        return True
    except sqlite3.Error as exc:
        fail(f"Database error: {exc}")
        return False


def check_files() -> bool:
    raw_count = len(list(raw_pdf_dir().glob("*.pdf")))
    if raw_count:
        ok(f"Raw PDFs found: {raw_count}")
    else:
        warn("No raw PDFs found. The app can still run; add PDFs from the Import PDF screen.")

    required_graph_files = [graph_dir() / "nodes.csv", graph_dir() / "edges.csv", graph_dir() / "knowledge_graph.json"]
    missing = [path for path in required_graph_files if not path.exists()]
    if missing:
        fail("Missing graph output files. Run: python scripts/setup_project.py")
        return False
    ok("Graph output files exist")
    return True


def check_ollama() -> None:
    load_env_file()
    expected_model = os.environ.get("MIAGE_OLLAMA_MODEL", "qwen2.5:7b")
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
                models = {
                    str(item.get(key))
                    for item in data.get("models", [])
                    for key in ("name", "model")
                    if item.get(key)
                }
                if expected_model in models:
                    ok(f"Ollama API reachable; model installed: {expected_model}")
                else:
                    warn(f"Ollama API reachable, but model '{expected_model}' is missing. Run: python scripts/setup_ollama.py --pull")
                return
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass
    warn("Ollama API not reachable. LLM suggestions are optional; manual import review still works.")


def main() -> None:
    print("MIAGE Thesis Knowledge Graph - environment doctor\n")
    checks = [
        check_python(),
        check_imports(),
        check_database(),
        check_files(),
    ]
    check_ollama()
    if all(checks):
        print("\nDoctor result: ready")
        raise SystemExit(0)
    print("\nDoctor result: setup required")
    print("Try:")
    print("  python scripts/setup_project.py --install-deps")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
