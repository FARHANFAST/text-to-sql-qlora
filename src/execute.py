"""Run a single SQL query against a SQLite database, read-only, with a timeout."""
import sqlite3
import threading
from pathlib import Path


def run_query(db_path: Path | str, query: str, timeout: float = 5.0) -> tuple[list | None, str | None]:
    """Execute `query` read-only against db_path.

    Returns (rows, None) on success, or (None, error_message) on failure (bad SQL,
    a write attempt against the read-only connection, or a timeout).

    The timeout uses a background Timer that calls conn.interrupt() instead of
    SIGALRM, since SIGALRM doesn't exist on Windows.
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        return None, f"connect error: {e}"

    # matches the official test-suite-sql-eval evaluator's handling of databases
    # with invalid UTF-8 bytes (e.g. a corrupted row in wta_1.sqlite)
    conn.text_factory = lambda b: b.decode(errors="ignore")

    timer = threading.Timer(timeout, conn.interrupt)
    timer.start()
    try:
        rows = conn.execute(query).fetchall()
        return rows, None
    except sqlite3.Error as e:
        return None, str(e)
    finally:
        timer.cancel()
        conn.close()
