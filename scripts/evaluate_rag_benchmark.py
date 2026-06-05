import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import db_path, reports_dir
from rag.service import RagService


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    question: str
    expected_ids: tuple[str, ...] = ()
    expected_concepts: tuple[str, ...] = ()
    expected_use_case: str = ""
    top_k: int = 5
    min_matches: int = 1
    notes: str = ""


CASES: list[BenchmarkCase] = [
    BenchmarkCase("q001", "Which theses study fraud detection with machine learning?", ("thesis_0112", "thesis_0087", "thesis_0120"), expected_use_case="detection de fraude / risque financier", min_matches=2),
    BenchmarkCase("q002", "Find work about ensemble methods for insurance fraud detection.", ("thesis_0087",)),
    BenchmarkCase("q003", "Which thesis compares techniques for credit card fraud on imbalanced data?", ("thesis_0120",)),
    BenchmarkCase("q004", "Show research about breast cancer classification using machine learning.", ("thesis_0090", "thesis_0022", "thesis_0091", "thesis_0116"), expected_use_case="sante / aide au diagnostic", min_matches=2),
    BenchmarkCase("q005", "Which thesis uses vision language models for mammography interpretation?", ("thesis_0117",)),
    BenchmarkCase("q006", "Find the thesis about diabetes prediction with federated learning and non-IID data.", ("thesis_0142",)),
    BenchmarkCase("q007", "Which work discusses Moore's law and quantum computing?", ("thesis_0043",)),
    BenchmarkCase("q008", "Find the thesis about confidentiality of Ethereum blockchain transactions.", ("thesis_0049",)),
    BenchmarkCase("q009", "Which thesis predicts Bitcoin evolution from social network sentiment?", ("thesis_0075",)),
    BenchmarkCase("q010", "Show the thesis about online automatic crypto trading with machine learning.", ("thesis_0045",)),
    BenchmarkCase("q011", "Find theses about fake news detection using BERT, SVM or GPT embeddings.", ("thesis_0119", "thesis_0150"), expected_concepts=("detection de desinformation",), min_matches=2),
    BenchmarkCase("q012", "Which thesis uses GPT-3 embeddings for fake news detection?", ("thesis_0150",)),
    BenchmarkCase("q013", "Which theses are about security challenges in data lakes?", ("thesis_0137", "thesis_0140", "thesis_0059"), expected_concepts=("data lake",), min_matches=2),
    BenchmarkCase("q014", "Find research on metadata management for non-structured data in a data lake.", ("thesis_0059", "thesis_0140")),
    BenchmarkCase("q015", "Which thesis is about evolving data models inside a data warehouse?", ("thesis_0058",)),
    BenchmarkCase("q016", "Find the thesis about augmented BI on OLAP cubes.", ("thesis_0054",)),
    BenchmarkCase("q017", "Which thesis uses process mining to improve incident handling?", ("thesis_0026",)),
    BenchmarkCase("q018", "Show work on MLOps and containerized cloud pipelines.", ("thesis_0113", "thesis_0121"), expected_concepts=("mlops", "devops", "cloud computing"), min_matches=2),
    BenchmarkCase("q019", "Find the thesis on automatic deployment and generation of microservices.", ("thesis_0018",)),
    BenchmarkCase("q020", "Which thesis studies similarity search between source codes?", ("thesis_0141",)),
    BenchmarkCase("q021", "Find research on detecting C code plagiarism in education.", ("thesis_0036",)),
    BenchmarkCase("q022", "Which theses discuss LLM security vulnerabilities or prompt attacks?", ("thesis_0125", "thesis_0011", "thesis_0144"), expected_concepts=("large language models", "cybersecurite"), min_matches=2),
    BenchmarkCase("q023", "Show theses about generative AI in software development.", ("thesis_0076", "thesis_0023", "thesis_0134", "thesis_0136"), expected_use_case="developpement logiciel / devops"),
    BenchmarkCase("q024", "Which thesis uses an LLM to generate application documentation?", ("thesis_0134", "thesis_0136")),
    BenchmarkCase("q025", "Find the thesis about AI for software quality control processes.", ("thesis_0108",)),
    BenchmarkCase("q026", "Which theses discuss variable selection and hyperparameter optimization?", ("thesis_0101", "thesis_0126", "thesis_0078"), expected_concepts=("optimisation",), min_matches=2),
    BenchmarkCase("q027", "Find the thesis about vertex cover approximation using machine learning as a heuristic.", ("thesis_0008",)),
    BenchmarkCase("q028", "Which thesis compares algorithms for the Conway graph?", ("thesis_0046", "thesis_0143"), expected_concepts=("graphes",)),
    BenchmarkCase("q029", "Find the thesis on university course scheduling with a genetic algorithm.", ("thesis_0052",)),
    BenchmarkCase("q030", "Which theses optimize airport ground flow?", ("thesis_0097", "thesis_0122")),
    BenchmarkCase("q031", "Find work on multi-criteria optimization for supplier selection.", ("thesis_0057",)),
    BenchmarkCase("q032", "Which thesis studies migration toward serverless architectures?", ("thesis_0040",)),
    BenchmarkCase("q033", "Find the thesis about IoT stream anomaly detection in real time.", ("thesis_0027",)),
    BenchmarkCase("q034", "Which thesis detects DDoS attacks in cloud environments with RNN?", ("thesis_0013",)),
    BenchmarkCase("q035", "Find the thesis about protecting RBAC systems against privilege escalation.", ("thesis_0063",)),
    BenchmarkCase("q036", "Which thesis discusses security flaws in connected vehicles?", ("thesis_0107",)),
    BenchmarkCase("q037", "Find research about e-commerce scalper bots and anti-bot strategies.", ("thesis_0004",)),
    BenchmarkCase("q038", "Which thesis applies transfer learning to sign language recognition?", ("thesis_0139",)),
    BenchmarkCase("q039", "Find the thesis about a deep learning movie recommendation system.", ("thesis_0148",)),
    BenchmarkCase("q040", "Which thesis is about green machine learning trends?", ("thesis_0030",)),
    BenchmarkCase("q041", "Give me cybersecurity attack detection theses.", expected_use_case="cybersecurite / detection d'attaques", expected_concepts=("cybersecurite",), min_matches=3),
    BenchmarkCase("q042", "Give me health diagnosis and medical AI theses.", expected_use_case="sante / aide au diagnostic", expected_concepts=("sante",), min_matches=3),
    BenchmarkCase("q043", "Find operational optimization, planning or scheduling theses.", expected_use_case="optimisation operationnelle", expected_concepts=("optimisation",), min_matches=3),
    BenchmarkCase("q044", "Show graph analysis and graph algorithm theses.", expected_use_case="analyse de graphes / reseaux", expected_concepts=("graphes",), min_matches=2),
    BenchmarkCase("q045", "Find business intelligence and data platform theses.", expected_use_case="gestion des donnees / data platform", expected_concepts=("business intelligence", "data lake", "data warehouse"), min_matches=2),
    BenchmarkCase("q046", "Show large language model or LLM theses.", expected_concepts=("large language models",), min_matches=3),
    BenchmarkCase("q047", "Find cloud computing theses.", expected_concepts=("cloud computing",), min_matches=2),
    BenchmarkCase("q048", "Show blockchain-related theses.", expected_concepts=("blockchain",), min_matches=2),
    BenchmarkCase("q049", "Find energy, environment and software sustainability theses.", expected_use_case="energie / environnement", expected_concepts=("energie",), min_matches=1),
    BenchmarkCase("q050", "Show sentiment analysis and customer satisfaction theses.", ("thesis_0138", "thesis_0075", "thesis_0148"), expected_concepts=("analyse de sentiments",), min_matches=1),
]


