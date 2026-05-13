"""
KOBİ AI Platform — Telegram Bot Servisi
Admin bildirimleri + müşteri webhook handler.
"""

import logging
from typing import Optional

import httpx

from config.settings import get_settings

logger = logging.getLogger(__name__)


def send_message(text: str, chat_id: Optional[str] = None, parse_mode: str = "Markdown") -> bool:
    """Admin kanalına veya belirtilen chat_id'ye mesaj gönder."""
    s = get_settings()
    if not s.telegram_bot_token:
        logger.warning("[Telegram] Bot token ayarlanmamış, mesaj atlandı.")
        return False

    target = chat_id or s.telegram_admin_chat_id
    if not target:
        logger.warning("[Telegram] Hedef chat_id yok, mesaj atlandı.")
        return False

    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    payload = {"chat_id": target, "text": text, "parse_mode": parse_mode}
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"[Telegram] Gönderim hatası {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        logger.error(f"[Telegram] İstek hatası: {e}")
        return False


def send_customer_message(chat_id: str, text: str) -> bool:
    """Müşteriye özel Telegram mesajı gönder."""
    return send_message(text, chat_id=chat_id)


def set_webhook(webhook_url: str) -> bool:
    """Telegram webhook URL'sini kaydet."""
    s = get_settings()
    if not s.telegram_bot_token:
        return False
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/setWebhook"
    try:
        resp = httpx.post(url, json={"url": webhook_url}, timeout=10)
        ok = resp.status_code == 200 and resp.json().get("ok")
        if ok:
            logger.info(f"[Telegram] Webhook ayarlandı: {webhook_url}")
        else:
            logger.error(f"[Telegram] Webhook hatası: {resp.text}")
        return bool(ok)
    except Exception as e:
        logger.error(f"[Telegram] Webhook isteği hatası: {e}")
        return False


