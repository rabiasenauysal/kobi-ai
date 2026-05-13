"""
KOBİ AI Platform — SQL Agent (LangGraph tabanlı hata düzeltme)

Akış:
  execute → check_error
                ↓ hata
         classify_error
          ↙    ↓    ↘
    syntax  column  unknown
          ↘    ↓    ↙
           fix_sql
               ↓
            execute  (max 3 retry)

NOT: TYF kalıntıları (View_RaceResults_Analytics, ActivityYear vb.) tamamen
kaldırıldı. KOBİ ERP tabloları ve kolonları kullanılıyor.
"""

import re
from typing import Any, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from openai import OpenAI


# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    question: str
    sql: str
    sql_original: str
    error: str
    error_type: str
    retry_count: int
    result: Optional[Any]
    schema_context: str
    column_names: List[str]
    forced_viz_type: Optional[str]


MAX_RETRY = 3

# ── SQLite mikro_ai.db — gerçek kolon adları (doğrulandı) ───────────────────
ALL_COLUMN_NAMES = [
    # SIPARISLER  ← sip_durum TEXT! sip_durumu/sip_depono/sip_teslim_tarih YOK!
    "sip_no", "sip_Guid", "sip_tarih", "sip_musteri_kod",
    "sip_eticaret_kanal_kodu", "sip_evrakno_seri", "sip_evrakno_sira",
    "sip_durum", "sip_tutar", "sip_kargo_no", "sip_aciklama",
    "sip_iptal", "sip_hidden",

    # STOK_HAREKETLERI  ← sth_tarih YOK! sth_fis_tarihi kullan!
    "sth_id", "sth_stok_kod", "sth_cari_kodu", "sth_sip_uid",
    "sth_fis_tarihi", "sth_birimfiyat", "sth_tutar", "sth_miktar",
    "sth_iskonto1", "sth_masraf1",
    "sth_cins", "sth_evrakno_seri", "sth_evrakno_sira",
    "sth_iptal", "sth_hidden",

    # STOKLAR  ← sto_birim1_ad/sto_max_stok/sto_resim_url YOK!
    "sto_kod", "sto_isim",
    "sto_marka_kodu", "sto_anagrup_kod", "sto_altgrup_kod",
    "sto_satis_fiyat1", "sto_satis_fiyat2", "sto_alis_fiyat",
    "sto_birim", "sto_min_stok",
    "sto_iptal", "sto_hidden",

    # CARI_HESAPLAR  ← cari_eposta (cari_EMail DEĞİL!)
    "cari_kod", "cari_unvan1", "cari_unvan2", "cari_eposta",
    "cari_tel", "cari_sehir", "cari_telegram_chat_id",
    "cari_iptal", "cari_hidden",

    # KARGO_GONDERILERI  ← kargo_firma TEXT (kargo_sirkettipi YOK!)
    "kargo_id", "kargo_evrakuid", "kargo_sip_no", "kargo_takip_no",
    "kargo_firma", "kargo_durum", "kargo_gonderim_tarihi",
    "kargo_teslim_tarihi", "kargo_beklenen_teslim",
    "kargo_gecikme_flag", "kargo_musteri_bilgilendirildi",
    "kargo_iptal", "kargo_hidden",

    # IADE_TALEPLERI  ← itlp_stok_kodu (itlp_stokodu DEĞİL!)
    "itlp_id", "itlp_musteri_kodu", "itlp_stok_kodu", "itlp_miktari",
    "itlp_aciklama", "itlp_tarihi", "itlp_tip", "itlp_durum",
    "itlp_evrak_sira", "itlp_iptal", "itlp_hidden",

    # E_TICARET_URUN_ESLEME
    "eu_stok_kodu", "eu_eticaret_platform_id", "eu_eticaret_urun_id",
    "eu_Guid", "eu_iptal", "eu_hidden",

    # STOK_DEPO_DETAYLARI  ← sdp_stok_miktari = gerçek stok!
    "sdp_id", "sdp_depo_kod", "sdp_depo_no", "sdp_stok_miktari",
    "sdp_sip_stok", "sdp_min_stok", "sdp_max_stok",
    "sdp_iptal", "sdp_hidden",

    # GOREVLER
    "id", "baslik", "aciklama", "atanan_rol", "atanan_kullanici_id",
    "durum", "oncelik", "sip_no", "tarih", "tamamlanma_tarihi", "olusturma_tarihi",

    # STOK_FIYAT_DEGISIKLIKLERI
    "fid_stok_kod", "fid_eskifiy_tutar", "fid_yenifiy_tutar",
    "fid_tarih", "fid_prof_uid", "fid_iptal", "fid_hidden",

    # CARI_HESAP_HAREKETLERI
    "cha_kod", "cha_meblag", "cha_cinsi", "cha_tarihi",
    "cha_aciklama", "cha_evrakno_seri", "cha_evrakno_sira",
    "cha_vade", "cha_sip_uid", "cha_iptal", "cha_hidden",

    # ODEME_EMIRLERI
    "sck_sahip_cari_kodu", "sck_tutar", "sck_tip",
    "sck_taksit_sayisi", "sck_vade", "sck_bankano", "sck_duzen_tarih",
    "sck_iptal", "sck_hidden",

    # BARKOD_TANIMLARI  ← bar_kodu (NOT: bar_barkodno DEĞİL!)
    "bar_stokkodu", "bar_kodu", "bar_barkodtipi",
    "bar_iptal", "bar_hidden",

    # STOK_MARKALARI  ← prefix: mrk_ (marka_ değil!)
    "mrk_kod", "mrk_ismi", "mrk_iptal", "mrk_hidden",

    # STOK_ANA_GRUPLARI  ← prefix: san_ (sag_ değil!)
    "san_kod", "san_isim", "san_iptal", "san_hidden",

    # STOK_ALT_GRUPLARI  ← prefix: sta_
    "sta_kod", "sta_isim", "sta_ana_grup_kod", "sta_iptal", "sta_hidden",

    # DEPOLAR
    "dep_no", "dep_adi", "dep_Il", "dep_subeno", "dep_iptal", "dep_hidden",

    # CARI_HESAP_ADRESLERI
    "adr_cari_kod", "adr_cadde", "adr_il", "adr_Semt",
    "adr_posta_kodu", "adr_tel_no1", "adr_Adres_kodu",
    "adr_iptal", "adr_hidden",
]

