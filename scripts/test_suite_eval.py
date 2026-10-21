"""Test-suite accuracy for a predictions file, computed directly (no subprocess into the
official evaluator's CLI) so it's actually fast enough to run on 1,034 dev examples:

- real per-query timeout (threading.Timer + conn.interrupt, works on Windows), instead of
  the official evaluator's asyncio.wait_for, which can't cancel a blocking sqlite3 call and
  pays for a fresh event loop on every single query
- one worker process per CPU core, one dev example per task
- resumable: every finished example is appended to a cache file immediately, so Ctrl+C or
  a crash loses at most the one example being evaluated at that moment
- unbuffered progress: a line every 50 completed examples with elapsed/ETA

Run a small timing sample first:
    python -u scripts/test_suite_eval.py --pred results/predictions_exp_baseline_v2.jsonl \
        --tag exp_baseline_v2 --sample 50

Then the full run (same command without --sample resumes from the cache and finishes it):
    python -u scripts/test_suite_eval.py --pred results/predictions_exp_baseline_v2.jsonl \
        --tag exp_baseline_v2
"""
import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_utils import load_split  # noqa: E402

RESULTS_DIR = ROOT / "results"


def _worker(args):
    idx, db_id, pred_sql, gold_sql, timeout = args
    from evaluate import test_suite_match_one  # re-imported per worker process (Windows spawn)
    start = time.time()
    try:
        correct = test_suite_match_one(db_id, pred_sql, gold_sql, timeout=timeout)
        error = None
    except Exception as e:
        correct = False
        error = str(e)
    return {"idx": idx, "correct": correct, "time_sec": time.time() - start, "error": error}


def load_cache(cache_path: Path) -> dict:
    cache = {}
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                cache[row["idx"]] = row
    return cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", required=True, help="results/predictions_<tag>.jsonl with cleaned_sql + gold_sql")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sample", type=int, default=None, help="only run the first N examples, to time it")
    parser.add_argument("--workers", type=int, default=None, help="default: os.cpu_count()")
    parser.add_argument("--timeout", type=float, default=5.0, help="per-query timeout in seconds")
    args = parser.parse_args()

    rows = [json.loads(l) for l in open(args.pred, encoding="utf-8")]
    if args.sample:
        rows = rows[: args.sample]

    cache_path = RESULTS_DIR / f"test_suite_cache_{args.tag}.jsonl"
    cache = load_cache(cache_path)

    todo = [(i, r) for i, r in enumerate(rows) if i not in cache]
    print(f"{len(rows)} examples total, {len(cache)} already cached, {len(todo)} to run "
          f"(workers={args.workers or 'cpu_count'}, timeout={args.timeout}s/query)", flush=True)

    if not todo:
        print("nothing to do — all requested examples are already cached.", flush=True)
    else:
        tasks = [(i, r["db_id"], r["cleaned_sql"], r["gold_sql"], args.timeout) for i, r in todo]
        start = time.time()
        done = 0
        cache_file = open(cache_path, "a", encoding="utf-8")
        try:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(_worker, t) for t in tasks]
                for fut in as_completed(futures):
                    result = fut.result()
                    cache_file.write(json.dumps(result) + "\n")
                    cache_file.flush()
                    cache[result["idx"]] = result
                    done += 1
                    if done % 50 == 0 or done == len(todo):
                        elapsed = time.time() - start
                        rate = elapsed / done
                        eta = rate * (len(todo) - done)
                        print(f"  {done}/{len(todo)} done, {elapsed:.0f}s elapsed, "
                              f"~{eta:.0f}s remaining for this run", flush=True)
        finally:
            cache_file.close()

        elapsed = time.time() - start
        if todo:
            per_example = elapsed / len(todo)
            print(f"this run: {len(todo)} examples in {elapsed:.0f}s "
                  f"({per_example:.2f}s/example average)", flush=True)
            if args.sample:
                projected = per_example * 1034
                print(f"projected time for the full 1,034-example dev set: "
                      f"~{projected:.0f}s (~{projected / 60:.1f} min)", flush=True)

    if len(cache) < len(rows):
        print(f"stopped with {len(rows) - len(cache)} examples still not cached — rerun the same "
              f"command (without --sample) to resume.", flush=True)
        return

    correct = [cache[i]["correct"] for i in range(len(rows))]
    errors = [cache[i] for i in range(len(rows)) if cache[i]["error"]]
    if errors:
        print(f"WARNING: {len(errors)} examples raised an error (e.g. gold failed on a variant) "
              f"— first one: idx {errors[0]['idx']}: {errors[0]['error']}", flush=True)

    sys.path.insert(0, str(ROOT / "tools" / "test-suite-sql-eval"))
    from evaluation import Evaluator
    examples = load_split("dev")[: len(rows)]
    hardness_of = Evaluator().eval_hardness
    hardness = [hardness_of(ex["sql"]) for ex in examples]
    levels = ["easy", "medium", "hard", "extra"]
    per_difficulty = {
        level: sum(c for c, h in zip(correct, hardness) if h == level) / max(1, hardness.count(level))
        for level in levels
    }

    from evaluate import bootstrap_ci
    mean, lo, hi = bootstrap_ci(correct)
    metrics = {
        "tag": args.tag, "n_examples": len(rows), "test_suite_accuracy": mean,
        "test_suite_95ci": [lo, hi], "test_suite_per_difficulty": per_difficulty,
    }
    print(json.dumps(metrics, indent=2))

    metrics_path = RESULTS_DIR / f"metrics_{args.tag}.json"
    if metrics_path.exists():
        existing = json.loads(metrics_path.read_text(encoding="utf-8"))
        existing.update({
            "test_suite_accuracy": metrics["test_suite_accuracy"],
            "test_suite_95ci": metrics["test_suite_95ci"],
            "test_suite_per_difficulty": metrics["test_suite_per_difficulty"],
        })
        metrics_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"merged into {metrics_path.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
