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
from evaluate import (
    bootstrap_ci, evaluate_predictions, official_ex, official_per_example_correct, strip_sql_fences,
)

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

    cleaned_sqls = [strip_sql_fences(raw_by_idx[idx]["raw_output"]) for idx in range(len(examples))]
    for idx, ex in enumerate(examples):
        assert raw_by_idx[idx]["db_id"] == ex["db_id"], f"idx {idx} db_id mismatch"

    result = evaluate_predictions(cleaned_sqls, examples, args.split)

    # Official per-example correctness (column-order permutation, DISTINCT removal) so the
    # 95% CI and per-difficulty breakdown we report actually match the official EX number,
    # rather than pairing it with a CI computed under our stricter evaluator.
    official_correct = official_per_example_correct(cleaned_sqls, examples, args.split)
    official_mean, official_lo, official_hi = bootstrap_ci(official_correct)

    sys.path.insert(0, str(ROOT / "tools" / "test-suite-sql-eval"))
    from evaluation import Evaluator
    hardness_of = Evaluator().eval_hardness
    hardness = [hardness_of(ex["sql"]) for ex in examples]
    levels = ["easy", "medium", "hard", "extra"]
    per_difficulty_official_exact = {
        level: sum(c for c, h in zip(official_correct, hardness) if h == level) / max(1, hardness.count(level))
        for level in levels
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    combined_path = RESULTS_DIR / f"predictions_{args.tag}.jsonl"
    gen_times = []
    with open(combined_path, "w", encoding="utf-8") as f:
        for idx, ex in enumerate(examples):
            row = raw_by_idx[idx]
            gen_times.append(row["gen_time_sec"])
            f.write(json.dumps({
                "db_id": ex["db_id"], "question": ex["question"], "gold_sql": ex["query"],
                "raw_output": row["raw_output"], "cleaned_sql": cleaned_sqls[idx],
                "gen_time_sec": row["gen_time_sec"],
                "correct_custom": result["correct"][idx], "correct_official": official_correct[idx],
            }) + "\n")

    gold_path = ROOT / "data" / "raw" / "spider" / "spider_data" / f"{args.split}_gold.sql"
    pred_sql_path = RESULTS_DIR / f"_tmp_{args.tag}.sql"
    with open(pred_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned_sqls) + "\n")
    official_agg = official_ex(gold_path, pred_sql_path, args.split)
    pred_sql_path.unlink()

    # Cross-check: per-example official correctness (eval_exec_match called directly) must
    # match the aggregate CLI call (evaluation.py), since both wrap the same underlying
    # comparison. The CLI only prints 3 decimal places, so allow for that rounding.
    if abs(official_mean - official_agg["all"]) > 5e-4:
        print(f"WARNING: per-example official EX ({official_mean:.4f}) and aggregate official "
              f"EX ({official_agg['all']:.4f}) disagree on {args.tag} — the two call paths diverged.")

    # Test-suite accuracy is computed separately (scripts/test_suite_eval.py) — it's only
    # required for final configurations (best baseline, best fine-tuned, final pipeline),
    # not for every prompt-experiment iteration. See PROGRESS.md "Decisions".
    metrics = {
        "tag": args.tag, "split": args.split, "n_examples": len(examples),
        "ex_custom": result["ex"], "ex_official": official_agg["all"],
        "ex_official_95ci": [official_lo, official_hi],
        "per_difficulty_custom": result["per_difficulty"],
        "per_difficulty_official": {k: official_agg[k] for k in ("easy", "medium", "hard", "extra")},
        "per_difficulty_official_exact": per_difficulty_official_exact,
        "test_suite_accuracy": "pending",
        "test_suite_per_difficulty": "pending",
        "avg_gen_time_sec_batched": sum(gen_times) / len(gen_times),
        "predictions_file": str(combined_path.relative_to(ROOT)),
    }
    metrics_path = RESULTS_DIR / f"metrics_{args.tag}.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))
    print(f"note: custom evaluator EX ({result['ex']:.4f}) is stricter than the official evaluator "
          f"({official_agg['all']:.4f}) — the official evaluator allows column-order permutation and "
          f"ignores DISTINCT mismatches by default; our quick evaluator does not. This is expected, "
          f"not a bug (see PROGRESS.md).")


if __name__ == "__main__":
    main()
