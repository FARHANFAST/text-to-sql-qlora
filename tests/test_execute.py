import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from execute import run_query

SAMPLE_DB = Path(__file__).resolve().parent / "fixtures" / "sample.sqlite"


def test_run_query_success():
    rows, err = run_query(SAMPLE_DB, "SELECT name FROM singer WHERE age > 25 ORDER BY name")
    assert err is None
    assert rows == [("Alice",), ("Bob",)]


def test_run_query_bad_sql_returns_error():
    rows, err = run_query(SAMPLE_DB, "SELECT * FROM no_such_table")
    assert rows is None
    assert err is not None


def test_run_query_write_rejected():
    rows, err = run_query(SAMPLE_DB, "DELETE FROM singer")
    assert rows is None
    assert "readonly" in err


def test_run_query_timeout():
    start = time.time()
    rows, err = run_query(
        SAMPLE_DB,
        "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt) SELECT count(*) FROM cnt",
        timeout=0.5,
    )
    elapsed = time.time() - start
    assert rows is None
    assert err is not None
    assert elapsed < 3.0  # didn't hang
