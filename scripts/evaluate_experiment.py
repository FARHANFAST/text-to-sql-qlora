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
    # The official CLI evaluator expects exactly one SQL string per line, paired by line
    # number with the gold file. A prediction containing an embedded newline (the model
    # occasionally formats SQL across multiple lines) would inject extra lines here and
    # desync every gold/pred pair after it, silently corrupting the aggregate EX number.
    # Collapse embedded newlines to a space first -- SQL is whitespace-insensitive, so this
    # can't change what the query means.
    one_line_sqls = [" ".join(sql.split()) for sql in cleaned_sqls]
    with open(pred_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(one_line_sqls) + "\n")
    official_agg = official_ex(gold_path, pred_sql_path, args.split)
    pred_sql_path.unlink()

    # The headline ex_official comes from the direct per-example eval_exec_match calls
    # (official_mean / per_difficulty_official_exact above), NOT from this CLI aggregate call.
    # Reason: the vendored evaluation.py's evaluate() does `p_str.replace("value", "1")` on
    # every prediction unconditionally (line ~569), a leftover from its value-plugging mode
    # that corrupts any prediction containing the literal substring "value" even when
    # plug_value=False. Confirmed on the Spider test run (2026-11-07/08): this flips 10 of
    # Run A final's predictions on the boxes/warehouses database (column literally named
    # "value") from correct to incorrect. See PROGRESS.md and docs/test_suite_sql_eval_value_bug.md
    # for the full writeup and a draft upstream issue. The CLI aggregate is still computed and
    # kept below for transparency/cross-checking, just not used as the headline number.
    if abs(official_mean - official_agg["all"]) > 5e-4:
        print(f"NOTE: per-example official EX ({official_mean:.4f}) and the CLI aggregate official "
              f"EX ({official_agg['all']:.4f}) disagree on {args.tag}. This is the known "
              f"evaluation.py 'value'->'1' replacement bug (see PROGRESS.md) if any prediction "
              f"contains the literal substring 'value'; the per-example number is used as the "
              f"headline here. If this disagreement shows up somewhere without that substring "
              f"present, treat it as a new bug and investigate before trusting either number.")

    # Test-suite accuracy is computed separately (scripts/test_suite_eval.py), and only for
    # dev: the test-suite database download only has perturbation variants for dev's 20
    # databases, not test's 40 (see evaluate.py's official_test_suite_accuracy), so for the
    # test split it's never going to exist, not just not-yet-run.
    test_suite_status = "not applicable (test split has no perturbation databases)" if args.split == "test" else "pending"
    metrics = {
        "tag": args.tag, "split": args.split, "n_examples": len(examples),
        "ex_custom": result["ex"], "ex_official": official_mean,
        "ex_official_95ci": [official_lo, official_hi],
        "per_difficulty_custom": result["per_difficulty"],
        "per_difficulty_official": per_difficulty_official_exact,
        "ex_official_cli_aggregate": official_agg["all"],
        "per_difficulty_official_cli_aggregate": {k: official_agg[k] for k in ("easy", "medium", "hard", "extra")},
        "test_suite_accuracy": test_suite_status,
        "test_suite_per_difficulty": test_suite_status,
        "avg_gen_time_sec_batched": sum(gen_times) / len(gen_times),
        "predictions_file": str(combined_path.relative_to(ROOT)),
    }
    metrics_path = RESULTS_DIR / f"metrics_{args.tag}.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))
    print(f"note: custom evaluator EX ({result['ex']:.4f}) is stricter than the official evaluator "
          f"({official_mean:.4f}) — the official evaluator allows column-order permutation and "
          f"ignores DISTINCT mismatches by default; our quick evaluator does not. This is expected, "
          f"not a bug (see PROGRESS.md).")


if __name__ == "__main__":
    main()
