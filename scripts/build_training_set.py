"""Step 6: build the fine-tuning training set.

Spider train_spider + train_others, prompt v2 (the winner of Step 4+5, no few-shot in
training prompts), chat-formatted with the target SQL as the assistant turn. Holds out
~5% of examples as a validation split, grouped by db_id (whole databases, never split
across train/val) so validation loss reflects unseen schemas, not unseen rows.

Usage:
    python scripts/build_training_set.py
"""
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_utils import check_query_executes, db_ids, load_split  # noqa: E402
from prompts import build_training_example, token_count  # noqa: E402

OUT_DIR = ROOT / "data" / "processed"
VAL_FRACTION = 0.05
SEED = 0
PROMPT_VERSION = "v2"


def collapse_whitespace(sql: str) -> str:
    """Collapse runs of whitespace to a single space (e.g. Spider's "Name ,  Country"
    detokenization artifact -> "Name , Country"). Formatting only, never changes meaning."""
    return re.sub(r"\s+", " ", sql).strip()


def main():
    train_spider = [(ex, "train_spider") for ex in load_split("train_spider")]
    train_others = [(ex, "train_others") for ex in load_split("train_others")]
    combined = train_spider + train_others
    print(f"train_spider: {len(train_spider)}, train_others: {len(train_others)}, "
          f"combined: {len(combined)}")

    train_ids = {ex["db_id"] for ex, _ in combined}
    dev_ids = db_ids(load_split("dev"))
    test_ids = db_ids(load_split("test"))
    overlap_dev = train_ids & dev_ids
    overlap_test = train_ids & test_ids
    print(f"train db_ids: {len(train_ids)}, overlap with dev: {len(overlap_dev)}, "
          f"overlap with test: {len(overlap_test)}")
    assert not overlap_dev, f"train/dev db_id overlap: {overlap_dev}"
    assert not overlap_test, f"train/test db_id overlap: {overlap_test}"

    kept, dropped = [], []
    for ex, split in combined:
        err = check_query_executes(ex["db_id"], split, ex["query"])
        (kept if err is None else dropped).append((ex, split, err))
    print(f"dropped {len(dropped)}/{len(combined)} examples whose gold SQL failed to execute")
    for ex, split, err in [d for d in dropped][:10]:
        print(f"  [{split}] {ex['db_id']}: {err} -- {ex['query']}")
    kept = [(ex, split) for ex, split, _ in kept]

    by_db = {}
    for ex, split in kept:
        by_db.setdefault(ex["db_id"], []).append((ex, split))
    kept_ids = sorted(by_db)
    rng = random.Random(SEED)
    rng.shuffle(kept_ids)

    target_val_n = len(kept) * VAL_FRACTION
    val_ids, val_count = set(), 0
    for db_id in kept_ids:
        if val_count >= target_val_n:
            break
        val_ids.add(db_id)
        val_count += len(by_db[db_id])

    train_rows = [(ex, split) for ex, split in kept if ex["db_id"] not in val_ids]
    val_rows = [(ex, split) for ex, split in kept if ex["db_id"] in val_ids]
    print(f"validation: {len(val_ids)} db_ids, {len(val_rows)} examples "
          f"({len(val_rows) / len(kept):.1%} of kept examples)")
    print(f"train: {len(kept_ids) - len(val_ids)} db_ids, {len(train_rows)} examples")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    full_token_stats = {}
    for name, rows in (("train", train_rows), ("val", val_rows)):
        path = OUT_DIR / f"sft_{name}.jsonl"
        lengths = []
        with open(path, "w", encoding="utf-8") as f:
            for ex, split in rows:
                target = collapse_whitespace(ex["query"])
                built = build_training_example(PROMPT_VERSION, ex, split, target)
                n_prompt = token_count(built["prompt_text"])
                n_full = token_count(built["full_text"])
                lengths.append(n_full)
                f.write(json.dumps({
                    "db_id": ex["db_id"], "split": split, "question": ex["question"],
                    "gold_sql": ex["query"], "target_sql": target,
                    "prompt_text": built["prompt_text"], "full_text": built["full_text"],
                    "prompt_tokens": n_prompt, "full_tokens": n_full,
                }) + "\n")
        full_token_stats[name] = sorted(lengths)
        print(f"wrote {path} ({len(rows)} examples)")

    for name, lengths in full_token_stats.items():
        if not lengths:
            continue
        n = len(lengths)
        print(f"{name} full-sequence tokens: min={lengths[0]} p50={lengths[n // 2]} "
              f"p90={lengths[int(n * 0.9)]} p99={lengths[int(n * 0.99)]} max={lengths[-1]}")

    all_lengths = sorted(full_token_stats["train"] + full_token_stats["val"])
    n = len(all_lengths)
    print(f"\ncombined full-sequence tokens, n={n}:")
    for cutoff in (512, 768, 1024, 1536, 2048):
        n_over = sum(1 for x in all_lengths if x > cutoff)
        print(f"  max_seq_len={cutoff}: {n_over} examples exceed it ({n_over / n:.2%})")


if __name__ == "__main__":
    main()
