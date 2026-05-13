"""
KOBİ AI Platform — Usage Logger (SQLite)
pyodbc/SQL Server yerine sqlite3 kullanır.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from services.db import query, execute, execute_lastrowid, get_conn


# ─── DDL ─────────────────────────────────────────────────────────────────────

_DDL_USAGE_LOGS = """
CREATE TABLE IF NOT EXISTS ChatbotUsageLogs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    question              TEXT NOT NULL,
    status                TEXT DEFAULT 'pending',
    user_id               TEXT,
    user_ip               TEXT,
    session_id            TEXT,
    generated_sql         TEXT,
    sql_execution_time_ms REAL,
    row_count             INTEGER,
    ai_model              TEXT,
    prompt_tokens         INTEGER,
    completion_tokens     INTEGER,
    total_tokens          INTEGER,
    estimated_cost        REAL,
    response_time_ms      REAL,
    error_message         TEXT,
    error_type            TEXT,
    user_feedback         TEXT,
    feedback_comment      TEXT,
    extra_data            TEXT,
    created_at            TEXT DEFAULT (datetime('now'))
)
"""

_DDL_CHAT_MESSAGES = """
CREATE TABLE IF NOT EXISTS ChatMessages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    client_id  TEXT,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    sql_query  TEXT,
    row_count  INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
)
"""


# ─── Data Class ──────────────────────────────────────────────────────────────

@dataclass
class UsageLogData:
    question:              str   = ""
    status:                str   = "pending"
    user_id:               Optional[str]   = None
    user_ip:               Optional[str]   = None
    session_id:            Optional[str]   = None
    generated_sql:         Optional[str]   = None
    sql_execution_time_ms: Optional[float] = None
    row_count:             Optional[int]   = None
    ai_model:              Optional[str]   = None
    prompt_tokens:         Optional[int]   = None
    completion_tokens:     Optional[int]   = None
    total_tokens:          Optional[int]   = None
    estimated_cost:        Optional[float] = None
    response_time_ms:      Optional[float] = None
    error_message:         Optional[str]   = None
    error_type:            Optional[str]   = None
    user_feedback:         Optional[str]   = None
    feedback_comment:      Optional[str]   = None
    extra_data:            Optional[str]   = None


# ─── Logger ──────────────────────────────────────────────────────────────────

class UsageLogger:

    _COST_TABLE = {
        "gpt-4o":        (0.005,   0.015),
        "gpt-4o-mini":   (0.00015, 0.0006),
        "gpt-4-turbo":   (0.01,    0.03),
        "gpt-4":         (0.03,    0.06),
        "gpt-3.5-turbo": (0.0005,  0.0015),
    }

    def __init__(self):
        self._ensure_tables()
        print("✅ UsageLogger (SQLite) başlatıldı")

    def _ensure_tables(self) -> None:
        conn = get_conn()
        conn.execute(_DDL_USAGE_LOGS)
        conn.execute(_DDL_CHAT_MESSAGES)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_log_session ON ChatbotUsageLogs(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON ChatMessages(session_id)")
        conn.commit()

    # ── Log Kayıt ─────────────────────────────────────────────────────────────

    def log_usage(self, log_data: UsageLogData) -> Optional[int]:
        try:
            if log_data.total_tokens and not log_data.estimated_cost:
                log_data.estimated_cost = self._calculate_cost(
                    log_data.ai_model or "gpt-4o-mini",
                    log_data.prompt_tokens or 0,
                    log_data.completion_tokens or 0,
                )
            return execute_lastrowid(
                """INSERT INTO ChatbotUsageLogs
                   (question, status, user_id, user_ip, session_id,
                    generated_sql, sql_execution_time_ms, row_count,
                    ai_model, prompt_tokens, completion_tokens, total_tokens,
                    estimated_cost, response_time_ms, error_message, error_type, extra_data)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    (log_data.question or "")[:1000],
                    log_data.status,
                    log_data.user_id, log_data.user_ip, log_data.session_id,
                    log_data.generated_sql,
                    log_data.sql_execution_time_ms, log_data.row_count,
                    log_data.ai_model,
                    log_data.prompt_tokens, log_data.completion_tokens,
                    log_data.total_tokens, log_data.estimated_cost,
                    log_data.response_time_ms,
                    log_data.error_message, log_data.error_type,
                    log_data.extra_data,
                ),
            )
        except Exception as e:
            print(f"❌ Log kaydetme hatası: {e}")
            return None

    # ── Feedback ──────────────────────────────────────────────────────────────

    def update_feedback(self, log_id: int, feedback: str, comment: Optional[str] = None) -> bool:
        try:
            execute(
                "UPDATE ChatbotUsageLogs SET user_feedback=?, feedback_comment=? WHERE id=?",
                (feedback, comment, log_id),
            )
            return True
        except Exception as e:
            print(f"❌ Feedback güncelleme hatası: {e}")
            return False

    # ── Chat Mesajları ────────────────────────────────────────────────────────

    def save_message(
        self,
        session_id: str,
        client_id: Optional[str],
        role: str,
        content: str,
        sql_query: Optional[str] = None,
        row_count: Optional[int] = None,
    ) -> None:
        try:
            execute(
                """INSERT INTO ChatMessages (session_id, client_id, role, content, sql_query, row_count)
                   VALUES (?,?,?,?,?,?)""",
                (session_id, client_id, role, (content or "")[:4000], sql_query, row_count),
            )
        except Exception as e:
            print(f"❌ save_message hatası: {e}")

    def get_chat_messages(self, session_id: str) -> List[Dict[str, Any]]:
        try:
            return query(
                "SELECT * FROM ChatMessages WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            )
        except Exception as e:
            print(f"❌ get_chat_messages hatası: {e}")
            return []

    def get_client_sessions(self, client_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            return query(
                """SELECT session_id,
                          MIN(created_at) AS started_at,
                          MAX(created_at) AS last_message,
                          COUNT(*) AS message_count,
                          MIN(CASE WHEN role='user' THEN content END) AS title
                   FROM ChatMessages
                   WHERE client_id=?
                   GROUP BY session_id
                   ORDER BY MAX(created_at) DESC
                   LIMIT ?""",
                (client_id, limit),
            )
        except Exception as e:
            print(f"❌ get_client_sessions hatası: {e}")
            return []

    # ── İstatistikler ─────────────────────────────────────────────────────────

    def get_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        try:
            rows = query(
                """SELECT
                       COUNT(*) AS total_queries,
                       SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS successful_queries,
                       SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) AS failed_queries,
                       AVG(CAST(response_time_ms AS REAL)) AS avg_response_time_ms,
                       SUM(COALESCE(total_tokens, 0)) AS total_tokens,
                       SUM(COALESCE(estimated_cost, 0)) AS total_cost_usd
                   FROM ChatbotUsageLogs
                   WHERE created_at >= date('now', ? || ' days')""",
                (f"-{abs(days)}",),
            )
            if not rows:
                return {}
            r = rows[0]
            total = r["total_queries"] or 0
            success = r["successful_queries"] or 0
            return {
                "total_queries":        total,
                "successful_queries":   success,
                "failed_queries":       r["failed_queries"] or 0,
                "success_rate":         round(success / total * 100, 1) if total > 0 else 0.0,
                "avg_response_time_ms": round(r["avg_response_time_ms"] or 0, 1),
                "total_tokens":         r["total_tokens"] or 0,
                "total_cost_usd":       round(r["total_cost_usd"] or 0, 6),
            }
        except Exception as e:
            print(f"❌ get_usage_stats hatası: {e}")
            return {}

    def get_recent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            return query(
                """SELECT id, question, status, user_id, session_id,
                          generated_sql, row_count, ai_model,
                          prompt_tokens, completion_tokens, total_tokens,
                          response_time_ms, error_message, created_at
                   FROM ChatbotUsageLogs
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            )
        except Exception as e:
            print(f"❌ get_recent_logs hatası: {e}")
            return []

    # ── Maliyet ───────────────────────────────────────────────────────────────

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        model_lower = model.lower()
        rates = next(
            (v for k, v in self._COST_TABLE.items() if k in model_lower),
            (0.00015, 0.0006),
        )
        return round(prompt_tokens / 1000 * rates[0] + completion_tokens / 1000 * rates[1], 8)
