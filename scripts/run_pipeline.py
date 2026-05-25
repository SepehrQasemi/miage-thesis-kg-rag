import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(args: list[str]) -> None:
    print("\n>", " ".join(args))
    completed = subprocess.run(args, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full local extraction improvement pipeline.")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--with-llm-review", action="store_true", help="Run local Ollama review for needs_review rows.")
    parser.add_argument("--generate-abstracts", action="store_true", help="Generate marked abstracts when no extracted abstract exists.")
    parser.add_argument("--limit", type=int, default=None, help="Limit PDF processing and LLM passes for testing.")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR fallback.")
    args = parser.parse_args()

    process_cmd = [sys.executable, "scripts/process_pdfs.py", "--force"]
    if args.no_ocr:
        process_cmd.append("--no-ocr")
    if args.limit:
        process_cmd.extend(["--limit", str(args.limit)])
    run_step(process_cmd)

    run_step([sys.executable, "scripts/repair_titles.py"])

    override_file = ROOT / "data" / "manual_overrides" / "theses_metadata.csv"
    if override_file.exists():
        run_step([sys.executable, "scripts/apply_manual_overrides.py"])

    if args.with_llm_review:
        llm_cmd = [sys.executable, "scripts/llm_review_needs_review.py", "--model", args.model, "--apply"]
        if args.limit:
            llm_cmd.extend(["--limit", str(args.limit)])
        run_step(llm_cmd)

    if args.generate_abstracts:
        abstract_cmd = [sys.executable, "scripts/llm_generate_missing_abstracts.py", "--model", args.model, "--apply"]
        if args.limit:
            abstract_cmd.extend(["--limit", str(args.limit)])
        run_step(abstract_cmd)

    run_step([sys.executable, "scripts/export_csv.py"])
    run_step([sys.executable, "scripts/export_quality_report.py"])

    validation_cmd = [sys.executable, "scripts/validate_dataset.py"]
    if args.limit:
        validation_cmd.append("--allow-subset")
    run_step(validation_cmd)

    run_step([sys.executable, "scripts/build_knowledge_graph.py"])
    run_step([sys.executable, "scripts/validate_knowledge_graph.py"])


if __name__ == "__main__":
    main()