# Veritabanı ve tablo referansı (agent fix prompt'larında kullanılır)
DB_CONTEXT = "SQLite (mikro_ai.db)"

# LLM düzeltme prompt'larına eklenen kritik kolon haritası
KOLON_HARITASI = """
⚠️ SQLite KURALLARI:
  - YEAR()/MONTH() yok → strftime('%Y', kolon) / strftime('%m', kolon) kullan
  - STRING_AGG yok → group_concat(kolon, ', ') kullan
  - TOP N yok → LIMIT N kullan
  - ISNULL yok → COALESCE(kolon, 0) kullan
  - COLLATE Turkish_CI_AS yok → LOWER(kolon) LIKE LOWER('%...%') kullan

VAR OLMAYAN → DOĞRU KOLON:
  sip_durumu       → sip_durum  (TEXT: 'Hazırlanıyor'|'Kargoya Verildi'|'Teslim Edildi'|'İptal')
  sip_depono/sip_teslim_tarih/sip_create_date/sip_satici_kod → YOK!
  sto_miktar       → YOKTUR! Stok miktarı için: STOK_DEPO_DETAYLARI.sdp_stok_miktari (gerçek stok)
  sto_birim1_ad/sto_max_stok/sto_resim_url → YOK! birim için: sto_birim
  sth_tarih        → YOK! Tarih için: sth_fis_tarihi kullan!
  sth_miktar2/sth_ilave_edilecek_kdv/sth_satirno/sth_giris_depo_no → YOK!
  kargo_sirkettipi → kargo_firma (TEXT: 'Aras'|'MNG'|'Yurtiçi'|'PTT'|'Sürat')
  kargo_evraknosira → kargo_id  (int, birincil anahtar)
  kargo_gonderitarihi → kargo_gonderim_tarihi
  kargo_mastergonderino → YOK!
  cari_EMail/cari_Email → cari_eposta
  cari_grup_kodu/cari_bolge_kodu/cari_kaydagiristarihi → YOK!
  itlp_neden       → itlp_aciklama   (iade nedeni)
  itlp_tarih       → itlp_tarihi     (sonda 'i' var!)
  sip_uid          → sth_sip_uid     (JOIN için: sth_evrakno_sira=sip_evrakno_sira)
  kargo_kaynak     → sip_eticaret_kanal_kodu  (SIPARISLER'de)
  marka_isim/marka_kod → mrk_ismi / mrk_kod  (STOK_MARKALARI prefix: mrk_)
  sag_isim/sag_kod → san_isim / san_kod       (STOK_ANA_GRUPLARI prefix: san_)
  salt_isim/salt_kod → sta_isim / sta_kod     (STOK_ALT_GRUPLARI prefix: sta_)
  bar_barkodno     → bar_kodu                 (BARKOD_TANIMLARI)
  dvz_alis/dvz_satis → dov_fiyat1 / dov_fiyat2 (DOVIZ_KURLARI prefix: dov_)
  [placeholder]    → YASAK! Gerçek değer kullan veya mantıklı filtre yaz.
"""
MAIN_TABLES = (
    "SIPARISLER, STOKLAR, STOK_HAREKETLERI, CARI_HESAPLAR, "
    "KARGO_GONDERILERI, IADE_TALEPLERI, E_TICARET_URUN_ESLEME, "
    "STOK_DEPO_DETAYLARI, STOK_FIYAT_DEGISIKLIKLERI, "
    "CARI_HESAP_HAREKETLERI, ODEME_EMIRLERI, BARKOD_TANIMLARI"
)


