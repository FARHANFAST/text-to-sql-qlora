import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from self_correct import build_retry_prompt, error_type, pick_final, run_self_correction

SAMPLE_DB = Path(__file__).resolve().parent / "fixtures" / "sample.sqlite"

GOOD = "SELECT name FROM singer"
BROKEN = "SELECT nam FROM singer"
EMPTY = "SELECT name FROM singer WHERE age > 1000"

ROWS = [{"idx": 0, "db_id": "sample", "question": "List the singer names.",
         "prompt": "<|im_start|>user\nq<|im_end|>\n<|im_start|>assistant\n"}]


def out(sql):
    return {"raw_output": sql, "gen_time_sec": 0.1}


def run(first_sql, retry_sqls, mode="error", retry_on_empty=False):
    """Run the loop with a scripted model that returns retry_sqls in order."""
    seen_prompts = []
    replies = iter(retry_sqls)

    def generate_fn(prompts):
        seen_prompts.extend(prompts)
        return [out(next(replies)) for _ in prompts]

    records = run_self_correction(ROWS, [out(first_sql)], generate_fn, lambda db_id: SAMPLE_DB,
                                  mode=mode, retry_on_empty=retry_on_empty)
    return records[0], seen_prompts


def test_no_retry_when_first_attempt_runs():
    rec, prompts = run(GOOD, [])
    assert rec["n_attempts"] == 1 and prompts == []
    assert rec["raw_output"] == GOOD


def test_error_is_retried_and_fixed():
    rec, prompts = run(BROKEN, [GOOD])
    assert rec["n_attempts"] == 2
    assert rec["raw_output"] == GOOD
    assert rec["attempts"][0]["status"] == "error"
    assert rec["gen_time_sec"] == 0.2


def test_stops_after_two_retries():
    rec, prompts = run(BROKEN, [BROKEN, BROKEN, GOOD])
    assert rec["n_attempts"] == 3
    assert rec["attempts"][-1]["status"] == "error"


def test_error_mode_shows_the_error_and_plain_mode_does_not():
    _, error_prompts = run(BROKEN, [GOOD], mode="error")
    _, plain_prompts = run(BROKEN, [GOOD], mode="plain")
    assert "no such column: nam" in error_prompts[0]
    assert "no such column" not in plain_prompts[0]
    assert BROKEN in plain_prompts[0]


def test_empty_result_only_retried_when_asked():
    rec, _ = run(EMPTY, [GOOD], retry_on_empty=False)
    assert rec["n_attempts"] == 1
    rec, _ = run(EMPTY, [GOOD], retry_on_empty=True)
    assert rec["n_attempts"] == 2 and rec["raw_output"] == GOOD


def test_retry_that_errors_does_not_replace_a_query_that_ran():
    rec, _ = run(EMPTY, [BROKEN, BROKEN], retry_on_empty=True)
    assert rec["n_attempts"] == 3
    assert rec["raw_output"] == EMPTY


def test_pick_final_falls_back_to_last_attempt_when_all_error():
    assert pick_final([{"status": "error"}, {"status": "error"}]) == 1


def test_retry_prompt_is_valid_chatml():
    prompt = build_retry_prompt(ROWS[0]["prompt"], BROKEN, "try again")
    assert prompt == (
        "<|im_start|>user\nq<|im_end|>\n<|im_start|>assistant\n"
        f"{BROKEN}<|im_end|>\n<|im_start|>user\ntry again<|im_end|>\n<|im_start|>assistant\n"
    )


def test_error_type():
    assert error_type("no such column: T2.name") == "wrong column"
    assert error_type("no such table: tournaments") == "wrong table"
    assert error_type('near "FROM": syntax error') == "syntax"
    assert error_type("misuse of aggregate: count()") == "other"


def test_notebook_copies_match_src():
    # the Kaggle notebook can't import from src/, so it carries copies of these files
    nb = json.loads((ROOT / "kaggle" / "09_self_correction.ipynb").read_text(encoding="utf-8"))
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for name in ("postprocess.py", "execute.py", "self_correct.py"):
        header = f"%%writefile {name}\n"
        cell = next(c for c in cells if c.startswith(header))
        src = (ROOT / "src" / name).read_text(encoding="utf-8")
        assert cell[len(header):].strip() == src.strip(), f"{name} in the notebook is out of date"
