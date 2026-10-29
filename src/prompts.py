"""Prompt builders for text-to-SQL, versioned v1/v2/v3.

v1: schema as CREATE TABLE statements (no foreign keys), then the question, then "SQL:"
v2: v1 plus a foreign keys list and up to 3 sample rows per table
v3: v2 plus 3 fixed few-shot examples (schema+question+SQL turns), taken from train only

Schema info (columns, types, primary/foreign keys, sample rows) is read straight from
each SQLite database via PRAGMA, not from tables.json, so types and keys always match
what the model will actually be able to query.
"""
import sqlite3

from data_utils import db_path

MODEL_NAME = "Qwen/Qwen2.5-Coder-1.5B-Instruct"

SYSTEM_PROMPT = (
    "You are a SQL expert. Given a database schema and a question, write a single "
    "SQLite query that answers the question. Reply with only the SQL query, no explanation."
)

# fixed few-shot examples for v3, picked from train for pattern diversity
# (a plain WHERE filter, a GROUP BY aggregation, and a JOIN), kept short on purpose.
FEW_SHOT_EXAMPLES = [
    {"db_id": "department_management", "split": "train_spider",
     "question": "How many heads of the departments are older than 56 ?",
     "query": "SELECT count(*) FROM head WHERE age  >  56"},
    {"db_id": "farm", "split": "train_spider",
     "question": "Please show the different statuses of cities and the average population of cities with each status.",
     "query": "SELECT Status ,  avg(Population) FROM city GROUP BY Status"},
    {"db_id": "musical", "split": "train_spider",
     "question": "Show names of actors and names of musicals they are in.",
     "query": "SELECT T1.Name ,  T2.Name FROM actor AS T1 JOIN musical AS T2 ON T1.Musical_ID  =  T2.Musical_ID"},
]


def _connect(db_id: str, split: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path(db_id, split)}?mode=ro", uri=True)
    conn.text_factory = lambda b: b.decode(errors="ignore")
    return conn


def _table_names(db_id: str, split: str) -> list[str]:
    conn = _connect(db_id, split)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _table_info(db_id: str, split: str, table: str) -> list[tuple]:
    """(cid, name, type, notnull, dflt_value, pk_position) per column, in declaration order."""
    conn = _connect(db_id, split)
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    conn.close()
    return rows


def _foreign_keys(db_id: str, split: str, table: str) -> list[tuple[str, str, str]]:
    """(from_col, to_table, to_col) per foreign key defined on `table`."""
    conn = _connect(db_id, split)
    rows = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
    conn.close()
    return [(r[3], r[2], r[4]) for r in rows]


def _sample_rows(db_id: str, split: str, table: str, n: int = 3) -> tuple[list[str], list[tuple]]:
    conn = _connect(db_id, split)
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
    rows = conn.execute(f'SELECT * FROM "{table}" LIMIT {n}').fetchall()
    conn.close()
    return cols, rows


def _create_table_sql(db_id: str, split: str, table: str) -> str:
    cols = _table_info(db_id, split, table)
    lines = [f'  "{name}" {ctype}' for _, name, ctype, _, _, _ in cols]
    pk_cols = [name for _, name, _, _, _, pk in sorted(cols, key=lambda c: c[5]) if pk > 0]
    if pk_cols:
        lines.append("  PRIMARY KEY (" + ", ".join(f'"{p}"' for p in pk_cols) + ")")
    return f'CREATE TABLE "{table}" (\n' + ",\n".join(lines) + "\n)"


def schema_v1(db_id: str, split: str) -> str:
    return "\n\n".join(_create_table_sql(db_id, split, t) for t in _table_names(db_id, split))


def schema_v2(db_id: str, split: str) -> str:
    tables = _table_names(db_id, split)
    blocks = []
    fk_lines = []
    for t in tables:
        block = _create_table_sql(db_id, split, t)
        cols, rows = _sample_rows(db_id, split, t)
        if rows:
            header = "\t".join(cols)
            sample = "\n".join("\t".join(str(v) for v in row) for row in rows)
            block += f"\n/*\n{len(rows)} example rows from {t}:\n{header}\n{sample}\n*/"
        blocks.append(block)
        for from_col, to_table, to_col in _foreign_keys(db_id, split, t):
            fk_lines.append(f"-- {t}.{from_col} = {to_table}.{to_col}")
    schema_text = "\n\n".join(blocks)
    if fk_lines:
        schema_text += "\n\n-- Foreign keys:\n" + "\n".join(fk_lines)
    return schema_text


