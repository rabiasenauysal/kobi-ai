"""
KOBİ AI Platform — Müşteri Route'ları
Misafir müşteriler için sipariş sorgulama ve chat.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.auth_service import get_optional_user
from services.db import query

router = APIRouter(prefix="/api/customer", tags=["customer"])


class OrderQueryRequest(BaseModel):
    sip_no: Optional[str] = None
    takip_no: Optional[str] = None
    email: Optional[str] = None


class CustomerChatRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None   # app.js bu field'ı gönderiyor
    session_id: Optional[str] = None
    client_id: Optional[str] = None


# ── Sipariş Sorgulama ─────────────────────────────────────────────────────────

@router.post("/order-lookup")
async def order_lookup(body: OrderQueryRequest, user=Depends(get_optional_user)):
    """Müşteri sipariş ve kargo durumu sorgular (giriş gerektirmez)."""
    if not body.sip_no and not body.takip_no and not body.email:
        raise HTTPException(status_code=400, detail="Sipariş no, takip no veya e-posta gerekli")

    filters = ["s.sip_iptal=0"]
    params = []

    if body.sip_no:
        filters.append("s.sip_no=?")
        params.append(body.sip_no.strip())
    if body.takip_no:
        filters.append("k.kargo_takip_no=?")
        params.append(body.takip_no.strip())
    if body.email:
        filters.append("LOWER(c.cari_eposta)=LOWER(?)")
        params.append(body.email.strip())

    where = " AND ".join(filters)

    rows = query(f"""
        SELECT s.sip_no, s.sip_tarih, s.sip_durum,
               s.sip_eticaret_kanal_kodu AS kanal,
               k.kargo_takip_no, k.kargo_firma,
               k.kargo_durum AS kargo_durum,
               k.kargo_beklenen_teslim,
               k.kargo_gecikme_flag,
               c.cari_unvan1 AS musteri_adi
        FROM SIPARISLER s
        LEFT JOIN KARGO_GONDERILERI k ON s.sip_Guid = k.kargo_evrakuid
        LEFT JOIN CARI_HESAPLAR c ON s.sip_musteri_kod = c.cari_kod
        WHERE {where}
        ORDER BY s.sip_tarih DESC
        LIMIT 10
    """, params)

    if not rows:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    return {"orders": rows}


# ── Müşteri Chat ──────────────────────────────────────────────────────────────

@router.post("/chat")
async def customer_chat(body: CustomerChatRequest, user=Depends(get_optional_user)):
    """
    Müşteri modu: yalnızca sipariş/kargo/iade konularına yanıt verir.
    SQL erişimi kısıtlıdır — sadece müşteriye ait sorular yanıtlanır.
    """
    msg = (body.message or body.question or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Mesaj boş olamaz")

    # Sipariş numarası veya takip numarası içeren sorgular doğrudan yanıtlanır
    import re
    sip_match = re.search(r'\b(SP|SIP|SİP)[-\s]?(\d+)\b', msg, re.IGNORECASE)
    takip_match = re.search(r'\b([A-Z]{2,3}\d{8,20})\b', msg)

    if sip_match or takip_match:
        req = OrderQueryRequest(
            sip_no=sip_match.group(0) if sip_match else None,
            takip_no=takip_match.group(0) if takip_match else None,
        )
        try:
            result = await order_lookup(req, user)
            orders = result.get("orders", [])
            if orders:
                o = orders[0]
                reply = (
                    f"Sipariş Durumu:\n"
                    f"• Sipariş No: {o.get('sip_no', '-')}\n"
                    f"• Durum: {o.get('sip_durum', '-')}\n"
                    f"• Kargo: {o.get('kargo_firma', '-')} — {o.get('kargo_durum', '-')}\n"
                )
                if o.get("kargo_takip_no"):
                    reply += f"• Takip No: {o['kargo_takip_no']}\n"
                if o.get("kargo_beklenen_teslim"):
                    reply += f"• Tahmini Teslimat: {o['kargo_beklenen_teslim']}\n"
                if o.get("kargo_gecikme_flag"):
                    reply += "⚠️ Bu siparişin teslimatı gecikmiş görünüyor. Kargo firmasıyla iletişime geçmenizi öneririz."
                return {"answer": reply, "type": "order_status"}
        except HTTPException:
            pass

    # Genel müşteri sorularını AI ile yanıtla (kısıtlı prompt)
    try:
        from openai import OpenAI
        from config.settings import get_settings
        s = get_settings()
        client = OpenAI(api_key=s.openai_api_key)

        system = (
            "Sen bir e-ticaret müşteri hizmetleri asistanısın. "
            "Yalnızca sipariş, kargo, iade ve ürün konularında yardım edersin. "
            "Kısa, nazik ve Türkçe yanıtlar verirsin. "
            "Veritabanına erişimin yok — genel bilgi ve yönlendirme yaparsın."
        )

        resp = client.chat.completions.create(
            model=s.chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": msg},
            ],
            max_tokens=300,
        )
        reply = resp.choices[0].message.content.strip()
        return {"answer": reply, "type": "general"}

    except Exception as e:
        return {
            "answer": "Üzgünüm, şu an yardımcı olamıyorum. Lütfen daha sonra tekrar deneyin.",
            "type": "error",
        }
