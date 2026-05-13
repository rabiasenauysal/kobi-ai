-- KOBİ AI Platform — SQLite Şema
-- Mikro ERP tablo yapısına uyumlu, SQLite syntax ile

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─── Referans Tablolar ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS STOK_MARKALARI (
    mrk_kod  TEXT PRIMARY KEY,
    mrk_ismi TEXT NOT NULL,
    mrk_iptal   INTEGER DEFAULT 0,
    mrk_hidden  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS STOK_ANA_GRUPLARI (
    san_kod  TEXT PRIMARY KEY,
    san_isim TEXT NOT NULL,
    san_iptal   INTEGER DEFAULT 0,
    san_hidden  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS STOK_ALT_GRUPLARI (
    sta_kod     TEXT PRIMARY KEY,
    sta_isim    TEXT NOT NULL,
    sta_ana_grup TEXT,
    sta_iptal   INTEGER DEFAULT 0,
    sta_hidden  INTEGER DEFAULT 0
);

-- ─── Ürün ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS STOKLAR (
    sto_kod          TEXT PRIMARY KEY,
    sto_isim         TEXT NOT NULL,
    sto_marka_kodu   TEXT,
    sto_anagrup_kod  TEXT,
    sto_altgrup_kod  TEXT,
    sto_satis_fiyat1 REAL DEFAULT 0,
    sto_satis_fiyat2 REAL DEFAULT 0,
    sto_alis_fiyat   REAL DEFAULT 0,
    sto_birim        TEXT DEFAULT 'ADET',
    sto_min_stok     REAL DEFAULT 0,
    sto_iptal        INTEGER DEFAULT 0,
    sto_hidden       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS STOK_DEPO_DETAYLARI (
    sdp_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sdp_depo_kod    TEXT NOT NULL,
    sdp_depo_no     INTEGER DEFAULT 1,
    sdp_stok_miktari REAL DEFAULT 0,
    sdp_sip_stok    REAL DEFAULT 0,
    sdp_min_stok    REAL DEFAULT 0,
    sdp_max_stok    REAL DEFAULT 0,
    sdp_iptal       INTEGER DEFAULT 0,
    sdp_hidden      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS BARKOD_TANIMLARI (
    bar_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bar_stok_kodu TEXT,
    bar_kodu      TEXT,
    bar_iptal     INTEGER DEFAULT 0,
    bar_hidden    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS E_TICARET_URUN_ESLEME (
    eu_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    eu_stok_kodu       TEXT,
    eu_platform_kodu   TEXT,
    eu_platform        TEXT,
    eu_platform_urun_id TEXT,
    eu_iptal           INTEGER DEFAULT 0,
    eu_hidden          INTEGER DEFAULT 0
);

-- ─── Müşteri ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS CARI_HESAPLAR (
    cari_kod      TEXT PRIMARY KEY,
    cari_unvan1   TEXT NOT NULL,
    cari_unvan2   TEXT,
    cari_eposta   TEXT,
    cari_tel      TEXT,
    cari_sehir    TEXT,
    cari_telegram_chat_id TEXT,
    cari_iptal    INTEGER DEFAULT 0,
    cari_hidden   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS CARI_HESAP_ADRESLERI (
    adr_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    adr_cari_kod TEXT,
    adr_il       TEXT,
    adr_ilce     TEXT,
    adr_adres    TEXT,
    adr_iptal    INTEGER DEFAULT 0,
    adr_hidden   INTEGER DEFAULT 0
);

-- ─── Sipariş ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SIPARISLER (
    sip_no                   TEXT PRIMARY KEY,
    sip_Guid                 TEXT UNIQUE,
    sip_evrakno_sira         INTEGER,
    sip_evrakno_seri         TEXT,
    sip_musteri_kod          TEXT,
    sip_tarih                TEXT,
    sip_eticaret_kanal_kodu  TEXT,
    sip_durum                TEXT DEFAULT 'Hazırlanıyor',
    sip_tutar                REAL DEFAULT 0,
    sip_kargo_no             TEXT,
    sip_aciklama             TEXT,
    sip_iptal                INTEGER DEFAULT 0,
    sip_hidden               INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS SIPARIS_ESLEME (
    es_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    es_sip_guid  TEXT,
    es_stok_kodu TEXT,
    es_miktar    REAL DEFAULT 1,
    es_fiyat     REAL DEFAULT 0
);

-- ─── Stok Hareketleri ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS STOK_HAREKETLERI (
    sth_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sth_fis_tarihi    TEXT,
    sth_stok_kod      TEXT,
    sth_sip_uid       TEXT,
    sth_evrakno_sira  INTEGER,
    sth_evrakno_seri  TEXT,
    sth_cins          INTEGER,
    sth_miktar        REAL DEFAULT 0,
    sth_tutar         REAL,
    sth_birimfiyat    REAL DEFAULT 0,
    sth_iskonto1      REAL DEFAULT 0,
    sth_masraf1       REAL DEFAULT 0,
    sth_cari_kodu     TEXT,
    sth_iptal         INTEGER DEFAULT 0,
    sth_hidden        INTEGER DEFAULT 0
);

-- ─── Kargo ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS KARGO_GONDERILERI (
    kargo_id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    kargo_evrakuid               TEXT,
    kargo_sip_no                 TEXT,
    kargo_takip_no               TEXT,
    kargo_firma                  TEXT,
    kargo_durum                  TEXT DEFAULT 'Hazırlanıyor',
    kargo_gonderim_tarihi        TEXT,
    kargo_teslim_tarihi          TEXT,
    kargo_beklenen_teslim        TEXT,
    kargo_gecikme_flag           INTEGER DEFAULT 0,
    kargo_musteri_bilgilendirildi INTEGER DEFAULT 0,
    kargo_iptal                  INTEGER DEFAULT 0,
    kargo_hidden                 INTEGER DEFAULT 0
);

-- ─── İade ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS IADE_TALEPLERI (
    itlp_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    itlp_tarihi       TEXT,
    itlp_musteri_kodu TEXT,
    itlp_stok_kodu    TEXT,
    itlp_miktari      REAL DEFAULT 1,
    itlp_aciklama     TEXT,
    itlp_tip          TEXT DEFAULT 'İade',
    itlp_durum        TEXT DEFAULT 'Bekliyor',
    itlp_evrak_sira   INTEGER,
    itlp_iptal        INTEGER DEFAULT 0,
    itlp_hidden       INTEGER DEFAULT 0
);

-- ─── Ödeme ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ODEME_EMIRLERI (
    sck_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sck_sip_no    TEXT,
    sck_tarih     TEXT,
    sck_tutar     REAL DEFAULT 0,
    sck_odeme_tipi TEXT,
    sck_iptal     INTEGER DEFAULT 0,
    sck_hidden    INTEGER DEFAULT 0
);

-- ─── Döviz ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS DOVIZ_KURLARI (
    dov_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dov_tarih     TEXT,
    dov_doviz_kodu TEXT,
    dov_fiyat1    REAL,
    dov_fiyat2    REAL
);

-- ─── Yeni Tablolar (Hackathon Özellikleri) ──────────────────────────────────

CREATE TABLE IF NOT EXISTS KULLANICILAR (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT UNIQUE NOT NULL,
    sifre_hash      TEXT NOT NULL,
    ad              TEXT,
    rol             TEXT DEFAULT 'yonetici',
    aktif           INTEGER DEFAULT 1,
    olusturma_tarihi TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS GOREVLER (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    baslik               TEXT NOT NULL,
    aciklama             TEXT,
    atanan_rol           TEXT,
    atanan_kullanici_id  INTEGER,
    durum                TEXT DEFAULT 'Bekliyor',
    oncelik              TEXT DEFAULT 'Normal',
    sip_no               TEXT,
    tarih                TEXT DEFAULT (date('now')),
    tamamlanma_tarihi    TEXT,
    olusturma_tarihi     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS BILDIRIMLER (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    tip                  TEXT,
    baslik               TEXT,
    mesaj                TEXT,
    hedef                TEXT DEFAULT 'yonetici',
    okundu               INTEGER DEFAULT 0,
    telegram_gonderildi  INTEGER DEFAULT 0,
    olusturma_tarihi     TEXT DEFAULT (datetime('now'))
);

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
);

CREATE TABLE IF NOT EXISTS ChatMessages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    client_id  TEXT,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    sql_query  TEXT,
    row_count  INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- ─── İndeksler ──────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_sip_tarih   ON SIPARISLER(sip_tarih);
CREATE INDEX IF NOT EXISTS idx_sip_kanal   ON SIPARISLER(sip_eticaret_kanal_kodu);
CREATE INDEX IF NOT EXISTS idx_sip_musteri ON SIPARISLER(sip_musteri_kod);
CREATE INDEX IF NOT EXISTS idx_sth_tarih   ON STOK_HAREKETLERI(sth_fis_tarihi);
CREATE INDEX IF NOT EXISTS idx_sth_cins    ON STOK_HAREKETLERI(sth_cins);
CREATE INDEX IF NOT EXISTS idx_sth_stok    ON STOK_HAREKETLERI(sth_stok_kod);
CREATE INDEX IF NOT EXISTS idx_kargo_sip   ON KARGO_GONDERILERI(kargo_sip_no);
CREATE INDEX IF NOT EXISTS idx_kargo_gecik ON KARGO_GONDERILERI(kargo_gecikme_flag);
CREATE INDEX IF NOT EXISTS idx_log_session ON ChatbotUsageLogs(session_id);
CREATE INDEX IF NOT EXISTS idx_msg_session ON ChatMessages(session_id);