# ─────────────────────────────────────────────
# KURAL TABANLI DÜZELTME HARİTASI
# LLM ve find_closest_column'dan önce bu kontrol edilir.
# ─────────────────────────────────────────────
KURAL_TABANLI_DUZELTMELER = {
    # SIPARISLER yanlış kolonlar → doğru
    "sip_durumu":        "sip_durum",
    "sip_depono":        "REWRITE:siparis_durum",  # kolon yok
    # STOKLAR'da miktar kolonu yok — doğru tablo: STOK_DEPO_DETAYLARI
    "sto_miktar":        "REWRITE:kritik_stok",
    "minimum_eşik":      "REWRITE:kritik_stok",
    "minimum_esik":      "REWRITE:kritik_stok",
    "sto_birim1_ad":     "sto_birim",
    # STOK_HAREKETLERI
    "sth_tarih":         "sth_fis_tarihi",
    # KARGO yanlış kolonlar → doğru
    "kargo_sirkettipi":  "kargo_firma",
    "kargo_evraknosira": "kargo_id",
    "kargo_gonderitarihi": "kargo_gonderim_tarihi",
    "kargo_mastergonderino": "kargo_id",
    # CARI_HESAPLAR
    "cari_email":        "cari_eposta",
    "cari_EMail":        "cari_eposta",
    "cari_grup_kodu":    "cari_kod",
    # İade kolonları
    "itlp_neden":        "itlp_aciklama",
    # itlp_sip_uid yoktur — agent crash döngüsünü kır
    "itlp_sip_uid":      "REWRITE:iade_ciro",
    "itlp_tarih":        "itlp_tarihi",
    # Sipariş JOIN kolonu
    "sip_uid":           "sth_sip_uid",
    # Kanal kolonu
    "kargo_kaynak":      "sip_eticaret_kanal_kodu",
    # Referans tablo prefix'leri (eski/yanlış → doğru)
    "marka_isim":        "mrk_ismi",
    "marka_kod":         "mrk_kod",
    "marka_iptal":       "mrk_iptal",
    "sag_isim":          "san_isim",
    "sag_kod":           "san_kod",
    "sag_iptal":         "san_iptal",
    "salt_isim":         "sta_isim",
    "salt_kod":          "sta_kod",
    "bar_barkodno":      "bar_kodu",
    "dvz_alis":          "dov_fiyat1",
    "dvz_satis":         "dov_fiyat2",
    "dvz_tarih":         "dov_tarih",
    "dvz_kod":           "dov_no",
    # STOK_DEPO_DETAYLARI
    "sdp_sip_stok":      "sdp_stok_miktari",  # siparişte bekleyen değil, gerçek stok
}

