"""
KOBİ AI Platform — Zamanlayıcı Servisi
APScheduler ile periyodik görevleri otomatik çalıştırır.

Varsayılan zamanlama:
  • 08:00  → Tüm rollere sabah görev listesi + admin günlük raporu
  • Her 30 dk → Geciken kargo tespiti & bildirim
  • Her 60 dk → Kritik stok kontrolü & bildirim
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("[Scheduler] APScheduler yüklü değil — zamanlanmış görevler devre dışı.")

_scheduler: Optional["AsyncIOScheduler"] = None


# ── İş Fonksiyonları ──────────────────────────────────────────────────────────

def _job_morning_tasks():
    """08:00 — Rollere sabah görev listesi + admin günlük raporu."""
    logger.info("[Scheduler] Sabah görev gönderimi başladı")
    try:
        from services.alert_service import send_morning_tasks
        send_morning_tasks()
        logger.info("[Scheduler] Sabah görevleri tamamlandı")
    except Exception as e:
        logger.error(f"[Scheduler] Sabah görevi hatası: {e}")


def _job_cargo_alerts():
    """Geciken kargoları tespit et, yöneticiye bildir."""
    logger.info("[Scheduler] Geciken kargo kontrolü")
    try:
        from services.alert_service import check_delayed_shipments, send_delay_alerts
        delayed = check_delayed_shipments()
        if delayed:
            send_delay_alerts(delayed)
            logger.info(f"[Scheduler] {len(delayed)} geciken kargo bildirimi gönderildi")
    except Exception as e:
        logger.error(f"[Scheduler] Kargo uyarı hatası: {e}")


def _job_stock_alerts():
    """Kritik stok seviyelerini kontrol et, uyarı gönder."""
    logger.info("[Scheduler] Kritik stok kontrolü")
    try:
        from services.alert_service import check_critical_stock, send_stock_alerts
        items = check_critical_stock()
        if items:
            send_stock_alerts(items)
            logger.info(f"[Scheduler] {len(items)} kritik stok uyarısı gönderildi")
    except Exception as e:
        logger.error(f"[Scheduler] Stok uyarı hatası: {e}")


# ── Scheduler Yönetimi ────────────────────────────────────────────────────────

def start_scheduler() -> None:
    global _scheduler
    if not APSCHEDULER_AVAILABLE:
        return
    if _scheduler and _scheduler.running:
        return

    from config.settings import get_settings
    s = get_settings()

    _scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

    # 08:00 — sabah görev listesi + günlük rapor
    _scheduler.add_job(
        _job_morning_tasks,
        CronTrigger(hour=s.morning_report_hour, minute=s.morning_report_minute,
                    timezone="Europe/Istanbul"),
        id="morning_tasks",
        name="Sabah Görev & Rapor",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Her 30 dakika — geciken kargo kontrolü
    _scheduler.add_job(
        _job_cargo_alerts,
        IntervalTrigger(minutes=30),
        id="cargo_alerts",
        name="Geciken Kargo Kontrolü",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Her 60 dakika — kritik stok kontrolü
    _scheduler.add_job(
        _job_stock_alerts,
        IntervalTrigger(minutes=60),
        id="stock_alerts",
        name="Kritik Stok Kontrolü",
        replace_existing=True,
        misfire_grace_time=120,
    )

    _scheduler.start()

    # Log sonraki çalışma zamanlarını
    for job in _scheduler.get_jobs():
        nxt = job.next_run_time
        nxt_str = nxt.strftime("%d.%m %H:%M") if nxt else "?"
        logger.info(f"[Scheduler] {job.name} — sonraki: {nxt_str}")

    logger.info(
        f"[Scheduler] Zamanlayıcı başlatıldı — "
        f"Sabah raporu: {s.morning_report_hour:02d}:{s.morning_report_minute:02d}"
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Zamanlayıcı durduruldu.")
    _scheduler = None


def get_scheduler() -> Optional["AsyncIOScheduler"]:
    return _scheduler


def get_jobs_info() -> list:
    """Dashboard için zamanlayıcı job listesi döner."""
    if not _scheduler:
        return []
    jobs = []
    for job in _scheduler.get_jobs():
        nxt = job.next_run_time
        jobs.append({
            "id":       job.id,
            "name":     job.name,
            "next_run": nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else None,
            "trigger":  str(job.trigger),
        })
    return jobs


def trigger_morning_now() -> str:
    """Manuel olarak sabah görevini hemen çalıştır (test/demo için)."""
    try:
        _job_morning_tasks()
        return "Sabah görev mesajları gönderildi"
    except Exception as e:
        return f"Hata: {e}"
