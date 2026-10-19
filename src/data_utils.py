"""Loading Spider splits, gold SQL, and database paths."""
import json
import sqlite3
from pathlib import Path

SPIDER_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "spider" / "spider_data"

# which database folder each split's examples execute against
SPLIT_DB_FOLDER = {
    "train_spider": "database",
    "train_others": "database",
    "dev": "database",
    "test": "test_database",
}


def load_split(name: str) -> list[dict]:
    """Load one Spider split by file stem: train_spider, train_others, dev, or test."""
    path = SPIDER_DIR / f"{name}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def db_ids(examples: list[dict]) -> set[str]:
    return {ex["db_id"] for ex in examples}


def db_path(db_id: str, split: str) -> Path:
    """Path to the sqlite file for db_id, in the folder used by `split`."""
    folder = SPLIT_DB_FOLDER[split]
    return SPIDER_DIR / folder / db_id / f"{db_id}.sqlite"


def all_db_ids(split: str) -> set[str]:
    """Every db_id present in the given split's database folder (not just the ones used by its examples)."""
    folder = SPIDER_DIR / SPLIT_DB_FOLDER[split]
    return {p.name for p in folder.iterdir() if p.is_dir()}


def check_query_executes(db_id: str, split: str, query: str, timeout: float = 5.0) -> str | None:
    """Run query read-only against db_id's sqlite file. Returns None on success, else the error message."""
    path = db_path(db_id, split)
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout)
        # matches the official evaluator (exec_eval.py) so the two agree on databases
        # with invalid UTF-8 bytes, e.g. a corrupted row in wta_1.sqlite
        conn.text_factory = lambda b: b.decode(errors="ignore")
        try:
            conn.execute(query).fetchall()
        finally:
            conn.close()
        return None
    except sqlite3.Error as e:
        return str(e)
