"""
KOBİ AI Platform — Uygulama Ayarları
Tüm konfigürasyon .env dosyasından okunur.
"""

import os
from functools import lru_cache
from pathlib import Path


def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k not in os.environ:
                os.environ[k] = v


_load_env()

_BASE_DIR = Path(__file__).parent.parent


class Settings:

    # ── OpenAI ──────────────────────────────────────────────
    openai_api_key:  str = os.environ.get("OPENAI_API_KEY",  "")
    chat_model:      str = os.environ.get("CHAT_MODEL",      "gpt-4o-mini")
    embedding_model: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

    # ── SQLite ───────────────────────────────────────────────
    sqlite_db_path: str = os.environ.get(
        "SQLITE_DB_PATH",
        str(_BASE_DIR / "db" / "kobi_demo.db")
    )

    # ── Qdrant / ChromaDB (collection adı aynı kalır) ────────
    qdrant_host:            str = "localhost"
    qdrant_port:            int = 6341
    qdrant_collection_name: str = os.environ.get("CHROMA_COLLECTION", "kobi_ai_schema")

    # ── RAG ──────────────────────────────────────────────────
    top_k_results: int = int(os.environ.get("TOP_K_RESULTS", "5"))
    chunk_size:    int = int(os.environ.get("CHUNK_SIZE",    "500"))
    chunk_overlap: int = int(os.environ.get("CHUNK_OVERLAP", "50"))

    # ── Güvenlik / Auth ──────────────────────────────────────
    jwt_secret:    str = os.environ.get("JWT_SECRET",    "kobi-ai-super-secret-2026")
    jwt_expire_h:  int = int(os.environ.get("JWT_EXPIRE_H", "24"))
    chat_pin:      str = os.environ.get("CHAT_PIN",      "demo2026")
    pipeline_pin:  str = os.environ.get("PIPELINE_PIN",  "pipeline123")

    # ── Telegram ─────────────────────────────────────────────
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_admin_chat_id: str = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
    # Rol bazlı Telegram chat ID'leri (ayarlanmadıysa admin'e düşer)
    telegram_depo_chat_id:   str = os.environ.get("TELEGRAM_DEPO_CHAT_ID", "")
    telegram_kargo_chat_id:  str = os.environ.get("TELEGRAM_KARGO_CHAT_ID", "")
    telegram_mh_chat_id:     str = os.environ.get("TELEGRAM_MH_CHAT_ID", "")
    # Scheduler
    morning_report_hour:   int = int(os.environ.get("MORNING_REPORT_HOUR", "8"))
    morning_report_minute: int = int(os.environ.get("MORNING_REPORT_MINUTE", "0"))

    # ── Logging ──────────────────────────────────────────────
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")

    # ── Geriye dönük uyumluluk (pyodbc kaldırıldı) ───────────
    @property
    def connection_string(self) -> str:
        return f"sqlite:///{self.sqlite_db_path}"

    @property
    def db_server(self) -> str:
        return "SQLite"

    @property
    def db_name(self) -> str:
        return Path(self.sqlite_db_path).name


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def print_config() -> None:
    s = get_settings()
    print(f"""
  DB       : {s.sqlite_db_path}
  Model    : {s.chat_model}
  ChromaDB : {s.qdrant_collection_name}
  Telegram : {'✅ Ayarlı' if s.telegram_bot_token else '❌ Ayarlanmadı'}
""")
