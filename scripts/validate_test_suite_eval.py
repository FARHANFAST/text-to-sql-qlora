"""Validate scripts/test_suite_eval.py (our fast test-suite accuracy checker) before
trusting it for headline numbers.

Part A: gold-as-predictions on the full dev set must score 100% test-suite accuracy with
zero timeouts. Any gold query that errors or times out on any variant is reported.

Part B: cross-check our per-example correctness against the official evaluator's own
`eval_exec_match` (same function the CLI calls internally) on a fixed random sample of 200
dev examples, for prompt v2. Reports agreement example by example, not just the aggregate.

The official evaluator has no real per-query timeout for queries that eventually finish:
it wraps a blocking sqlite3 call in `asyncio.wait_for`, which can't cancel a call that
never yields control, so its 60s "timeout" constant only matters in theory. It will return
correctly, however slow, for any query that finishes at all, and hang forever on one that
doesn't (e.g. an unbounded recursive CTE) - this is what stalled the original 1,034-example
test-suite run for 1.5 hours. We cap each official per-example check at a generous wall
clock timeout here specifically to avoid that failure mode, not because the official
function has a working timeout of its own.

Usage:
    python -u scripts/validate_test_suite_eval.py
"""
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_utils import load_split  # noqa: E402

OFFICIAL_PER_EXAMPLE_TIMEOUT = 30.0  # wall-clock cap per example for the official path


def _gold_worker(args):
    idx, db_id, gold_sql, timeout = args
    from evaluate import test_suite_match_one
    try:
        ok = test_suite_match_one(db_id, gold_sql, gold_sql, timeout=timeout)
        return {"idx": idx, "ok": ok, "error": None, "timeout": False}
    except Exception as e:
        msg = str(e)
        return {"idx": idx, "ok": False, "error": msg, "timeout": "interrupted" in msg}


def _official_worker(args):
    idx, db_id, pred_sql, gold_sql = args
    sys.path.insert(0, str(ROOT / "tools" / "test-suite-sql-eval"))
    from exec_eval import eval_exec_match
    db = ROOT / "data" / "raw" / "test_suite" / "database" / db_id / f"{db_id}.sqlite"
    try:
        ok = bool(eval_exec_match(
            db=str(db), p_str=pred_sql, g_str=gold_sql,
            plug_value=False, keep_distinct=False, progress_bar_for_each_datapoint=False,
        ))
        return {"idx": idx, "ok": ok, "error": None}
    except Exception as e:
        return {"idx": idx, "ok": False, "error": str(e)}


def part_a_gold_sanity():
    print("=== Part A: gold-as-predictions, full dev set, our fast evaluator ===", flush=True)
    examples = load_split("dev")
    tasks = [(i, ex["db_id"], ex["query"], 5.0) for i, ex in enumerate(examples)]

    start = time.time()
    results = []
    with ProcessPoolExecutor() as pool:
        for i, result in enumerate(pool.map(_gold_worker, tasks, chunksize=4)):
            results.append(result)
            if (i + 1) % 200 == 0:
                print(f"  {i + 1}/{len(tasks)} done, {time.time() - start:.0f}s elapsed", flush=True)
    elapsed = time.time() - start

    n_ok = sum(r["ok"] for r in results)
    n_timeout = sum(r["timeout"] for r in results)
    n_other_error = sum(r["error"] is not None and not r["timeout"] for r in results)
    print(f"gold-as-predictions test-suite accuracy: {n_ok}/{len(results)} = {n_ok / len(results):.4f} "
          f"({elapsed:.0f}s)", flush=True)
    print(f"timeouts: {n_timeout}, other errors: {n_other_error}", flush=True)

    for r in results:
        if r["error"] is not None:
            ex = examples[r["idx"]]
            kind = "TIMEOUT" if r["timeout"] else "ERROR"
            print(f"  [{kind}] idx={r['idx']} db_id={ex['db_id']}: {r['error']}", flush=True)
            print(f"    gold: {ex['query']}", flush=True)

    ok = n_ok == len(results) and n_timeout == 0 and n_other_error == 0
    print("PASS" if ok else "FAIL", flush=True)
    return ok


