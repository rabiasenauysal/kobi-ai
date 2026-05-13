"""
KOBİ AI Platform — RAG Service (Text-to-SQL)

RAG-FIRST MİMARİ:
- use_schema varsayılan olarak True — her sorguda Qdrant'tan şema çekilir.
- Sistem promptu kısa ve kural odaklı (mikro_system_prompt.py'den).
- Tablo/kolon detayları Qdrant'tan dinamik olarak eklenir.
- EntityCache fuzzy eşleşme → doğru filtre değerleri.
- DataQualityFilter → _iptal/_hidden filtresi eksikse ekler.
"""

import re
import traceback
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from openai import OpenAI

from config.settings import get_settings
from services.vector_store import VectorStore
from services.sql_executor import SQLExecutor
from services.usage_logger import UsageLogger, UsageLogData
from services.sql_agent import SQLAgent
from services.zero_result_handler import ZeroResultHandler
from services.handlers.entity_cache import EntityCache


# ─────────────────────────────────────────────────────────────────────────────
# GÖRSELLEŞTİRME TİPİ TESPİTİ
# ─────────────────────────────────────────────────────────────────────────────

def detect_requested_viz_type(question: str) -> Optional[str]:
    """Kullanıcı soruda belirli bir grafik tipi istedi mi?"""
    q = question.lower()
    if any(k in q for k in ["pasta", "pie", "daire grafik"]):
        return "pie"
    if any(k in q for k in ["çizgi", "line", "trend", "zaman serisi"]):
        return "line"
    if any(k in q for k in ["çubuk", "bar grafik", "sütun grafik", "histogram"]):
        return "bar"
    if any(k in q for k in ["tablo", "liste halinde", "tablo olarak"]):
        return "table"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# VERİ KALİTE FİLTRESİ
# ─────────────────────────────────────────────────────────────────────────────

class DataQualityFilter:
    """
    Üretilen SQL'de _iptal=0 AND _hidden=0 filtreleri eksikse ekler.
    Sistem promptunda bu kural zorunlu olarak var; bu sınıf güvenlik katmanıdır.
    """

    TABLE_FILTERS = {
        "SIPARISLER":                ("sip_iptal",    "sip_hidden"),
        "STOKLAR":                   ("sto_iptal",     "sto_hidden"),
        "STOK_HAREKETLERI":          ("sth_iptal",     "sth_hidden"),
        "CARI_HESAPLAR":             ("cari_iptal",    "cari_hidden"),
        "KARGO_GONDERILERI":         ("kargo_iptal",   "kargo_hidden"),
        "IADE_TALEPLERI":            ("itlp_iptal",    "itlp_hidden"),
        "ODEME_EMIRLERI":            ("sck_iptal",     "sck_hidden"),
        "E_TICARET_URUN_ESLEME":     ("eu_iptal",      "eu_hidden"),
        "STOK_DEPO_DETAYLARI":       ("sdp_iptal",     "sdp_hidden"),
        "STOK_FIYAT_DEGISIKLIKLERI": ("fid_iptal",     "fid_hidden"),
        "BARKOD_TANIMLARI":          ("bar_iptal",     "bar_hidden"),
        "CARI_HESAP_HAREKETLERI":    ("cha_iptal",     "cha_hidden"),
        "STOK_MARKALARI":            ("mrk_iptal",     "mrk_hidden"),
        "STOK_ANA_GRUPLARI":         ("san_iptal",     "san_hidden"),
        "STOK_ALT_GRUPLARI":         ("sta_iptal",     "sta_hidden"),
        "CARI_HESAP_ADRESLERI":      ("adr_iptal",     "adr_hidden"),
    }

    def needs_filter(self, sql: str) -> bool:
        sql_upper = sql.upper()
        return any(tbl in sql_upper for tbl in self.TABLE_FILTERS)

    def ensure_active_filters(self, sql: str) -> str:
        """
        SQL'de kullanılan tablolar için filtre eksikse ekle.

        Alias-aware yaklaşım:
        - FROM/JOIN satırından alias'ı tespit et (örn: sdp, st, sth)
        - Filtre eklerken alias.kolon formatında yaz
        - WHERE yoksa ilk FROM/JOIN sonrasına ekle
        - CTE sorgularda dış WHERE'e ekle
        """
        sql_upper = sql.upper()

        for table, (iptal_col, hidden_col) in self.TABLE_FILTERS.items():
            if table not in sql_upper:
                continue

            # Filtreler zaten var mı? (prefix veya alias ile)
            col_prefix = iptal_col.split("_")[0]  # sip, sto, sth, sdp vb.
            has_iptal  = iptal_col.upper() in sql_upper or f"{col_prefix}_IPTAL" in sql_upper
            has_hidden = (hidden_col is None) or (
                hidden_col.upper() in sql_upper or f"{col_prefix}_HIDDEN" in sql_upper
            )
            if has_iptal and has_hidden:
                continue

            # FROM/JOIN'deki alias'ı bul
            alias_pattern = (
                rf"(?:FROM|JOIN)\s+(?:\[?dbo\]?\.)?\[?{re.escape(table)}\]?"
                rf"(?:\s+(?:AS\s+)?(\w+))?"
            )
            match = re.search(alias_pattern, sql, re.IGNORECASE)
            if not match:
                continue

            alias = match.group(1)  # None veya alias adı (sdp, st, sth vb.)

            # Filtre koşullarını alias ile yaz
            conditions = []
            if not has_iptal:
                col = f"{alias}.{iptal_col}" if alias else iptal_col
                conditions.append(f"{col} = 0")
            if hidden_col and not has_hidden:
                col = f"{alias}.{hidden_col}" if alias else hidden_col
                conditions.append(f"{col} = 0")

            if not conditions:
                continue

            cond_str = " AND ".join(conditions)

            if "WHERE" in sql_upper:
                where_pos = sql_upper.find("WHERE")
                before = sql[:where_pos + 5]
                after  = sql[where_pos + 5:].strip()
                sql = f"{before} {cond_str} AND {after}"
                sql_upper = sql.upper()
            else:
                end = match.end()
                sql = sql[:end] + f" WHERE {cond_str}" + sql[end:]
                sql_upper = sql.upper()

        return sql



