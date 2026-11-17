"""Compare the self-correction variants from one Kaggle run of kaggle/09_self_correction.ipynb.

Reads results/step9/ (raw notebook output), scores every variant with the official
evaluator's per-example match, and writes results/self_correction_summary.json and
results/self_correction_examples.md.

Every variant is compared against this run's own first attempt, so the comparison
never mixes two Kaggle environments.

Usage:
    python scripts/analyze_self_correction.py [--split dev]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_utils import load_split
from evaluate import bootstrap_ci, compare, official_per_example_correct, strip_sql_fences
from self_correct import error_type

STEP9_DIR = ROOT / "results" / "step9"
RESULTS_DIR = ROOT / "results"
VARIANTS = ["plain", "error", "plain_empty", "error_empty"]
ERROR_TYPES = ["wrong column", "wrong table", "syntax", "other"]
LEVELS = ["easy", "medium", "hard", "extra"]


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    return sorted(rows, key=lambda r: r["idx"])


def score(rows, examples, split, hardness):
    sqls = [strip_sql_fences(r["raw_output"]) for r in rows]
    correct = official_per_example_correct(sqls, examples, split)
    ex, lo, hi = bootstrap_ci(correct)
    per_difficulty = {
        level: sum(c for c, h in zip(correct, hardness) if h == level) / hardness.count(level)
        for level in LEVELS
    }
    return correct, {"ex_official": ex, "ex_official_95ci": [lo, hi], "per_difficulty_official": per_difficulty}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    parser.add_argument("--dir", default=str(STEP9_DIR), help="folder with the notebook's output files")
    parser.add_argument("--out", default=str(RESULTS_DIR), help="folder to write the summary files to")
    args = parser.parse_args()
    step9_dir, out_dir = Path(args.dir), Path(args.out)
    suffix = "" if args.split == "dev" else f"_{args.split}"

    examples = load_split(args.split)
    n = len(examples)
    sys.path.insert(0, str(ROOT / "tools" / "test-suite-sql-eval"))
    from evaluation import Evaluator
    hardness = [Evaluator().eval_hardness(ex["sql"]) for ex in examples]

    first = load_jsonl(step9_dir / "predictions_attempt1.jsonl")
    assert len(first) == n, f"expected {n} first attempts, got {len(first)}"
    for row, ex in zip(first, examples):
        assert row["db_id"] == ex["db_id"], f"idx {row['idx']} db_id mismatch"

    summary = {"split": args.split, "n_examples": n}

    # Does this run's first attempt reproduce the earlier Run A predictions? (dev only)
    exp4_path = ROOT / "results" / "step8_run_a" / "predictions_run_a.jsonl"
    if args.split == "dev" and exp4_path.exists():
        exp4 = load_jsonl(exp4_path)
        same = sum(strip_sql_fences(a["raw_output"]) == strip_sql_fences(b["raw_output"])
                   for a, b in zip(first, exp4))
        summary["attempt1_identical_to_exp4"] = {"same": same, "n": n, "rate": same / n}
        print(f"attempt 1 identical to Exp 4 predictions: {same}/{n} ({same / n:.1%})")

    base_correct, base_metrics = score(first, examples, args.split, hardness)
    base_metrics["avg_gen_time_sec_batched"] = sum(r["gen_time_sec"] for r in first) / n
    summary["no_retry"] = base_metrics
    print(f"no retry: EX {base_metrics['ex_official']:.1%} {base_metrics['ex_official_95ci']}")

    examples_md = ["# Self-correction: before/after examples", ""]

    for name in VARIANTS:
        path = step9_dir / f"selfcorrect_{name}.jsonl"
        if not path.exists():
            continue
        rows = load_jsonl(path)
        assert len(rows) == n
        correct, metrics = score(rows, examples, args.split, hardness)
        mc = compare(correct, base_correct)  # b = variant right & baseline wrong
        retried = [r for r in rows if r["n_attempts"] > 1]

        # what happened to each question that was retried, grouped by why it was retried
        groups = {}
        for r in retried:
            a0 = r["attempts"][0]
            trigger = error_type(a0["error"]) if a0["status"] == "error" else "empty result"
            g = groups.setdefault(trigger, {"retried": 0, "runs_after_retry": 0, "changed_final_sql": 0,
                                            "fixed": 0, "broken": 0})
            g["retried"] += 1
            g["runs_after_retry"] += r["attempts"][r["final_attempt"]]["status"] != "error"
            g["changed_final_sql"] += r["final_attempt"] != 0
            g["fixed"] += correct[r["idx"]] and not base_correct[r["idx"]]
            g["broken"] += base_correct[r["idx"]] and not correct[r["idx"]]

        retry_gen = sum(a["gen_time_sec"] for r in retried for a in r["attempts"][1:])
        exec_time = sum(r["exec_time_sec"] for r in rows)
        metrics.update({
            "mcnemar_vs_no_retry": {"fixed": mc["b"], "broken": mc["c"], "p_value": mc["p_value"]},
            "n_retried": len(retried),
            "n_retried_twice": sum(r["n_attempts"] == 3 for r in rows),
            "avg_attempts": sum(r["n_attempts"] for r in rows) / n,
            "retry_gen_time_sec_total": retry_gen,
            "exec_time_sec_total": exec_time,
            "extra_time_sec_per_question": (retry_gen + exec_time) / n,
            "extra_time_sec_per_retried_question": (retry_gen / len(retried)) if retried else 0.0,
            "avg_gen_time_sec_batched": sum(r["gen_time_sec"] for r in rows) / n,
            "by_trigger": groups,
        })
        summary[name] = metrics

        print(f"\n{name}: EX {metrics['ex_official']:.1%} {metrics['ex_official_95ci']} | "
              f"fixed {mc['b']}, broke {mc['c']}, p={mc['p_value']:.2g} | retried {len(retried)}, "
              f"avg attempts {metrics['avg_attempts']:.3f}, "
              f"+{metrics['extra_time_sec_per_question']:.3f}s/question")
        for trigger in ERROR_TYPES + ["empty result"]:
            if trigger in groups:
                print(f"  {trigger}: {groups[trigger]}")

        # the first 3 fixed questions from different databases, shown as they are
        examples_md += [f"## {name}", ""]
        seen_dbs = set()
        for r in retried:
            i = r["idx"]
            if not (correct[i] and not base_correct[i]) or r["db_id"] in seen_dbs:
                continue
            seen_dbs.add(r["db_id"])
            a0, af = r["attempts"][0], r["attempts"][r["final_attempt"]]
            examples_md += [
                f"**{r['db_id']}, question {i}:** {r['question']}", "",
                f"- First attempt: `{a0['sql']}`",
                f"- Result: {a0['error'] if a0['status'] == 'error' else 'no rows'}",
                f"- Feedback given: {af['feedback_given']!r}",
                f"- Attempt {r['final_attempt'] + 1}: `{af['sql']}`",
                f"- Gold: `{examples[i]['query']}`", "",
            ]
            if len(seen_dbs) == 3:
                break

    with open(out_dir / f"self_correction_summary{suffix}.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    with open(out_dir / f"self_correction_examples{suffix}.md", "w", encoding="utf-8") as f:
        f.write("\n".join(examples_md))
    print(f"\nwrote self_correction_summary{suffix}.json and self_correction_examples{suffix}.md to {out_dir}")


if __name__ == "__main__":
    main()
