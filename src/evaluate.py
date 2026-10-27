"""Execution accuracy evaluation.

Two ways to score predictions:
- `evaluate_predictions`: our own quick evaluator, for fast iteration.
- `run_official_eval`: wraps the official test-suite-sql-eval evaluator, used for the
  numbers we actually report. Both must agree on the sanity test in tests/.

Both apply the same bag-semantics rule for comparing result sets: row order only
matters if the gold query has an ORDER BY, matching how the official evaluator decides it.
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

from data_utils import SPIDER_DIR, db_path
from execute import run_query

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools" / "test-suite-sql-eval"
TEST_SUITE_DB_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "test_suite" / "database"


def strip_sql_fences(text: str) -> str:
    """Strip a markdown code fence (```sql ... ``` or ``` ... ```) wrapping a model's raw output."""
    text = text.strip()
    fence = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def result_sets_match(gold_rows: list, pred_rows: list, order_matters: bool) -> bool:
    if order_matters:
        return gold_rows == pred_rows
    return Counter(gold_rows) == Counter(pred_rows)


def evaluate_predictions(predictions: list[str], examples: list[dict], split: str) -> dict:
    """Execute each prediction against gold on its database.

    Returns a dict with per-example correctness (`correct`), overall EX (`ex`),
    and EX by Spider difficulty (`per_difficulty`). Difficulty is computed by the
    official evaluator's own hardness logic (`Evaluator.eval_hardness`), reused as-is
    on the parsed `sql` field Spider's json already provides, rather than re-deriving it.
    """
    assert len(predictions) == len(examples)
    sys.path.insert(0, str(TOOLS_DIR))
    from evaluation import Evaluator
    hardness_of = Evaluator().eval_hardness

    correct = []
    hardness = []
    for pred_sql, ex in zip(predictions, examples):
        db = db_path(ex["db_id"], split)
        gold_rows, gold_err = run_query(db, ex["query"])
        if gold_err:
            raise RuntimeError(f"gold query failed to execute on {ex['db_id']}: {gold_err}")
        pred_rows, pred_err = run_query(db, pred_sql)
        order_matters = "order by" in ex["query"].lower()
        ok = pred_err is None and result_sets_match(gold_rows, pred_rows, order_matters)
        correct.append(ok)
        hardness.append(hardness_of(ex["sql"]))

    levels = ["easy", "medium", "hard", "extra"]
    per_difficulty = {
        level: sum(c for c, h in zip(correct, hardness) if h == level) / max(1, hardness.count(level))
        for level in levels
    }
    return {"correct": correct, "ex": sum(correct) / len(correct), "per_difficulty": per_difficulty}


def normalize_sql_for_exact_match(sql: str) -> str:
    """Loose string normalization for a secondary exact-match number: lowercase, collapse
    whitespace, drop a trailing semicolon. This is NOT the official Spider exact-match
    (which compares parsed SQL components, e.g. treating a different column order in the
    SELECT list as equivalent) -- it's a plain string comparison, reported only as a
    secondary, clearly-labelled number (CLAUDE.md: headline metric is EX, never exact
    match). Inflated by a fine-tuned model's tendency to imitate gold SQL formatting
    (spacing, keyword case) more closely than a zero-shot base model would."""
    s = sql.strip().rstrip(";").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def exact_match_rate(predictions: list[str], golds: list[str]) -> float:
    assert len(predictions) == len(golds)
    matches = sum(normalize_sql_for_exact_match(p) == normalize_sql_for_exact_match(g)
                  for p, g in zip(predictions, golds))
    return matches / len(predictions)


def bootstrap_ci(correct: list[bool], n_resamples: int = 1000, ci: float = 0.95, seed: int = 0) -> tuple[float, float, float]:
    """95% bootstrap confidence interval for EX: resample the per-example correctness
    list with replacement n_resamples times, take the mean each time, and report the
    2.5th/97.5th percentile of those means. Captures how much EX would plausibly swing
    if we'd happened to sample a different dev set of the same size."""
    rng = np.random.default_rng(seed)
    arr = np.asarray(correct, dtype=float)
    means = np.array([rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_resamples)])
    lo, hi = np.percentile(means, [(1 - ci) / 2 * 100, (1 + ci) / 2 * 100])
    return float(arr.mean()), float(lo), float(hi)


def compare(correct_a: list[bool], correct_b: list[bool]) -> dict:
    """McNemar's test: is model A's accuracy really different from model B's on the
    same questions, or could the gap be noise? Only looks at examples where exactly one
    model got it right (the "discordant pairs") — if A and B agree, that example carries
    no information about which model is better. With few discordant pairs, uses the exact
    binomial test instead of the chi-square approximation, which is unreliable there."""
    assert len(correct_a) == len(correct_b)
    b = sum(a and not bb for a, bb in zip(correct_a, correct_b))  # A right, B wrong
    c = sum(bb and not a for a, bb in zip(correct_a, correct_b))  # B right, A wrong
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "statistic": None, "p_value": 1.0}
    if n < 25:
        p_value = min(1.0, 2 * stats.binom.cdf(min(b, c), n, 0.5))
        return {"b": b, "c": c, "statistic": None, "p_value": p_value}
    statistic = (abs(b - c) - 1) ** 2 / n
    p_value = 1 - stats.chi2.cdf(statistic, df=1)
    return {"b": b, "c": c, "statistic": statistic, "p_value": p_value}