# İade + Ciro birleşik sorgu şablonu (Cartesian product önleme)
IADE_CIRO_SQL = """WITH iade AS (
    SELECT itlp_musteri_kodu,
           COUNT(*) AS iade_sayisi,
           SUM(itlp_miktari) AS iade_adet
    FROM IADE_TALEPLERI
    WHERE itlp_iptal = 0 AND itlp_hidden = 0
    GROUP BY itlp_musteri_kodu
),
ciro AS (
    SELECT sth_cari_kodu,
           SUM(sth_birimfiyat * sth_miktar) AS toplam_ciro,
           COUNT(DISTINCT sth_evrakno_sira) AS siparis_sayisi
    FROM STOK_HAREKETLERI
    WHERE sth_cins = 8 AND sth_iptal = 0 AND sth_hidden = 0
    GROUP BY sth_cari_kodu
)
SELECT
    i.itlp_musteri_kodu,
    i.iade_sayisi,
    i.iade_adet,
    COALESCE(c.toplam_ciro, 0)     AS toplam_ciro,
    COALESCE(c.siparis_sayisi, 0)  AS siparis_sayisi,
    ROUND(i.iade_adet / NULLIF(c.siparis_sayisi, 0) * 100, 1) AS iade_oran_pct
FROM iade i
LEFT JOIN ciro c ON i.itlp_musteri_kodu = c.sth_cari_kodu
ORDER BY i.iade_sayisi DESC
LIMIT 50"""

# Kritik stok sorgusu için hazır SQL şablonu (SQLite doğrulanmış)
KRITIK_STOK_SQL = """SELECT
    s.sto_kod,
    s.sto_isim,
    COALESCE(sdp.sdp_stok_miktari, 0) AS mevcut_stok,
    sdp.sdp_min_stok,
    sdp.sdp_min_stok - COALESCE(sdp.sdp_stok_miktari, 0) AS stok_acigi
FROM STOKLAR s
JOIN STOK_DEPO_DETAYLARI sdp ON s.sto_kod = sdp.sdp_depo_kod
WHERE s.sto_iptal = 0 AND s.sto_hidden = 0
  AND sdp.sdp_iptal = 0
  AND sdp.sdp_min_stok > 0
  AND COALESCE(sdp.sdp_stok_miktari, 0) <= sdp.sdp_min_stok
ORDER BY stok_acigi DESC
LIMIT 50"""

# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def classify_error(error_msg: str) -> str:
    e = error_msg.lower()

    # GROUP BY / aggregate hatası — syntax'tan önce kontrol et
    if (
        "not contained in either an aggregate" in e
        or "is invalid in the select list" in e
        or "(8120)" in e
    ):
        return "group_by_error"

    # Invalid column
    if (
        "invalid column name" in e
        or "42s22" in e
        or "(207)" in e
        or ("column" in e and "not found" in e)
        or "multi-part identifier" in e
    ):
        return "invalid_column"

    # Syntax
    if (
        "incorrect syntax" in e
        or "syntax error" in e
        or "42000" in e
        or "unexpected token" in e
        or "parse error" in e
        or "(102)" in e
    ):
        return "syntax"

    # Invalid object / table
    if (
        "invalid object name" in e
        or ("object" in e and "not found" in e)
        or "(208)" in e
    ):
        return "invalid_table"

    # Divide by zero
    if "divide by zero" in e or "(8134)" in e:
        return "divide_by_zero"

    return "unknown"


def extract_bad_column(error_msg: str) -> Optional[str]:
    match = re.search(r"invalid column name ['\"]?(\w+)['\"]?", error_msg, re.IGNORECASE)
    if match:
        return match.group(1)
    match2 = re.search(r'multi-part identifier ["\']([^"\']+)["\']', error_msg, re.IGNORECASE)
    if match2:
        return match2.group(1)
    return None


