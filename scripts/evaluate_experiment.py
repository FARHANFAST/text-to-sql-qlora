"""Turn a raw Kaggle predictions file into a results/ entry: clean the SQL, execute it
against dev, and report everything needed for an EXPERIMENTS.md row.

Usage:
    python scripts/evaluate_experiment.py --pred <raw predictions jsonl from Kaggle> \
        --tag exp1_baseline_v1 --split dev
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_utils import load_split
from evaluate import bootstrap_ci, evaluate_predictions, official_ex, strip_sql_fences

RESULTS_DIR = ROOT / "results"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", required=True, help="raw predictions jsonl from the Kaggle notebook")
    parser.add_argument("--tag", required=True, help="short name for this experiment, used in output filenames")
    parser.add_argument("--split", default="dev")
    args = parser.parse_args()

    examples = load_split(args.split)

    raw_by_idx = {}
    with open(args.pred, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            raw_by_idx[row["idx"]] = row

    assert len(raw_by_idx) == len(examples), f"expected {len(examples)} predictions, got {len(raw_by_idx)}"

    RESULTS_DIR.mkdir(exist_ok=True)
    combined_path = RESULTS_DIR / f"predictions_{args.tag}.jsonl"
    cleaned_sqls = []
    gen_times = []
    with open(combined_path, "w", encoding="utf-8") as f:
        for idx, ex in enumerate(examples):
            row = raw_by_idx[idx]
            assert row["db_id"] == ex["db_id"], f"idx {idx} db_id mismatch: {row['db_id']} vs {ex['db_id']}"
            cleaned = strip_sql_fences(row["raw_output"])
            cleaned_sqls.append(cleaned)
            gen_times.append(row["gen_time_sec"])
            f.write(json.dumps({
                "db_id": ex["db_id"], "question": ex["question"], "gold_sql": ex["query"],
                "raw_output": row["raw_output"], "cleaned_sql": cleaned, "gen_time_sec": row["gen_time_sec"],
            }) + "\n")

    result = evaluate_predictions(cleaned_sqls, examples, args.split)
    mean, lo, hi = bootstrap_ci(result["correct"])

    gold_path = ROOT / "data" / "raw" / "spider" / "spider_data" / f"{args.split}_gold.sql"
    pred_sql_path = RESULTS_DIR / f"_tmp_{args.tag}.sql"
    with open(pred_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned_sqls) + "\n")
    official = official_ex(gold_path, pred_sql_path, args.split)
    pred_sql_path.unlink()

    metrics = {
        "tag": args.tag, "split": args.split, "n_examples": len(examples),
        "ex_custom": result["ex"], "ex_official": official["all"],
        "ex_95ci": [lo, hi], "per_difficulty_custom": result["per_difficulty"],
        "per_difficulty_official": {k: official[k] for k in ("easy", "medium", "hard", "extra")},
        "avg_gen_time_sec": sum(gen_times) / len(gen_times),
        "predictions_file": str(combined_path.relative_to(ROOT)),
    }
    metrics_path = RESULTS_DIR / f"metrics_{args.tag}.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))
    if abs(result["ex"] - official["all"]) > 1e-9:
        print(f"WARNING: custom evaluator ({result['ex']:.4f}) and official evaluator "
              f"({official['all']:.4f}) disagree on {args.tag} — investigate before trusting this number.")


if __name__ == "__main__":
    main()
