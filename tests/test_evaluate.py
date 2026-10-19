import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from evaluate import bootstrap_ci, compare, result_sets_match, strip_sql_fences
from execute import run_query

SAMPLE_DB = Path(__file__).resolve().parent / "fixtures" / "sample.sqlite"

# a few questions against the sample db, each as (gold_sql, wrong_sql)
QUESTIONS = [
    ("SELECT name FROM singer WHERE age > 25 ORDER BY name", "SELECT name FROM singer WHERE age > 100"),
    ("SELECT count(*) FROM singer", "SELECT count(*) FROM singer WHERE age < 0"),
    ("SELECT max(age) FROM singer", "SELECT min(age) FROM singer"),
]


def _correct(predictions: list[str], golds: list[str]) -> list[bool]:
    correct = []
    for pred_sql, gold_sql in zip(predictions, golds):
        gold_rows, gold_err = run_query(SAMPLE_DB, gold_sql)
        assert gold_err is None, f"gold query failed: {gold_err}"
        pred_rows, pred_err = run_query(SAMPLE_DB, pred_sql)
        order_matters = "order by" in gold_sql.lower()
        correct.append(pred_err is None and result_sets_match(gold_rows, pred_rows, order_matters))
    return correct


def test_gold_scores_100_percent():
    golds = [g for g, _ in QUESTIONS]
    correct = _correct(golds, golds)
    assert all(correct)
    assert sum(correct) / len(correct) == 1.0


def test_broken_sql_scores_0_percent():
    golds = [g for g, _ in QUESTIONS]
    wrong = [w for _, w in QUESTIONS]
    correct = _correct(wrong, golds)
    assert not any(correct)
    assert sum(correct) / len(correct) == 0.0


def test_markdown_fences_stripped():
    assert strip_sql_fences("```sql\nSELECT 1\n```") == "SELECT 1"
    assert strip_sql_fences("```\nSELECT 1\n```") == "SELECT 1"
    assert strip_sql_fences("SELECT 1") == "SELECT 1"
    assert strip_sql_fences("  ```sql\nSELECT 1\n```  ") == "SELECT 1"


def test_result_sets_match_ignores_order_when_no_order_by():
    assert result_sets_match([(1,), (2,)], [(2,), (1,)], order_matters=False)
    assert not result_sets_match([(1,), (2,)], [(2,), (1,)], order_matters=True)


def test_bootstrap_ci_brackets_the_true_rate():
    correct = [True] * 70 + [False] * 30  # 70% accuracy
    mean, lo, hi = bootstrap_ci(correct, n_resamples=500, seed=0)
    assert mean == 0.7
    assert lo < 0.7 < hi


def test_compare_mcnemar_no_difference_gives_high_p_value():
    a = [True, False, True, False] * 10
    result = compare(a, a)
    assert result["b"] == 0 and result["c"] == 0
    assert result["p_value"] == 1.0


def test_compare_mcnemar_detects_clear_difference():
    a = [True] * 20 + [False] * 5  # 20 right
    b = [False] * 20 + [False] * 5  # 0 right, all discordant pairs favor a
    result = compare(a, b)
    assert result["b"] == 20
    assert result["c"] == 0
    assert result["p_value"] < 0.05