def find_closest_column(bad_col: str, all_columns: List[str]) -> Optional[str]:
    """
    Hatalı kolon adına en yakın gerçek kolon adını bul.
    Güvenli: belirsiz prefix eşleşmelerini reddeder (LLM daha iyi düzeltir).
    """
    bad_upper = bad_col.upper().replace("_", "")

    # 1. Tam eşleşme (case-insensitive)
    for col in all_columns:
        if col.upper() == bad_col.upper():
            return col

    # 2. Güçlü içerme — en az 5 karakter overlap
    if len(bad_upper) >= 5:
        for col in all_columns:
            col_norm = col.upper().replace("_", "")
            if bad_upper in col_norm and len(bad_upper) >= 5:
                return col

    # 3. Benzer suffix (son 6+ karakter eşleşiyor)
    if len(bad_upper) >= 6:
        for col in all_columns:
            col_norm = col.upper().replace("_", "")
            if len(col_norm) >= 6 and bad_upper[-6:] == col_norm[-6:]:
                return col

    # 4. Prefix eşleşmesi SADECE 7+ karakter için — kısa prefix yanıltıcı
    if len(bad_upper) >= 7:
        for col in all_columns:
            col_norm = col.upper().replace("_", "")
            if len(col_norm) >= 7 and bad_upper[:7] == col_norm[:7]:
                return col

    # Güvenli eşleşme bulunamadı → LLM düzeltsin
    return None


def is_cte_query(sql: str) -> bool:
    sql_upper = sql.upper().strip()
    return sql_upper.startswith("WITH ") and " AS (" in sql_upper


# ─────────────────────────────────────────────
# AGENT
# ─────────────────────────────────────────────

