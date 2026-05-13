"""
KOBİ AI Platform — Manuel Schema (E-Ticaret / ERP)
=====================================================
Veritabanı: MIKRO_AI  |  34 tablo  |  306 anlamlı kolon
Kaynak: db_schema_raw.json (2026-05-09) — TÜM KOLON ADLARI DOĞRULANMIŞTIR.

DÜZELTILEN HATALAR (önceki sürüme göre):
  STOK_MARKALARI  : marka_kod/marka_isim    → mrk_kod/mrk_ismi
  STOK_ANA_GRUPLARI: sag_kod/sag_isim       → san_kod/san_isim
  STOK_ALT_GRUPLARI: salt_kod/salt_isim     → sta_kod/sta_isim
  DOVIZ_KURLARI   : dvz_alis/dvz_satis      → dov_fiyat1/dov_fiyat2/dov_no
  KARGO_TANIMLARI : kargo_kod/kargo_isim    → krg_kodu/krg_adi
  STOK_BEDEN      : beden_kod/beden_isim    → bdn_kodu/bdn_ismi
  STOK_RENK       : renk_kod/renk_isim      → rnk_kodu/rnk_ismi
  CARI_HESAP_GRUPLARI: chg_kod/chg_isim     → crg_kod/crg_isim
  CARI_HESAP_BOLGELERI: bol_isim            → bol_ismi
  BANKALAR        : ban_isim                → ban_ismi
  DEPOLAR         : dep_isim                → dep_adi
  PERSONELLER     : per_isim                → per_adi
  STOK_BIRIMLERI  : bir_kod/bir_isim        → unit_ismi/unit_yabanci_isim
  ODEME_PLANLARI  : odp_kod/odp_isim        → odp_kodu/odp_adi
  PROMOSYON_TANIMLARI: prm_kod/prm_isim     → Promo_kodu/Promo_ismi

RAG MİMARİSİ — 3 Katmanlı Chunk Stratejisi:
  1. Tablo chunk'ları: Her tablo için zengin açıklama + gerçek kolon adları
  2. JOIN chunk'ları: Tablolar arası birleştirme yolları
  3. Query pattern chunk'ları: Sık kullanılan sorgu şablonları (YENİ)
"""

from typing import Dict, List, Any
import networkx as nx


# ─────────────────────────────────────────────────────────────────────────────
# MANUEL JOIN İLİŞKİLERİ
# ─────────────────────────────────────────────────────────────────────────────

class ManualSchemaGraph:
    """KOBİ ERP FK'sız JOIN ilişkileri."""

    MANUAL_RELATIONSHIPS = [
        ("STOK_HAREKETLERI",          "sth_sip_uid",           "SIPARISLER",              "sip_Guid"),
        ("SIPARISLER",                "sip_musteri_kod",        "CARI_HESAPLAR",           "cari_kod"),
        ("KARGO_GONDERILERI",         "kargo_evrakuid",         "SIPARISLER",              "sip_Guid"),
        ("STOK_HAREKETLERI",          "sth_stok_kod",           "STOKLAR",                 "sto_kod"),
        ("STOK_HAREKETLERI",          "sth_cari_kodu",          "CARI_HESAPLAR",           "cari_kod"),
        ("E_TICARET_URUN_ESLEME",     "eu_stok_kodu",           "STOKLAR",                 "sto_kod"),
        ("STOK_DEPO_DETAYLARI",       "sdp_depo_kod",           "STOKLAR",                 "sto_kod"),
        ("BARKOD_TANIMLARI",          "bar_stokkodu",           "STOKLAR",                 "sto_kod"),
        ("STOKLAR",                   "sto_marka_kodu",         "STOK_MARKALARI",          "mrk_kod"),
        ("STOKLAR",                   "sto_anagrup_kod",        "STOK_ANA_GRUPLARI",       "san_kod"),
        ("STOKLAR",                   "sto_altgrup_kod",        "STOK_ALT_GRUPLARI",       "sta_kod"),
        ("CARI_HESAP_HAREKETLERI",    "cha_kod",                "CARI_HESAPLAR",           "cari_kod"),
        ("CARI_HESAP_ADRESLERI",      "adr_cari_kod",           "CARI_HESAPLAR",           "cari_kod"),
        ("ODEME_EMIRLERI",            "sck_sahip_cari_kodu",    "CARI_HESAPLAR",           "cari_kod"),
        ("IADE_TALEPLERI",            "itlp_musteri_kodu",      "CARI_HESAPLAR",           "cari_kod"),
        ("IADE_TALEPLERI",            "itlp_stok_kodu",         "STOKLAR",                 "sto_kod"),
        ("STOK_FIYAT_DEGISIKLIKLERI", "fid_stok_kod",           "STOKLAR",                 "sto_kod"),
        ("STOKLAR",                   "sto_altgrup_kod",        "STOK_ALT_GRUPLARI",       "sta_kod"),
    ]

    @classmethod
    def build_graph(cls, tables: List[str] = None) -> nx.Graph:
        graph = nx.Graph()
        rels = cls.MANUAL_RELATIONSHIPS
        if tables:
            ts = {t.upper() for t in tables}
            rels = [r for r in rels if r[0].upper() in ts and r[2].upper() in ts]
        for child, cc, parent, pc in rels:
            cond = f"{child}.{cc} = {parent}.{pc}"
            if graph.has_edge(child, parent):
                graph[child][parent].setdefault("conditions", []).append(cond)
            else:
                graph.add_edge(child, parent, condition=cond, conditions=[cond])
        return graph

    @classmethod
    def get_table_descriptions(cls) -> Dict[str, str]:
        return _TABLE_DESCRIPTIONS


# ─────────────────────────────────────────────────────────────────────────────
# TABLO AÇIKLAMALARI
# ─────────────────────────────────────────────────────────────────────────────

