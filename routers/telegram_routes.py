"""
KOBİ AI Platform — Telegram Webhook Route'ları
POST /api/telegram/webhook — Telegram'dan gelen güncellemeleri işle.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Telegram'dan gelen POST isteklerini işle."""
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz JSON")

    try:
        from services.telegram_bot import handle_update
        await handle_update(update)
    except Exception as e:
        logger.error(f"[TelegramWebhook] İşleme hatası: {e}")

    return {"ok": True}


@router.post("/setup")
async def setup_webhook(request: Request):
    """Webhook URL'sini Telegram'a kaydet. Gövde: {url: 'https://...'}"""
    body = await request.json()
    webhook_url = body.get("url", "").strip()
    if not webhook_url:
        raise HTTPException(status_code=400, detail="url gerekli")

    from services.telegram_bot import set_webhook
    ok = set_webhook(webhook_url + "/api/telegram/webhook")
    if not ok:
        raise HTTPException(status_code=500, detail="Webhook ayarlanamadı — token kontrolü yapın")
    return {"ok": True, "webhook": webhook_url + "/api/telegram/webhook"}


@router.get("/status")
async def telegram_status():
    """Bot durumunu kontrol et."""
    from services.telegram_bot import get_bot_info
    info = get_bot_info()
    s = get_settings()
    return {
        "configured": bool(s.telegram_bot_token),
        "bot": info,
    }


@router.post("/send-report")
async def send_report_now():
    """Manuel olarak günlük raporu Telegram'a gönder."""
    from services.alert_service import send_daily_report
    send_daily_report()
    return {"ok": True, "message": "Rapor gönderildi"}
