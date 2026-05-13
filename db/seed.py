"""
KOBİ AI Platform — Demo Veri Seed Scripti
Gerçekçi Türk KOBİ verisi oluşturur (6 aylık)
"""

import sqlite3
import random
import uuid
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "kobi_demo.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

random.seed(42)


def rnd_date(start: datetime, end: datetime) -> str:
    delta = end - start
    return (start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))).strftime("%Y-%m-%d")


def rnd_datetime(start: datetime, end: datetime) -> str:
    delta = end - start
    return (start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))).strftime("%Y-%m-%d %H:%M:%S")


START = datetime(2025, 11, 1)
END = datetime(2026, 5, 13)

KANALLAR = ["Trendyol", "HepsiBurada", "N11", "CSP", "Amazon"]
KANAL_AGIRLIK = [0.40, 0.25, 0.15, 0.12, 0.08]

KARGO_FIRMALARI = ["Yurtiçi Kargo", "Aras Kargo", "MNG Kargo", "PTT Kargo", "Sürat Kargo"]

ILLER = [
    "İstanbul", "Ankara", "İzmir", "Bursa", "Antalya",
    "Konya", "Adana", "Gaziantep", "Kayseri", "Mersin",
    "Trabzon", "Samsun", "Diyarbakır", "Eskişehir", "Denizli"
]

IADE_NEDENLERI = [
    "Beden uyuşmazlığı", "Renk farklılığı", "Ürün hasarlı geldi",
    "Beğenmedim", "Yanlış ürün gönderildi", "Kalite beklentiyi karşılamadı",
    "Geç teslimat", "Çift sipariş verildi"
]

