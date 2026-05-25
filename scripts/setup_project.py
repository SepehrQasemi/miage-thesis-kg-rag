import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from common.db import connect, init_schema
from common.paths import (
    cache_dir,
    db_path,
    graph_dir,
    processed_dir,
    raw_pdf_dir,
    reports_dir,
    staging_dir,
)
from common.pipeline_outputs import rebuild_graph_outputs


DATA_DIRECTORIES = [
    raw_pdf_dir,
    processed_dir,
    reports_dir,
    graph_dir,
    cache_dir,
    staging_dir,
]


def run(command: list[str]) -> None:
    print(">", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def create_directories() -> None:
    for directory_factory in DATA_DIRECTORIES:
        directory_factory().mkdir(parents=True, exist_ok=True)
    (ROOT / "output").mkdir(parents=True, exist_ok=True)


def ensure_env_file() -> None:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if env_path.exists() or not example_path.exists():
        return
    shutil.copy2(example_path, env_path)
    print(f"Created {env_path.relative_to(ROOT)} from .env.example")


def initialize_database(reset: bool) -> None:
    database = db_path()
    if reset and database.exists():
        database.unlink()
    with connect(database) as conn:
        init_schema(conn)
    rebuild_graph_outputs(database)
    print(f"Database ready: {database}")


def raw_pdf_count() -> int:
    return len(list(raw_pdf_dir().glob("*.pdf")))


def install_dependencies() -> None:
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def install_playwright_browser() -> None:
    run([sys.executable, "-m", "playwright", "install", "chromium"])


def build_existing_data(no_ocr: bool) -> None:
    if raw_pdf_count() == 0:
        print("No PDFs found in data/raw/theses_pdf. Skipping extraction pipeline.")
        return
    command = [sys.executable, "scripts/run_pipeline.py"]
    if no_ocr:
        command.append("--no-ocr")
    run(command)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a fresh local checkout for running the MIAGE thesis app.")
    parser.add_argument("--install-deps", action="store_true", help="Install Python dependencies from requirements.txt.")
    parser.add_argument("--install-playwright", action="store_true", help="Install Playwright Chromium for UI tests.")
    parser.add_argument("--install-ollama", action="store_true", help="Install Ollama if missing, then pull the configured model.")
    parser.add_argument("--ollama-model", default="qwen2.5:7b", help="Ollama model to pull when --install-ollama is used.")
    parser.add_argument("--reset-db", action="store_true", help="Delete and recreate the local SQLite database.")
    parser.add_argument("--build-data", action="store_true", help="Process PDFs already present in data/raw/theses_pdf.")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR when --build-data is used.")
    args = parser.parse_args()

    create_directories()
    ensure_env_file()

    if args.install_deps:
        install_dependencies()
    if args.install_playwright:
        install_playwright_browser()
    if args.install_ollama:
        run([sys.executable, "scripts/setup_ollama.py", "--install", "--pull", "--model", args.ollama_model])

    initialize_database(reset=args.reset_db)

    if args.build_data:
        build_existing_data(no_ocr=args.no_ocr)

    print("\nSetup complete.")
    print("Run the app:")
    print("  python scripts/run_web_app.py --port 8000")
    print("Open:")
    print("  http://127.0.0.1:8000")
    if raw_pdf_count() == 0:
        print("\nNo raw PDFs were found. Use the Import PDF screen to add theses.")
    else:
        print(f"\nRaw PDFs available: {raw_pdf_count()}")


if __name__ == "__main__":
    main()
