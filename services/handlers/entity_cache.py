"""
KOBİ AI Platform — Entity Cache & Fuzzy Matcher (SQLite)
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz, process as rfprocess
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

FUZZY_THRESHOLD = 60


class EntityCache:

    ENTITY_QUERIES = {
        "product": (
            "SELECT DISTINCT sto_isim AS val FROM STOKLAR "
            "WHERE sto_isim IS NOT NULL AND sto_iptal=0 AND sto_hidden=0 LIMIT 2000"
        ),
        "product_code": (
            "SELECT DISTINCT sto_kod AS val FROM STOKLAR "
            "WHERE sto_kod IS NOT NULL AND sto_iptal=0 LIMIT 2000"
        ),
        "brand": (
            "SELECT DISTINCT mrk_ismi AS val FROM STOK_MARKALARI "
            "WHERE mrk_ismi IS NOT NULL AND mrk_iptal=0 LIMIT 500"
        ),
        "channel": (
            "SELECT DISTINCT sip_eticaret_kanal_kodu AS val FROM SIPARISLER "
            "WHERE sip_eticaret_kanal_kodu IS NOT NULL AND sip_eticaret_kanal_kodu!='' "
            "AND sip_iptal=0"
        ),
        "category": (
            "SELECT DISTINCT san_isim AS val FROM STOK_ANA_GRUPLARI "
            "WHERE san_isim IS NOT NULL AND san_iptal=0 LIMIT 200"
        ),
        "customer": (
            "SELECT DISTINCT cari_unvan1 AS val FROM CARI_HESAPLAR "
            "WHERE cari_unvan1 IS NOT NULL AND cari_iptal=0 AND cari_hidden=0 LIMIT 1000"
        ),
    }

    PRODUCT_SIGNALS  = ["ürün", "urun", "stok", "mal", "pijama", "gömlek", "pantolon",
                        "elbise", "ayakkabı", "çanta", "tişört", "bluz", "sto_isim"]
    BRAND_SIGNALS    = ["marka", "brand", "markası", "markalı"]
    CHANNEL_SIGNALS  = ["trendyol", "hepsiburada", "n11", "amazon", "kanal", "platform",
                        "pazaryeri", "pazar yeri", "e-ticaret", "eticaret", "csp"]
    CATEGORY_SIGNALS = ["kategori", "grup", "ana grup", "giyim", "aksesuar", "ev yaşam"]
    CUSTOMER_SIGNALS = ["müşteri", "musteri", "cari", "alıcı", "customer"]

    CHANNEL_ALIASES = {
        "trendyol": "Trendyol", "trendyl": "Trendyol", "trendiol": "Trendyol",
        "hepsiburada": "HepsiBurada", "hepsi": "HepsiBurada", "hb": "HepsiBurada",
        "n11": "N11", "n 11": "N11",
        "amazon": "Amazon",
        "kendi site": "CSP", "kendi sitem": "CSP", "websitem": "CSP", "csp": "CSP",
    }

    def __init__(self, executor):
        self.executor = executor
        self._cache: Dict[str, List[str]] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        print("[EntityCache] Entity'ler yükleniyor...")
        for entity_type, sql in self.ENTITY_QUERIES.items():
            try:
                result = self.executor.execute_query(sql)
                if result.success and result.data:
                    col = result.columns[0]
                    values = [str(r[col]).strip() for r in result.data if r.get(col)]
                    self._cache[entity_type] = values
                    print(f"[EntityCache] {entity_type}: {len(values)} kayıt")
                else:
                    self._cache[entity_type] = []
            except Exception as e:
                self._cache[entity_type] = []
                print(f"[EntityCache] {entity_type} hata: {e}")
        self._loaded = True

    def enrich_question(self, question: str) -> Tuple[str, List[str]]:
        if not self._loaded:
            self.load()
        if not RAPIDFUZZ_AVAILABLE:
            return "", []

        q_lower = question.lower()
        matches, context_lines = [], []

        channel_match = self._check_channel_alias(q_lower)
        if channel_match:
            context_lines.append(
                f"- E-Ticaret Kanalı: \"{channel_match}\" "
                f"(SQL: sip_eticaret_kanal_kodu = '{channel_match}')"
            )
            matches.append(channel_match)

        search_types = []
        if any(s in q_lower for s in self.PRODUCT_SIGNALS):
            search_types.append("product")
        if any(s in q_lower for s in self.BRAND_SIGNALS):
            search_types.append("brand")
        if not channel_match and any(s in q_lower for s in self.CHANNEL_SIGNALS):
            search_types.append("channel")
        if any(s in q_lower for s in self.CATEGORY_SIGNALS):
            search_types.append("category")
        if any(s in q_lower for s in self.CUSTOMER_SIGNALS):
            search_types.append("customer")
        if not search_types and not channel_match:
            search_types = ["product", "channel", "customer"]

        type_labels = {
            "product": "Ürün adı", "product_code": "Ürün kodu",
            "brand": "Marka adı", "channel": "Satış kanalı",
            "category": "Ürün kategorisi", "customer": "Müşteri adı",
        }

        for entity_type in search_types:
            candidates = self._cache.get(entity_type, [])
            if not candidates:
                continue
            best_match, best_score = self._find_best_match(question, candidates)
            if not best_match or best_score < FUZZY_THRESHOLD:
                continue
            label = type_labels.get(entity_type, entity_type)
            if entity_type == "product":
                like = self._make_product_like_pattern(best_match)
                context_lines.append(
                    f"- {label}: \"{best_match}\"\n"
                    f"  SQL: WHERE LOWER(sto_isim) LIKE LOWER('{like}')"
                )
            elif entity_type == "channel":
                context_lines.append(
                    f"- {label}: \"{best_match}\"\n"
                    f"  SQL: WHERE sip_eticaret_kanal_kodu = '{best_match}'"
                )
            elif entity_type == "customer":
                like = self._make_like_pattern(best_match)
                context_lines.append(
                    f"- {label}: \"{best_match}\"\n"
                    f"  SQL: WHERE LOWER(cari_unvan1) LIKE LOWER('{like}')"
                )
            else:
                context_lines.append(f"- {label}: \"{best_match}\"")
            matches.append(best_match)

        if context_lines:
            ctx = "VERİTABANINDAKİ GERÇEK DEĞERLER (SQL yazarken bunları kullan):\n" + "\n".join(context_lines)
            return ctx, matches
        return "", []

    def _check_channel_alias(self, q_lower: str) -> Optional[str]:
        for alias, canonical in self.CHANNEL_ALIASES.items():
            if alias in q_lower:
                return canonical
        return None

    def _make_product_like_pattern(self, product_name: str) -> str:
        stop = {"ve", "ile", "bir", "bu", "şu", "o", "da", "de", "mi", "the", "and"}
        words = [w for w in product_name.split() if w.lower() not in stop and len(w) >= 3]
        selected = words[:3] or [product_name]
        return "%" + "%".join(selected) + "%"

    def _make_like_pattern(self, value: str) -> str:
        return f"%{value.replace(' ', '%')}%"

    def _find_best_match(self, question: str, candidates: List[str]) -> Tuple[Optional[str], float]:
        if not candidates:
            return None, 0.0
        best_match, best_score = None, 0.0
        result = rfprocess.extractOne(question, candidates, scorer=fuzz.partial_ratio, score_cutoff=FUZZY_THRESHOLD)
        if result:
            best_match, best_score = result[0], result[1]
        words = [w for w in re.split(r'\s+', question) if len(w) >= 3]
        for word in words:
            r = rfprocess.extractOne(word, candidates, scorer=fuzz.partial_ratio, score_cutoff=FUZZY_THRESHOLD)
            if r and r[1] > best_score:
                best_match, best_score = r[0], r[1]
        return best_match, best_score

    def get_stats(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._cache.items()}

    def clear(self, entity_type: str = None) -> None:
        if entity_type:
            self._cache.pop(entity_type, None)
        else:
            self._cache.clear()
            self._loaded = False