def official_db_dir(split: str) -> Path:
    """Directory to pass as --db to the official evaluator for plain EX (one sqlite
    file per db_id, no perturbation variants)."""
    if split == "test":
        return SPIDER_DIR / "test_database"
    return SPIDER_DIR / "database"


def official_table_path(split: str) -> Path:
    return SPIDER_DIR / ("test_tables.json" if split == "test" else "tables.json")


def run_official_eval(gold_path, pred_path, db_dir, table_path, etype: str = "exec") -> dict:
    """Shell out to the official evaluator and parse its printed execution-accuracy table.
    Returns EX by difficulty plus overall, e.g. {"easy": .., "medium": .., "hard": ..,
    "extra": .., "all": ..}."""
    result = subprocess.run(
        [sys.executable, "evaluation.py",
         "--gold", str(Path(gold_path).resolve()), "--pred", str(Path(pred_path).resolve()),
         "--db", str(Path(db_dir).resolve()), "--table", str(Path(table_path).resolve()), "--etype", etype],
        cwd=TOOLS_DIR, capture_output=True, text=True, check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("execution"):
            easy, medium, hard, extra, overall = (float(x) for x in line.split()[1:6])
            return {"easy": easy, "medium": medium, "hard": hard, "extra": extra, "all": overall}
    raise RuntimeError("could not find execution accuracy line in official evaluator output:\n" + result.stdout)


def official_ex(gold_path, pred_path, split: str) -> dict:
    """Plain execution accuracy via the official evaluator: valid for any split."""
    return run_official_eval(gold_path, pred_path, official_db_dir(split), official_table_path(split))


def official_per_example_correct(predictions: list[str], examples: list[dict], split: str) -> list[bool]:
    """Per-example correctness using the official evaluator's own exec-match function
    (column-order permutation, DISTINCT removal), not our stricter Counter comparison.
    Lets us compute a 95% CI and McNemar that actually match the official EX number,
    instead of pairing it with a CI from our own (more conservative) evaluator."""
    sys.path.insert(0, str(TOOLS_DIR))
    from exec_eval import eval_exec_match

    db_dir = official_db_dir(split)
    correct = []
    for pred_sql, ex in zip(predictions, examples):
        db = db_dir / ex["db_id"] / f"{ex['db_id']}.sqlite"
        ok = bool(eval_exec_match(
            db=str(db), p_str=pred_sql, g_str=ex["query"],
            plug_value=False, keep_distinct=False, progress_bar_for_each_datapoint=False,
        ))
        correct.append(ok)
    return correct


def official_test_suite_accuracy(gold_path, pred_path) -> dict:
    """Test-suite accuracy via the official evaluator: dev only. The test-suite database
    download only has perturbation variants for dev's 20 databases, not test's 40, so this
    can never be computed for the test split — there's nothing to point --db at."""
    return run_official_eval(gold_path, pred_path, TEST_SUITE_DB_DIR, official_table_path("dev"))


def test_suite_match_one(db_id: str, pred_sql: str, gold_sql: str, timeout: float = 5.0) -> bool:
    """Test-suite match for one example: same comparison rule as the official evaluator
    (column-order permutation, DISTINCT removed, bag semantics unless gold has ORDER BY),
    checked across every perturbed database variant for db_id.

    Runs each query with our own Windows-safe timeout (threading.Timer + conn.interrupt),
    unlike the official evaluator's `asyncio.wait_for`, which can't actually cancel a
    blocking sqlite3 call and also pays the cost of a new event loop per query — the
    combination is why the official evaluator is impractically slow on 1,034 examples.
    """
    sys.path.insert(0, str(TOOLS_DIR))
    from exec_eval import postprocess, result_eq
    from parse import remove_distinct

    p_str, g_str = postprocess(pred_sql), postprocess(gold_sql)
    p_str, g_str = remove_distinct(p_str), remove_distinct(g_str)
    order_matters = "order by" in g_str.lower()

    variant_dir = TEST_SUITE_DB_DIR / db_id
    variants = sorted(variant_dir.glob("*.sqlite"))
    if not variants:
        raise RuntimeError(f"no test-suite database variants found for {db_id} in {variant_dir}")

    for variant in variants:
        gold_rows, gold_err = run_query(variant, g_str, timeout=timeout)
        if gold_err:
            raise RuntimeError(f"gold query failed on test-suite variant {variant}: {gold_err}")
        pred_rows, pred_err = run_query(variant, p_str, timeout=timeout)
        if pred_err is not None:
            return False
        if not result_eq(gold_rows, pred_rows, order_matters=order_matters):
            return False
    return True