_TABLE_DESCRIPTIONS: Dict[str, str] = {

"SIPARISLER": """TABLO: SIPARISLER — E-Ticaret Sipariş Başlıkları
Kullanım: Sipariş sayısı, kanal analizi, tarih filtresi, müşteri siparişleri.
Satır sayısı: ~24.000 | Prefix: sip_ | VERİTABANI: SQLite

⚠️ SQLite kullanılıyor: strftime('%Y', sip_tarih) kullan — YEAR() yok!
⚠️ sip_durum TEXT kolonudur — tinyint değil, CASE WHEN kullanma!

JOIN KOLONLARI:
- sip_Guid (TEXT): Ana join anahtarı.
  → sip_Guid = sth_sip_uid → STOK_HAREKETLERI (satır detayları, ciro)
  → sip_Guid = kargo_evrakuid → KARGO_GONDERILERI (kargo bilgisi)
- sip_musteri_kod (TEXT): → sip_musteri_kod = cari_kod → CARI_HESAPLAR
- sip_no (int): Sipariş numarası. kargo_sip_no ile eşleşir.

E-TİCARET KANALI:
- sip_eticaret_kanal_kodu (TEXT): Satış kanalı/pazar yeri.
  Değerler: 'Trendyol' | 'HepsiBurada' | 'N11' | 'CSP'
  Filtre: WHERE sip_eticaret_kanal_kodu = 'Trendyol'

ZAMAN:
- sip_tarih (TEXT): Sipariş tarihi. SQLite tarih: date(sip_tarih), strftime(...)

SİPARİŞ BİLGİSİ:
- sip_evrakno_sira (int): Evrak sıra numarası. STOK_HAREKETLERI.sth_evrakno_sira ile eşleşir.
- sip_evrakno_seri (TEXT): 'ETK' = e-ticaret siparişi.
- sip_durum (TEXT): ⚠️ 'Hazırlanıyor' | 'Kargoya Verildi' | 'Teslim Edildi' | 'İptal'
  Filtre: WHERE sip_durum = 'Hazırlanıyor'  — sayısal değer kullanma!
- sip_tutar (float): Sipariş toplam tutarı.
- sip_kargo_no (TEXT): Kargo takip numarası.
- sip_aciklama (TEXT): Açıklama alanı.

AKTİF FİLTRE: WHERE sip_iptal = 0 AND sip_hidden = 0
SİPARİŞ SAYIMI: COUNT(DISTINCT sip_Guid) — COUNT(*) kullanma!

ÖRNEK:
SELECT sip_eticaret_kanal_kodu, COUNT(DISTINCT sip_Guid) AS siparis_sayisi
FROM SIPARISLER WHERE sip_iptal = 0 GROUP BY sip_eticaret_kanal_kodu

DURUM SAYIMI:
SELECT sip_durum, COUNT(*) AS adet FROM SIPARISLER
WHERE sip_iptal=0 GROUP BY sip_durum""",

"STOK_HAREKETLERI": """TABLO: STOK_HAREKETLERI — Stok Giriş/Çıkış Hareketleri
Kullanım: CİRO HESABI, satış miktarı, ürün bazlı satış, aylık trend.
Satır sayısı: ~9.120 | Prefix: sth_

JOIN KOLONLARI:
- sth_sip_uid (uniqueidentifier): → sth_sip_uid = sip_Guid → SIPARISLER
- sth_stok_kod (nvarchar 25): → sth_stok_kod = sto_kod → STOKLAR
- sth_cari_kodu (nvarchar 25): → sth_cari_kodu = cari_kod → CARI_HESAPLAR
- sth_giris_depo_no (int): Depo numarası.

HAREKET TİPİ (sth_cins) — KRİTİK:
- sth_cins = 8: E-ticaret satışı ← CİRO HESABINDA ZORUNLU FİLTRE
- sth_cins = 7: Normal satış faturası
- sth_cins = 4: İade girişi
- sth_cins = 1: Alış girişi
- sth_evrakno_seri (nvarchar 255): 'ETK' = e-ticaret.
- sth_evrakno_sira (int): Evrak sıra numarası.
- sth_satirno (int): Sipariş satır numarası.

FİNANSAL KOLONLAR:
- sth_tutar (float): TOPLAM TUTAR — CİRO = SUM(sth_tutar)
- sth_birimfiyat (float): Birim satış fiyatı.
- sth_miktar (float): Satış miktarı (adet).
- sth_iskonto1 (float): İskonto oranı %.
- sth_masraf1 (float): Ek masraf.

ZAMAN:
- sth_fis_tarihi (TEXT): Fiş tarihi. TARİH FİLTRELERİ İÇİN BU KULLAN!
  ⚠️ sth_tarih kolonu SQLite DB'de YOK — sadece sth_fis_tarihi kullan!
  SQLite tarih: date(sth_fis_tarihi), strftime('%Y', sth_fis_tarihi)

AKTİF FİLTRE: WHERE sth_iptal = 0 AND sth_hidden = 0
E-TİCARET SATIŞ: WHERE sth_cins = 8 AND sth_iptal = 0

CİRO: SELECT SUM(sth_tutar) FROM STOK_HAREKETLERI WHERE sth_cins=8 AND sth_iptal=0
AYLIK: SELECT strftime('%Y', sth_fis_tarihi) AS yil,
              strftime('%m', sth_fis_tarihi) AS ay,
              SUM(sth_tutar) AS ciro
       FROM STOK_HAREKETLERI
       WHERE sth_cins=8 AND sth_iptal=0
       GROUP BY yil, ay ORDER BY yil, ay""",

"STOKLAR": """TABLO: STOKLAR — Ürün Kartları (SKU)
Kullanım: Ürün adı arama, marka/kategori filtresi, fiyatlar.
Satır sayısı: ~6.000 | Prefix: sto_

JOIN KOLONLARI (ANA ANAHTAR: sto_kod):
- sto_kod (TEXT): Ürün kodu. TÜM STOK JOIN'LERİNİN ANAHTARI.
  → sto_kod = sth_stok_kod → STOK_HAREKETLERI
  → sto_kod = sdp_depo_kod → STOK_DEPO_DETAYLARI (stok miktarı buradan!)
  → sto_kod = itlp_stok_kodu → IADE_TALEPLERI
- sto_marka_kodu (TEXT): → sto_marka_kodu = mrk_kod → STOK_MARKALARI
- sto_anagrup_kod (TEXT): → sto_anagrup_kod = san_kod → STOK_ANA_GRUPLARI
- sto_altgrup_kod (TEXT): → sto_altgrup_kod = sta_kod → STOK_ALT_GRUPLARI

ÜRÜN BİLGİSİ:
- sto_isim (TEXT): Ürün adı. ARAMA: LOWER(sto_isim) LIKE LOWER('%...%')
  ⚠️ SQLite'da COLLATE Turkish_CI_AS yok — LOWER() kullan!
- sto_birim (TEXT): 'AD'=Adet, 'CFT'=Çift, 'KG'=Kilogram
- sto_min_stok (float): Minimum stok / yeniden sipariş noktası.
- sto_satis_fiyat1 (float): Birinci satış fiyatı.
- sto_satis_fiyat2 (float): İkinci satış fiyatı.
- sto_alis_fiyat (float): Alış fiyatı.

⚠️ STOK MİKTARI STOKLAR'DA YOK! Mevcut stok için: STOK_DEPO_DETAYLARI.sdp_stok_miktari
⚠️ sto_birim1_ad, sto_max_stok, sto_resim_url, sto_plu_no kolonları YOK!

AKTİF FİLTRE: WHERE sto_iptal = 0 AND sto_hidden = 0

EN ÇOK SATAN ÜRÜNLER:
SELECT s.sto_kod, s.sto_isim, SUM(sth.sth_tutar) AS ciro
FROM STOK_HAREKETLERI sth JOIN STOKLAR s ON sth.sth_stok_kod = s.sto_kod
WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND s.sto_iptal=0
GROUP BY s.sto_kod, s.sto_isim ORDER BY ciro DESC""",

"CARI_HESAPLAR": """TABLO: CARI_HESAPLAR — Müşteri ve Tedarikçi Kayıtları
Kullanım: Müşteri adı arama, sipariş geçmişi, müşteri bazlı analiz.
Satır sayısı: ~5.000 | Prefix: cari_ | VERİTABANI: SQLite

JOIN KOLONLARI (ANA ANAHTAR: cari_kod):
- cari_kod (TEXT): Cari kodu. TÜM MÜŞTERİ JOIN'LERİNİN ANAHTARI.
  → cari_kod = sip_musteri_kod → SIPARISLER
  → cari_kod = sth_cari_kodu  → STOK_HAREKETLERI
  → cari_kod = itlp_musteri_kodu → IADE_TALEPLERI

MÜŞTERİ BİLGİSİ:
- cari_unvan1 (TEXT): Müşteri/firma adı. ARAMA BURADAN.
  ⚠️ SQLite'da COLLATE Turkish_CI_AS yok! Kullanım: LOWER(cari_unvan1) LIKE LOWER('%Ahmet%')
- cari_unvan2 (TEXT): İkinci ünvan / kısa ad.
- cari_eposta (TEXT): E-posta adresi. ⚠️ cari_EMail DEĞİL, cari_eposta!
- cari_tel (TEXT): Telefon numarası.
- cari_sehir (TEXT): Şehir.
- cari_telegram_chat_id (TEXT): Telegram chat ID (bildirim için).

⚠️ cari_EMail, cari_grup_kodu, cari_bolge_kodu, cari_kaydagiristarihi YOK!

AKTİF FİLTRE: WHERE cari_iptal = 0 AND cari_hidden = 0""",

"E_TICARET_URUN_ESLEME": """TABLO: E_TICARET_URUN_ESLEME — Platform Ürün Eşleme
Kullanım: Mikro stok kodu ile Trendyol/HepsiBurada/N11 ürün ID eşleştirme.
Satır sayısı: ~19.884 | Prefix: eu_

KOLONLAR:
- eu_stok_kodu (nvarchar 25): → eu_stok_kodu = sto_kod → STOKLAR
- eu_eticaret_platform_id (nvarchar 50): 'TRD'=Trendyol | 'HBS'=HepsiBurada | 'N11'=N11 | 'CSP'=Kendi Site
- eu_eticaret_urun_id (nvarchar 50): Platformdaki ürün ID (örn: 'TRD-46913810').
- eu_create_date (datetime2): Eşleme tarihi.
- eu_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE eu_iptal = 0 AND eu_hidden = 0""",

"STOK_DEPO_DETAYLARI": """TABLO: STOK_DEPO_DETAYLARI — Depo Bazlı Stok Seviyeleri
Kullanım: Kritik stok tespiti, depo bazlı stok durumu, mevcut stok miktarı.
Satır sayısı: ~18.000 | Prefix: sdp_

KOLONLAR:
- sdp_id (int): Birincil anahtar.
- sdp_depo_kod (TEXT): → sdp_depo_kod = sto_kod → STOKLAR
- sdp_depo_no (int): Depo numarası.
- sdp_stok_miktari (float): MEVCUTTAKİ GERÇEK STOK MİKTARI — bu kullan!
- sdp_sip_stok (float): Siparişe ayrılan/rezerve stok.
- sdp_min_stok (float): Minimum stok eşiği. Altına düşünce kritik!
- sdp_max_stok (float): Maksimum stok limiti.

AKTİF FİLTRE: WHERE sdp_iptal = 0 AND sdp_hidden = 0
KRİTİK STOK: WHERE sdp_stok_miktari <= sdp_min_stok (mevcut stok min eşiğin altında)

KRİTİK STOK SORGUSU:
SELECT sdp.sdp_depo_no, s.sto_kod, s.sto_isim,
       sdp.sdp_stok_miktari AS mevcut_stok, sdp.sdp_min_stok
FROM STOK_DEPO_DETAYLARI sdp JOIN STOKLAR s ON sdp.sdp_depo_kod = s.sto_kod
WHERE sdp.sdp_stok_miktari <= sdp.sdp_min_stok AND sdp.sdp_iptal=0 AND s.sto_iptal=0
ORDER BY sdp.sdp_stok_miktari ASC""",

"STOK_FIYAT_DEGISIKLIKLERI": """TABLO: STOK_FIYAT_DEGISIKLIKLERI — Fiyat Değişiklik Geçmişi
Kullanım: Fiyat artışı/azalışı analizi.
Satır sayısı: ~15.000 | Prefix: fid_

KOLONLAR:
- fid_stok_kod (nvarchar 25): → fid_stok_kod = sto_kod → STOKLAR
- fid_eskifiy_tutar (float): Eski fiyat.
- fid_yenifiy_tutar (float): Yeni fiyat.
- fid_tarih (datetime2): Fiyat değişiklik tarihi.
- fid_prof_uid (uniqueidentifier): İlişkili profil.
- fid_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE fid_iptal = 0 AND fid_hidden = 0

FİYAT DEĞİŞİM:
SELECT f.fid_stok_kod, s.sto_isim, f.fid_tarih, f.fid_eskifiy_tutar, f.fid_yenifiy_tutar,
       (f.fid_yenifiy_tutar - f.fid_eskifiy_tutar) AS fark
FROM STOK_FIYAT_DEGISIKLIKLERI f JOIN STOKLAR s ON f.fid_stok_kod = s.sto_kod
WHERE f.fid_iptal=0 AND s.sto_iptal=0 ORDER BY f.fid_tarih DESC""",

"IADE_TALEPLERI": """TABLO: IADE_TALEPLERI — Müşteri İade Talepleri
Kullanım: İade analizi, en çok iade edilen ürünler, iade nedeni dağılımı.
Satır sayısı: ~1.600 | Prefix: itlp_

KOLONLAR:
- itlp_musteri_kodu (nvarchar 25): → itlp_musteri_kodu = cari_kod → CARI_HESAPLAR
- itlp_stok_kodu (nvarchar 25): → itlp_stok_kodu = sto_kod → STOKLAR  ⚠️ itlp_stokodu DEĞİL!
- itlp_miktari (float): İade miktarı.
- itlp_aciklama (nvarchar 40): İade nedeni. Örnek: 'Renk farklı','Beden uygun değil'
- itlp_tarihi (datetime2): İade talep tarihi.
- itlp_tip (tinyint): 0=Standart 1=Değişim 2=Hasar
- itlp_evrak_sira (int): İade evrak numarası.
- itlp_stokhar_uid (uniqueidentifier): Bağlı stok hareketi.
- itlp_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE itlp_iptal = 0 AND itlp_hidden = 0

EN ÇOK İADE EDİLEN:
SELECT i.itlp_stok_kodu, s.sto_isim, COUNT(*) AS iade_sayisi
FROM IADE_TALEPLERI i JOIN STOKLAR s ON i.itlp_stok_kodu = s.sto_kod
WHERE i.itlp_iptal=0 AND s.sto_iptal=0
GROUP BY i.itlp_stok_kodu, s.sto_isim ORDER BY iade_sayisi DESC""",

"KARGO_GONDERILERI": """TABLO: KARGO_GONDERILERI — Kargo Gönderi Kayıtları
Kullanım: Kargo durumu, geciken kargolar, müşteri bilgilendirme.
Satır sayısı: ~7.952 | Prefix: kargo_ | VERİTABANI: SQLite

JOIN KOLONLARI:
- kargo_evrakuid (TEXT): → kargo_evrakuid = sip_Guid → SIPARISLER
- kargo_sip_no (int): → kargo_sip_no = sip_no → SIPARISLER

KARGO BİLGİSİ:
- kargo_id (int): Birincil anahtar.
- kargo_takip_no (TEXT): Kargo takip numarası.
- kargo_firma (TEXT): Kargo şirketi adı. 'Aras' | 'MNG' | 'Yurtiçi' | 'PTT' | 'Sürat'
  ⚠️ kargo_sirkettipi kolonu YOK — firma adı TEXT olarak kargo_firma'da!
- kargo_durum (TEXT): 'Hazırlanıyor' | 'Kargoda' | 'Yolda' | 'Gecikti' | 'Teslim Edildi' | 'İptal'
- kargo_gonderim_tarihi (TEXT): Kargoya teslim tarihi. ⚠️ kargo_gonderitarihi DEĞİL!
- kargo_teslim_tarihi (TEXT): Gerçek teslim tarihi.
- kargo_beklenen_teslim (TEXT): Planlanan teslim tarihi.
- kargo_gecikme_flag (int): 1=Gecikiyor, 0=Normal.
- kargo_musteri_bilgilendirildi (int): 1=Bilgilendirildi, 0=Bilgilendirilmedi.

⚠️ OLMAYAN KOLONLAR: kargo_evraknosira, kargo_sirkettipi, kargo_mastergonderino, kargo_gonderitarihi

AKTİF FİLTRE: WHERE kargo_iptal = 0 AND kargo_hidden = 0

GECİKEN KARGOLAR:
SELECT k.kargo_id, k.kargo_sip_no, k.kargo_firma, k.kargo_beklenen_teslim,
       c.cari_unvan1 AS musteri
FROM KARGO_GONDERILERI k
LEFT JOIN SIPARISLER s ON k.kargo_sip_no = s.sip_no
LEFT JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
WHERE k.kargo_gecikme_flag=1 AND k.kargo_iptal=0

KARGO FİRMA DAĞILIMI:
SELECT kargo_firma, COUNT(*) AS gonderi_sayisi
FROM KARGO_GONDERILERI WHERE kargo_iptal=0
GROUP BY kargo_firma ORDER BY gonderi_sayisi DESC""",

"CARI_HESAP_HAREKETLERI": """TABLO: CARI_HESAP_HAREKETLERI — Müşteri Hesap Hareketleri
Kullanım: Borç/alacak analizi, müşteri ödeme geçmişi.
Satır sayısı: ~8.000 | Prefix: cha_

KOLONLAR:
- cha_kod (nvarchar 25): → cha_kod = cari_kod → CARI_HESAPLAR
- cha_meblag (float): Hareket tutarı.
- cha_cinsi (tinyint): Hareket tipi. 6=E-ticaret satış.
- cha_tarihi (datetime2): Hareket tarihi.
- cha_vade (int): Vade gün sayısı.
- cha_aciklama (nvarchar 127): Açıklama.
- cha_evrakno_seri (nvarchar 255): 'ETK'=e-ticaret.
- cha_sip_uid (uniqueidentifier): → SIPARISLER.sip_Guid
- cha_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE cha_iptal = 0 AND cha_hidden = 0""",

"ODEME_EMIRLERI": """TABLO: ODEME_EMIRLERI — Ödeme Emirleri
Kullanım: Ödeme analizi, taksit, banka dağılımı.
Satır sayısı: ~8.330 | Prefix: sck_

KOLONLAR:
- sck_sahip_cari_kodu (nvarchar 25): → sck_sahip_cari_kodu = cari_kod → CARI_HESAPLAR
- sck_tutar (float): Ödeme tutarı.
- sck_tip (tinyint): Ödeme tipi.
- sck_taksit_sayisi (smallint): Taksit sayısı.
- sck_vade (datetime2): Vade tarihi.
- sck_bankano (nvarchar 25): → sck_bankano = ban_kod → BANKALAR
- sck_duzen_tarih (datetime2): Düzenlenme tarihi.
- sck_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE sck_iptal = 0 AND sck_hidden = 0""",

"BARKOD_TANIMLARI": """TABLO: BARKOD_TANIMLARI — Ürün Barkod Tanımları
Kullanım: Barkod ile ürün arama.
Satır sayısı: ~3.000 | Prefix: bar_

KOLONLAR:
- bar_stokkodu (nvarchar 25): → bar_stokkodu = sto_kod → STOKLAR
- bar_kodu (nvarchar 255): Barkod değeri (EAN-13, QR) ⚠️ bar_barkodno DEĞİL!
- bar_barkodtipi (tinyint): Barkod formatı.
- bar_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE bar_iptal = 0 AND bar_hidden = 0""",

"CARI_HESAP_ADRESLERI": """TABLO: CARI_HESAP_ADRESLERI — Müşteri Adres Kayıtları
Kullanım: Teslimat adresi, il bazlı analiz.
Satır sayısı: ~5.000 | Prefix: adr_

KOLONLAR:
- adr_cari_kod (nvarchar 25): → adr_cari_kod = cari_kod → CARI_HESAPLAR
- adr_Adres_kodu (nvarchar 10): '01'=Fatura, '02'=Teslimat.
- adr_cadde (nvarchar 127): Sokak/Cadde.
- adr_il (nvarchar 50): İl adı.
- adr_Semt (nvarchar 25): Semt/İlçe.
- adr_posta_kodu (nvarchar 8): Posta kodu.
- adr_tel_no1 (nvarchar 10): Telefon.
- adr_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE adr_iptal = 0 AND adr_hidden = 0""",

# ─── REFERANS TABLOLAR ─────────────────────────────────────────────────────

"STOK_MARKALARI": """TABLO: STOK_MARKALARI — Marka Tanımları
Satır sayısı: ~150 | Prefix: mrk_

KOLONLAR (JSON DOĞRULANDI):
- mrk_kod (nvarchar 25): Marka kodu. ⚠️ marka_kod DEĞİL!
  JOIN: mrk_kod = sto_marka_kodu → STOKLAR
- mrk_ismi (nvarchar 40): Marka adı. ⚠️ marka_isim DEĞİL, mrk_ismi!
- mrk_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE mrk_iptal = 0 AND mrk_hidden = 0

MARKA BAZLI SATIŞ:
SELECT m.mrk_ismi, SUM(sth.sth_tutar) AS ciro
FROM STOK_MARKALARI m
JOIN STOKLAR s ON m.mrk_kod = s.sto_marka_kodu
JOIN STOK_HAREKETLERI sth ON s.sto_kod = sth.sth_stok_kod
WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND s.sto_iptal=0 AND m.mrk_iptal=0
GROUP BY m.mrk_ismi ORDER BY ciro DESC""",

"STOK_ANA_GRUPLARI": """TABLO: STOK_ANA_GRUPLARI — Ana Ürün Kategorileri
Satır sayısı: ~12 | Prefix: san_

KOLONLAR (JSON DOĞRULANDI):
- san_kod (nvarchar 25): Ana grup kodu. ⚠️ sag_kod DEĞİL, san_kod!
  JOIN: san_kod = sto_anagrup_kod → STOKLAR
- san_isim (nvarchar 40): Ana grup adı. ⚠️ sag_isim DEĞİL, san_isim!
- san_Guid (int): Guid (int tipinde).

AKTİF FİLTRE: WHERE san_iptal = 0 AND san_hidden = 0""",

"STOK_ALT_GRUPLARI": """TABLO: STOK_ALT_GRUPLARI — Alt Ürün Kategorileri
Satır sayısı: ~68 | Prefix: sta_

KOLONLAR (JSON DOĞRULANDI):
- sta_kod (nvarchar 25): Alt grup kodu. ⚠️ salt_kod DEĞİL, sta_kod!
  JOIN: sta_kod = sto_altgrup_kod → STOKLAR
- sta_isim (nvarchar 40): Alt grup adı. ⚠️ salt_isim DEĞİL, sta_isim!
- sta_ana_grup_kod (nvarchar 25): → sta_ana_grup_kod = san_kod → STOK_ANA_GRUPLARI
- sta_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE sta_iptal = 0 AND sta_hidden = 0""",

"STOK_RENK_TANIMLARI": """TABLO: STOK_RENK_TANIMLARI — Renk Tanımları
Satır sayısı: ~20 | Prefix: rnk_

KOLONLAR (JSON DOĞRULANDI):
- rnk_kodu (nvarchar 25): Renk kodu. ⚠️ renk_kod DEĞİL, rnk_kodu!
- rnk_ismi (nvarchar 40): Renk adı. ⚠️ renk_isim DEĞİL, rnk_ismi!
  Örnek: 'Siyah', 'Beyaz', 'Kırmızı', 'Lacivert'
- rnk_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE rnk_iptal = 0 AND rnk_hidden = 0""",

"STOK_BEDEN_TANIMLARI": """TABLO: STOK_BEDEN_TANIMLARI — Beden Tanımları
Satır sayısı: ~18 | Prefix: bdn_

KOLONLAR (JSON DOĞRULANDI):
- bdn_kodu (nvarchar 25): Beden kodu. ⚠️ beden_kod DEĞİL, bdn_kodu!
- bdn_ismi (nvarchar 40): Beden adı. ⚠️ beden_isim DEĞİL, bdn_ismi!
  Örnek: 'XS', 'S', 'M', 'L', 'XL', 'XXL', '36', '38', '40'
- bdn_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE bdn_iptal = 0 AND bdn_hidden = 0""",

"STOK_KATEGORILERI": """TABLO: STOK_KATEGORILERI — Stok Kategorileri
Satır sayısı: ~12 | Prefix: ktg_

KOLONLAR (JSON DOĞRULANDI):
- ktg_kod (nvarchar 25): Kategori kodu. ⚠️ kat_kod DEĞİL, ktg_kod!
- ktg_isim (nvarchar 50): Kategori adı. ⚠️ kat_isim DEĞİL, ktg_isim!
- ktg_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE ktg_iptal = 0 AND ktg_hidden = 0""",

"STOK_BIRIMLERI": """TABLO: STOK_BIRIMLERI — Ölçü Birimleri
Satır sayısı: ~8 | Prefix: unit_

KOLONLAR (JSON DOĞRULANDI):
- unit_ismi (nvarchar 10): Birim adı. ⚠️ bir_isim DEĞİL, unit_ismi!
  Örnek: 'AD'=Adet, 'KG'=Kilogram, 'MT'=Metre
- unit_yabanci_isim (nvarchar 127): Yabancı dil birim adı.
- unit_Guid (int): GUID (int tipinde).

AKTİF FİLTRE: WHERE unit_iptal = 0 AND unit_hidden = 0""",

"DEPOLAR": """TABLO: DEPOLAR — Depo Tanımları
Satır sayısı: ~30 | Prefix: dep_

KOLONLAR (JSON DOĞRULANDI):
- dep_no (int): Depo numarası. sdp_depo_no ile eşleşir.
- dep_adi (nvarchar 50): Depo adı. ⚠️ dep_isim DEĞİL, dep_adi!
- dep_Il (nvarchar 50): Deponun bulunduğu il.
- dep_subeno (int): Bağlı şube numarası.
- dep_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE dep_iptal = 0 AND dep_hidden = 0""",

"KARGO_TANIMLARI": """TABLO: KARGO_TANIMLARI — Kargo Şirketi Tanımları
Satır sayısı: ~24 | Prefix: krg_

KOLONLAR (JSON DOĞRULANDI):
- krg_kodu (nvarchar 25): Kargo kodu. ⚠️ kargo_kod DEĞİL, krg_kodu!
- krg_adi (nvarchar 50): Kargo şirketi adı. ⚠️ kargo_isim DEĞİL, krg_adi!
- krg_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE krg_iptal = 0 AND krg_hidden = 0
NOT: kargo_sirkettipi: 1=Yurtiçi 2=Aras 3=MNG 4=PTT 5=Sürat""",

"CARI_HESAP_GRUPLARI": """TABLO: CARI_HESAP_GRUPLARI — Müşteri Grupları
Satır sayısı: ~15 | Prefix: crg_

KOLONLAR (JSON DOĞRULANDI):
- crg_kod (nvarchar 25): Grup kodu. ⚠️ chg_kod DEĞİL, crg_kod!
  JOIN: crg_kod = cari_grup_kodu → CARI_HESAPLAR
- crg_isim (nvarchar 40): Grup adı. ⚠️ chg_isim DEĞİL, crg_isim!
- crg_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE crg_iptal = 0 AND crg_hidden = 0""",

"CARI_HESAP_BOLGELERI": """TABLO: CARI_HESAP_BOLGELERI — Müşteri Bölgeleri
Satır sayısı: ~21 | Prefix: bol_

KOLONLAR (JSON DOĞRULANDI):
- bol_kod (nvarchar 25): Bölge kodu. JOIN: bol_kod = cari_bolge_kodu → CARI_HESAPLAR
- bol_ismi (nvarchar 40): Bölge adı. ⚠️ bol_isim DEĞİL, bol_ismi!
- bol_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE bol_iptal = 0 AND bol_hidden = 0""",

"BANKALAR": """TABLO: BANKALAR — Banka Tanımları
Satır sayısı: ~24 | Prefix: ban_

KOLONLAR (JSON DOĞRULANDI):
- ban_kod (nvarchar 25): Banka kodu. JOIN: ban_kod = sck_bankano → ODEME_EMIRLERI
- ban_ismi (nvarchar 50): Banka adı. ⚠️ ban_isim DEĞİL, ban_ismi!
- ban_SwiftKodu (nvarchar 25): SWIFT kodu.
- ban_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE ban_iptal = 0 AND ban_hidden = 0""",

"KASALAR": """TABLO: KASALAR — Kasa Tanımları
Satır sayısı: ~15 | Prefix: kas_

KOLONLAR:
- kas_kod (nvarchar 25): Kasa kodu.
- kas_isim (nvarchar 40): Kasa adı.
- kas_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE kas_iptal = 0 AND kas_hidden = 0""",

"ODEME_PLANLARI": """TABLO: ODEME_PLANLARI — Ödeme Planları
Satır sayısı: ~30 | Prefix: odp_

KOLONLAR (JSON DOĞRULANDI):
- odp_kodu (nvarchar 25): Plan kodu. ⚠️ odp_kod DEĞİL, odp_kodu!
- odp_adi (nvarchar 50): Plan adı. ⚠️ odp_isim DEĞİL, odp_adi!
  Örnek: 'Peşin', '3 Taksit', '6 Taksit', '12 Taksit'
- odp_no (int): Plan numarası.
- odp_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE odp_iptal = 0 AND odp_hidden = 0""",

"PROMOSYON_TANIMLARI": """TABLO: PROMOSYON_TANIMLARI — Kampanya/Promosyon Tanımları
Satır sayısı: ~20 | Prefix: Promo_

KOLONLAR (JSON DOĞRULANDI):
- Promo_kodu (nvarchar 25): Kampanya kodu. ⚠️ prm_kod DEĞİL, Promo_kodu!
- Promo_ismi (nvarchar 50): Kampanya adı. ⚠️ prm_isim DEĞİL, Promo_ismi!
- Promo_baslangic_gunu (datetime2): Başlangıç tarihi.
- Promo_bitis_gunu (datetime2): Bitiş tarihi.
- Promo_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE Promo_iptal = 0 AND Promo_hidden = 0""",

"DOVIZ_KURLARI": """TABLO: DOVIZ_KURLARI — Döviz Kuru Geçmişi
Kullanım: USD/EUR kur analizi, döviz fiyat dönüşümü.
Satır sayısı: ~4.386 | Prefix: dov_

KOLONLAR (JSON DOĞRULANDI):
- dov_no (tinyint): Döviz kodu/tipi. ⚠️ dvz_kod DEĞİL, dov_no!
- dov_tarih (datetime2): Kur tarihi. ⚠️ dvz_tarih DEĞİL, dov_tarih!
- dov_fiyat1 (float): Birinci kur (alış). ⚠️ dvz_alis DEĞİL, dov_fiyat1!
- dov_fiyat2 (float): İkinci kur (satış). ⚠️ dvz_satis DEĞİL, dov_fiyat2!
- dov_fiyat3 (float): Üçüncü kur değeri.
- dov_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE dov_iptal = 0 AND dov_hidden = 0""",

"PERSONELLER": """TABLO: PERSONELLER — Personel Kayıtları
Satır sayısı: ~60 | Prefix: per_

KOLONLAR (JSON DOĞRULANDI):
- per_kod (nvarchar 25): Personel kodu. SIPARISLER.sip_satici_kod ile eşleşir.
- per_adi (nvarchar 50): Personel adı. ⚠️ per_isim DEĞİL, per_adi!
- per_soyadi (nvarchar 50): Personel soyadı.
- per_giris_tar (datetime2): İşe giriş tarihi.
- per_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE per_iptal = 0 AND per_hidden = 0""",

"SUBELER": """TABLO: SUBELER — Şube Tanımları
Satır sayısı: ~3 | Prefix: Sube_ (büyük S!)

KOLONLAR (JSON DOĞRULANDI):
- Sube_kodu (nvarchar 15): Şube kodu. Örnek: 'MRK'=Merkez.
- Sube_adi (nvarchar 50): Şube adı.
- Sube_no (int): Şube numarası.
- sube_Il (nvarchar 50): Şubenin ili. ⚠️ küçük 's' ile başlar!
- Sube_Guid (uniqueidentifier): GUID.

AKTİF FİLTRE: WHERE Sube_iptal = 0 AND Sube_hidden = 0""",

"SIPARIS_ESLEME": """TABLO: SIPARIS_ESLEME — Sipariş Talep/Temin Eşleme
Kullanım: Siparişler arası talep-temin ilişkisi.
Satır sayısı: ~24.000 | Prefix: se_

KOLONLAR:
- se_Guid (uniqueidentifier): Bu eşlemenin GUID'i.
- se_Talep_uid (uniqueidentifier): Talep sipariş GUID'i.
- se_Temin_uid (uniqueidentifier): Temin sipariş GUID'i.
- se_create_date (datetime2): Oluşturulma tarihi.

AKTİF FİLTRE: WHERE se_iptal = 0 AND se_hidden = 0""",

"ILLER": """TABLO: ILLER — İl Tanımları (Türkiye)
Satır sayısı: ~243

KOLONLAR:
- iller_ilkodu (nvarchar 3): İl kodu. '34'=İstanbul, '06'=Ankara.
- iller_iladi (nvarchar 25): İl adı.
- iller_bolgekodu (nvarchar 5): Bölge kodu.

AKTİF FİLTRE: WHERE iller_iptal = 0 AND iller_hidden = 0""",

"ILCELER": """TABLO: ILCELER — İlçe Tanımları
Satır sayısı: ~1.002

KOLONLAR:
- ilceler_ilkodu (nvarchar 3): İl kodu.
- ilceler_ilcekodu (nvarchar 5): İlçe kodu.
- ilceler_ilceadi (nvarchar 25): İlçe adı.

AKTİF FİLTRE: WHERE ilceler_iptal = 0 AND ilceler_hidden = 0""",

}


