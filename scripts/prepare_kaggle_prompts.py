"""Strip gold SQL out of the dev prompt files before uploading to Kaggle.

Kaggle only needs db_id, question, and the rendered prompt to run inference.
Gold SQL stays local so it never has to be trusted to a remote notebook.
"""
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
OUT_DIR = SRC_DIR / "kaggle_upload"

def _strip_gold(src, out):
    with open(src, encoding="utf-8") as fin, open(out, "w", encoding="utf-8") as fout:
        for idx, line in enumerate(fin):
            row = json.loads(line)
            fout.write(json.dumps({
                "idx": idx, "db_id": row["db_id"], "question": row["question"], "prompt": row["prompt"],
            }) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for version in ("v1", "v2", "v3"):
        _strip_gold(SRC_DIR / f"prompts_{version}_dev.jsonl", OUT_DIR / f"prompts_{version}_dev.jsonl")
    # test: v2 only (the chosen prompt version) -- built once, not run until the final
    # fine-tuned model is picked (CLAUDE.md's dev-vs-test rule).
    _strip_gold(SRC_DIR / "prompts_v2_test.jsonl", OUT_DIR / "prompts_v2_test.jsonl")
