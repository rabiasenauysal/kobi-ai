"""
KOBİ AI Platform — SQLite Sorgu Çalıştırıcı
pyodbc/SQL Server yerine sqlite3 kullanır.
"""

import sqlite3
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, date
import decimal

from services.db import get_conn


@dataclass
class QueryResult:
    success: bool
    data: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    execution_time_ms: float
    visualization_type: str
    error: Optional[str] = None


class SQLExecutor:

    def __init__(self):
        print("✅ SQLExecutor (SQLite) başlatıldı")

    def execute_query(self, sql: str, forced_viz_type: str = None) -> QueryResult:
        start = datetime.now()
        try:
            clean_sql = self._preprocess(sql)
            conn = get_conn()
            cur = conn.execute(clean_sql)

            if cur.description is None:
                return QueryResult(
                    success=True, data=[], columns=[], row_count=0,
                    execution_time_ms=self._ms(start),
                    visualization_type="table",
                )

            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()

            data = []
            for row in rows:
                row_dict = {}
                for i, val in enumerate(row):
                    if isinstance(val, (datetime, date)):
                        row_dict[columns[i]] = val.isoformat()
                    elif isinstance(val, decimal.Decimal):
                        row_dict[columns[i]] = float(val)
                    elif isinstance(val, bytes):
                        row_dict[columns[i]] = val.decode("utf-8", errors="ignore")
                    else:
                        row_dict[columns[i]] = val
                data.append(row_dict)

            ms = self._ms(start)
            viz = forced_viz_type or self.determine_visualization_type(data, columns)

            return QueryResult(
                success=True, data=data, columns=columns,
                row_count=len(data), execution_time_ms=ms,
                visualization_type=viz,
            )

        except Exception as e:
            return QueryResult(
                success=False, data=[], columns=[], row_count=0,
                execution_time_ms=self._ms(start),
                visualization_type="error", error=str(e),
            )

    # ── SQL Ön İşleme (MSSQL → SQLite uyumluluk katmanı) ────────────────────

    def _preprocess(self, sql: str) -> str:
        """MSSQL kalıplarını SQLite'a çevir."""
        # TOP N → LIMIT N (SELECT TOP N ... → SELECT ... LIMIT N)
        sql = re.sub(
            r'\bSELECT\s+TOP\s*\(?\s*(\d+)\s*\)?',
            r'SELECT',
            sql, flags=re.IGNORECASE
        )
        # TOP N'i LIMIT olarak ekle (basit durum — subquery değilse)
        top_match = re.search(r'TOP\s*\(?\s*(\d+)\s*\)?', sql, re.IGNORECASE)
        if top_match:
            n = top_match.group(1)
            sql = re.sub(r'\bTOP\s*\(?\s*\d+\s*\)?', '', sql, flags=re.IGNORECASE)
            if 'LIMIT' not in sql.upper():
                sql = sql.rstrip('; \n') + f' LIMIT {n}'

        # ISNULL → COALESCE
        sql = re.sub(r'\bISNULL\s*\(', 'COALESCE(', sql, flags=re.IGNORECASE)

        # GETDATE() → date('now')
        sql = re.sub(r'\bGETDATE\s*\(\s*\)', "date('now')", sql, flags=re.IGNORECASE)

        # DATEADD(DAY, -N, date) → date(date, '-N days')
        def _dateadd(m):
            unit = m.group(1).lower()
            n = m.group(2)
            col = m.group(3).strip()
            sqlite_unit = {"day": "days", "month": "months", "year": "years"}.get(unit, "days")
            sign = "" if n.startswith("-") else "+"
            return f"date({col}, '{sign}{n} {sqlite_unit}')"

        sql = re.sub(
            r'\bDATEADD\s*\(\s*(DAY|MONTH|YEAR)\s*,\s*(-?\d+)\s*,\s*([^)]+)\)',
            _dateadd, sql, flags=re.IGNORECASE
        )

        # YEAR(col) → strftime('%Y', col)
        sql = re.sub(r'\bYEAR\s*\(([^)]+)\)', r"CAST(strftime('%Y', \1) AS INTEGER)", sql, flags=re.IGNORECASE)

        # MONTH(col) → strftime('%m', col)
        sql = re.sub(r'\bMONTH\s*\(([^)]+)\)', r"CAST(strftime('%m', \1) AS INTEGER)", sql, flags=re.IGNORECASE)

        # DAY(col) → strftime('%d', col)
        sql = re.sub(r'\bDAY\s*\(([^)]+)\)', r"CAST(strftime('%d', \1) AS INTEGER)", sql, flags=re.IGNORECASE)

        # STRING_AGG → group_concat
        sql = re.sub(r'\bSTRING_AGG\s*\(', 'group_concat(', sql, flags=re.IGNORECASE)

        # CONVERT(varchar..., col, 120) → strftime('%Y-%m-%d', col)
        sql = re.sub(
            r'\bCONVERT\s*\(\s*varchar\s*\([^)]+\)\s*,\s*([^,]+),\s*120\s*\)',
            r"strftime('%Y-%m-%d', \1)", sql, flags=re.IGNORECASE
        )

        # [dbo]. prefix kaldır
        sql = re.sub(r'\[?dbo\]?\.', '', sql, flags=re.IGNORECASE)

        # COLLATE Turkish_CI_AS kaldır (SQLite desteklemez)
        sql = re.sub(r'\s+COLLATE\s+Turkish_CI_AS', '', sql, flags=re.IGNORECASE)

        # CAST(x AS DECIMAL(p,s)) → ROUND(x, s)
        sql = re.sub(
            r'\bCAST\s*\(([^)]+)\s+AS\s+DECIMAL\s*\(\s*\d+\s*,\s*(\d+)\s*\)\s*\)',
            lambda m: f'ROUND({m.group(1)}, {m.group(2)})',
            sql, flags=re.IGNORECASE
        )

        # SCOPE_IDENTITY() → last_insert_rowid()
        sql = re.sub(r'\bSCOPE_IDENTITY\s*\(\s*\)', 'last_insert_rowid()', sql, flags=re.IGNORECASE)

        return sql.strip()

    def _ms(self, start: datetime) -> float:
        return (datetime.now() - start).total_seconds() * 1000

    def determine_visualization_type(self, data: List[Dict], columns: List[str]) -> str:
        if not data:
            return "table"

        col_count = len(columns)
        row_count = len(data)

        numeric_cols, text_cols, year_cols = [], [], []

        for col in columns:
            samples = [row.get(col) for row in data[:5] if row.get(col) is not None]
            if not samples:
                text_cols.append(col)
                continue
            is_num = all(isinstance(v, (int, float)) for v in samples)
            if is_num:
                is_year = all(isinstance(v, (int, float)) and 2000 <= int(v) <= 2100 for v in samples)
                if is_year and col.lower() in ("yil", "yıl", "year", "ay"):
                    year_cols.append(col)
                else:
                    numeric_cols.append(col)
            else:
                text_cols.append(col)

        if col_count == 1 and len(numeric_cols) == 1:
            return "table"
        if col_count == 2 and len(text_cols) == 1 and len(numeric_cols) == 1:
            return "pie" if row_count <= 7 else "bar"
        if col_count == 2 and year_cols and numeric_cols:
            return "line"
        if col_count >= 3:
            if year_cols and numeric_cols:
                return "line"
            if text_cols and columns[0] in text_cols and len(numeric_cols) >= 2:
                return "bar"
            if len(text_cols) >= 1 and len(numeric_cols) == 1:
                return "pie" if row_count <= 7 else "bar"
        if len(numeric_cols) == col_count:
            return "bar"
        return "table"