# ─────────────────────────────────────────────────────────────────────────────
# SORGU PATTERN CHUNK'LARI — 3. RAG katmanı
# ─────────────────────────────────────────────────────────────────────────────

QUERY_PATTERN_CHUNKS: List[Dict[str, str]] = [
    {
        "description": """SORGU PATTERN: Kanal Bazlı Ciro Raporu
Kullanıcı "kanal bazlı ciro", "Trendyol satışları", "HepsiBurada cirosu", "pazar yeri raporu" sorduğunda:
SELECT s.sip_eticaret_kanal_kodu AS kanal,
       COUNT(DISTINCT s.sip_Guid) AS siparis_sayisi,
       SUM(sth.sth_tutar) AS toplam_ciro
FROM SIPARISLER s
JOIN STOK_HAREKETLERI sth ON s.sip_Guid = sth.sth_sip_uid
WHERE s.sip_iptal = 0 AND sth.sth_iptal = 0 AND sth.sth_cins = 8
GROUP BY s.sip_eticaret_kanal_kodu ORDER BY toplam_ciro DESC""",
        "topic": "kanal_ciro"
    },
    {
        "description": """SORGU PATTERN: Aylık Ciro Trendi / Zaman Serisi
Kullanıcı "aylık trend", "zaman serisi", "aylık satış", "ay ay ciro" sorduğunda:
⚠️ SQLite kullanılıyor: strftime() kullan — YEAR()/MONTH() yok! sth_tarih yok — sth_fis_tarihi kullan!
SELECT strftime('%Y', sth_fis_tarihi) AS yil,
       strftime('%m', sth_fis_tarihi) AS ay,
       COUNT(DISTINCT sth_sip_uid) AS siparis_sayisi,
       SUM(sth_tutar) AS ciro, SUM(sth_miktar) AS adet
FROM STOK_HAREKETLERI
WHERE sth_cins = 8 AND sth_iptal = 0
GROUP BY yil, ay
ORDER BY yil, ay""",
        "topic": "aylik_trend"
    },
    {
        "description": """SORGU PATTERN: En Çok Satan Ürünler
Kullanıcı "en çok satan", "çok satılan ürünler", "en iyi ürünler", "top ürünler" sorduğunda:
SELECT s.sto_isim, s.sto_kod,
       SUM(sth.sth_miktar) AS toplam_adet,
       SUM(sth.sth_tutar) AS toplam_ciro
FROM STOK_HAREKETLERI sth JOIN STOKLAR s ON sth.sth_stok_kod = s.sto_kod
WHERE sth.sth_cins = 8 AND sth.sth_iptal = 0 AND s.sto_iptal = 0
GROUP BY s.sto_kod, s.sto_isim ORDER BY toplam_ciro DESC""",
        "topic": "en_cok_satan"
    },
    {
        "description": """SORGU PATTERN: Kritik Stok Uyarısı
Kullanıcı "kritik stok", "stok bitti", "eksik stok", "minimum stok altında", "yeniden sipariş" sorduğunda:
SELECT sdp.sdp_depo_no, s.sto_kod, s.sto_isim,
       sdp.sdp_min_stok, sdp.sdp_sip_stok,
       (sdp.sdp_sip_stok - sdp.sdp_min_stok) AS asim
FROM STOK_DEPO_DETAYLARI sdp JOIN STOKLAR s ON sdp.sdp_depo_kod = s.sto_kod
WHERE sdp.sdp_sip_stok >= sdp.sdp_min_stok
  AND sdp.sdp_iptal = 0 AND s.sto_iptal = 0
ORDER BY asim DESC""",
        "topic": "kritik_stok"
    },
    {
        "description": """SORGU PATTERN: İade Analizi
Kullanıcı "en çok iade", "iade edilen ürünler", "iade oranı", "iade nedenleri" sorduğunda:
⚠️ SQLite: STRING_AGG yok → group_concat kullan!
SELECT i.itlp_stok_kodu, s.sto_isim,
       COUNT(*) AS iade_talep_sayisi,
       SUM(i.itlp_miktari) AS toplam_iade_adet,
       group_concat(DISTINCT i.itlp_aciklama) AS iade_nedenleri
FROM IADE_TALEPLERI i JOIN STOKLAR s ON i.itlp_stok_kodu = s.sto_kod
WHERE i.itlp_iptal = 0 AND s.sto_iptal = 0
GROUP BY i.itlp_stok_kodu, s.sto_isim ORDER BY iade_talep_sayisi DESC""",
        "topic": "iade_analizi"
    },
    {
        "description": """SORGU PATTERN: Müşteri Sipariş Geçmişi
Kullanıcı belirli bir müşteri adı veya "müşteri siparişleri", "müşteri geçmişi" sorduğunda:
⚠️ sip_durum TEXT! COLLATE Turkish_CI_AS yok → LOWER() kullan!
SELECT s.sip_no AS siparis_no, s.sip_tarih,
       s.sip_eticaret_kanal_kodu AS kanal, s.sip_durum,
       SUM(sth.sth_tutar) AS siparis_tutari
FROM SIPARISLER s
JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
LEFT JOIN STOK_HAREKETLERI sth ON s.sip_evrakno_sira = sth.sth_evrakno_sira AND sth.sth_iptal = 0
WHERE LOWER(c.cari_unvan1) LIKE LOWER('%ARAMA_TERİMİ%')
  AND s.sip_iptal = 0 AND c.cari_iptal = 0
GROUP BY s.sip_no, s.sip_tarih, s.sip_eticaret_kanal_kodu, s.sip_durum
ORDER BY s.sip_tarih DESC""",
        "topic": "musteri_siparis"
    },
    {
        "description": """SORGU PATTERN: Fiyat Değişiklik Raporu
Kullanıcı "fiyat değişikliği", "zam yapılan ürünler", "fiyat artışı", "fiyat azalışı" sorduğunda:
SELECT f.fid_stok_kod, s.sto_isim, f.fid_tarih,
       f.fid_eskifiy_tutar AS eski_fiyat, f.fid_yenifiy_tutar AS yeni_fiyat,
       (f.fid_yenifiy_tutar - f.fid_eskifiy_tutar) AS degisim,
       ROUND(((f.fid_yenifiy_tutar-f.fid_eskifiy_tutar)/NULLIF(f.fid_eskifiy_tutar,0))*100,1) AS yuzde
FROM STOK_FIYAT_DEGISIKLIKLERI f JOIN STOKLAR s ON f.fid_stok_kod = s.sto_kod
WHERE f.fid_iptal = 0 AND s.sto_iptal = 0 ORDER BY f.fid_tarih DESC""",
        "topic": "fiyat_degisikligi"
    },
    {
        "description": """SORGU PATTERN: Marka Bazlı Satış Analizi
Kullanıcı "marka satışları", "markaya göre ciro", belirli bir marka adı sorduğunda:
SELECT m.mrk_ismi AS marka, SUM(sth.sth_tutar) AS ciro, SUM(sth.sth_miktar) AS adet
FROM STOK_MARKALARI m
JOIN STOKLAR s ON m.mrk_kod = s.sto_marka_kodu
JOIN STOK_HAREKETLERI sth ON s.sto_kod = sth.sth_stok_kod
WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND s.sto_iptal=0 AND m.mrk_iptal=0
GROUP BY m.mrk_ismi ORDER BY ciro DESC
NOT: STOK_MARKALARI kolonları mrk_kod ve mrk_ismi — marka_kod ve marka_isim değil!""",
        "topic": "marka_satis"
    },
    {
        "description": """SORGU PATTERN: Sipariş Durumu Analizi
Kullanıcı "bekleyen siparişler", "kargodaki siparişler", "sipariş durumu dağılımı" sorduğunda:
⚠️ sip_durum TEXT kolonu — CASE WHEN sayısal değer kullanma!
Değerler: 'Hazırlanıyor' | 'Kargoya Verildi' | 'Teslim Edildi' | 'İptal'
SELECT sip_durum,
       COUNT(DISTINCT sip_Guid) AS siparis_sayisi
FROM SIPARISLER WHERE sip_iptal = 0
GROUP BY sip_durum ORDER BY siparis_sayisi DESC""",
        "topic": "siparis_durumu"
    },
    {
        "description": """SORGU PATTERN: Kargo Şirketi Dağılımı
Kullanıcı "hangi kargo şirketi", "kargo analizi", "aras kargo", "yurtiçi kargo" sorduğunda:
⚠️ kargo_sirkettipi kolonu YOK! kargo_firma TEXT kolonu kullan!
SELECT kargo_firma, COUNT(*) AS gonderi_sayisi,
       SUM(kargo_gecikme_flag) AS geciken_adet
FROM KARGO_GONDERILERI WHERE kargo_iptal = 0
GROUP BY kargo_firma ORDER BY gonderi_sayisi DESC""",
        "topic": "kargo_dagılımı"
    },
    {
        "description": """SORGU PATTERN: Kategori Bazlı Satış Analizi
Kullanıcı "kategoriye göre satış", "giyim cirosu", "ana grup satış" sorduğunda:
SELECT ag.san_isim AS ana_kategori, SUM(sth.sth_tutar) AS ciro
FROM STOK_ANA_GRUPLARI ag
JOIN STOKLAR s ON ag.san_kod = s.sto_anagrup_kod
JOIN STOK_HAREKETLERI sth ON s.sto_kod = sth.sth_stok_kod
WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND s.sto_iptal=0 AND ag.san_iptal=0
GROUP BY ag.san_isim ORDER BY ciro DESC
NOT: STOK_ANA_GRUPLARI kolonları san_kod ve san_isim — sag_kod ve sag_isim değil!""",
        "topic": "kategori_satis"
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# CHUNK ÜRETME FONKSİYONLARI
# ─────────────────────────────────────────────────────────────────────────────

PRIMARY_TABLES = [
    "SIPARISLER", "STOKLAR", "STOK_HAREKETLERI", "CARI_HESAPLAR",
    "E_TICARET_URUN_ESLEME", "STOK_DEPO_DETAYLARI", "KARGO_GONDERILERI",
    "IADE_TALEPLERI", "ODEME_EMIRLERI", "CARI_HESAP_HAREKETLERI",
    "STOK_FIYAT_DEGISIKLIKLERI", "BARKOD_TANIMLARI", "CARI_HESAP_ADRESLERI",
]

REFERENCE_TABLES = [
    "STOK_MARKALARI", "STOK_ANA_GRUPLARI", "STOK_ALT_GRUPLARI",
    "STOK_KATEGORILERI", "STOK_RENK_TANIMLARI", "STOK_BEDEN_TANIMLARI",
    "STOK_BIRIMLERI", "DEPOLAR", "KARGO_TANIMLARI",
    "CARI_HESAP_GRUPLARI", "CARI_HESAP_BOLGELERI",
    "ODEME_PLANLARI", "BANKALAR", "KASALAR", "PROMOSYON_TANIMLARI",
    "DOVIZ_KURLARI", "PERSONELLER", "SUBELER",
    "SIPARIS_ESLEME", "ILLER", "ILCELER",
]

ALL_TABLES = PRIMARY_TABLES + REFERENCE_TABLES


def generate_manual_table_chunks(tables=None, main_table=None) -> List[Dict[str, Any]]:
    """Her tablo için ayrı, zengin Qdrant chunk'ı üret."""
    descriptions = _TABLE_DESCRIPTIONS
    docs = []
    target = tables or ALL_TABLES
    for tbl in target:
        tbl_upper = tbl.upper().replace("DBO.", "")
        desc = descriptions.get(tbl_upper, f"Tablo: {tbl_upper}")
        table_type = "primary" if tbl_upper in PRIMARY_TABLES else "reference"
        docs.append({
            "description": desc,
            "type": table_type,
            "table_name": tbl_upper,
            "columns": _get_column_names(tbl_upper),
        })
    return docs


def generate_manual_join_chunks(tables=None, main_table=None) -> List[Dict[str, Any]]:
    """JOIN ilişkilerini chunk formatına çevir."""
    docs = []
    for child, cc, parent, pc in ManualSchemaGraph.MANUAL_RELATIONSHIPS:
        join_desc = (
            f"JOIN: {child} ile {parent} nasıl birleştirilir:\n"
            f"  ON {child}.{cc} = {parent}.{pc}\n"
            f"SQL: FROM {child} JOIN {parent} ON {child}.{cc} = {parent}.{pc}\n"
            f"Semantik: {child} kaydının bağlı {parent} kaydı bu koşulla bulunur."
        )
        docs.append({
            "description": join_desc,
            "type": "join_path",
            "source_table": child,
            "target_table": parent,
            "path": [child, parent],
        })
    return docs


def generate_query_pattern_chunks() -> List[Dict[str, Any]]:
    """Sorgu pattern chunk'larını üret — RAG'ın 3. katmanı."""
    docs = []
    for pattern in QUERY_PATTERN_CHUNKS:
        docs.append({
            "description": pattern["description"],
            "type": "query_pattern",
            "source_table": pattern.get("topic", ""),
            "target_table": "QUERY_PATTERN",
            "path": [],
        })
    return docs


def _get_column_names(table_name: str) -> List[str]:
    """Tablo kolon listesi (db_schema_raw.json doğrulandı)."""
    col_map = {
        "SIPARISLER": ["sip_no","sip_Guid","sip_tarih","sip_musteri_kod",
                       "sip_eticaret_kanal_kodu","sip_evrakno_seri","sip_evrakno_sira",
                       "sip_durum","sip_tutar","sip_kargo_no","sip_aciklama",
                       "sip_iptal","sip_hidden"],
        "STOKLAR": ["sto_kod","sto_isim","sto_marka_kodu","sto_anagrup_kod",
                    "sto_altgrup_kod","sto_satis_fiyat1","sto_satis_fiyat2",
                    "sto_alis_fiyat","sto_birim","sto_min_stok",
                    "sto_iptal","sto_hidden"],
        "STOK_HAREKETLERI": ["sth_id","sth_stok_kod","sth_cari_kodu","sth_sip_uid",
                              "sth_fis_tarihi","sth_birimfiyat",
                              "sth_tutar","sth_miktar","sth_iskonto1",
                              "sth_masraf1","sth_cins",
                              "sth_evrakno_seri","sth_evrakno_sira",
                              "sth_iptal","sth_hidden"],
        "CARI_HESAPLAR": ["cari_kod","cari_unvan1","cari_unvan2","cari_eposta",
                           "cari_tel","cari_sehir","cari_telegram_chat_id",
                           "cari_iptal","cari_hidden"],
        "E_TICARET_URUN_ESLEME": ["eu_stok_kodu","eu_eticaret_platform_id",
                                    "eu_eticaret_urun_id","eu_Guid","eu_create_date",
                                    "eu_iptal","eu_hidden"],
        "STOK_DEPO_DETAYLARI": ["sdp_id","sdp_depo_kod","sdp_depo_no","sdp_stok_miktari",
                                  "sdp_sip_stok","sdp_min_stok","sdp_max_stok",
                                  "sdp_iptal","sdp_hidden"],
        "STOK_FIYAT_DEGISIKLIKLERI": ["fid_stok_kod","fid_eskifiy_tutar","fid_yenifiy_tutar",
                                        "fid_tarih","fid_prof_uid","fid_Guid","fid_iptal","fid_hidden"],
        "IADE_TALEPLERI": ["itlp_id","itlp_musteri_kodu","itlp_stok_kodu","itlp_miktari",
                            "itlp_aciklama","itlp_tarihi","itlp_tip","itlp_durum",
                            "itlp_evrak_sira","itlp_iptal","itlp_hidden"],
        "KARGO_GONDERILERI": ["kargo_id","kargo_evrakuid","kargo_sip_no","kargo_takip_no",
                               "kargo_firma","kargo_durum","kargo_gonderim_tarihi",
                               "kargo_teslim_tarihi","kargo_beklenen_teslim",
                               "kargo_gecikme_flag","kargo_musteri_bilgilendirildi",
                               "kargo_iptal","kargo_hidden"],
        "CARI_HESAP_HAREKETLERI": ["cha_kod","cha_meblag","cha_cinsi","cha_tarihi",
                                     "cha_aciklama","cha_evrakno_seri","cha_evrakno_sira",
                                     "cha_vade","cha_sip_uid","cha_Guid","cha_iptal","cha_hidden"],
        "ODEME_EMIRLERI": ["sck_sahip_cari_kodu","sck_tutar","sck_tip","sck_taksit_sayisi",
                            "sck_vade","sck_bankano","sck_duzen_tarih","sck_Guid","sck_iptal","sck_hidden"],
        "BARKOD_TANIMLARI": ["bar_stokkodu","bar_kodu","bar_barkodtipi","bar_Guid","bar_iptal","bar_hidden"],
        "CARI_HESAP_ADRESLERI": ["adr_cari_kod","adr_cadde","adr_il","adr_Semt",
                                   "adr_posta_kodu","adr_tel_no1","adr_Adres_kodu",
                                   "adr_Guid","adr_iptal","adr_hidden"],
        # Referans tablolar — düzeltilmiş gerçek kolon adları
        "STOK_MARKALARI": ["mrk_kod","mrk_ismi","mrk_Guid","mrk_iptal","mrk_hidden"],
        "STOK_ANA_GRUPLARI": ["san_kod","san_isim","san_Guid","san_iptal","san_hidden"],
        "STOK_ALT_GRUPLARI": ["sta_kod","sta_isim","sta_ana_grup_kod","sta_Guid","sta_iptal","sta_hidden"],
        "STOK_KATEGORILERI": ["ktg_kod","ktg_isim","ktg_Guid","ktg_iptal","ktg_hidden"],
        "STOK_RENK_TANIMLARI": ["rnk_kodu","rnk_ismi","rnk_Guid","rnk_iptal","rnk_hidden"],
        "STOK_BEDEN_TANIMLARI": ["bdn_kodu","bdn_ismi","bdn_Guid","bdn_iptal","bdn_hidden"],
        "STOK_BIRIMLERI": ["unit_ismi","unit_yabanci_isim","unit_Guid","unit_iptal","unit_hidden"],
        "DEPOLAR": ["dep_no","dep_adi","dep_Il","dep_subeno","dep_Guid","dep_iptal","dep_hidden"],
        "KARGO_TANIMLARI": ["krg_kodu","krg_adi","krg_Guid","krg_iptal","krg_hidden"],
        "CARI_HESAP_GRUPLARI": ["crg_kod","crg_isim","crg_Guid","crg_iptal","crg_hidden"],
        "CARI_HESAP_BOLGELERI": ["bol_kod","bol_ismi","bol_Guid","bol_iptal","bol_hidden"],
        "BANKALAR": ["ban_kod","ban_ismi","ban_SwiftKodu","ban_Guid","ban_iptal","ban_hidden"],
        "KASALAR": ["kas_kod","kas_isim","kas_Guid","kas_iptal","kas_hidden"],
        "ODEME_PLANLARI": ["odp_kodu","odp_adi","odp_no","odp_Guid","odp_iptal","odp_hidden"],
        "PROMOSYON_TANIMLARI": ["Promo_kodu","Promo_ismi","Promo_baslangic_gunu","Promo_bitis_gunu","Promo_Guid","Promo_iptal","Promo_hidden"],
        "DOVIZ_KURLARI": ["dov_no","dov_tarih","dov_fiyat1","dov_fiyat2","dov_fiyat3","dov_Guid","dov_iptal","dov_hidden"],
        "PERSONELLER": ["per_kod","per_adi","per_soyadi","per_giris_tar","per_Guid","per_iptal","per_hidden"],
        "SUBELER": ["Sube_kodu","Sube_adi","Sube_no","sube_Il","Sube_Guid","Sube_iptal","Sube_hidden"],
        "SIPARIS_ESLEME": ["se_Guid","se_Talep_uid","se_Temin_uid","se_create_date","se_iptal","se_hidden"],
        "ILLER": ["iller_ilkodu","iller_iladi","iller_bolgekodu","iller_iptal","iller_hidden"],
        "ILCELER": ["ilceler_ilkodu","ilceler_ilcekodu","ilceler_ilceadi","ilceler_iptal","ilceler_hidden"],
    }
    return col_map.get(table_name.upper(), [])