def _user_turn(schema_text: str, question: str) -> str:
    return f"{schema_text}\n\nQuestion: {question}\nSQL:"


def build_messages(version: str, example: dict, split: str) -> list[dict]:
    """Chat messages for one example, under prompt version v1/v2/v3.

    example needs at least 'db_id' and 'question'. split says which database folder
    the target example's db_id lives in (dev uses 'dev', train uses 'train_spider' etc.).
    """
    if version not in ("v1", "v2", "v3"):
        raise ValueError(f"unknown prompt version: {version}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if version == "v3":
        for shot in FEW_SHOT_EXAMPLES:
            shot_schema = schema_v2(shot["db_id"], shot["split"])
            messages.append({"role": "user", "content": _user_turn(shot_schema, shot["question"])})
            messages.append({"role": "assistant", "content": shot["query"]})

    schema_text = schema_v1(example["db_id"], split) if version == "v1" else schema_v2(example["db_id"], split)
    messages.append({"role": "user", "content": _user_turn(schema_text, example["question"])})
    return messages


_tokenizer = None


def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    return _tokenizer


def build_prompt(version: str, example: dict, split: str) -> str:
    """Full prompt text, exactly as the model will see it after the chat template."""
    messages = build_messages(version, example, split)
    tok = get_tokenizer()
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def build_training_example(version: str, example: dict, split: str, target_sql: str) -> dict:
    """Prompt text and full (prompt + target) text for one training example.

    `prompt_text` is an exact prefix of `full_text` (both end the same way up through
    "<|im_start|>assistant\\n"), so Step 7 can tokenize both, take their token-count
    difference, and mask that many leading tokens out of the loss — training on the SQL
    tokens only, not the prompt.
    """
    messages = build_messages(version, example, split)
    tok = get_tokenizer()
    prompt_text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    full_text = tok.apply_chat_template(
        messages + [{"role": "assistant", "content": target_sql}], tokenize=False, add_generation_prompt=False
    )
    assert full_text.startswith(prompt_text), "chat template broke the prompt/target prefix invariant"
    return {"prompt_text": prompt_text, "full_text": full_text}


def token_count(text: str) -> int:
    return len(get_tokenizer()(text)["input_ids"])


if __name__ == "__main__":
    import json
    from pathlib import Path

    from data_utils import load_split

    out_dir = Path(__file__).resolve().parents[1] / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    dev = load_split("dev")

    for version in ("v1", "v2", "v3"):
        lengths = []
        path = out_dir / f"prompts_{version}_dev.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for ex in dev:
                text = build_prompt(version, ex, "dev")
                n = token_count(text)
                lengths.append(n)
                f.write(json.dumps({
                    "db_id": ex["db_id"], "question": ex["question"], "gold_sql": ex["query"],
                    "prompt": text, "tokens": n,
                }) + "\n")
        lengths.sort()
        mid = lengths[len(lengths) // 2]
        print(f"{version}: wrote {path} | min={lengths[0]} median={mid} max={lengths[-1]}")

    # Test prompts (v2 only -- the chosen prompt version): built now so the upload is ready,
    # but the test set itself gets run exactly once per final model, per CLAUDE.md's
    # dev-vs-test rule. Gold SQL stays in this file (kept local, stripped before upload by
    # scripts/prepare_kaggle_prompts.py), same pattern as the dev prompt files.
    test = load_split("test")
    lengths = []
    path = out_dir / "prompts_v2_test.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for ex in test:
            text = build_prompt("v2", ex, "test")
            n = token_count(text)
            lengths.append(n)
            f.write(json.dumps({
                "db_id": ex["db_id"], "question": ex["question"], "gold_sql": ex["query"],
                "prompt": text, "tokens": n,
            }) + "\n")
    lengths.sort()
    mid = lengths[len(lengths) // 2]
    print(f"v2 (test): wrote {path} | min={lengths[0]} median={mid} max={lengths[-1]}")
