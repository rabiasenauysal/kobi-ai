"""
KOBİ AI Platform — Alert Servisi
Stok uyarıları, kargo gecikmesi tespiti, Telegram bildirimleri.
"""

from datetime import datetime
from typing import List, Dict, Any

from services.db import query, execute
from services.telegram_bot import send_message as tg_send


# ── Stok Uyarıları ────────────────────────────────────────────────────────────

def check_critical_stock() -> List[Dict[str, Any]]:
    """Minimum stok seviyesinin altındaki ürünleri tespit et."""
    rows = query("""
        SELECT st.sto_kod, st.sto_isim, st.sto_min_stok,
               COALESCE(sdp.sdp_stok_miktari, 0) AS mevcut_stok,
               st.sto_min_stok - COALESCE(sdp.sdp_stok_miktari, 0) AS eksik_miktar
        FROM STOKLAR st
        LEFT JOIN STOK_DEPO_DETAYLARI sdp ON st.sto_kod = sdp.sdp_depo_kod
        WHERE st.sto_iptal = 0 AND st.sto_min_stok > 0
          AND COALESCE(sdp.sdp_stok_miktari, 0) < st.sto_min_stok
        ORDER BY eksik_miktar DESC
        LIMIT 20
    """)
    return rows


def send_stock_alerts(critical_items: List[Dict]) -> None:
    if not critical_items:
        return
    lines = [f"⚠️ *KRİTİK STOK UYARISI* — {len(critical_items)} ürün"]
    for item in critical_items[:5]:
        lines.append(
            f"• {item['sto_isim'][:30]} — "
            f"Mevcut: {item['mevcut_stok']:.0f} / Min: {item['sto_min_stok']:.0f}"
        )
    if len(critical_items) > 5:
        lines.append(f"... ve {len(critical_items) - 5} ürün daha")
    msg = "\n".join(lines)

    tg_send(msg)
    _save_notification("stok_uyari", "Kritik Stok Uyarısı", msg)


# ── Kargo Gecikme Tespiti ─────────────────────────────────────────────────────

def check_delayed_shipments() -> List[Dict[str, Any]]:
    """Beklenen teslim tarihi geçmiş ve teslim edilmemiş kargoları tespit et."""
    today = datetime.now().strftime("%Y-%m-%d")
    rows = query("""
        SELECT k.kargo_id, k.kargo_sip_no, k.kargo_takip_no,
               k.kargo_firma, k.kargo_beklenen_teslim,
               k.kargo_gonderim_tarihi, k.kargo_musteri_bilgilendirildi,
               s.sip_musteri_kod, c.cari_unvan1, c.cari_eposta, c.cari_telegram_chat_id
        FROM KARGO_GONDERILERI k
        LEFT JOIN SIPARISLER s ON k.kargo_sip_no = s.sip_no
        LEFT JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
        WHERE k.kargo_iptal = 0
          AND k.kargo_durum NOT IN ('Teslim Edildi', 'İade', 'İptal')
          AND k.kargo_beklenen_teslim IS NOT NULL
          AND k.kargo_beklenen_teslim < ?
        ORDER BY k.kargo_beklenen_teslim ASC
        LIMIT 50
    """, (today,))

    # gecikme_flag güncelle
    for row in rows:
        execute(
            "UPDATE KARGO_GONDERILERI SET kargo_gecikme_flag=1 WHERE kargo_id=?",
            (row["kargo_id"],)
        )

    return rows


def send_delay_alerts(delayed: List[Dict]) -> None:
    if not delayed:
        return
    lines = [f"🚚 *KARGO GECİKME RAPORU* — {len(delayed)} sipariş"]
    for d in delayed[:5]:
        lines.append(
            f"• Sipariş {d['kargo_sip_no']} — {d['cari_unvan1'] or 'Müşteri'} "
            f"(Beklenen: {d['kargo_beklenen_teslim']})"
        )
    if len(delayed) > 5:
        lines.append(f"... ve {len(delayed) - 5} sipariş daha")
    msg = "\n".join(lines)

    tg_send(msg)
    _save_notification("kargo_gecikme", "Kargo Gecikmesi", msg)


