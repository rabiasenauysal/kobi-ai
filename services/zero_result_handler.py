"""
KOBİ AI Platform — Zero Result Handler
========================================
SQL 0 satır döndürdüğünde devreye girer:
  - SQL'deki LIKE aramalarını tespit eder
  - O kolonların gerçek değerlerini DB'den fuzzy benzerlik ile çeker
  - En yakın 3 adayı döndürür: "X, Y, Z'yi mi kastettiniz?"
  - Kullanıcı seçim yaparsa orijinal soru + seçilen değerle tekrar sorgu yapılır

TYF'den farklar:
  - View_RaceResults_Analytics → Mikro tabloları (STOKLAR, CARI_HESAPLAR vb.)
  - ActivityName/RaceClassName/AthleteFullName → sto_isim/cari_unvan1/sip_eticaret_kanal_kodu
  - Sporcu/kulüp domain mantığı → ürün/müşteri/kanal domain mantığı
"""

import re
import logging
from typing import Any, Dict, List

from openai import OpenAI

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ARANACAK KOLONLAR VE ETİKETLER
# ─────────────────────────────────────────────────────────────────────────────

SEARCHABLE_COLUMNS = [
    # STOKLAR
    "sto_isim",
    "sto_kod",
    # CARI_HESAPLAR
    "cari_unvan1",
    "cari_unvan2",
    # SIPARISLER
    "sip_eticaret_kanal_kodu",
    "sip_aciklama",
    # IADE_TALEPLERI
    "itlp_aciklama",
    # Marka / Grup  ← gerçek kolon adları (JSON doğrulandı)
    "mrk_ismi",
    "san_isim",
    "sta_isim",
]

COLUMN_LABELS = {
    "sto_isim":                 "ürün adı",
    "sto_kod":                  "ürün kodu",
    "cari_unvan1":              "müşteri/cari",
    "cari_unvan2":              "müşteri/cari",
    "sip_eticaret_kanal_kodu":  "satış kanalı",
    "sip_aciklama":             "sipariş açıklaması",
    "itlp_aciklama":            "iade nedeni",
    "mrk_ismi":                 "marka",
    "san_isim":                 "ana kategori",
    "sta_isim":                 "alt kategori",
}

# Kolon → tablo eşlemesi (DB'den değerleri çekmek için)
COLUMN_TABLE_MAP = {
    "sto_isim":                ("STOKLAR",            "sto_isim",               "sto_iptal = 0"),
    "sto_kod":                 ("STOKLAR",            "sto_kod",                "sto_iptal = 0"),
    "cari_unvan1":             ("CARI_HESAPLAR",      "cari_unvan1",            "cari_iptal = 0"),
    "cari_unvan2":             ("CARI_HESAPLAR",      "cari_unvan2",            "cari_iptal = 0"),
    "sip_eticaret_kanal_kodu": ("SIPARISLER",         "sip_eticaret_kanal_kodu","sip_iptal = 0"),
    "sip_aciklama":            ("SIPARISLER",         "sip_aciklama",           "sip_iptal = 0"),
    "itlp_aciklama":           ("IADE_TALEPLERI",     "itlp_aciklama",          "itlp_iptal = 0"),
    "mrk_ismi":                ("STOK_MARKALARI",     "mrk_ismi",               "mrk_iptal = 0"),
    "san_isim":                ("STOK_ANA_GRUPLARI",  "san_isim",               "san_iptal = 0"),
    "sta_isim":                ("STOK_ALT_GRUPLARI",  "sta_isim",               "sta_iptal = 0"),
}

# SQL'deki kolon adından COLUMN_TABLE_MAP anahtarına düşme
_SQL_COLUMN_FALLBACK_MAP = [
    (["STO_ISIM"],                   "sto_isim"),
    (["STO_KOD"],                    "sto_kod"),
    (["CARI_UNVAN1", "CARI_UNVAN2"], "cari_unvan1"),
    (["SIP_ETICARET_KANAL_KODU"],    "sip_eticaret_kanal_kodu"),
    (["SIP_ACIKLAMA"],               "sip_aciklama"),
    (["ITLP_ACIKLAMA"],              "itlp_aciklama"),
    (["MRK_ISMI"],                   "mrk_ismi"),
    (["SAN_ISIM"],                   "san_isim"),
    (["STA_ISIM"],                   "sta_isim"),
]

# Ürün adı aramasında anlamsız genel kelimeler (çok sonuç getirir)
_PRODUCT_STOP_WORDS = {
    "VE", "İLE", "BİR", "BU", "ŞU", "O", "DA", "DE",
    "ÇOK", "EN", "İÇİN", "OLAN", "VEYA", "AMA",
    "THE", "AND", "OR", "FOR", "WITH",
}


# ─────────────────────────────────────────────────────────────────────────────
# ZERO RESULT HANDLER
# ─────────────────────────────────────────────────────────────────────────────

