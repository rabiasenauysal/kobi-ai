"""
KOBİ AI Platform — Dashboard Route'ları
Özet KPI'lar, siparişler, stok, kargo, görevler, analitik.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from services.auth_service import get_optional_user
from services.db import query, execute
from services.alert_service import check_critical_stock, check_delayed_shipments

router = APIRouter(prefix="/api", tags=["dashboard"])


# ── KPI Özet ─────────────────────────────────────────────────────────────────

@router.get("/dashboard/summary")
async def dashboard_summary():
    # Veritabanındaki en son tarih — demo verisinin bugünden geride olabileceği durumu destekler
    last_date_row = query(
        "SELECT MAX(date(sip_tarih)) AS ld FROM SIPARISLER WHERE sip_iptal=0"
    )
    last_date = (last_date_row[0]["ld"] if last_date_row else None) or datetime.now().strftime("%Y-%m-%d")

    siparisler = query(
        "SELECT COUNT(*) AS n FROM SIPARISLER WHERE date(sip_tarih)=? AND sip_iptal=0", (last_date,)
    )
    hafta_row = query(
        "SELECT COUNT(*) AS n FROM SIPARISLER WHERE date(sip_tarih)>=date(?,'-7 days') AND sip_iptal=0", (last_date,)
    )
    bekleyen = query(
        "SELECT COUNT(*) AS n FROM SIPARISLER WHERE sip_durum='Hazırlanıyor' AND sip_iptal=0"
    )
    kargoda = query(
        "SELECT COUNT(*) AS n FROM KARGO_GONDERILERI WHERE kargo_durum='Kargoda' AND kargo_iptal=0"
    )
    geciken = query(
        "SELECT COUNT(*) AS n FROM KARGO_GONDERILERI WHERE kargo_gecikme_flag=1 AND kargo_iptal=0"
    )
    teslim_row = query(
        "SELECT COUNT(*) AS n FROM SIPARISLER WHERE sip_durum='Teslim Edildi' AND sip_iptal=0 AND date(sip_tarih)>=date(?,'-30 days')", (last_date,)
    )
    kritik_stok = check_critical_stock()

    # Son güne ait ciro
    ciro_row = query("""
        SELECT COALESCE(SUM(sth.sth_birimfiyat * sth.sth_miktar), 0) AS ciro
        FROM STOK_HAREKETLERI sth
        JOIN SIPARISLER s ON s.sip_evrakno_sira = sth.sth_evrakno_sira
        WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND s.sip_iptal=0
          AND date(sth.sth_fis_tarihi)=?
    """, (last_date,))

    return {
        "today": last_date,
        "bugun_siparis": siparisler[0]["n"] if siparisler else 0,
        "hafta_siparis": hafta_row[0]["n"] if hafta_row else 0,
        "bekleyen_siparis": bekleyen[0]["n"] if bekleyen else 0,
        "kargodaki": kargoda[0]["n"] if kargoda else 0,
        "geciken_kargo": geciken[0]["n"] if geciken else 0,
        "teslim_30gun": teslim_row[0]["n"] if teslim_row else 0,
        "kritik_stok_urun": len(kritik_stok),
        "bugun_ciro": round((ciro_row[0]["ciro"] if ciro_row else 0), 2),
    }


# ── Siparişler ────────────────────────────────────────────────────────────────

@router.get("/orders")
async def get_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    durum: Optional[str] = None,
    kanal: Optional[str] = None,
):
    offset = (page - 1) * limit
    filters = ["s.sip_iptal=0", "s.sip_hidden=0"]
    params = []
    if durum:
        filters.append("s.sip_durum=?")
        params.append(durum)
    if kanal:
        filters.append("s.sip_eticaret_kanal_kodu=?")
        params.append(kanal)

    where = " AND ".join(filters)
    rows = query(f"""
        SELECT s.sip_Guid, s.sip_no, s.sip_tarih, s.sip_durum,
               s.sip_eticaret_kanal_kodu AS kanal,
               c.cari_unvan1 AS musteri,
               k.kargo_takip_no, k.kargo_firma, k.kargo_durum,
               COALESCE(SUM(sth.sth_birimfiyat * sth.sth_miktar), 0) AS tutar
        FROM SIPARISLER s
        LEFT JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
        LEFT JOIN KARGO_GONDERILERI k ON s.sip_Guid = k.kargo_evrakuid
        LEFT JOIN STOK_HAREKETLERI sth ON s.sip_evrakno_sira = sth.sth_evrakno_sira
            AND sth.sth_cins=8 AND sth.sth_iptal=0
        WHERE {where}
        GROUP BY s.sip_Guid
        ORDER BY s.sip_tarih DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    total_row = query(f"SELECT COUNT(*) AS n FROM SIPARISLER s WHERE {where}", params)
    total = total_row[0]["n"] if total_row else 0

    return {"orders": rows, "total": total, "page": page, "limit": limit}


