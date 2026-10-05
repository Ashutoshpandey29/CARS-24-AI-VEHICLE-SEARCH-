"""SQLite access.

Each worker thread keeps one read-only connection open instead of opening a
new one per request. The API never writes, so connections are safe to share
across requests on the same thread.
"""
import sqlite3
import threading

from app.config import get_settings

_local = threading.local()


def _connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    con.execute("PRAGMA mmap_size = 268435456")  # 256 MB, lets reads skip the page cache copy
    con.execute("PRAGMA cache_size = -65536")  # 64 MB per connection
    con.execute("PRAGMA temp_store = MEMORY")
    return con


def get_connection() -> sqlite3.Connection:
    path = get_settings().db_path
    con = getattr(_local, "con", None)
    if con is None or getattr(_local, "path", None) != path:
        con = _connect(path)
        _local.con, _local.path = con, path
    return con


def ping() -> bool:
    try:
        get_connection().execute("SELECT 1 FROM cars LIMIT 1")
        return True
    except sqlite3.Error:
        return False