class SQLAgent:

    def __init__(self, openai_client: OpenAI, sql_executor, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.executor = sql_executor
        self.model = model
        self.graph = self._build_graph()
        print(f"✅ SQLAgent başlatıldı (model: {model}, max_retry: {MAX_RETRY})")

    # ── GRAPH ──────────────────────────────────

    def _build_graph(self):
        g = StateGraph(AgentState)

        g.add_node("execute",        self._node_execute)
        g.add_node("classify_error", self._node_classify_error)
        g.add_node("fix_syntax",     self._node_fix_syntax)
        g.add_node("fix_column",     self._node_fix_column)
        g.add_node("fix_unknown",    self._node_fix_unknown)

        g.set_entry_point("execute")

        g.add_conditional_edges("execute", self._route_after_execute, {
            "success":        END,
            "classify_error": "classify_error",
            "max_retry":      END,
        })

        g.add_conditional_edges("classify_error", self._route_error_type, {
            "syntax":   "fix_syntax",
            "column":   "fix_column",
            "unknown":  "fix_unknown",
        })

        g.add_edge("fix_syntax",  "execute")
        g.add_edge("fix_column",  "execute")
        g.add_edge("fix_unknown", "execute")

        return g.compile()

    # ── ROUTING ────────────────────────────────

    def _route_after_execute(self, state: AgentState) -> str:
        if state["result"] and state["result"].success:
            return "success"
        if state["retry_count"] >= MAX_RETRY:
            print(f"   ⛔ Max retry ({MAX_RETRY}) aşıldı, durduruluyor.")
            return "max_retry"
        return "classify_error"

    def _route_error_type(self, state: AgentState) -> str:
        t = state["error_type"]
        if t in ("syntax", "group_by_error", "divide_by_zero"):
            return "syntax"
        if t in ("invalid_column", "invalid_table"):
            return "column"
        return "unknown"

    # ── NODES ──────────────────────────────────

    def _node_execute(self, state: AgentState) -> AgentState:
        retry = state["retry_count"]
        if retry > 0:
            print(f"   🔄 Retry #{retry}: SQL çalıştırılıyor...")
        else:
            print(f"   ⚡ SQL çalıştırılıyor...")

        result = self.executor.execute_query(
            state["sql"],
            forced_viz_type=state.get("forced_viz_type")
        )

        if result.success:
            print(f"   ✅ Başarılı! {result.row_count} satır")
            return {**state, "result": result, "error": ""}
        else:
            print(f"   ❌ Hata: {result.error}")
            return {**state, "result": result, "error": result.error or ""}

    def _node_classify_error(self, state: AgentState) -> AgentState:
        error = state["error"]
        error_type = classify_error(error)
        print(f"   🔍 Hata tipi: {error_type} | {error[:80]}")
        return {**state, "error_type": error_type, "retry_count": state["retry_count"] + 1}

    def _node_fix_syntax(self, state: AgentState) -> AgentState:
        print(f"   🔧 Syntax düzeltme...")
        sql = state["sql"]
        error = state["error"]

        # ── 1. STRING_AGG(DISTINCT ...) → SQL Server desteklemiyor ──
        if re.search(r'STRING_AGG\s*\(\s*DISTINCT', sql, re.IGNORECASE):
            print(f"   ✏️  LLM'siz düzeltme: STRING_AGG(DISTINCT ...) → STRING_AGG(...)")
            fixed = re.sub(
                r'STRING_AGG\s*\(\s*DISTINCT\s+',
                'STRING_AGG(',
                sql,
                flags=re.IGNORECASE
            )
            return {**state, "sql": fixed}

        # ── 2. Sıfıra bölme hatası → NULLIF ile düzelt ──────────────
        if state["error_type"] == "divide_by_zero" or "divide by zero" in error.lower():
            print(f"   🤖 Sıfıra bölme hatası (LLM)...")
            prompt = f"""SQLite'da sıfıra bölme hatası aldık.

HATA: {error}

HATALI SQL:
{sql}

ÇÖZÜM: Bölen ifadeyi NULLIF(..., 0) ile sar. Örnek:
  YANLIŞ: count_satis / count_iade
  DOĞRU:  count_satis / NULLIF(count_iade, 0)

Ayrıca NULL sonuçlar için COALESCE(..., 0) kullan (SQLite'da ISNULL yok).
Sadece düzeltilmiş SQL'i döndür. Markdown kullanma."""
            fixed = self._call_llm(prompt)
            return {**state, "sql": fixed}

        # ── 3. GROUP BY hatası ───────────────────────────────────────
        if state["error_type"] == "group_by_error" or (
            "not contained in either an aggregate" in error.lower()
            or "(8120)" in error
        ):
            print(f"   🤖 GROUP BY hatası düzeltme (LLM)...")
            prompt = f"""SQLite GROUP BY hatası aldık.
SELECT listesinde aggregate fonksiyona alınmamış veya GROUP BY'a eklenmemiş kolon var.

HATA: {error}

HATALI SQL:
{sql}

Hataya sebep olan kolonu ya GROUP BY'a ekle ya da aggregate fonksiyona (MIN, MAX, STRING_AGG vs.) al.

⚠️ UYARI: SQLite'da STRING_AGG YOK — group_concat(kolon, sep) kullan. ISNULL yerine COALESCE, TOP yerine LIMIT kullan.

Sadece düzeltilmiş SQL'i döndür. Markdown kullanma."""
            fixed = self._call_llm(prompt)
            print(f"   ✏️  Düzeltilmiş SQL: {fixed[:80]}...")
            return {**state, "sql": fixed}

        # ── 4. Genel syntax hatası (LLM) ────────────────────────────
        print(f"   🤖 Syntax hatası LLM ile düzeltiliyor...")
        cte_rule = ""
        if is_cte_query(sql):
            cte_rule = "\n⚠️ CTE KURALI: Dış SELECT'te kullanılacak tüm kolonların CTE SELECT listesinde tanımlı olması şart!\n"

        col_list = self._build_col_list()
        prompt = f"""SQLite syntax hatası aldık. SQL'i düzelt.

HATA: {error}

HATALI SQL:
{sql}

VERİTABANI: {DB_CONTEXT}
ANA TABLOLAR: {MAIN_TABLES}
{cte_rule}
⚠️ UYARI: SQLite'da STRING_AGG YOK — group_concat(kolon, sep) kullan. ISNULL yerine COALESCE, TOP yerine LIMIT kullan.

MEVCUT KOLONLAR (örnek):
{col_list[:800]}

Sadece düzeltilmiş SQL'i döndür. Açıklama yapma. Markdown kullanma."""

        fixed = self._call_llm(prompt)
        print(f"   ✏️  Düzeltilmiş SQL: {fixed[:80]}...")
        return {**state, "sql": fixed}

    def _node_fix_column(self, state: AgentState) -> AgentState:
        print(f"   🔧 Kolon düzeltme...")
        error = state["error"]
        sql = state["sql"]
        bad_col = extract_bad_column(error)
        col_list = self._build_col_list()

        # ── CTE SORGUSU ───────────────────────────────────────────
        if is_cte_query(sql):
            print(f"   🤖 CTE kolon düzeltme...")
            prompt = f"""SQLite'da CTE kolon hatası aldık.

HATA: {error}

HATALI SQL:
{sql}

VERİTABANI: {DB_CONTEXT}
⚠️ CTE KURALI: Dış SELECT'te kullanılacak tüm kolonların CTE SELECT listesinde tanımlı olması şart!

MEVCUT KOLONLAR:
{col_list}

Hem yanlış kolon adını düzelt hem CTE SELECT listelerini kontrol et.
Sadece düzeltilmiş SQL'i döndür. Açıklama yapma. Markdown kullanma."""
            fixed = self._call_llm(prompt)
            print(f"   ✏️  Düzeltilmiş SQL: {fixed[:80]}...")
            return {**state, "sql": fixed}

        # ── ÖNCE: Kural tabanlı bilinen hatalar ──────────────────
        # SQL'deki tüm [bracket] placeholder'ları tespit et
        import re as _re
        brackets = _re.findall(r'\[([^\]]{2,40})\]', sql)
        has_placeholder = any(
            any(c in p for c in ' ,.-') or any(ord(c) > 127 for c in p)
            for p in brackets
        )

        # Bilinen yanlış kolon → doğru eşleştirme
        rewrite_needed = None
        for wrong, right in KURAL_TABANLI_DUZELTMELER.items():
            # Boşlukları normalize ederek karşılaştır
            sql_norm = _re.sub(r'\s+', ' ', sql.lower())
            if wrong.lower() in sql_norm:
                if right.startswith("REWRITE:"):
                    rewrite_needed = right.split(":")[1]
                    break
                else:
                    print(f"   ✏️  Kural tabanlı düzeltme: '{wrong}' → '{right}'")
                    sql = _re.sub(
                        rf'(?i)\b{_re.escape(wrong)}\b',
                        right, sql
                    )
                    # Birden fazla kural uygulanabilir, devam et
                    state = {**state, "sql": sql}

        if rewrite_needed == "iade_ciro":
            print(f"   ✏️  Kural tabanlı REWRITE: iade+ciro → güvenli CTE şablonu")
            return {**state, "sql": IADE_CIRO_SQL}

        if rewrite_needed == "kritik_stok":
            print(f"   ✏️  Kural tabanlı REWRITE: stok miktarı → KRİTİK STOK şablonu")
            return {**state, "sql": KRITIK_STOK_SQL}

        # Kural dışı basit düzeltme yapıldıysa dön
        sql = state["sql"]
        if sql != state.get("sql_original", ""):
            # placeholder kalmadıysa direkt dön
            remaining = _re.findall(r'\[([^\]]{2,40})\]', sql)
            bad_remaining = [p for p in remaining
                             if any(c in p for c in ' ,.-') or any(ord(c) > 127 for c in p)]
            if not bad_remaining:
                return {**state, "sql": sql}

        # ── NORMAL SORGU: önce LLM'siz dene ──────────────────────
        if bad_col:
            closest = find_closest_column(bad_col, ALL_COLUMN_NAMES)
            if closest and closest.upper() != bad_col.upper():
                print(f"   ✏️  LLM'siz düzeltme: '{bad_col}' → '{closest}'")
                fixed_sql = _re.sub(
                    rf'\b{_re.escape(bad_col)}\b',
                    closest,
                    sql,
                    flags=_re.IGNORECASE
                )
                return {**state, "sql": fixed_sql}

        # LLM ile düzelt
        print(f"   🤖 LLM ile kolon düzeltme...")
        prompt = f"""SQLite'da kolon ismi hatası aldık.

HATA: {error}

HATALI SQL:
{sql}

VERİTABANI: {DB_CONTEXT}
ANA TABLOLAR: {MAIN_TABLES}

{KOLON_HARITASI}

MEVCUT KOLONLAR:
{col_list}

Hataya sebep olan kolon adını yukarıdaki haritaya ve kolon listesine göre düzelt.
Sadece düzeltilmiş SQL'i döndür. Açıklama yapma. Markdown kullanma."""

        fixed = self._call_llm(prompt)
        print(f"   ✏️  Düzeltilmiş SQL: {fixed[:80]}...")
        return {**state, "sql": fixed}

    def _node_fix_unknown(self, state: AgentState) -> AgentState:
        print(f"   🔧 Bilinmeyen hata - schema ile düzeltme (LLM)...")
        col_list = self._build_col_list()

        cte_rule = ""
        if is_cte_query(state["sql"]):
            cte_rule = "\n⚠️ CTE KURALI: Dış SELECT'te kullanılacak tüm kolonların CTE SELECT listesinde tanımlı olması şart!\n"

        prompt = f"""SQLite hatası aldık. Hatayı analiz edip SQL'i düzelt.

KULLANICI SORUSU: {state['question']}

HATA: {state['error']}

HATALI SQL:
{state['sql']}

VERİTABANI: {DB_CONTEXT}
ANA TABLOLAR: {MAIN_TABLES}
{cte_rule}
{KOLON_HARITASI}

⚠️ STRING_AGG YOK → group_concat(kolon, sep) kullan. TOP yerine LIMIT. ISNULL yerine COALESCE.
⚠️ Sıfıra bölme → NULLIF(..., 0) kullan.
⚠️ JOIN'leri açıkça yaz — FK yok.
⚠️ [placeholder] YASAK — gerçek değer veya mantıklı filtre kullan.
⚠️ SIPARISLER-STOK_HAREKETLERI JOIN: sth_sip_uid NULL olabilir!
   Güvenli: ON s.sip_evrakno_sira=sth.sth_evrakno_sira AND s.sip_evrakno_seri=sth.sth_evrakno_seri
⚠️ Tarih filtresi için sth_fis_tarihi kullan (sth_tarih NULL olabilir!)

MEVCUT KOLONLAR:
{col_list[:1500]}

SCHEMA CONTEXT:
{state['schema_context'][:800]}

Hatanın sebebini bul ve düzelt. Sadece düzeltilmiş SQL döndür. Markdown kullanma."""

        fixed = self._call_llm(prompt)
        print(f"   ✏️  Düzeltilmiş SQL: {fixed[:80]}...")
        return {**state, "sql": fixed}

    # ── YARDIMCI ───────────────────────────────

    def _build_col_list(self) -> str:
        return "\n".join(f"- {c}" for c in ALL_COLUMN_NAMES)

    def _call_llm(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=800,
        )
        sql = response.choices[0].message.content.strip()

        # Markdown temizle
        if sql.startswith("```"):
            sql = sql.split("```")[1]
            if sql.lower().startswith("sql\n") or sql.lower().startswith("sql "):
                sql = sql[3:]
            sql = sql.strip()
        if sql.endswith("```"):
            sql = sql[:-3].strip()

        return sql

    # ── PUBLIC API ─────────────────────────────

    def run(
        self,
        sql: str,
        question: str,
        schema_context: str,
        forced_viz_type: Optional[str] = None,
    ):
        """
        Agent'ı çalıştır.
        rag_service.py'de hata alınınca çağrılır.
        Returns: (QueryResult, final_sql)
        """
        initial_state: AgentState = {
            "question":        question,
            "sql":             sql,
            "sql_original":    sql,
            "error":           "",
            "error_type":      "",
            "retry_count":     0,
            "result":          None,
            "schema_context":  schema_context,
            "column_names":    ALL_COLUMN_NAMES,
            "forced_viz_type": forced_viz_type,
        }

        final_state = self.graph.invoke(initial_state)

        result    = final_state["result"]
        final_sql = final_state["sql"]
        retries   = final_state["retry_count"]

        if retries > 0:
            if result and result.success:
                print(f"   ✅ Agent {retries} denemede düzeltti.")
            else:
                print(f"   ⛔ Agent {retries} denemede düzeltemedi.")

        return result, final_sql