# ── Stok ──────────────────────────────────────────────────────────────────────

@router.get("/stock/critical")
async def get_critical_stock():
    items = check_critical_stock()
    return {"items": items, "count": len(items)}


@router.get("/stock/stats")
async def get_stock_stats():
    """Stok durum sayıları: kritik / düşük / sağlıklı."""
    rows = query("""
        SELECT
            SUM(CASE WHEN COALESCE(sdp.sdp_stok_miktari,0) = 0                               THEN 1 ELSE 0 END) AS kritik,
            SUM(CASE WHEN COALESCE(sdp.sdp_stok_miktari,0) > 0
                      AND COALESCE(sdp.sdp_stok_miktari,0) < st.sto_min_stok               THEN 1 ELSE 0 END) AS dusuk,
            SUM(CASE WHEN COALESCE(sdp.sdp_stok_miktari,0) >= st.sto_min_stok              THEN 1 ELSE 0 END) AS saglikli
        FROM STOKLAR st
        LEFT JOIN STOK_DEPO_DETAYLARI sdp ON st.sto_kod = sdp.sdp_depo_kod
        WHERE st.sto_iptal = 0 AND st.sto_min_stok > 0
    """)
    r = rows[0] if rows else {}
    return {"kritik": r.get("kritik") or 0, "dusuk": r.get("dusuk") or 0, "saglikli": r.get("saglikli") or 0}


