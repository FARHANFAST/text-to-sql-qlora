"""Copy the SQLite files a split needs into one folder, ready to zip for Kaggle.

The self-correction notebook executes SQL, so it needs the databases themselves.
Only the .sqlite files are copied (no gold SQL, no schema.sql).

Usage:
    python scripts/prepare_kaggle_databases.py --split dev
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_utils import db_ids, db_path, load_split

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    args = parser.parse_args()

    out_dir = ROOT / "data" / "processed" / "kaggle_upload" / f"{args.split}_databases"
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = sorted(db_ids(load_split(args.split)))
    total = 0
    for db_id in ids:
        src = db_path(db_id, args.split)
        shutil.copy(src, out_dir / f"{db_id}.sqlite")
        total += src.stat().st_size
    print(f"copied {len(ids)} databases ({total / 1e6:.1f} MB) to {out_dir}")
