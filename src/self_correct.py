"""Self-correction loop: generate SQL, execute it, and retry when it fails.

The loop only uses signals that exist at inference time: the SQLite error message,
or the fact that the query returned no rows. It never sees gold SQL or gold results.

It doesn't know how the SQL is generated. The caller passes `generate_fn`, so the same
loop runs on a GPU with batched generate or on a CPU with llama.cpp.
"""
import time

from execute import run_query
from postprocess import strip_sql_fences

MAX_RETRIES = 2

# feedback modes: what the model is told after a failed attempt
#   "plain": only that the query was wrong
#   "error": the SQLite error message (or that the result was empty)
MODES = ("plain", "error")

PLAIN_FEEDBACK = "That query is not right. Write a corrected SQLite query. Reply with only the SQL query."
ERROR_FEEDBACK = (
    "That query failed with this error: {error}\n"
    "Write a corrected SQLite query. Reply with only the SQL query."
)
EMPTY_FEEDBACK = (
    "That query ran but returned no rows. If the question should have an answer, "
    "write a corrected SQLite query. Reply with only the SQL query."
)


def error_type(error: str) -> str:
    """Bucket a SQLite error message into one of four simple types."""
    e = error.lower()
    if "no such column" in e:
        return "wrong column"
    if "no such table" in e:
        return "wrong table"
    if "syntax error" in e or "incomplete input" in e or "unrecognized token" in e:
        return "syntax"
    return "other"


def execute_attempt(db_path, sql: str, timeout: float = 5.0) -> dict:
    """Run one attempt. status is "ok" (rows came back), "empty" (ran, no rows) or "error"."""
    start = time.time()
    rows, error = run_query(db_path, sql, timeout)
    exec_time = time.time() - start
    if error is not None:
        return {"status": "error", "error": error, "exec_time_sec": exec_time}
    return {"status": "ok" if rows else "empty", "error": None, "exec_time_sec": exec_time}


def feedback_for(attempt: dict, mode: str) -> str:
    if mode == "plain":
        return PLAIN_FEEDBACK
    if attempt["status"] == "error":
        return ERROR_FEEDBACK.format(error=attempt["error"])
    return EMPTY_FEEDBACK


def build_retry_prompt(prompt: str, failed_output: str, feedback: str) -> str:
    """Extend a ChatML prompt with the failed answer and a feedback turn.

    `prompt` ends with "<|im_start|>assistant\\n", so the failed output goes in as that
    assistant turn, followed by a new user turn. This is the same text Qwen's chat
    template produces for [..., assistant, user] with add_generation_prompt=True.
    """
    return (
        f"{prompt}{failed_output}<|im_end|>\n"
        f"<|im_start|>user\n{feedback}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def needs_retry(attempt: dict, retry_on_empty: bool) -> bool:
    return attempt["status"] == "error" or (retry_on_empty and attempt["status"] == "empty")


def pick_final(attempts: list[dict]) -> int:
    """Index of the attempt to return: the latest one that executed without an error.

    A retry never replaces a query that ran with one that crashes. If every attempt
    errored, return the last one.
    """
    for i in range(len(attempts) - 1, -1, -1):
        if attempts[i]["status"] != "error":
            return i
    return len(attempts) - 1


def run_self_correction(rows, first_outputs, generate_fn, db_path_fn, mode,
                        retry_on_empty=False, max_retries=MAX_RETRIES, execute_fn=execute_attempt):
    """Run the retry loop for a list of questions, one retry round at a time.

    rows:          [{"idx", "db_id", "question", "prompt"}], prompt already chat-templated
    first_outputs: [{"raw_output", "gen_time_sec"}], the first attempt for each row
    generate_fn:   list of prompts -> list of {"raw_output", "gen_time_sec"}
    db_path_fn:    db_id -> path of its sqlite file

    Working by round (not by question) lets a GPU generate all retries of a round in
    one batch. Returns one record per row with every attempt and the final SQL.
    """
    assert mode in MODES, f"unknown mode: {mode}"

    def make_attempt(row, output, feedback):
        sql = strip_sql_fences(output["raw_output"])
        attempt = {"raw_output": output["raw_output"], "sql": sql,
                   "gen_time_sec": output["gen_time_sec"], "feedback_given": feedback}
        attempt.update(execute_fn(db_path_fn(row["db_id"]), sql))
        return attempt

    attempts = [[make_attempt(row, out, None)] for row, out in zip(rows, first_outputs)]
    prompts = [row["prompt"] for row in rows]

    for _ in range(max_retries):
        todo = [i for i, a in enumerate(attempts) if needs_retry(a[-1], retry_on_empty)]
        if not todo:
            break
        feedbacks = [feedback_for(attempts[i][-1], mode) for i in todo]
        for i, feedback in zip(todo, feedbacks):
            prompts[i] = build_retry_prompt(prompts[i], attempts[i][-1]["raw_output"], feedback)
        outputs = generate_fn([prompts[i] for i in todo])
        for i, output, feedback in zip(todo, outputs, feedbacks):
            attempts[i].append(make_attempt(rows[i], output, feedback))

    records = []
    for row, row_attempts in zip(rows, attempts):
        final = pick_final(row_attempts)
        records.append({
            "idx": row["idx"], "db_id": row["db_id"], "question": row["question"],
            # raw_output / gen_time_sec keep the same meaning as in the plain predictions
            # files, so scripts/evaluate_experiment.py reads this file unchanged
            "raw_output": row_attempts[final]["raw_output"],
            "gen_time_sec": sum(a["gen_time_sec"] for a in row_attempts),
            "exec_time_sec": sum(a["exec_time_sec"] for a in row_attempts),
            "n_attempts": len(row_attempts), "final_attempt": final,
            "attempts": row_attempts,
        })
    return records
