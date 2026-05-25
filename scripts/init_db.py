import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.db import connect, init_schema
from common.paths import db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the SQLite database.")
    parser.add_argument("--reset", action="store_true", help="Delete the existing database before creating it.")
    args = parser.parse_args()

    path = db_path()
    if args.reset and path.exists():
        path.unlink()

    with connect(path) as conn:
        init_schema(conn)

    print(f"Database initialized: {path}")


if __name__ == "__main__":
    main()