# ── Günlük Sabah Raporu ───────────────────────────────────────────────────────

def generate_daily_report() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = datetime.now()
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    siparisler = query(
        "SELECT COUNT(*) AS n FROM SIPARISLER WHERE sip_tarih=? AND sip_iptal=0",
        (today,)
    )
    bekleyen = query(
        "SELECT COUNT(*) AS n FROM SIPARISLER WHERE sip_durum='Hazırlanıyor' AND sip_iptal=0"
    )
    kargoda = query(
        "SELECT COUNT(*) AS n FROM KARGO_GONDERILERI "
        "WHERE kargo_durum='Kargoda' AND kargo_iptal=0"
    )
    geciken = query(
        "SELECT COUNT(*) AS n FROM KARGO_GONDERILERI WHERE kargo_gecikme_flag=1 AND kargo_iptal=0"
    )
    kritik_stok = check_critical_stock()

    n_sip  = siparisler[0]["n"] if siparisler else 0
    n_bek  = bekleyen[0]["n"] if bekleyen else 0
    n_kar  = kargoda[0]["n"] if kargoda else 0
    n_gec  = geciken[0]["n"] if geciken else 0
    n_stok = len(kritik_stok)

    msg = (
        f"📊 *GÜNLÜK OPERASYON RAPORU* — {today}\n\n"
        f"📦 Bugünkü yeni sipariş: *{n_sip}*\n"
        f"⏳ Hazırlanmayı bekleyen: *{n_bek}*\n"
        f"🚚 Kargoda olan: *{n_kar}*\n"
        f"⚠️ Geciken kargo: *{n_gec}*\n"
        f"📉 Kritik stok uyarısı: *{n_stok} ürün*\n\n"
        f"KOBİ AI dashboard: /dashboard"
    )
    return msg


def send_daily_report() -> None:
    msg = generate_daily_report()
    tg_send(msg)
    _save_notification("gunluk_rapor", "Günlük Operasyon Raporu", msg)


# ── Rol Bazlı Sabah Görev Mesajları ──────────────────────────────────────────

ROL_EMOJI = {
    "depo": "📦",
    "kargo": "🚚",
    "musteri_hizmetleri": "🎧",
    "satin_alma": "🛒",
}
ROL_LABEL = {
    "depo": "Depo Sorumlusu",
    "kargo": "Kargo Görevlisi",
    "musteri_hizmetleri": "Müşteri Hizmetleri",
    "satin_alma": "Satınalma",
}

def _rol_chat_id(rol: str) -> str:
    """Rol için Telegram chat_id döner; ayarlanmamışsa admin chat_id'ye düşer."""
    from config.settings import get_settings
    s = get_settings()
    mapping = {
        "depo":               s.telegram_depo_chat_id,
        "kargo":              s.telegram_kargo_chat_id,
        "musteri_hizmetleri": s.telegram_mh_chat_id,
    }
    return mapping.get(rol, "") or s.telegram_admin_chat_id


