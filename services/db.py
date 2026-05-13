"""
KOBİ AI Platform — SQLite Bağlantı Yöneticisi
SQL Server (pyodbc) yerine SQLite kullanır.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DB_PATH: Optional[str] = None
_local = threading.local()


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        from config.settings import get_settings
        _DB_PATH = get_settings().sqlite_db_path
    return _DB_PATH


def get_conn() -> sqlite3.Connection:
    """Her thread için tek bağlantı (thread-local)."""
    path = get_db_path()
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _open(path)
    # Bağlantı kapanmış olabilir
    try:
        _local.conn.execute("SELECT 1")
    except Exception:
        _local.conn = _open(path)
    return _local.conn


def _open(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-32000")
    return conn


def query(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    """SELECT sorgusu — dict listesi döner."""
    conn = get_conn()
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def execute(sql: str, params: Tuple = ()) -> int:
    """INSERT/UPDATE/DELETE — etkilenen satır sayısı döner."""
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount


def execute_lastrowid(sql: str, params: Tuple = ()) -> Optional[int]:
    """INSERT — eklenen satırın ID'sini döner."""
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def executemany(sql: str, params_list) -> int:
    conn = get_conn()
    cur = conn.executemany(sql, params_list)
    conn.commit()
    return cur.rowcount
