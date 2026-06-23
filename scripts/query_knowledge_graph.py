import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from graph.neo4j_store import Neo4jGraphQueryService


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        print("No results.")
        return
    widths = {
        column: max(len(column), *(len(format_cell(row.get(column, ""))) for row in rows))
        for column in columns
    }
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    print(header)
    print(separator)
    for row in rows:
        print(" | ".join(format_cell(row.get(column, "")).ljust(widths[column]) for column in columns))


def format_cell(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    return text[:137] + "..." if len(text) > 140 else text


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_cell(row.get(column, "")) for column in columns})


def output_rows(rows: list[dict[str, Any]], columns: list[str], output: str, csv_path: str | None = None) -> None:
    if output == "json":
        print_json(rows)
    else:
        print_table(rows, columns)
    if csv_path:
        write_csv(Path(csv_path), rows)
        print(f"\nCSV written: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the Neo4j MIAGE thesis Knowledge Graph.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary_parser = subparsers.add_parser("summary", help="Show graph node and edge counts.")
    summary_parser.add_argument("--json", action="store_true", help="Print raw JSON.")

    top_parser = subparsers.add_parser("top", help="Show top graph nodes by incoming edges.")
    top_parser.add_argument("--type", required=True, choices=["Concept", "Keyword", "UseCase", "Methodology", "Year", "MasterLevel", "Track"])
    top_parser.add_argument("--limit", type=int, default=20)
    top_parser.add_argument("--json", action="store_true")
    top_parser.add_argument("--csv", default=None, help="Optional CSV output path.")

    profile_parser = subparsers.add_parser("profile", help="Show a thesis graph profile.")
    profile_parser.add_argument("thesis_id")
    profile_parser.add_argument("--json", action="store_true")

    similar_parser = subparsers.add_parser("similar", help="Find theses related to a thesis.")
    similar_parser.add_argument("thesis_id")
    similar_parser.add_argument("--limit", type=int, default=10)
    similar_parser.add_argument("--json", action="store_true")
    similar_parser.add_argument("--csv", default=None, help="Optional CSV output path.")

    concept_parser = subparsers.add_parser("concept", help="Show theses and related concepts for a concept.")
    concept_parser.add_argument("label")
    concept_parser.add_argument("--limit", type=int, default=10)
    concept_parser.add_argument("--json", action="store_true")

    entity_parser = subparsers.add_parser("entity", help="List theses connected to one entity node.")
    entity_parser.add_argument("--type", required=True, choices=["Concept", "Keyword", "UseCase", "Methodology", "Year", "MasterLevel", "Track"])
    entity_parser.add_argument("--label", required=True)
    entity_parser.add_argument("--limit", type=int, default=20)
    entity_parser.add_argument("--json", action="store_true")
    entity_parser.add_argument("--csv", default=None, help="Optional CSV output path.")

    search_parser = subparsers.add_parser("search", help="Search theses by graph filters.")
    search_parser.add_argument("--concept", action="append", default=[])
    search_parser.add_argument("--keyword", action="append", default=[])
    search_parser.add_argument("--use-case", default=None)
    search_parser.add_argument("--methodology", default=None)
    search_parser.add_argument("--year", default=None)
    search_parser.add_argument("--master-level", default=None)
    search_parser.add_argument("--track", default=None)
    search_parser.add_argument("--match", choices=["all", "any"], default="all")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--json", action="store_true")
    search_parser.add_argument("--csv", default=None, help="Optional CSV output path.")

    args = parser.parse_args()
    service = Neo4jGraphQueryService()
    service.verify_connectivity()

    try:
        if args.command == "summary":
            summary = service.summary()
            if args.json:
                print_json(summary)
            else:
                print("Nodes:", summary["nodes_total"])
                print("Edges:", summary["edges_total"])
                print("\nNode counts")
                print_table([{"type": k, "count": v} for k, v in summary["node_counts"].items()], ["type", "count"])
                print("\nEdge counts")
                print_table([{"type": k, "count": v} for k, v in summary["edge_counts"].items()], ["type", "count"])

        elif args.command == "top":
            rows = service.top_nodes(args.type, limit=args.limit)
            output_rows(rows, ["node_id", "label", "incoming_edges"], "json" if args.json else "table", args.csv)

        elif args.command == "profile":
            profile = service.thesis_profile(args.thesis_id)
            if args.json:
                print_json(profile)
            else:
                print(f"{profile['thesis_id']} - {profile['title']}")
                print(f"Year: {profile['year']} | Level: {profile['master_level']} | Track: {profile['track']}")
                print(f"Use case: {profile['use_case']}")
                print(f"Methodology: {profile['methodology']}")
                for key in ["concepts", "keywords"]:
                    items = profile["graph"].get(key, [])
                    print(f"\n{key.title()}:")
                    print_table(items[:20], ["label", "weight"])

        elif args.command == "similar":
            rows = service.similar_theses(args.thesis_id, limit=args.limit)
            output_rows(
                rows,
                ["thesis_id", "weight", "shared_concept_count", "shared_concepts", "year", "master_level", "title"],
                "json" if args.json else "table",
                args.csv,
            )

        elif args.command == "concept":
            overview = service.concept_overview(args.label, limit=args.limit)
            if args.json:
                print_json(overview)
            else:
                print(f"Concept: {overview['concept']['label']}")
                print("\nConnected theses")
                print_table(overview["theses"], ["thesis_id", "year", "master_level", "title"])
                print("\nRelated concepts")
                print_table(overview["related_concepts"], ["label", "shared_theses"])

        elif args.command == "entity":
            rows = service.theses_by_entity(args.type, args.label, limit=args.limit)
            output_rows(
                rows,
                ["thesis_id", "year", "master_level", "track", "use_case", "title"],
                "json" if args.json else "table",
                args.csv,
            )

        elif args.command == "search":
            rows = service.search_theses(
                concepts=args.concept,
                keywords=args.keyword,
                use_case=args.use_case,
                methodology=args.methodology,
                year=args.year,
                master_level=args.master_level,
                track=args.track,
                match=args.match,
                limit=args.limit,
            )
            output_rows(
                rows,
                ["thesis_id", "matched_filters", "score", "year", "master_level", "track", "use_case", "title"],
                "json" if args.json else "table",
                args.csv,
            )
    except LookupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