def generate_role_morning_message(rol: str) -> str:
    """Belirtilen rol için sabah görev listesi mesajı üret."""
    today = datetime.now().strftime("%Y-%m-%d")
    saat  = datetime.now().strftime("%H:%M")
    emoji = ROL_EMOJI.get(rol, "📋")
    label = ROL_LABEL.get(rol, rol)

    gorevler = query(
        """SELECT baslik, oncelik, tarih FROM GOREVLER
           WHERE atanan_rol=? AND durum IN ('Bekliyor','Devam Ediyor')
             AND (tarih IS NULL OR tarih <= ?)
           ORDER BY CASE oncelik WHEN 'Acil' THEN 0 WHEN 'Yüksek' THEN 1 ELSE 2 END, tarih
           LIMIT 10""",
        (rol, today)
    )

    lines = [f"{emoji} *Günaydın! Bugünkü Görev Listesi — {label}*",
             f"📅 {today} · {saat}\n"]

    if not gorevler:
        lines.append("✅ Bugün için bekleyen göreviniz yok.")
    else:
        for i, g in enumerate(gorevler, 1):
            onc = "🔴" if g["oncelik"] == "Acil" else "🟡" if g["oncelik"] == "Yüksek" else "🔵"
            tarih_str = f"  _(son: {g['tarih']})_" if g.get("tarih") else ""
            lines.append(f"{i}. {onc} {g['baslik']}{tarih_str}")

    # Rol özel özet
    if rol == "depo":
        siparisler = query(
            "SELECT COUNT(*) AS n FROM SIPARISLER "
            "WHERE sip_durum='Hazırlanıyor' AND sip_iptal=0"
        )
        n = siparisler[0]["n"] if siparisler else 0
        lines.append(f"\n📦 Hazırlanmayı bekleyen sipariş: *{n}*")
    elif rol == "kargo":
        geciken = query(
            "SELECT COUNT(*) AS n FROM KARGO_GONDERILERI "
            "WHERE kargo_gecikme_flag=1 AND kargo_iptal=0 "
            "AND kargo_durum NOT IN ('Teslim Edildi','İptal')"
        )
        kargoda = query(
            "SELECT COUNT(*) AS n FROM KARGO_GONDERILERI "
            "WHERE kargo_durum='Kargoda' AND kargo_iptal=0"
        )
        n_gec = geciken[0]["n"] if geciken else 0
        n_kar = kargoda[0]["n"] if kargoda else 0
        lines.append(f"\n🚚 Kargoda olan: *{n_kar}* · ⚠️ Geciken: *{n_gec}*")
    elif rol == "musteri_hizmetleri":
        bekleyen = query(
            "SELECT COUNT(*) AS n FROM IADE_TALEPLERI "
            "WHERE iade_durum='Bekliyor'"
        )
        n = bekleyen[0]["n"] if bekleyen else 0
        lines.append(f"\n🔄 Bekleyen iade talebi: *{n}*")

    lines.append("\n_KOBİ AI ile iyi çalışmalar! 🤖_")
    return "\n".join(lines)


def send_morning_tasks() -> None:
    """Tüm rollere sabah görev mesajı gönder + admin'e günlük rapor."""
    for rol in ["depo", "kargo", "musteri_hizmetleri"]:
        try:
            msg     = generate_role_morning_message(rol)
            chat_id = _rol_chat_id(rol)
            tg_send(msg, chat_id=chat_id)
            _save_notification("sabah_gorev", f"Sabah Görevi — {ROL_LABEL.get(rol, rol)}", msg)
        except Exception as e:
            print(f"[Alert] Sabah görev gönderim hatası ({rol}): {e}")

    # Admin'e de günlük operasyon raporu
    try:
        send_daily_report()
    except Exception as e:
        print(f"[Alert] Günlük rapor gönderim hatası: {e}")


# ── Tedarikçi Mail Taslağı ────────────────────────────────────────────────────

def generate_supplier_email(product: Dict, recommended_qty: int) -> str:
    from openai import OpenAI
    from config.settings import get_settings
    s = get_settings()
    client = OpenAI(api_key=s.openai_api_key)

    prompt = (
        f"Aşağıdaki ürün için tedarikçiye Türkçe bir sipariş maili taslağı yaz:\n"
        f"Ürün: {product.get('sto_isim', '')}\n"
        f"Ürün Kodu: {product.get('sto_kod', '')}\n"
        f"Mevcut Stok: {product.get('mevcut_stok', 0):.0f} adet\n"
        f"Minimum Stok: {product.get('sto_min_stok', 0):.0f} adet\n"
        f"Önerilen Sipariş Miktarı: {recommended_qty} adet\n\n"
        "Mail kısa, profesyonel olsun. Konu satırı dahil."
    )
    resp = client.chat.completions.create(
        model=s.chat_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
    )
    return resp.choices[0].message.content.strip()


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def _save_notification(tip: str, baslik: str, mesaj: str) -> None:
    try:
        execute(
            "INSERT INTO BILDIRIMLER (tip, baslik, mesaj, hedef) VALUES (?,?,?,?)",
            (tip, baslik, mesaj[:1000], "yonetici"),
        )
    except Exception as e:
        print(f"[Alert] Bildirim kayıt hatası: {e}")