def result_matches(row: dict[str, Any], case: BenchmarkCase) -> bool:
    concepts = {item.strip().lower() for item in str(row.get("concepts") or "").split(";") if item.strip()}
    if case.expected_ids and row["thesis_id"] in case.expected_ids:
        return True
    if case.expected_use_case and row.get("use_case") == case.expected_use_case:
        return True
    if case.expected_concepts and any(concept.lower() in concepts for concept in case.expected_concepts):
        return True
    return False


def evaluate_case(service: RagService, case: BenchmarkCase) -> dict[str, Any]:
    response = service.answer(case.question, top_k=case.top_k, use_llm=False)
    results = response["results"]
    retrieved_ids = [row["thesis_id"] for row in results]
    exact_hit_rank = ""
    if case.expected_ids:
        for index, thesis_id in enumerate(retrieved_ids, start=1):
            if thesis_id in case.expected_ids:
                exact_hit_rank = index
                break
    match_count = sum(1 for row in results if result_matches(row, case))
    passed = match_count >= case.min_matches
    if case.expected_ids and not exact_hit_rank:
        passed = False
    return {
        "case_id": case.case_id,
        "question": case.question,
        "passed": passed,
        "match_count": match_count,
        "min_matches": case.min_matches,
        "exact_hit_rank": exact_hit_rank,
        "expected_ids": "; ".join(case.expected_ids),
        "expected_use_case": case.expected_use_case,
        "expected_concepts": "; ".join(case.expected_concepts),
        "retrieved_ids": "; ".join(retrieved_ids),
        "top_result": f"{results[0]['thesis_id']} | {results[0]['score']} | {results[0]['title']}" if results else "",
        "answer": response["answer"],
    }


def write_reports(rows: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    reports_dir().mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir() / "rag_benchmark_50.csv"
    summary_path = reports_dir() / "rag_benchmark_50_summary.json"
    columns = [
        "case_id",
        "passed",
        "match_count",
        "min_matches",
        "exact_hit_rank",
        "expected_ids",
        "expected_use_case",
        "expected_concepts",
        "retrieved_ids",
        "top_result",
        "question",
        "answer",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return csv_path, summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate 50 fixed RAG benchmark questions against the local thesis dataset.")
    parser.add_argument("--min-pass-rate", type=float, default=0.80)
    parser.add_argument("--no-fail", action="store_true", help="Always exit 0 after writing the report.")
    args = parser.parse_args()

    service = RagService(db_path())
    rows = [evaluate_case(service, case) for case in CASES]
    passed = sum(1 for row in rows if row["passed"])
    failed_rows = [row for row in rows if not row["passed"]]
    summary = {
        "cases": len(rows),
        "passed": passed,
        "failed": len(failed_rows),
        "pass_rate": round(passed / max(1, len(rows)), 4),
        "min_pass_rate": args.min_pass_rate,
        "failed_case_ids": [row["case_id"] for row in failed_rows],
    }
    csv_path, summary_path = write_reports(rows, summary)
    print(f"RAG benchmark cases: {summary['cases']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Pass rate: {summary['pass_rate']:.2%}")
    print(f"Report: {csv_path}")
    print(f"Summary: {summary_path}")
    if failed_rows:
        print("\nFailed cases:")
        for row in failed_rows:
            print(f"- {row['case_id']}: {row['question']}")
            print(f"  expected_ids={row['expected_ids']} expected_use_case={row['expected_use_case']} expected_concepts={row['expected_concepts']}")
            print(f"  retrieved={row['retrieved_ids']}")
    if not args.no_fail and summary["pass_rate"] < args.min_pass_rate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