def part_b_crosscheck():
    print("\n=== Part B: cross-check vs official evaluator, 200-example sample (seed 42), v2 ===", flush=True)
    rows = [json.loads(l) for l in open(ROOT / "results" / "predictions_exp_baseline_v2.jsonl", encoding="utf-8")]
    sample_idx = sorted(random.Random(42).sample(range(len(rows)), 200))

    print("our fast evaluator:", flush=True)
    from evaluate import test_suite_match_one
    ours = {}
    start = time.time()
    with ProcessPoolExecutor() as pool:
        tasks = [(i, rows[i]["db_id"], rows[i]["cleaned_sql"], rows[i]["gold_sql"], 5.0) for i in sample_idx]
        futures = {pool.submit(_ours_worker, t): t[0] for t in tasks}
        for fut in futures:
            idx = futures[fut]
            ours[idx] = fut.result()
    print(f"  done in {time.time() - start:.0f}s", flush=True)

    print("official evaluator (eval_exec_match directly, same function the CLI uses), "
          f"capped at {OFFICIAL_PER_EXAMPLE_TIMEOUT:.0f}s/example:", flush=True)
    official = {}
    start = time.time()
    # Manual pool lifecycle, not a `with` block: a context manager's shutdown(wait=True)
    # would block on any future we've already given up on, defeating the per-task timeout.
    pool = ProcessPoolExecutor()
    try:
        pending = {}
        for i in sample_idx:
            task = (i, rows[i]["db_id"], rows[i]["cleaned_sql"], rows[i]["gold_sql"])
            pending[pool.submit(_official_worker, task)] = i
        for fut, idx in pending.items():
            try:
                official[idx] = fut.result(timeout=OFFICIAL_PER_EXAMPLE_TIMEOUT)
            except Exception as e:
                official[idx] = {"idx": idx, "ok": None, "error": f"official-side timeout/error: {e}"}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    print(f"  done in {time.time() - start:.0f}s", flush=True)

    agree = 0
    disagreements = []
    for i in sample_idx:
        o, f = official[i]["ok"], ours[i]["ok"]
        if o is None:
            disagreements.append((i, o, f, "official timed out (>%.0fs) — can't compare" % OFFICIAL_PER_EXAMPLE_TIMEOUT))
            continue
        if o == f:
            agree += 1
        else:
            disagreements.append((i, o, f, None))

    print(f"agreement: {agree}/{len(sample_idx)} = {agree / len(sample_idx):.4f}", flush=True)
    our_acc = sum(ours[i]["ok"] for i in sample_idx) / len(sample_idx)
    official_scored = [i for i in sample_idx if official[i]["ok"] is not None]
    official_acc = sum(official[i]["ok"] for i in official_scored) / len(official_scored) if official_scored else None
    print(f"our test-suite accuracy on this sample: {our_acc:.4f}", flush=True)
    print(f"official test-suite accuracy on this sample: {official_acc}", flush=True)

    if disagreements:
        print(f"\n{len(disagreements)} disagreement(s):", flush=True)
        for idx, o, f, note in disagreements:
            row = rows[idx]
            print(f"  idx={idx} db_id={row['db_id']} official={o} ours={f}" + (f" ({note})" if note else ""), flush=True)
            print(f"    gold: {row['gold_sql']}", flush=True)
            print(f"    pred: {row['cleaned_sql']}", flush=True)
    else:
        print("\nno disagreements.", flush=True)

    return agree == len(sample_idx)


def _ours_worker(args):
    idx, db_id, pred_sql, gold_sql, timeout = args
    from evaluate import test_suite_match_one
    try:
        ok = test_suite_match_one(db_id, pred_sql, gold_sql, timeout=timeout)
        return {"idx": idx, "ok": ok, "error": None}
    except Exception as e:
        return {"idx": idx, "ok": False, "error": str(e)}


if __name__ == "__main__":
    a_ok = part_a_gold_sanity()
    b_ok = part_b_crosscheck()
    print(f"\nPart A: {'PASS' if a_ok else 'FAIL'}, Part B: {'PASS (full agreement)' if b_ok else 'see disagreements above'}")