# ─────────────────────────────────────────────────────────────────────────────
# SİSTEM PROMPTU — RAG-First builder
# ─────────────────────────────────────────────────────────────────────────────

try:
    from services.mikro_system_prompt import (
        MIKRO_BASE_SYSTEM_PROMPT as BASE_SYSTEM_PROMPT,
        VOICE_CHAT_ADDENDUM,
        MIKRO_GREETING_KEYWORDS as GREETING_KEYWORDS,
        MIKRO_GREETING_RESPONSE as GREETING_RESPONSE,
    )
except ImportError:
    BASE_SYSTEM_PROMPT = (
        "Sen KOBİ AI E-Ticaret analisti için SQLite SQL üretiyorsun.\n"
        "Veritabanı: kobi_demo.db (SQLite) — prefix yok, direkt tablo adı yaz.\n"
        "Her sorguda: [prefix]_iptal = 0 AND [prefix]_hidden = 0 filtresi ekle.\n"
        "Metin aramaları: LOWER(kolon) LIKE LOWER('%arama%') kullan.\n"
        "STRING_AGG YOK — group_concat(kolon, ', ') kullan. TOP yerine LIMIT.\n"
    )
    VOICE_CHAT_ADDENDUM = ""
    GREETING_KEYWORDS = ["merhaba", "selam", "günaydın", "hey", "test"]
    GREETING_RESPONSE = "Merhaba! KOBİ AI hazır. Nasıl yardımcı olabilirim?"

# Geriye dönük uyumluluk
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT


def build_system_prompt(question: str = "") -> str:
    """Kısa sistem promptu + sohbet modu kuralları."""
    return BASE_SYSTEM_PROMPT + VOICE_CHAT_ADDENDUM


def build_system_prompt_voice(question: str = "") -> str:
    return BASE_SYSTEM_PROMPT + VOICE_CHAT_ADDENDUM