def delete_webhook() -> bool:
    """Telegram webhook'u kaldır (polling moduna geç)."""
    s = get_settings()
    if not s.telegram_bot_token:
        return False
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/deleteWebhook"
    try:
        resp = httpx.post(url, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def get_bot_info() -> Optional[dict]:
    """Bot bilgilerini çek (token geçerlilik kontrolü)."""
    s = get_settings()
    if not s.telegram_bot_token:
        return None
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe"
    try:
        resp = httpx.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("result")
        return None
    except Exception:
        return None


# ── Gelen Update İşleyici ─────────────────────────────────────────────────────

async def handle_update(update: dict) -> Optional[str]:
    """
    Telegram'dan gelen update'i işle.
    Herkes doğal dilde soru sorabilir — SQL Agent veritabanından yanıt üretir.
    """
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None

    chat_id  = str(message["chat"]["id"])
    user_text = message.get("text", "").strip()
    username  = message.get("from", {}).get("first_name", "Kullanıcı")

    if not user_text:
        return None

    # ── Hızlı Komutlar ────────────────────────────────────────────────────────

    if user_text.startswith("/start") or user_text.startswith("/yardim") or user_text.startswith("/help"):
        reply = (
            f"Merhaba {username}! 👋\n\n"
            "Ben *KOBİ AI* asistanıyım. Doğal Türkçe ile her şeyi sorabilirsiniz:\n\n"
            "📦 *Sipariş sorguları*\n"
            "  • \"Bugün kaç sipariş geldi?\"\n"
            "  • \"Bekleyen siparişler hangileri?\"\n\n"
            "🚚 *Kargo takibi*\n"
            "  • \"Geciken kargolar var mı?\"\n"
            "  • \"Kargo firması bazında gecikme raporu\"\n\n"
            "📉 *Stok bilgisi*\n"
            "  • \"Hangi ürünler kritik stok seviyesinde?\"\n"
            "  • \"En çok satan 10 ürün neler?\"\n\n"
            "📊 *Satış ve analitik*\n"
            "  • \"Bu ay Trendyol cirosu nedir?\"\n"
            "  • \"Son 30 günün kanal bazlı raporu\"\n\n"
            "Hızlı komutlar:\n"
            "  /rapor — Günlük operasyon raporu\n"
            "  /stok  — Kritik stok listesi\n"
            "  /kargo — Geciken kargolar\n"
            "  /gorev — Bugünkü görevler\n"
        )
        send_message(reply, chat_id=chat_id)
        return reply

    if user_text.startswith("/rapor"):
        from services.alert_service import generate_daily_report
        send_message(generate_daily_report(), chat_id=chat_id)
        return "rapor gönderildi"

    if user_text.startswith("/stok"):
        from services.alert_service import check_critical_stock
        items = check_critical_stock()
        if items:
            lines = [f"⚠️ *Kritik Stok* — {len(items)} ürün\n"]
            for item in items[:10]:
                lines.append(
                    f"• {item['sto_isim'][:32]} "
                    f"({item['mevcut_stok']:.0f}/{item['sto_min_stok']:.0f} ad)"
                )
            if len(items) > 10:
                lines.append(f"...ve {len(items)-10} ürün daha")
            reply = "\n".join(lines)
        else:
            reply = "✅ Tüm ürünler yeterli stok seviyesinde."
        send_message(reply, chat_id=chat_id)
        return reply

    if user_text.startswith("/kargo"):
        from services.alert_service import check_delayed_shipments
        delayed = check_delayed_shipments()
        if delayed:
            lines = [f"🚚 *Geciken Kargolar* — {len(delayed)} sipariş\n"]
            for d in delayed[:8]:
                lines.append(
                    f"• Sipariş {d['kargo_sip_no']} — {d.get('cari_unvan1') or 'Müşteri'} "
                    f"(beklenen: {d['kargo_beklenen_teslim']})"
                )
            if len(delayed) > 8:
                lines.append(f"...ve {len(delayed)-8} kargo daha")
            reply = "\n".join(lines)
        else:
            reply = "✅ Geciken kargo bulunmuyor."
        send_message(reply, chat_id=chat_id)
        return reply

    if user_text.startswith("/gorev"):
        from services.db import query as db_query
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        gorevler = db_query(
            """SELECT baslik, atanan_rol, oncelik, durum FROM GOREVLER
               WHERE durum IN ('Bekliyor','Devam Ediyor')
                 AND (tarih IS NULL OR tarih <= ?)
               ORDER BY CASE oncelik WHEN 'Acil' THEN 0 WHEN 'Yüksek' THEN 1 ELSE 2 END
               LIMIT 15""",
            (today,)
        )
        if gorevler:
            lines = [f"📋 *Bugünkü Görevler* — {len(gorevler)} aktif\n"]
            for g in gorevler:
                onc = "🔴" if g["oncelik"] == "Acil" else "🟡" if g["oncelik"] == "Yüksek" else "🔵"
                lines.append(f"{onc} {g['baslik']} _{g['atanan_rol']}_")
            reply = "\n".join(lines)
        else:
            reply = "✅ Aktif görev yok."
        send_message(reply, chat_id=chat_id)
        return reply

    # ── Doğal Dil Sorgusu → SQL Agent ─────────────────────────────────────────
    # "Yazıyor..." göstergesi gönder
    try:
        import httpx as _httpx
        _s = get_settings()
        _httpx.post(
            f"https://api.telegram.org/bot{_s.telegram_bot_token}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=3,
        )
    except Exception:
        pass

    try:
        from services.rag_service import RAGService
        s = get_settings()
        rag = RAGService()
        result = rag.query(
            question=user_text,
            session_id=f"tg_{chat_id}",
            analytical=False,
            analytical_depth="low",
            already_clarified=True,
        )

        if isinstance(result, dict):
            reply_text = result.get("explanation") or result.get("answer") or result.get("message") or str(result)
        else:
            reply_text = str(result)

        # Telegram mesaj limiti 4096 karakter
        if len(reply_text) > 3800:
            reply_text = reply_text[:3700] + "\n\n_...devamı için dashboard'u ziyaret edin._"

        send_message(reply_text, chat_id=chat_id)

        # Konuşmayı DB'ye kaydet (opsiyonel — dashboard'da gösterilebilir)
        try:
            from services.db import execute as db_exec
            db_exec(
                """INSERT OR IGNORE INTO BILDIRIMLER (tip, baslik, mesaj, hedef)
                   VALUES (?,?,?,?)""",
                ("telegram_soru", f"Bot: {username}", f"S: {user_text}\nY: {reply_text[:500]}", chat_id)
            )
        except Exception:
            pass

        return reply_text

    except Exception as e:
        logger.error(f"[Telegram] AI yanıt hatası: {e}")
        err_msg = "Üzgünüm, şu an isteğinizi işleyemedim. Lütfen tekrar deneyin ya da /yardim yazın."
        send_message(err_msg, chat_id=chat_id, parse_mode="")
        return err_msg