@router.get("/stock")
async def get_stock(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
):
    offset = (page - 1) * limit
    filters = ["st.sto_iptal=0", "st.sto_hidden=0"]
    params = []
    if search:
        filters.append("LOWER(st.sto_isim) LIKE LOWER(?)")
        params.append(f"%{search}%")

    where = " AND ".join(filters)
    rows = query(f"""
        SELECT st.sto_kod, st.sto_isim, st.sto_min_stok,
               m.mrk_ismi AS marka, ag.san_isim AS kategori,
               COALESCE(sdp.sdp_stok_miktari, 0) AS mevcut_stok
        FROM STOKLAR st
        LEFT JOIN STOK_MARKALARI m ON st.sto_marka_kodu = m.mrk_kod
        LEFT JOIN STOK_ANA_GRUPLARI ag ON st.sto_anagrup_kod = ag.san_kod
        LEFT JOIN STOK_DEPO_DETAYLARI sdp ON st.sto_kod = sdp.sdp_depo_kod
        WHERE {where}
        ORDER BY st.sto_isim
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    return {"items": rows}


# ── Kargo ─────────────────────────────────────────────────────────────────────

@router.get("/cargo/delayed")
async def get_delayed_cargo():
    items = check_delayed_shipments()
    return {"items": items, "count": len(items)}


@router.get("/cargo")
async def get_cargo(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    durum: Optional[str] = None,
):
    offset = (page - 1) * limit
    # Aktif kargolar: Kargoda + Gecikti + Hazırlanıyor (teslim edilmiş ve iptal hariç)
    filters = ["k.kargo_iptal=0", "k.kargo_durum NOT IN ('Teslim Edildi', 'İptal')"]
    params = []
    if durum:
        filters.pop()  # durum filtresi varsa NOT IN kaldır
        filters.append("k.kargo_durum=?")
        params.append(durum)

    where = " AND ".join(filters)
    rows = query(f"""
        SELECT k.kargo_id, k.kargo_sip_no, k.kargo_takip_no,
               k.kargo_firma, k.kargo_durum, k.kargo_gonderim_tarihi,
               k.kargo_beklenen_teslim, k.kargo_gecikme_flag,
               k.kargo_musteri_bilgilendirildi,
               c.cari_unvan1 AS musteri
        FROM KARGO_GONDERILERI k
        LEFT JOIN SIPARISLER s ON k.kargo_sip_no = s.sip_no
        LEFT JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
        WHERE {where}
        ORDER BY k.kargo_gecikme_flag DESC, k.kargo_gonderim_tarihi DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    total_row = query(f"SELECT COUNT(*) AS n FROM KARGO_GONDERILERI k WHERE {where}", params)
    return {"items": rows, "total": total_row[0]["n"] if total_row else 0}


@router.post("/cargo/{cargo_id}/notify")
async def notify_cargo_customer(cargo_id: int):
    """Geciken kargo için müşteriyi bilgilendir."""
    rows = query("""
        SELECT k.*, c.cari_unvan1 AS musteri, c.cari_eposta AS email
        FROM KARGO_GONDERILERI k
        LEFT JOIN SIPARISLER s ON k.kargo_sip_no = s.sip_no
        LEFT JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
        WHERE k.kargo_id=?
    """, (cargo_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Kargo bulunamadı")
    k = rows[0]
    execute("UPDATE KARGO_GONDERILERI SET kargo_musteri_bilgilendirildi=1 WHERE kargo_id=?", (cargo_id,))
    return {"message": f"{k['musteri'] or 'Müşteri'} bilgilendirildi", "kargo_id": cargo_id}


@router.post("/cargo/notify-all")
async def notify_all_delayed():
    """Tüm geciken kargolar için toplu bildirim."""
    rows = query("""
        SELECT k.kargo_id, k.kargo_sip_no, k.kargo_firma, k.kargo_beklenen_teslim,
               c.cari_unvan1 AS musteri
        FROM KARGO_GONDERILERI k
        LEFT JOIN SIPARISLER s ON k.kargo_sip_no = s.sip_no
        LEFT JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
        WHERE k.kargo_gecikme_flag=1 AND k.kargo_iptal=0 AND k.kargo_musteri_bilgilendirildi=0
    """)
    if not rows:
        return {"message": "Bildirilecek geciken kargo yok", "count": 0}
    ids = [r["kargo_id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    execute(f"UPDATE KARGO_GONDERILERI SET kargo_musteri_bilgilendirildi=1 WHERE kargo_id IN ({placeholders})", ids)

    # Telegram bildirimi
    try:
        from services.telegram_bot import send_message
        msg = f"📦 Toplu Kargo Bildirimi Gönderildi\n{len(rows)} geciken sipariş için müşteri bilgilendirmesi yapıldı:\n"
        for r in rows[:5]:
            msg += f"• {r['kargo_sip_no']} — {r['musteri'] or '?'}\n"
        if len(rows) > 5:
            msg += f"...ve {len(rows)-5} kargo daha"
        send_message(msg)
    except Exception:
        pass

    return {"message": f"{len(rows)} müşteri bilgilendirildi", "count": len(rows)}


# ── Görevler ─────────────────────────────────────────────────────────────────

@router.get("/tasks/today")
async def get_today_tasks():
    today = datetime.now().strftime("%Y-%m-%d")
    rows = query("""
        SELECT id, baslik, aciklama, oncelik, durum, tarih AS son_tarih, atanan_rol AS atanan_kisi, olusturma_tarihi
        FROM GOREVLER
        WHERE (tarih=? OR durum='Bekliyor')
          AND durum != 'Tamamlandi'
        ORDER BY
            CASE oncelik WHEN 'Yüksek' THEN 1 WHEN 'Orta' THEN 2 ELSE 3 END,
            tarih ASC
        LIMIT 20
    """, (today,))
    return {"tasks": rows}


@router.get("/tasks")
async def get_tasks():
    rows = query("""
        SELECT id, baslik, aciklama, oncelik, durum,
               tarih AS son_tarih, atanan_rol AS atanan_kisi, olusturma_tarihi
        FROM GOREVLER
        ORDER BY
            CASE oncelik WHEN 'Yüksek' THEN 1 WHEN 'Orta' THEN 2 ELSE 3 END,
            tarih ASC
    """)
    return {"tasks": rows}


@router.get("/tasks/stats")
async def get_task_stats():
    """Görev akışları için özet istatistik: rol bazlı dağılım ve genel sayılar."""
    # Genel sayılar
    total_row = query("SELECT COUNT(*) AS n FROM GOREVLER")
    tamamlanan = query("SELECT COUNT(*) AS n FROM GOREVLER WHERE durum='Tamamlandi'")
    bekleyen = query("SELECT COUNT(*) AS n FROM GOREVLER WHERE durum='Bekliyor'")
    devam = query("SELECT COUNT(*) AS n FROM GOREVLER WHERE durum='Devam Ediyor'")
    geciken = query("""
        SELECT COUNT(*) AS n FROM GOREVLER
        WHERE durum NOT IN ('Tamamlandi')
          AND tarih < date('now')
          AND tarih IS NOT NULL
    """)
    # Rol bazlı dağılım
    rol_rows = query("""
        SELECT atanan_rol, COUNT(*) AS gorev_sayisi,
               SUM(CASE WHEN durum='Tamamlandi' THEN 1 ELSE 0 END) AS tamamlanan,
               SUM(CASE WHEN durum='Bekliyor' THEN 1 ELSE 0 END) AS bekleyen,
               SUM(CASE WHEN durum='Devam Ediyor' THEN 1 ELSE 0 END) AS devam_eden
        FROM GOREVLER
        GROUP BY atanan_rol
        ORDER BY gorev_sayisi DESC
    """)
    # Son görevler
    son_gorevler = query("""
        SELECT baslik, atanan_rol, durum, oncelik, tarih
        FROM GOREVLER ORDER BY olusturma_tarihi DESC LIMIT 5
    """)
    return {
        "toplam": total_row[0]["n"] if total_row else 0,
        "tamamlanan": tamamlanan[0]["n"] if tamamlanan else 0,
        "bekleyen": bekleyen[0]["n"] if bekleyen else 0,
        "devam_eden": devam[0]["n"] if devam else 0,
        "geciken": geciken[0]["n"] if geciken else 0,
        "roller": rol_rows,
        "son_gorevler": son_gorevler,
    }


@router.post("/tasks")
async def create_task(body: dict):
    from services.db import execute_lastrowid
    tid = execute_lastrowid(
        "INSERT INTO GOREVLER (baslik, aciklama, oncelik, tarih, atanan_rol) VALUES (?,?,?,?,?)",
        (body.get("baslik"), body.get("aciklama", ""), body.get("oncelik", "Orta"),
         body.get("son_tarih", body.get("tarih")), body.get("atanan_kisi", body.get("atanan_rol"))),
    )
    return {"id": tid, "message": "Görev oluşturuldu"}


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: dict):
    col_map = {"son_tarih": "tarih", "atanan_kisi": "atanan_rol"}
    allowed = {"durum", "baslik", "aciklama", "oncelik", "tarih", "atanan_rol", "son_tarih", "atanan_kisi"}
    updates = {}
    for k, v in body.items():
        if k in allowed:
            col = col_map.get(k, k)
            updates[col] = v
    if not updates:
        return {"message": "Güncellenecek alan yok"}
    set_clause = ", ".join(f"{k}=?" for k in updates)
    execute(f"UPDATE GOREVLER SET {set_clause} WHERE id=?", list(updates.values()) + [task_id])
    return {"message": "Güncellendi"}


# ── Analitik ─────────────────────────────────────────────────────────────────

@router.get("/analytics/sales")
async def analytics_sales(
    days: int = Query(30, ge=1, le=365),
):
    rows = query("""
        SELECT s.sip_eticaret_kanal_kodu AS kanal,
               COUNT(DISTINCT s.sip_Guid) AS siparis_sayisi,
               ROUND(SUM(sth.sth_birimfiyat * sth.sth_miktar), 2) AS brut_ciro,
               ROUND(SUM(sth.sth_birimfiyat * sth.sth_miktar * (1 - sth.sth_iskonto1/100.0)), 2) AS net_ciro,
               ROUND(SUM(sth.sth_masraf1), 2) AS komisyon
        FROM SIPARISLER s
        JOIN STOK_HAREKETLERI sth ON s.sip_evrakno_sira = sth.sth_evrakno_sira
        WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND s.sip_iptal=0
          AND date(sth.sth_fis_tarihi) >= date('now', ? || ' days')
        GROUP BY s.sip_eticaret_kanal_kodu
        ORDER BY brut_ciro DESC
    """, (f"-{days}",))
    return {"channels": rows, "days": days}


@router.get("/analytics/top-products")
async def analytics_top_products(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
):
    rows = query("""
        SELECT st.sto_isim, st.sto_kod,
               SUM(sth.sth_miktar) AS adet,
               ROUND(SUM(sth.sth_birimfiyat * sth.sth_miktar), 2) AS ciro
        FROM STOK_HAREKETLERI sth
        JOIN STOKLAR st ON sth.sth_stok_kod = st.sto_kod
        WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND st.sto_iptal=0
          AND date(sth.sth_fis_tarihi) >= date('now', ? || ' days')
        GROUP BY st.sto_kod, st.sto_isim
        ORDER BY ciro DESC
        LIMIT ?
    """, (f"-{days}", limit))
    return {"products": rows}


@router.get("/analytics/monthly")
async def analytics_monthly():
    rows = query("""
        SELECT strftime('%Y', sth.sth_fis_tarihi) AS yil,
               strftime('%m', sth.sth_fis_tarihi) AS ay,
               COUNT(DISTINCT s.sip_Guid) AS siparis_sayisi,
               ROUND(SUM(sth.sth_birimfiyat * sth.sth_miktar), 2) AS ciro
        FROM STOK_HAREKETLERI sth
        JOIN SIPARISLER s ON s.sip_evrakno_sira = sth.sth_evrakno_sira
        WHERE sth.sth_cins=8 AND sth.sth_iptal=0 AND s.sip_iptal=0
        GROUP BY yil, ay
        ORDER BY yil, ay
    """)
    return {"monthly": rows}


@router.get("/analytics/returns")
async def analytics_returns(
    days: int = Query(30, ge=1, le=365),
):
    rows = query("""
        SELECT st.sto_isim,
               COUNT(*) AS iade_sayisi,
               group_concat(DISTINCT i.itlp_aciklama) AS nedenler
        FROM IADE_TALEPLERI i
        JOIN STOKLAR st ON i.itlp_stok_kodu = st.sto_kod
        WHERE i.itlp_iptal=0
          AND date(i.itlp_tarihi) >= date('now', ? || ' days')
        GROUP BY st.sto_kod, st.sto_isim
        ORDER BY iade_sayisi DESC
        LIMIT 20
    """, (f"-{days}",))
    return {"returns": rows}


# ── Bildirimler ───────────────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(
    limit: int = Query(20, ge=1, le=100),
):
    rows = query("""
        SELECT id, tip, baslik, mesaj, hedef, olusturma_tarihi
        FROM BILDIRIMLER
        ORDER BY olusturma_tarihi DESC
        LIMIT ?
    """, (limit,))
    return {"notifications": rows}


# ── Zamanlayıcı ────────────────────────────────────────────────────────────────

@router.get("/scheduler/jobs")
async def get_scheduler_jobs():
    """Aktif zamanlayıcı job'larını listele."""
    try:
        from services.scheduler import get_jobs_info
        return {"jobs": get_jobs_info(), "running": True}
    except Exception as e:
        return {"jobs": [], "running": False, "error": str(e)}


@router.post("/scheduler/trigger-morning")
async def trigger_morning_now():
    """Sabah görev mesajını hemen gönder (test/demo için)."""
    try:
        from services.alert_service import send_morning_tasks
        send_morning_tasks()
        return {"ok": True, "message": "Sabah görev mesajları gönderildi"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/scheduler/trigger-daily-report")
async def trigger_daily_report():
    """Günlük raporu hemen gönder."""
    try:
        from services.alert_service import send_daily_report
        send_daily_report()
        return {"ok": True, "message": "Günlük rapor Telegram'a gönderildi"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/scheduler/trigger-cargo-check")
async def trigger_cargo_check():
    """Geciken kargo kontrolünü hemen çalıştır."""
    try:
        from services.alert_service import check_delayed_shipments, send_delay_alerts
        delayed = check_delayed_shipments()
        if delayed:
            send_delay_alerts(delayed)
        return {"ok": True, "geciken": len(delayed), "message": f"{len(delayed)} geciken kargo kontrol edildi"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