def fix_turkish_like_patterns(sql: str) -> str:
    """LIKE değerlerindeki Türkçe karakterleri MSSQL character class'a çevir."""
    TR_CLASS_MAP = {
        "İ": "[İiIı]", "i": "[İiIı]", "I": "[İiIı]", "ı": "[İiIı]",
        "Ş": "[ŞşSs]", "ş": "[ŞşSs]",
        "Ç": "[ÇçCc]", "ç": "[ÇçCc]",
        "Ğ": "[ĞğGg]", "ğ": "[ĞğGg]",
        "Ü": "[ÜüUu]", "ü": "[ÜüUu]",
        "Ö": "[ÖöOo]", "ö": "[ÖöOo]",
    }

    def process(match):
        quote = match.group(1)
        value = match.group(2)
        result = []
        depth = 0
        for ch in value:
            if ch == "[":
                depth += 1; result.append(ch)
            elif ch == "]":
                depth = max(0, depth - 1); result.append(ch)
            elif depth > 0:
                result.append(ch)
            elif ch in TR_CLASS_MAP:
                result.append(TR_CLASS_MAP[ch])
            else:
                result.append(ch)
        nv = "".join(result)
        nv = re.sub(r"%{2,}", "%", nv)
        return f"LIKE {quote}{nv}{quote}"

    return re.sub(r"LIKE\s+(['\"])([^'\"]+)\1", process, sql, flags=re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# ANA RAG SERVİSİ
# ─────────────────────────────────────────────────────────────────────────────

class RAGService:
    """KOBİ ERP için RAG-First Text-to-SQL servisi."""

    def __init__(self):
        self.settings = get_settings()
        self.openai_client = OpenAI(api_key=self.settings.openai_api_key)

        self.vector_store = VectorStore()
        self.sql_executor = SQLExecutor()
        self.sql_agent = SQLAgent(
            openai_client=self.openai_client,
            sql_executor=self.sql_executor,
            model=self.settings.chat_model,
        )
        self.logger       = UsageLogger()
        self.data_filter  = DataQualityFilter()
        self.zero_result_handler = ZeroResultHandler(
            openai_client=self.openai_client,
            executor=self.sql_executor,
            model=self.settings.chat_model,
        )
        self.entity_cache = EntityCache(executor=self.sql_executor)

        self._db_max_date: str = ""
        self._db_date_range: str = self._fetch_db_date_range()

        print("✅ Mikro AI RAGService başlatıldı (RAG-First)")
        print(f"   Model: {self.settings.chat_model}")
        print(f"   Qdrant: {self.settings.qdrant_host}:{self.settings.qdrant_port}")
        if self._db_date_range:
            print(f"   Veri aralığı: {self._db_date_range}")

    # ── Ana Sorgu Metodu ─────────────────────────────────────────────────────

    def query(
        self,
        question: str,
        user_id: Optional[str] = None,
        user_ip: Optional[str] = None,
        session_id: Optional[str] = None,
        skip_filters: bool = False,
        analytical: bool = False,
        analytical_depth: Literal["light", "medium", "deep"] = "medium",
        use_schema: bool = True,         # ← RAG-First: default True
        memory=None,
        voice: bool = False,
        already_clarified: bool = False,
    ) -> Dict[str, Any]:
        """Kullanıcı sorusunu işle ve cevap üret."""

        start_time = datetime.now()
        clean_q    = question.strip().lower()

        # ── 0. Selamlama ─────────────────────────────────────────────────────
        if clean_q in GREETING_KEYWORDS:
            return {
                "success": True,
                "answer":  GREETING_RESPONSE,
                "sql":     "-- Selamlama (SQL üretilmedi)",
                "result":  None,
                "log_id":  None,
                "tokens":  {"prompt": 0, "completion": 0, "total": 0},
            }

        # ── Log Data ─────────────────────────────────────────────────────────
        log_data = UsageLogData(
            question=question,
            status="pending",
            user_id=user_id,
            user_ip=user_ip,
            session_id=session_id,
            ai_model=self.settings.chat_model,
        )

        try:
            # ── 1. Analytical Pipeline ────────────────────────────────────────
            if analytical:
                from services.analytical.runner import run_analytical_query
                return run_analytical_query(
                    question=question,
                    openai_client=self.openai_client,
                    model=self.settings.chat_model,
                    generate_sql_fn=self._generate_sql,
                    data_filter=self.data_filter,
                    executor=self.sql_executor,
                    sql_agent=self.sql_agent,
                    usage_logger=self.logger,
                    user_id=user_id,
                    user_ip=user_ip,
                    session_id=session_id,
                    analytical_depth=analytical_depth,
                    skip_filters=skip_filters,
                )

            # ── 2. Schema (RAG) — Her sorguda çalışır (use_schema=True default) ──
            context = ""

            if use_schema:
                try:
                    schema_docs = self.vector_store.search(
                        question, limit=self.settings.top_k_results
                    )
                    if schema_docs:
                        context = self._build_context(schema_docs)
                        print(f"   ✓ RAG: {len(schema_docs)} schema chunk getirildi")
                except Exception as e:
                    print(f"   ⚠️ Qdrant hatası (atlanıyor): {e}")

            # Entity cache → fuzzy eşleştirme
            entity_context, _ = self.entity_cache.enrich_question(question)
            if entity_context:
                context = entity_context + ("\n\n" + context if context else "")
                print(f"   ✓ Entity context eklendi")

            # ── 3. SQL Üretimi ────────────────────────────────────────────────
            print("🤖 SQL üretiliyor...")
            messages_override = None
            if memory and session_id:
                sys_prompt = build_system_prompt(question)
                date_ctx = self._build_date_range_context()
                full_sys = sys_prompt + (f"\n\n### VERİ ARALIĞI:\n{date_ctx}" if date_ctx else "")
                messages_override = memory.build_messages(
                    session_id=session_id,
                    system_prompt=full_sys,
                    schema_context=context,
                    user_question=question,
                    voice=voice,
                )

            sql_response = self._generate_sql(
                question=question,
                context=context,
                messages_override=messages_override,
                voice=voice,
            )

            # Sohbet modu kontrolü
            raw_sql = (sql_response.get("sql") or "").strip()
            is_real_sql = bool(raw_sql) and any(
                raw_sql.upper().startswith(kw)
                for kw in ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
            )
            if sql_response.get("voice_chat_answer") or (raw_sql and not is_real_sql):
                answer_text = sql_response.get("voice_chat_answer") or raw_sql
                return {
                    "success": True,
                    "answer": answer_text,
                    "sql": None, "sql_description": None, "result": None,
                    "filtered_count": 0, "has_filters": False, "log_id": None,
                    "tokens": {
                        "prompt":     sql_response["prompt_tokens"],
                        "completion": sql_response["completion_tokens"],
                        "total":      sql_response["total_tokens"],
                    },
                }

            sql_original      = sql_response["sql"]
            prompt_tokens     = sql_response["prompt_tokens"]
            completion_tokens = sql_response["completion_tokens"]
            total_tokens      = sql_response["total_tokens"]

            # ── 4. Filtreler ──────────────────────────────────────────────────
            sql_filtered = sql_original
            if not skip_filters:
                sql_filtered = self.data_filter.ensure_active_filters(sql_filtered)
                sql_filtered = self._fix_turkish_like_patterns(sql_filtered)

            print(f"   SQL: {sql_filtered[:600]}...")

            # ── 5. SQL Çalıştır ───────────────────────────────────────────────
            print("⚡ SQL çalıştırılıyor...")
            requested_viz = detect_requested_viz_type(question)
            result = self.sql_executor.execute_query(
                sql_filtered, forced_viz_type=requested_viz
            )
            if not result.success:
                result, sql_filtered = self.sql_agent.run(
                    sql=sql_filtered,
                    question=question,
                    schema_context=context,
                    forced_viz_type=requested_viz,
                )

            if not result.success:
                log_data.status        = "sql_error"
                log_data.generated_sql = sql_filtered
                log_data.error_type    = "sql_execution_error"
                log_data.error_message = result.error
                log_data.response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
                self.logger.log_usage(log_data)
                return {
                    "success": False,
                    "answer":  f"SQL çalıştırılamadı: {result.error}",
                    "sql": sql_filtered, "sql_original": sql_original,
                    "error": result.error, "result": result,
                    "filtered_count": 0, "has_filters": False,
                }

            print(f"   ✓ {result.row_count} satır ({result.execution_time_ms:.0f}ms)")

            # ── 6. Sıfır Sonuç → Öneri ───────────────────────────────────────
            _is_count_zero = (
                result.row_count == 1
                and len(result.columns) == 1
                and list(result.data[0].values())[0] == 0
                and "COUNT" in sql_filtered.upper()
                and "LIKE" in sql_filtered.upper()
            )

            if result.row_count == 0 or _is_count_zero:
                if already_clarified:
                    return {
                        "success": True,
                        "clarification_needed": False,
                        "answer": (
                            "Seçtiğiniz kriterlere ait veri bulunamadı. "
                            "Farklı filtre veya tarih aralığıyla tekrar deneyebilirsiniz."
                        ),
                        "sql": sql_filtered, "result": result,
                        "filtered_count": 0, "has_filters": False, "log_id": None,
                        "tokens": {"prompt": prompt_tokens, "completion": completion_tokens, "total": total_tokens},
                    }

                print("   🔍 0 satır → ZeroResultHandler devreye giriyor...")
                suggestion_result = self.zero_result_handler.handle(
                    sql=sql_filtered,
                    question=question,
                    original_result=result,
                )

                if suggestion_result.get("clarification_needed"):
                    suggestions = suggestion_result.get("suggestions", [])
                    # Birebir eşleşme → veri gerçekten yok
                    _exact_match = False
                    if suggestions:
                        sql_up  = sql_filtered.upper()
                        label   = (
                            suggestions[0].get("label", "") if isinstance(suggestions[0], dict)
                            else str(suggestions[0])
                        ).upper()
                        label_n = label.translate(str.maketrans("ÜÖŞĞIÇ", "UOSGIC"))
                        if label in sql_up or label_n in sql_up:
                            _exact_match = True
                        elif all(w in sql_up for w in [w for w in label_n.split() if len(w) >= 3]):
                            _exact_match = True

                    if not _exact_match:
                        return {
                            "success": True,
                            "clarification_needed": True,
                            "suggestions": suggestions,
                            "answer":   suggestion_result.get("message", ""),
                            "original_question": question,
                            "sql": sql_filtered, "result": None,
                            "filtered_count": 0, "has_filters": False, "log_id": None,
                            "tokens": {"prompt": prompt_tokens, "completion": completion_tokens, "total": total_tokens},
                        }

            # ── 7. Log ───────────────────────────────────────────────────────
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            log_data.status               = "success"
            log_data.generated_sql        = sql_filtered
            log_data.sql_execution_time_ms = result.execution_time_ms
            log_data.row_count            = result.row_count
            log_data.prompt_tokens        = prompt_tokens
            log_data.completion_tokens    = completion_tokens
            log_data.total_tokens         = total_tokens
            log_data.response_time_ms     = response_time
            log_id = self.logger.log_usage(log_data)

            # ── 8. Hafıza ─────────────────────────────────────────────────────
            if memory and session_id:
                memory.add_turn(
                    session_id=session_id,
                    user_question=question,
                    sql=sql_filtered,
                    sql_description="",
                )
                print(f"🧠 Hafıza: {memory.get_turn_count(session_id)} tur")

            answer = (
                "Bu kriterlere uygun kayıt bulunamadı."
                if result.row_count == 0
                else f"{result.row_count} kayıt bulundu."
            )

            return {
                "success": True,
                "answer":  answer,
                "sql_description": "",
                "sql":         sql_filtered,
                "sql_original":sql_original,
                "result":      result,
                "data":        result.data,
                "columns":     result.columns,
                "row_count":   result.row_count,
                "execution_time_ms": result.execution_time_ms,
                "visualization_type": result.visualization_type,
                "filtered_count": 0,
                "has_filters":    False,
                "log_id":         log_id,
                "supplements":    None,
                "tokens": {
                    "prompt":     prompt_tokens,
                    "completion": completion_tokens,
                    "total":      total_tokens,
                },
            }

        except Exception as e:
            print(f"❌ Hata: {e}")
            traceback.print_exc()
            log_data.status        = "error"
            log_data.error_type    = "system_error"
            log_data.error_message = str(e)
            log_data.response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            self.logger.log_usage(log_data)
            return {"success": False, "answer": f"Sistem hatası: {e}", "error": str(e)}

    # ── Yardımcı Metotlar ────────────────────────────────────────────────────

    def _generate_sql(
        self,
        question: str,
        context: str = "",
        messages_override=None,
        voice: bool = False,
    ) -> Dict[str, Any]:
        """OpenAI ile SQL üret."""

        if messages_override:
            messages = messages_override
        else:
            system_prompt = build_system_prompt(question)

            # Dinamik tarih aralığı — DB'den startup'ta çekildi
            date_ctx = self._build_date_range_context()
            if date_ctx:
                system_prompt += f"\n\n### VERİ ARALIĞI:\n{date_ctx}"

            if context:
                system_prompt += f"\n\n### VERİTABANI ŞEMA BAĞLAMI (RAG):\n{context}"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": question},
            ]

        response = self.openai_client.chat.completions.create(
            model=self.settings.chat_model,
            messages=messages,
            temperature=0.0,
            max_tokens=1500,
        )

        raw = response.choices[0].message.content.strip()

        # --VOICE_CHAT: formatını yakala
        voice_prefix = "--VOICE_CHAT:"
        if raw.startswith(voice_prefix):
            return {
                "sql": None,
                "voice_chat_answer": raw[len(voice_prefix):].strip(),
                "prompt_tokens":     response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens":      response.usage.total_tokens,
            }

        sql = raw

        # Karma cevaptan SQL çıkar
        if not sql.strip().upper().startswith(("SELECT", "WITH")):
            lines = sql.split("\n")
            sql_lines = []
            for line in lines:
                stripped = line.strip().upper()
                if stripped.startswith(("SELECT", "WITH", "INSERT", "UPDATE")):
                    sql_lines.append(line)
                elif sql_lines:
                    sql_lines.append(line)
            candidate = "\n".join(sql_lines).strip()
            if candidate.upper().startswith(("SELECT", "WITH")):
                sql = candidate

        # Markdown temizle
        if sql.startswith("```"):
            sql = sql.split("```")[1]
            if sql.lower().startswith("sql"):
                sql = sql[3:]
            sql = sql.strip()
        if sql.endswith("```"):
            sql = sql[:-3].strip()

        sql = self._fix_turkish_like_patterns(sql)
        sql = self._fix_name_equals(sql, question)
        sql = self._remove_placeholders(sql)

        return {
            "sql":               sql,
            "voice_chat_answer": None,
            "prompt_tokens":     response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens":      response.usage.total_tokens,
        }

    def _fix_turkish_like_patterns(self, sql: str) -> str:
        return fix_turkish_like_patterns(sql)

    def _fix_name_equals(self, sql: str, question: str) -> str:
        """LLM metin kolonunda = ürettiyse LIKE'a çevir."""
        text_cols = [
            "sto_isim", "cari_unvan1", "cari_unvan2",
            "sip_aciklama", "itlp_aciklama", "mrk_ismi",
            "san_isim", "sta_isim",
        ]
        for col in text_cols:
            pattern = re.compile(
                rf"{col}\s*=\s*'([^']+)'(\s*COLLATE\s+\S+)?",
                re.IGNORECASE,
            )
            match = pattern.search(sql)
            if match:
                value = match.group(1)
                like_clause = f"LOWER({col}) LIKE LOWER('%{value}%')"
                sql = pattern.sub(like_clause, sql, count=1)
                print(f"   🔧 {col} = → LIKE dönüştürüldü")
        return sql

    def _remove_placeholders(self, sql: str) -> str:
        """
        Bilinen yanlış kolon/yapıları düzelt.
        Bu metod execute'dan önce çalışır — agent retry sayısını korur.
        """
        import re as _re

        # Kural tabanlı düzeltmeler (sql_agent.py ile senkronize)
        KURAL_MAP = {
            "sto_miktar":   None,  # REWRITE gerekir, burada değil
            "itlp_neden":   "itlp_aciklama",
            "itlp_tarih":   "itlp_tarihi",
            "marka_isim":   "mrk_ismi",
            "marka_kod":    "mrk_kod",
            "marka_iptal":  "mrk_iptal",
            "sag_isim":     "san_isim",
            "sag_kod":      "san_kod",
            "sag_iptal":    "san_iptal",
            "salt_isim":    "sta_isim",
            "salt_kod":     "sta_kod",
            "bar_barkodno": "bar_kodu",
            "dvz_alis":     "dov_fiyat1",
            "dvz_satis":    "dov_fiyat2",
        }

        fixed = sql
        for wrong, right in KURAL_MAP.items():
            if right and _re.search(rf"(?i)\b{_re.escape(wrong)}\b", fixed):
                fixed = _re.sub(rf"(?i)\b{_re.escape(wrong)}\b", right, fixed)
                print(f"   🔧 Pre-fix: {wrong} → {right}")

        # Prefix'siz iptal/hidden kolonları düzelt
        # LLM bazen "AND iptal = 0" yazar — "AND sdp_iptal = 0" olmalı
        # Hangi tablonun kullanıldığını bak ve doğru prefix ekle
        TABLE_PREFIX_MAP = {
            "STOK_DEPO_DETAYLARI": "sdp",
            "STOK_HAREKETLERI": "sth",
            "SIPARISLER": "sip",
            "STOKLAR": "sto",
            "CARI_HESAPLAR": "cari",
            "IADE_TALEPLERI": "itlp",
            "KARGO_GONDERILERI": "kargo",
            "STOK_MARKALARI": "mrk",
        }
        # "AND iptal = 0" veya "WHERE iptal = 0" pattern
        bare_iptal = _re.search(r"(?:AND|WHERE|OR)\s+(iptal)\s*=\s*0", fixed, _re.IGNORECASE)
        if bare_iptal:
            # Hangi tablo kullanılmış — ilk eşleşen
            for tbl, prefix in TABLE_PREFIX_MAP.items():
                if tbl in fixed.upper():
                    fixed = fixed.replace(bare_iptal.group(0),
                                          bare_iptal.group(0).replace("iptal", f"{prefix}_iptal"))
                    print(f"   🔧 Pre-fix: bare iptal → {prefix}_iptal")
                    break

        # GETDATE() → DB max tarihi ile değiştir
        # Veritabanı geçmişte bitiyor, GETDATE() veri olmayan döneme denk gelir
        if "GETDATE()" in fixed.upper() and self._db_max_date:
            mx = self._db_max_date  # örn: "2025-09-13"
            # DATEADD(..., GETDATE()) → DATEADD(..., 'max_date')
            fixed = _re.sub(
                r"DATEADD\s*\((\s*(?:DAY|MONTH|YEAR)\s*,\s*-?\d+\s*),\s*GETDATE\s*\(\s*\)\s*\)",
                lambda m: f"DATEADD({m.group(1)}, '{mx}')",
                fixed,
                flags=_re.IGNORECASE
            )
            # Artık GETDATE() kalmışsa logla
            if "GETDATE()" in fixed.upper():
                print(f"   ⚠️ GETDATE() tespit edildi — ajan düzeltecek (DB max: {mx})")

        # ── İADE ORANI %100 CAP (defensive post-processor) ──────────────
        # Model bazen CASE WHEN cap eklemeyi unutur, %600 gibi saçma değerler çıkar.
        # Tespit: CAST(<X>.toplam_iade_adet * 100.0 / NULLIF(<Y>.toplam_satis_adet,0) AS DECIMAL(...)) AS iade_orani[_pct]
        iade_orani_pat = _re.compile(
            r"CAST\s*\(\s*"
            r"([\w]+\.toplam_iade_adet|toplam_iade_adet)\s*\*\s*100(?:\.0)?\s*/\s*"
            r"NULLIF\s*\(\s*([\w]+\.toplam_satis_adet|toplam_satis_adet)\s*,\s*0\s*\)"
            r"\s+AS\s+(DECIMAL\s*\([^)]+\))\s*\)"
            r"(\s+AS\s+iade_orani(?:_pct)?)",
            _re.IGNORECASE
        )
        def _cap_iade_orani(m):
            iade   = m.group(1)
            satis  = m.group(2)
            dec    = m.group(3)
            alias  = m.group(4)
            return (
                f"CAST(CASE WHEN {iade} >= {satis} THEN 100.00 "
                f"ELSE {iade} * 100.0 / NULLIF({satis}, 0) END AS {dec}){alias}"
            )
        new_fixed = iade_orani_pat.sub(_cap_iade_orani, fixed)
        if new_fixed != fixed:
            print("   🔧 Post-fix: iade_orani_pct → CASE WHEN ile %100'e cap edildi")
            fixed = new_fixed

        # ── İADE TUTARI YASAK FORMÜLÜ DEDEKTÖRÜ ──────────────────────────
        # Tespit: <X>.toplam_iade_adet * <Y>.toplam_ciro / NULLIF(<Z>.toplam_satis_adet,0) AS iade_tutari
        # Bu formül mathematically iade_adet × avg_price'a eş ama iade_adet>satis_adet olunca tutar>ciro çıkar.
        # avg_fiyat CTE'si tercih edilir. Burada sadece UYARI veriyoruz — auto-rewrite yapısal değişiklik gerektirir.
        iade_tutari_yasak = _re.search(
            r"toplam_iade_adet\s*\*\s*[\w]*\.?toplam_ciro\s*/\s*NULLIF\s*\(\s*[\w]*\.?toplam_satis_adet",
            fixed,
            _re.IGNORECASE,
        )
        if iade_tutari_yasak:
            print("   ⚠️ YASAK iade_tutari formülü tespit edildi: iade_adet*ciro/satis_adet")
            print("      → avg_fiyat CTE'si kullanılmalı. Sonuç değer doğru olabilir ama yöntem riskli.")

        # Placeholder uyarısı
        brackets = _re.findall(r"\[([^\]]{2,40})\]", fixed)
        for p in brackets:
            if any(c in p for c in " ,.-") or any(ord(c) > 127 for c in p):
                print(f"   ⚠️ Placeholder tespit edildi: [{p}] — agent düzeltecek")

        return fixed

    def _fetch_db_date_range(self) -> str:
        """
        Startup'ta DB'den gerçek veri tarih aralığını çeker.
        sth_fis_tarihi kullanır (sth_tarih NULL olabilir).
        Hata olursa boş string döner.
        """
        try:
            result = self.sql_executor.execute_query("""
                SELECT
                    MIN(date(sth_fis_tarihi)) AS min_tarih,
                    MAX(date(sth_fis_tarihi)) AS max_tarih,
                    COUNT(*) AS toplam_hareket,
                    SUM(CASE WHEN sth_cins = 8 THEN 1 ELSE 0 END) AS eticaret_hareket
                FROM STOK_HAREKETLERI
                WHERE sth_iptal = 0 AND sth_fis_tarihi IS NOT NULL
            """)
            if result.success and result.data:
                row = result.data[0]
                mn  = row.get("min_tarih", "")
                mx  = row.get("max_tarih", "")
                n   = row.get("toplam_hareket", 0)
                et  = row.get("eticaret_hareket", 0)
                if mn and mx:
                    self._db_max_date = mx   # "son X gün" hesabı için sakla
                    return f"{mn} → {mx} ({n:,} hareket, {et:,} e-ticaret satışı)"
        except Exception as e:
            print(f"   [DateRange] Uyarı: {e}")
        self._db_max_date = ""
        return ""

    def _build_date_range_context(self) -> str:
        """
        Sistem promptuna eklenecek tarih aralığı bağlamı.
        Tarih filtresi olmayan sorgularda LLM bu aralığı kullanır.
        """
        if not self._db_date_range:
            return ""
        # "2024-01-15 → 2025-11-30" formatından yıl/ay çıkar
        import re as _re
        m = _re.search(r"(\d{4}-\d{2}-\d{2})\s*→\s*(\d{4}-\d{2}-\d{2})", self._db_date_range)
        if not m:
            return ""
        min_date, max_date = m.group(1), m.group(2)
        min_year = min_date[:4]
        max_year = max_date[:4]
        lines = [
            f"VERİTABANI VERİ ARALIĞI: {min_date} ile {max_date} arasında.",
            f"VERİTABANINDAKİ SON TARİH: {max_date} — date('now') değil bu tarihi baz al!",
            "Kullanıcı tarih belirtmezse bu aralıktaki TÜM veriyi getir (tarih filtresi ekleme).",
            f"'Son 30 gün', 'son 3 ay' gibi göreceli tarih için date('now') KULLANMA!",
            f"Bunun yerine: date('{max_date}', '-30 days') gibi max tarihe göre hesapla.",
            f"Örnek — son 30 gün: date(sth_fis_tarihi) >= date('{max_date}', '-30 days')",
            f"Örnek — son 3 ay:   date(sth_fis_tarihi) >= date('{max_date}', '-3 months')",
            f"Belirli yıl: strftime('%Y', sth_fis_tarihi) = '{max_year}'",
            f"ASLA '{min_date}' öncesi veya '{max_date}' sonrası tarih filtresi koyma.",
        ]
        return "\n".join(lines)

    def _build_context(self, docs) -> str:
        """Qdrant dokümanlarını context string'e çevir."""
        if not docs:
            return ""
        parts = []
        for doc in docs:
            text = doc.get("text", "")
            if text:
                parts.append(text)
        return "\n\n---\n\n".join(parts[:6])