class ZeroResultHandler:
    """
    0 satır döndüren sorgular için öneri servisi.
    SQL'i otomatik düzeltmek yerine kullanıcıya "bunu mu kastettiniz?" sorar.
    """

    def __init__(self, openai_client: OpenAI, executor, model: str = "gpt-4o-mini"):
        self.client   = openai_client
        self.executor = executor
        self.model    = model
        logger.info("✅ ZeroResultHandler başlatıldı (Mikro AI)")

    def handle(self, sql: str, question: str, original_result) -> Dict:
        logger.info("[ZeroResult] 0 satır → öneri modu devreye giriyor...")

        like_patterns = self._extract_like_patterns(sql)
        if not like_patterns:
            logger.info("[ZeroResult] LIKE pattern bulunamadı.")
            return {"clarification_needed": False}

        column_searches = self._map_patterns_to_columns(sql, like_patterns)
        if not column_searches:
            return {"clarification_needed": False}

        all_suggestions = []
        message_parts   = []

        for cs in column_searches:
            candidates = self._fetch_fuzzy_candidates(cs)
            if not candidates:
                continue

            col_label  = COLUMN_LABELS.get(cs["column"], cs["column"])
            clean_term = cs["clean_term"]

            for val in candidates[:3]:
                all_suggestions.append({
                    "label":     val,
                    "value":     val.upper(),
                    "column":    cs["column"],
                    "col_label": col_label,
                })

            top_names = ", ".join(f'"{v}"' for v in candidates[:3])
            message_parts.append(
                f'"{clean_term}" adında {col_label} bulunamadı. '
                f'Şunları mı kastettiniz: {top_names}?'
            )

        if not all_suggestions:
            return {
                "clarification_needed": False,
                "message": "Arama kriterlerinizle eşleşen sonuç bulunamadı.",
            }

        message = " | ".join(message_parts)
        logger.info(f"[ZeroResult] {len(all_suggestions)} öneri hazırlandı")

        return {
            "clarification_needed": True,
            "suggestions":          all_suggestions,
            "message":              message,
            "original_question":    question,
        }

    # ── Private ──────────────────────────────────────────────────────────────

    def _clean_sql_pattern(self, pattern: str) -> str:
        """'%TRD%SIPARI%' → 'TRD SIPARI'"""
        cleaned = re.sub(r"\[([^\]]+)\]", lambda m: m.group(1)[0], pattern)
        cleaned = cleaned.replace("%", " ")
        cleaned = " ".join(cleaned.split()).strip()
        return cleaned

    def _extract_like_patterns(self, sql: str) -> List[str]:
        """SQL'den LIKE pattern'lerini çıkar (NOT LIKE hariç)."""
        result = []
        for line in sql.split("\n"):
            if re.search(r"NOT\s+LIKE", line, re.IGNORECASE):
                continue
            matches = re.findall(r"LIKE\s+['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
            for m in matches:
                clean = self._clean_sql_pattern(m)
                if len(clean.replace(" ", "")) >= 2:
                    result.append(m)
        return result

    def _map_patterns_to_columns(self, sql: str, like_patterns: List[str]) -> List[Dict]:
        results   = []
        sql_upper = sql.upper()

        for pattern in like_patterns:
            clean_term = self._clean_sql_pattern(pattern)

            # Pattern'in SQL'deki konumunu bul
            like_pos = -1
            for m in re.finditer(
                r"LIKE\s+['\"]" + re.escape(pattern) + r"['\"]", sql, re.IGNORECASE
            ):
                like_pos = m.start()
                break

            if like_pos == -1:
                continue

            snippet = sql[:like_pos].rstrip()
            snippet = re.sub(
                r"\s+COLLATE\s+\w+\s*$", "", snippet, flags=re.IGNORECASE
            ).rstrip()

            # Kolon adını tespit et
            found_col = None
            for col in SEARCHABLE_COLUMNS:
                if snippet.upper().endswith(col.upper()):
                    found_col = col
                    break
                if re.search(r"\b" + col + r"\s*$", snippet, re.IGNORECASE):
                    found_col = col
                    break

            # Fallback
            if not found_col:
                for keywords, col in _SQL_COLUMN_FALLBACK_MAP:
                    if any(kw in sql_upper for kw in keywords):
                        found_col = col
                        break

            # Son çare: ürün adı en yaygın arama
            if not found_col:
                found_col = "sto_isim"
                logger.warning(f"[ZeroResult] Kolon tespit edilemedi, fallback: sto_isim")

            results.append({
                "column":     found_col,
                "pattern":    pattern,
                "clean_term": clean_term,
            })

        return results

    def _select_search_words(self, clean_term: str, column: str) -> List[str]:
        """Temiz arama teriminden anlamlı kelimeleri seç."""
        words = clean_term.split()

        if column in ("sto_isim", "sto_kod"):
            # Ürün: sayılar + uzun kelimeler öncelikli, stop word'ler atlanır
            priority  = []
            secondary = []
            for w in words:
                wu = w.upper()
                if wu in _PRODUCT_STOP_WORDS:
                    continue
                if re.search(r"\d", w):
                    priority.append(w)
                elif len(w) >= 4:
                    secondary.append(w)
                else:
                    secondary.append(w)
            selected = priority if priority else secondary
            return selected[:4]

        elif column == "cari_unvan1":
            # Müşteri: uzun kelimeler önce
            return [w for w in words if len(w) >= 3][:4]

        else:
            return [w for w in words if len(w) >= 2][:4]

    def _fetch_fuzzy_candidates(self, cs: Dict) -> List[str]:
        """DB'den fuzzy benzerlik ile en yakın değerleri çek."""
        col        = cs["column"]
        clean_term = cs["clean_term"]

        # Tablo bilgisini al
        if col not in COLUMN_TABLE_MAP:
            logger.warning(f"[ZeroResult] Tablo haritasında kolon yok: {col}")
            return []

        table, db_col, where_clause = COLUMN_TABLE_MAP[col]
        candidates = []

        # Kelime bazlı arama
        search_words = self._select_search_words(clean_term, col)
        for word in search_words:
            safe_word = re.sub(r"['\";\\%_]", "", word)
            if len(safe_word) < 2:
                continue

            sql = (
                f"SELECT DISTINCT {db_col} "
                f"FROM {table} "
                f"WHERE LOWER({db_col}) LIKE LOWER('%{safe_word}%') "
                f"AND {db_col} IS NOT NULL "
                f"AND {where_clause} "
                f"ORDER BY {db_col} "
                f"LIMIT 20"
            )
            try:
                result = self.executor.execute_query(sql)
                if result.success and result.data:
                    for row in result.data:
                        val = row.get(db_col)
                        if val and str(val).strip() and str(val) not in candidates:
                            candidates.append(str(val).strip())
                logger.debug(f"[ZeroResult] '{safe_word}' → {len(result.data) if result.success else 0} sonuç")
            except Exception as e:
                logger.error(f"[ZeroResult] DB lookup hatası ({safe_word}): {e}")

        # N-gram araması
        ngram_src = re.sub(r"\s+", "", clean_term)
        ngrams    = [ngram_src[i:i+3] for i in range(max(0, len(ngram_src) - 2))]
        for ngram in ngrams[:6]:
            safe = re.sub(r"['\";\\%_]", "", ngram)
            if len(safe) < 2:
                continue
            sql = (
                f"SELECT DISTINCT {db_col} "
                f"FROM {table} "
                f"WHERE LOWER({db_col}) LIKE LOWER('%{safe}%') "
                f"AND {db_col} IS NOT NULL "
                f"AND {where_clause} "
                f"ORDER BY {db_col} "
                f"LIMIT 10"
            )
            try:
                result = self.executor.execute_query(sql)
                if result.success and result.data:
                    for row in result.data:
                        val = row.get(db_col)
                        if val and str(val).strip() and str(val) not in candidates:
                            candidates.append(str(val).strip())
            except Exception as e:
                logger.error(f"[ZeroResult] n-gram hatası ({safe}): {e}")
            if len(candidates) >= 20:
                break

        if not candidates:
            logger.info(f"[ZeroResult] '{clean_term}' için DB'de aday bulunamadı")
            return []

        return self._rank_by_similarity(clean_term, candidates, col)

    def _rank_by_similarity(
        self, search_term: str, candidates: List[str], column: str
    ) -> List[str]:
        """LLM ile en benzer 3 adayı seç."""
        if len(candidates) <= 3:
            return candidates[:3]

        col_label        = COLUMN_LABELS.get(column, column)
        candidates_text  = "\n".join(f"- {c}" for c in candidates[:20])

        prompt = f"""Kullanıcı "{search_term}" adında bir {col_label} aradı ama bulunamadı.
Aşağıdaki gerçek değerlerden kullanıcının kastettiği olabilecek EN BENZER 3 tanesini seç.

Seçim kriterleri (önem sırasına göre):
1. Türkçe karakter farklılıklarını dikkate al (İ/I, Ş/S, Ğ/G, Ü/U, Ö/O, Ç/C)
2. Yazım hatalarını ve kısaltmaları dikkate al
3. Anlam yakınlığını dikkate al
4. İlgisiz adayları kesinlikle seçme

Mevcut değerler:
{candidates_text}

Sadece seçtiğin 3 değeri, her biri ayrı satırda, başka hiçbir şey yazmadan döndür:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150,
            )
            lines    = response.choices[0].message.content.strip().split("\n")
            selected = []
            for line in lines:
                clean = line.strip().lstrip("- •123456789.)").strip()
                if clean and clean in candidates:
                    selected.append(clean)
                if len(selected) == 3:
                    break

            if not selected:
                logger.warning("[ZeroResult] LLM geçerli aday seçemedi, ilk 3 kullanılıyor")
                return candidates[:3]

            return selected

        except Exception as e:
            logger.error(f"[ZeroResult] LLM ranking hatası: {e}")
            return candidates[:3]