GOREV_SABLONLARI = [
    ("Günlük Paket Hazırlama", "Bugün teslim edilecek siparişlerin paketlenmesi", "depo"),
    ("Kargo Teslim Rotası", "Bugünkü teslimat rotasını düzenle", "kargo"),
    ("Stok Sayımı", "Kritik ürünlerin stok sayımını yap", "depo"),
    ("İade Kontrol", "Bekleyen iade taleplerini incele", "depo"),
    ("Müşteri Çağrı Takibi", "Yanıtsız müşteri çağrılarını döndür", "musteri_hizmetleri"),
]


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def seed(db_path: str = str(DB_PATH)):
    print(f"🌱 Seed başlatılıyor: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    cur = conn.cursor()

    # ── Kullanıcılar ─────────────────────────────────────────────────────────
    cur.executemany(
        "INSERT OR IGNORE INTO KULLANICILAR (email, sifre_hash, ad, rol) VALUES (?,?,?,?)",
        [
            ("admin@kobi.ai", hash_password("admin123"), "Sistem Yöneticisi", "yonetici"),
            ("depo@kobi.ai",  hash_password("depo123"),  "Depo Sorumlusu",    "depo"),
            ("kargo@kobi.ai", hash_password("kargo123"), "Kargo Görevlisi",   "kargo"),
        ]
    )

    # ── Markalar ─────────────────────────────────────────────────────────────
    markalar = [
        ("MRK001", "ModaLux"),
        ("MRK002", "ÇiçekGiyin"),
        ("MRK003", "YeşilAda"),
        ("MRK004", "AnadoluTarz"),
        ("MRK005", "EkoBask"),
        ("MRK006", "HanzeleModası"),
        ("MRK007", "TürkHandmade"),
        ("MRK008", "KarşıyakaTarz"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO STOK_MARKALARI (mrk_kod, mrk_ismi) VALUES (?,?)",
        markalar
    )

    # ── Ana Gruplar ───────────────────────────────────────────────────────────
    ana_gruplar = [
        ("AG001", "Kadın Giyim"),
        ("AG002", "Erkek Giyim"),
        ("AG003", "Çocuk Giyim"),
        ("AG004", "Aksesuar"),
        ("AG005", "Ev & Yaşam"),
        ("AG006", "Ayakkabı"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO STOK_ANA_GRUPLARI (san_kod, san_isim) VALUES (?,?)",
        ana_gruplar
    )

    # ── Ürünler ───────────────────────────────────────────────────────────────
    urun_sablonlari = [
        # (isim_prefix, ana_grup, marka, birim_fiyat_aralik, min_stok)
        ("Kadın Yazlık Elbise",     "AG001", "MRK001", (180, 450), 20),
        ("Kadın Bluz",              "AG001", "MRK002", (120, 280), 25),
        ("Kadın Jean Pantolon",     "AG001", "MRK001", (220, 480), 15),
        ("Kadın Trençkot",          "AG001", "MRK003", (380, 750), 10),
        ("Kadın Etek",              "AG001", "MRK002", (150, 320), 20),
        ("Kadın Sweatshirt",        "AG001", "MRK004", (160, 300), 18),
        ("Kadın Şort",              "AG001", "MRK001", (110, 230), 22),
        ("Kadın Pijama Takım",      "AG001", "MRK005", (200, 380), 15),
        ("Erkek Gömlek",            "AG002", "MRK006", (180, 380), 20),
        ("Erkek Jean Pantolon",     "AG002", "MRK004", (240, 520), 15),
        ("Erkek Tişört",            "AG002", "MRK007", (100, 220), 30),
        ("Erkek Eşofman Takım",     "AG002", "MRK004", (280, 550), 12),
        ("Erkek Mont",              "AG002", "MRK006", (450, 850), 8),
        ("Erkek Şort",              "AG002", "MRK007", (120, 250), 25),
        ("Erkek Polo Yaka Tişört",  "AG002", "MRK008", (130, 260), 20),
        ("Kız Çocuk Elbise",        "AG003", "MRK002", (120, 280), 18),
        ("Erkek Çocuk Tişört",      "AG003", "MRK007", (80, 180),  22),
        ("Çocuk Pijama",            "AG003", "MRK005", (150, 280), 15),
        ("Çocuk Spor Ayakkabı",     "AG006", "MRK003", (180, 380), 10),
        ("Kadın Çanta",             "AG004", "MRK001", (250, 650), 12),
        ("Erkek Kemer",             "AG004", "MRK008", (90, 220),  20),
        ("Kadın Şapka",             "AG004", "MRK002", (80, 180),  25),
        ("Atkı & Bere Set",         "AG004", "MRK003", (120, 250), 15),
        ("Kadın Terlik",            "AG006", "MRK001", (120, 280), 18),
        ("Erkek Sneaker",           "AG006", "MRK006", (280, 580), 10),
        ("Yastık Kılıfı 2'li Set",  "AG005", "MRK005", (80, 180),  20),
        ("Nevresim Takımı",         "AG005", "MRK005", (280, 580), 8),
        ("Banyo Havlusu",           "AG005", "MRK007", (60, 150),  25),
        ("Mutfak Önlüğü",           "AG005", "MRK008", (70, 160),  20),
        ("El Yapımı Sepet",         "AG005", "MRK007", (150, 350), 10),
    ]

    urunler = []
    bedenler = ["XS", "S", "M", "L", "XL", "XXL"]
    renkler = ["Siyah", "Beyaz", "Lacivert", "Kırmızı", "Yeşil", "Bej", "Gri"]

    sto_idx = 1
    for sablon in urun_sablonlari:
        isim_prefix, ana_grup, marka, fiyat_aralik, min_stok = sablon
        # Her şablon için 2-3 varyant (renk/beden)
        for renk in random.sample(renkler, k=random.randint(2, 4)):
            sto_kod = f"STK{sto_idx:04d}"
            sto_isim = f"{isim_prefix} - {renk}"
            satis_fiyat = round(random.uniform(*fiyat_aralik), 2)
            alis_fiyat = round(satis_fiyat * random.uniform(0.45, 0.65), 2)
            urunler.append((
                sto_kod, sto_isim, marka, ana_grup, None,
                satis_fiyat, satis_fiyat * 0.9, alis_fiyat,
                "ADET", min_stok
            ))
            sto_idx += 1

    cur.executemany(
        """INSERT OR IGNORE INTO STOKLAR
           (sto_kod, sto_isim, sto_marka_kodu, sto_anagrup_kod, sto_altgrup_kod,
            sto_satis_fiyat1, sto_satis_fiyat2, sto_alis_fiyat, sto_birim, sto_min_stok)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        urunler
    )

    # Stok depo detayları
    sdp_rows = []
    for u in urunler:
        sto_kod = u[0]
        min_stok = u[9]
        mevcut = random.randint(0, 80)
        sdp_rows.append((sto_kod, 1, mevcut, random.randint(0, 10), min_stok, min_stok * 3))
    cur.executemany(
        """INSERT OR IGNORE INTO STOK_DEPO_DETAYLARI
           (sdp_depo_kod, sdp_depo_no, sdp_stok_miktari, sdp_sip_stok, sdp_min_stok, sdp_max_stok)
           VALUES (?,?,?,?,?,?)""",
        sdp_rows
    )

    # ── Müşteriler ────────────────────────────────────────────────────────────
    isimler = [
        "Ayşe", "Fatma", "Emine", "Hatice", "Zeynep", "Elif", "Meryem", "Şule",
        "Mehmet", "Mustafa", "Ahmet", "Ali", "Hüseyin", "İbrahim", "Ömer", "Yusuf",
        "Selin", "Deniz", "Canan", "Pınar", "Gül", "Sevgi", "Derya", "Esra",
        "Burak", "Emre", "Can", "Kemal", "Serkan", "Murat", "Volkan", "Ozan"
    ]
    soyadlar = [
        "Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Özdemir",
        "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Koç", "Kurt", "Aydın",
        "Özkan", "Şimşek", "Bulut", "Erdoğan", "Güneş", "Polat", "Aksoy"
    ]

    musteriler = []
    for i in range(600):
        cari_kod = f"MST{i+1:05d}"
        ad = random.choice(isimler)
        soyad = random.choice(soyadlar)
        unvan = f"{ad} {soyad}"
        il = random.choice(ILLER)
        musteriler.append((
            cari_kod, unvan, None,
            f"{ad.lower()}.{soyad.lower()}{random.randint(1,99)}@gmail.com",
            f"05{random.randint(10,59)}{random.randint(1000000,9999999)}",
            il
        ))

    cur.executemany(
        """INSERT OR IGNORE INTO CARI_HESAPLAR
           (cari_kod, cari_unvan1, cari_unvan2, cari_eposta, cari_tel, cari_sehir)
           VALUES (?,?,?,?,?,?)""",
        musteriler
    )

    # ── Siparişler + Kargo + Stok Hareketleri ────────────────────────────────
    print("📦 Siparişler oluşturuluyor...")
    urun_kodlar = [u[0] for u in urunler]
    musteri_kodlar = [m[0] for m in musteriler]
    urun_fiyatlar = {u[0]: u[5] for u in urunler}

    siparisler = []
    kargo_rows = []
    sth_rows = []
    odeme_rows = []
    gorev_rows = []

    evrak_sira = 10000

    for i in range(2000):
        sip_no = f"SIP{i+1:06d}"
        sip_guid = str(uuid.uuid4())
        tarih = rnd_date(START, END)
        tarih_dt = datetime.strptime(tarih, "%Y-%m-%d")
        musteri = random.choice(musteri_kodlar)
        kanal = random.choices(KANALLAR, weights=KANAL_AGIRLIK)[0]
        evrak_sira += 1
        evrak_seri = "E"

        # Sipariş kalemi (1-3 ürün)
        n_urun = random.randint(1, 3)
        seçilen_urunler = random.sample(urun_kodlar, k=min(n_urun, len(urun_kodlar)))
        toplam_tutar = 0.0

        for sto_kod in seçilen_urunler:
            miktar = random.randint(1, 3)
            birim_fiyat = urun_fiyatlar.get(sto_kod, 200.0)
            iskonto = random.choice([0, 0, 0, 5, 10, 15])
            masraf = round(birim_fiyat * miktar * random.uniform(0.10, 0.18), 2)
            sth_tutar = round(birim_fiyat * miktar * (1 - iskonto / 100), 2)
            toplam_tutar += sth_tutar

            sth_rows.append((
                tarih, sto_kod, sip_guid, evrak_sira, evrak_seri,
                8,  # sth_cins=8 e-ticaret
                miktar, sth_tutar, birim_fiyat, iskonto, masraf, musteri
            ))

        # Sipariş durumu — tarihine göre mantıklı ata
        gün_önce = (END - tarih_dt).days
        if gün_önce < 2:
            durum = random.choices(
                ["Hazırlanıyor", "Kargoya Verildi"],
                weights=[0.6, 0.4]
            )[0]
        elif gün_önce < 7:
            durum = random.choices(
                ["Kargoya Verildi", "Teslim Edildi", "Hazırlanıyor"],
                weights=[0.4, 0.5, 0.1]
            )[0]
        else:
            durum = random.choices(
                ["Teslim Edildi", "Kargoya Verildi", "İptal"],
                weights=[0.82, 0.12, 0.06]
            )[0]

        iptal = 1 if durum == "İptal" else 0

        siparisler.append((
            sip_no, sip_guid, evrak_sira, evrak_seri,
            musteri, tarih, kanal, durum,
            round(toplam_tutar, 2), iptal
        ))

        # Kargo
        kargo_firma = random.choice(KARGO_FIRMALARI)
        kargo_takip = f"TRP{random.randint(100000000, 999999999)}"

        if durum == "İptal":
            kargo_durum = "İptal"
            gonderim_tarihi = None
            teslim_tarihi = None
            beklenen_teslim = None
            gecikme = 0
        elif durum == "Hazırlanıyor":
            kargo_durum = "Hazırlanıyor"
            gonderim_tarihi = None
            teslim_tarihi = None
            beklenen_teslim = (tarih_dt + timedelta(days=3)).strftime("%Y-%m-%d")
            gecikme = 0
        elif durum == "Kargoya Verildi":
            gonderim_dt = tarih_dt + timedelta(days=1)
            gonderim_tarihi = gonderim_dt.strftime("%Y-%m-%d")
            beklenen_teslim = (gonderim_dt + timedelta(days=3)).strftime("%Y-%m-%d")
            beklenen_dt = gonderim_dt + timedelta(days=3)
            gecikme = 1 if (END > beklenen_dt and random.random() < 0.15) else 0
            kargo_durum = "Gecikti" if gecikme else "Kargoda"
            teslim_tarihi = None
        else:  # Teslim Edildi
            gonderim_dt = tarih_dt + timedelta(days=1)
            gonderim_tarihi = gonderim_dt.strftime("%Y-%m-%d")
            teslim_gun = random.randint(2, 5)
            teslim_dt = gonderim_dt + timedelta(days=teslim_gun)
            teslim_tarihi = teslim_dt.strftime("%Y-%m-%d")
            beklenen_teslim = (gonderim_dt + timedelta(days=3)).strftime("%Y-%m-%d")
            gecikme = 0
            kargo_durum = "Teslim Edildi"

        kargo_rows.append((
            sip_guid, sip_no, kargo_takip, kargo_firma, kargo_durum,
            gonderim_tarihi, teslim_tarihi, beklenen_teslim,
            gecikme, 0
        ))

        # Ödeme
        odeme_rows.append((
            sip_no, tarih,
            round(toplam_tutar, 2),
            random.choice(["Kredi Kartı", "Havale", "Kapıda Ödeme"])
        ))

    # Batch insert
    cur.executemany(
        """INSERT OR IGNORE INTO SIPARISLER
           (sip_no, sip_Guid, sip_evrakno_sira, sip_evrakno_seri,
            sip_musteri_kod, sip_tarih, sip_eticaret_kanal_kodu, sip_durum,
            sip_tutar, sip_iptal)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        siparisler
    )

    cur.executemany(
        """INSERT INTO STOK_HAREKETLERI
           (sth_fis_tarihi, sth_stok_kod, sth_sip_uid, sth_evrakno_sira, sth_evrakno_seri,
            sth_cins, sth_miktar, sth_tutar, sth_birimfiyat, sth_iskonto1, sth_masraf1, sth_cari_kodu)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        sth_rows
    )

    cur.executemany(
        """INSERT INTO KARGO_GONDERILERI
           (kargo_evrakuid, kargo_sip_no, kargo_takip_no, kargo_firma, kargo_durum,
            kargo_gonderim_tarihi, kargo_teslim_tarihi, kargo_beklenen_teslim,
            kargo_gecikme_flag, kargo_musteri_bilgilendirildi)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        kargo_rows
    )

    cur.executemany(
        "INSERT INTO ODEME_EMIRLERI (sck_sip_no, sck_tarih, sck_tutar, sck_odeme_tipi) VALUES (?,?,?,?)",
        odeme_rows
    )

    # ── İadeler ───────────────────────────────────────────────────────────────
    iade_rows = []
    teslim_siparisler = [s for s in siparisler if s[7] == "Teslim Edildi"]
    for s in random.sample(teslim_siparisler, k=min(150, len(teslim_siparisler))):
        tarih_dt = datetime.strptime(s[5], "%Y-%m-%d")
        iade_tarihi = (tarih_dt + timedelta(days=random.randint(3, 14))).strftime("%Y-%m-%d")
        if datetime.strptime(iade_tarihi, "%Y-%m-%d") > END:
            continue
        sto_kod = random.choice(urun_kodlar)
        iade_rows.append((
            iade_tarihi, s[4], sto_kod,
            random.randint(1, 2),
            random.choice(IADE_NEDENLERI),
            random.choice(["İade", "Değişim"]),
            random.choice(["Bekliyor", "Onaylandı", "Tamamlandı"]),
            s[2]
        ))

    cur.executemany(
        """INSERT INTO IADE_TALEPLERI
           (itlp_tarihi, itlp_musteri_kodu, itlp_stok_kodu, itlp_miktari,
            itlp_aciklama, itlp_tip, itlp_durum, itlp_evrak_sira)
           VALUES (?,?,?,?,?,?,?,?)""",
        iade_rows
    )

    # ── Alış Hareketleri (stok yenileme, sth_cins=1) ─────────────────────────
    alis_rows = []
    for sto_kod in urun_kodlar:
        for _ in range(random.randint(2, 5)):
            tarih = rnd_date(START, END)
            miktar = random.randint(20, 100)
            birim_fiyat = urun_fiyatlar.get(sto_kod, 200.0) * random.uniform(0.45, 0.60)
            alis_rows.append((
                tarih, sto_kod, None, None, None,
                1, miktar, round(birim_fiyat * miktar, 2), round(birim_fiyat, 2),
                0, 0, None
            ))

    cur.executemany(
        """INSERT INTO STOK_HAREKETLERI
           (sth_fis_tarihi, sth_stok_kod, sth_sip_uid, sth_evrakno_sira, sth_evrakno_seri,
            sth_cins, sth_miktar, sth_tutar, sth_birimfiyat, sth_iskonto1, sth_masraf1, sth_cari_kodu)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        alis_rows
    )

    # ── Günlük Görevler ───────────────────────────────────────────────────────
    bugun = END.strftime("%Y-%m-%d")
    for baslik, aciklama, rol in GOREV_SABLONLARI:
        cur.execute(
            """INSERT OR IGNORE INTO GOREVLER (baslik, aciklama, atanan_rol, tarih, durum)
               VALUES (?,?,?,?,?)""",
            (baslik, aciklama, rol, bugun, random.choice(["Bekliyor", "Devam Ediyor"]))
        )

    # ── Bildirimler (örnek) ───────────────────────────────────────────────────
    cur.executemany(
        """INSERT INTO BILDIRIMLER (tip, baslik, mesaj, hedef) VALUES (?,?,?,?)""",
        [
            ("stok_uyari",    "Kritik Stok Uyarısı", "5 ürün minimum stok seviyesinin altına düştü.", "yonetici"),
            ("kargo_gecikme", "Kargo Gecikmesi",      "12 siparişin kargo teslimatı gecikiyor.",      "yonetici"),
            ("gunluk_rapor",  "Günlük Özet Raporu",   "Bugün 47 sipariş alındı, 38'i kargoya verildi.", "yonetici"),
        ]
    )

    conn.commit()
    conn.close()

    print(f"✅ Seed tamamlandı!")
    print(f"   Ürün: {len(urunler)}")
    print(f"   Müşteri: {len(musteriler)}")
    print(f"   Sipariş: {len(siparisler)}")
    print(f"   Stok hareketi: {len(sth_rows) + len(alis_rows)}")
    print(f"   Kargo: {len(kargo_rows)}")
    print(f"   İade: {len(iade_rows)}")
    print(f"   DB: {db_path}")


if __name__ == "__main__":
    seed()
