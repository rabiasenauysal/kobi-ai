"""
KOBİ AI Platform — FastAPI Web Server
E-Ticaret / ERP Analitik Chatbot API
"""

import os
import base64 as _base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from routers.auth_routes import router as auth_router
from routers.dashboard_routes import router as dashboard_router
from routers.customer_routes import router as customer_router
from routers.telegram_routes import router as telegram_router
from services.rag_service import RAGService
from services.usage_logger import UsageLogger
from services.conversation_memory import ConversationMemory
from config.settings import get_settings


# ── FastAPI App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="KOBİ AI Platform API",
    description="KOBİ E-Ticaret & ERP Analitik Asistan — Text-to-SQL + Proaktif Uyarılar",
    version="3.0.0",
)

# Routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(customer_router)
app.include_router(telegram_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static dosyalar (frontend build)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ── Global Servisler ───────────────────────────────────────────────────────

rag_service: Optional[RAGService] = None
usage_logger: Optional[UsageLogger] = None
memory = ConversationMemory(max_turns=10)


# ── Pydantic Modeller ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    user_id: Optional[str] = "web_user"
    client_id: Optional[str] = None
    session_id: Optional[str] = None
    analytical: bool = False
    analytical_depth: str = "medium"
    use_schema: bool = True
    voice: bool = False
    already_clarified: bool = False


class ChatResponse(BaseModel):
    success: bool
    answer: Optional[str] = None
    explanation: Optional[str] = None
    sql: Optional[str] = None
    sql_original: Optional[str] = None
    sql_description: Optional[str] = None
    data: Optional[list] = None
    columns: Optional[list] = None
    row_count: Optional[int] = None
    filtered_count: Optional[int] = 0
    has_filters: Optional[bool] = False
    visualization_type: Optional[str] = None
    execution_time_ms: Optional[float] = None
    tokens: Optional[dict] = None
    log_id: Optional[int] = None
    error: Optional[str] = None
    secondary_results: Optional[list] = None
    insight: Optional[str] = None
    analytical: Optional[bool] = False
    agent_count: Optional[int] = None
    comparison_sql_count: Optional[int] = None
    clarification_needed: Optional[bool] = False
    suggestions: Optional[list] = None
    original_question: Optional[str] = None
    supplements: Optional[list] = None


class FeedbackRequest(BaseModel):
    log_id: int
    feedback: str
    comment: Optional[str] = None


class StatsResponse(BaseModel):
    total_queries: int
    successful_queries: int
    failed_queries: int
    success_rate: float
    total_tokens: int
    total_cost_usd: float
    avg_response_time_ms: float


class RerunRequest(BaseModel):
    sql: str


# ── Startup / Shutdown ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    global rag_service, usage_logger

    print("\n" + "=" * 70)
    print("KOBİ AI PLATFORM — WEB SERVER BAŞLATILIYOR")
    print("=" * 70)

    from config.settings import print_config
    print_config()

    print("\nServisler başlatılıyor...")
    rag_service = RAGService()
    usage_logger = UsageLogger()

    # Zamanlayıcıyı başlat
    try:
        from services.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        print(f"[Scheduler] Başlatma hatası (devam ediliyor): {e}")

    print("Tüm servisler hazır!")
    print("=" * 70 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        from services.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass


# ── Sayfalar ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Ana sayfa — index.html'i döndür."""
    for candidate in [
        Path(__file__).parent / "static" / "index.html",
        Path(__file__).parent / "index.html",
    ]:
        if candidate.exists():
            return HTMLResponse(content=candidate.read_text(encoding="utf-8"))

    return HTMLResponse(
        content="""<!DOCTYPE html>
<html><head><title>KOBİ AI</title></head>
<body><h1>KOBİ AI Platform</h1>
<p>Frontend henüz deploy edilmedi. <a href="/docs">API Dokümantasyonu</a></p>
</body></html>""",
        status_code=200,
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "KOBİ AI Platform",
        "version": "3.0.0",
        "timestamp": datetime.now().isoformat(),
    }


# ── Ana Chat Endpoint ──────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG servisi henüz hazır değil")

    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Soru boş olamaz")

    client_ip = http_request.client.host
    session_id = request.session_id or "default"
    effective_user_id = request.client_id or request.user_id or "web_user"

    if usage_logger and memory.get_turn_count(session_id) == 0:
        db_msgs = usage_logger.get_chat_messages(session_id)
        if db_msgs:
            memory.hydrate_from_db(session_id, db_msgs)

    response = rag_service.query(
        question=question,
        user_id=effective_user_id,
        user_ip=client_ip,
        session_id=session_id,
        use_schema=request.use_schema,
        memory=memory,
        voice=request.voice,
        already_clarified=request.already_clarified,
        analytical=request.analytical,
        analytical_depth=request.analytical_depth,
    )

    if response["success"]:
        result = response.get("result")

        if usage_logger and session_id and effective_user_id:
            usage_logger.save_message(
                session_id=session_id,
                client_id=effective_user_id,
                role="user",
                content=question,
            )
            usage_logger.save_message(
                session_id=session_id,
                client_id=effective_user_id,
                role="assistant",
                content=(response.get("answer") or "")[:2000],
                sql_query=response.get("sql"),
                row_count=result.row_count if result else 0,
            )

        return ChatResponse(
            success=True,
            answer=response.get("answer"),
            explanation=response.get("answer"),
            sql=response.get("sql"),
            sql_original=response.get("sql_original"),
            sql_description=response.get("sql_description"),
            data=result.data if result else None,
            columns=result.columns if result else None,
            row_count=result.row_count if result else 0,
            filtered_count=response.get("filtered_count", 0),
            has_filters=response.get("has_filters", False),
            visualization_type=result.visualization_type if result else None,
            execution_time_ms=result.execution_time_ms if result else None,
            tokens=response.get("tokens"),
            log_id=response.get("log_id"),
            secondary_results=response.get("secondary_results", []),
            insight=response.get("insight"),
            analytical=response.get("analytical", False),
            agent_count=response.get("agent_count"),
            comparison_sql_count=response.get("comparison_sql_count"),
            clarification_needed=response.get("clarification_needed", False),
            suggestions=response.get("suggestions"),
            original_question=response.get("original_question"),
            supplements=response.get("supplements"),
        )
    else:
        return ChatResponse(
            success=False,
            error=response.get("error", "Bilinmeyen hata"),
        )


@app.post("/api/chat/no-filter", response_model=ChatResponse)
async def chat_no_filter(request: ChatRequest, http_request: Request):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG servisi hazır değil")

    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Soru boş olamaz")

    client_ip = http_request.client.host
    effective_user_id = request.client_id or request.user_id or "web_user"

    response = rag_service.query(
        question=question,
        user_id=effective_user_id,
        user_ip=client_ip,
        session_id=request.session_id,
        skip_filters=True,
    )

    result = response.get("result")
    if response["success"]:
        return ChatResponse(
            success=True,
            answer=f"[Filtreler devre dışı] {result.row_count if result else 0} sonuç.",
            sql=response.get("sql"),
            sql_original=response.get("sql_original"),
            data=result.data if result else None,
            columns=result.columns if result else None,
            row_count=result.row_count if result else 0,
            filtered_count=0,
            has_filters=False,
            visualization_type=result.visualization_type if result else None,
            execution_time_ms=result.execution_time_ms if result else None,
            tokens=response.get("tokens"),
            log_id=response.get("log_id"),
        )
    return ChatResponse(success=False, error=response.get("error", "Hata"))


# ── Feedback ───────────────────────────────────────────────────────────────

@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    if not usage_logger:
        raise HTTPException(status_code=503, detail="Logger hazır değil")
    if request.feedback not in ("positive", "negative"):
        raise HTTPException(status_code=400, detail="feedback: 'positive' veya 'negative'")

    ok = usage_logger.update_feedback(
        log_id=request.log_id,
        feedback=request.feedback,
        comment=request.comment,
    )
    if ok:
        return {"success": True, "message": "Geri bildirim kaydedildi"}
    raise HTTPException(status_code=500, detail="Geri bildirim kaydedilemedi")


# ── İstatistikler ──────────────────────────────────────────────────────────

@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(days: int = 7):
    if not usage_logger:
        raise HTTPException(status_code=503, detail="Logger hazır değil")
    stats = usage_logger.get_usage_stats(days=days)
    return StatsResponse(
        total_queries=stats.get("total_queries", 0),
        successful_queries=stats.get("successful_queries", 0),
        failed_queries=stats.get("failed_queries", 0),
        success_rate=stats.get("success_rate", 0.0),
        total_tokens=stats.get("total_tokens", 0),
        total_cost_usd=stats.get("total_cost_usd", 0.0),
        avg_response_time_ms=stats.get("avg_response_time_ms", 0.0),
    )


@app.get("/api/recent-logs")
async def get_recent_logs(limit: int = 20):
    if not usage_logger:
        raise HTTPException(status_code=503, detail="Logger hazır değil")
    logs = usage_logger.get_recent_logs(limit=limit)
    return {"logs": logs}


# ── Sohbet Geçmişi ─────────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history(client_id: str, limit: int = 50):
    if not usage_logger:
        raise HTTPException(status_code=503, detail="Logger hazır değil")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id gerekli")
    sessions = usage_logger.get_client_sessions(client_id=client_id, limit=limit)
    return {"sessions": sessions}


@app.get("/api/session/{session_id}/messages")
async def get_session_messages(session_id: str):
    if not usage_logger:
        raise HTTPException(status_code=503, detail="Logger hazır değil")
    messages = usage_logger.get_chat_messages(session_id=session_id)
    return {"messages": messages}


# ── SQL Yeniden Çalıştır ───────────────────────────────────────────────────

@app.post("/api/rerun")
async def rerun_sql(request: RerunRequest):
    from services.sql_executor import SQLExecutor
    if not request.sql:
        raise HTTPException(status_code=400, detail="sql gerekli")

    executor = SQLExecutor()
    result = executor.execute_query(request.sql)

    if result.success:
        return {
            "success": True,
            "data": result.data,
            "columns": result.columns,
            "row_count": result.row_count,
            "visualization_type": result.visualization_type,
            "execution_time_ms": result.execution_time_ms,
        }
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": result.error},
    )


# ── Günlük Rapor Gönder ───────────────────────────────────────────────────

@app.post("/api/report/send")
async def send_daily_report_now():
    try:
        from services.alert_service import send_daily_report, generate_daily_report
        msg = generate_daily_report()
        send_daily_report()
        return {"success": True, "message": "Günlük rapor Telegram'a gönderildi", "preview": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Tedarikçi E-posta ─────────────────────────────────────────────────────

@app.post("/api/supplier-email")
async def generate_supplier_email(request: Request):
    body = await request.json()
    product = body.get("product", {})
    qty = int(body.get("recommended_qty", 50))

    # Eğer product boşsa gerçek kritik stoktan al
    if not product:
        from services.alert_service import check_critical_stock
        items = check_critical_stock()
        if items:
            product = items[0]
            qty = max(100, int(items[0].get("eksik_miktar", 50) * 2))

    from services.alert_service import generate_supplier_email as gen_email
    mail = gen_email(product, qty)
    return {"email": mail}


@app.post("/api/supplier-email/bulk")
async def generate_bulk_supplier_email():
    """Tüm kritik stok ürünleri için mail taslağı oluştur."""
    from services.alert_service import check_critical_stock
    items = check_critical_stock()
    if not items:
        return {"email": "Kritik stok seviyesinde ürün bulunmuyor.", "items": []}

    lines = [
        "Sayın Tedarikçimiz,",
        "",
        "Aşağıdaki kalemler için stok yenileme talebimizi iletiyoruz.",
        "Önerilen miktarlar, son 90 günlük satış ortalamasına ve 2 haftalık hareket payına göre AI tarafından hesaplanmıştır.",
        "",
    ]
    for item in items[:10]:
        recommended = max(50, int(item.get("eksik_miktar", 20) * 2))
        lines.append(
            f"• {item['sto_isim'][:40]} — {recommended} ad"
            f"   (mevcut: {item['mevcut_stok']:.0f} ad / min {item['sto_min_stok']:.0f} ad)"
        )

    lines += [
        "",
        "Teslimat: Mümkünse Perşembe öğleden önce.",
        "İletişim: yonetici@kobi.ai",
        "",
        "Saygılarımızla,",
        "İşletme Yöneticisi",
    ]
    return {"email": "\n".join(lines), "items": items[:10]}


# ── TTS (Opsiyonel — Google Cloud) ────────────────────────────────────────

def _setup_google_credentials():
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        path = "/app/google_credentials.json"
        try:
            with open(path, "w") as f:
                f.write(creds_json)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        except Exception as e:
            print(f"[TTS] Credentials yazma hatası: {e}")


@app.post("/api/tts")
async def text_to_speech(request: Request):
    try:
        from google.cloud import texttospeech as _tts
        body = await request.json()
        text = (body.get("text") or "").strip()[:1000]
        if not text:
            return JSONResponse({"error": "Metin boş"}, status_code=400)

        _setup_google_credentials()
        client = _tts.TextToSpeechClient()
        response = client.synthesize_speech(
            input=_tts.SynthesisInput(text=text),
            voice=_tts.VoiceSelectionParams(
                language_code="tr-TR",
                name="tr-TR-Wavenet-A",
                ssml_gender=_tts.SsmlVoiceGender.FEMALE,
            ),
            audio_config=_tts.AudioConfig(
                audio_encoding=_tts.AudioEncoding.MP3,
                speaking_rate=1.05,
                pitch=1.0,
            ),
        )
        return JSONResponse({"audio_b64": _base64.b64encode(response.audio_content).decode()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/stt")
async def speech_to_text(request: Request):
    try:
        from google.cloud import speech as _speech
        _setup_google_credentials()
        body = await request.json()
        audio_b64 = body.get("audio_b64", "")
        if not audio_b64:
            return JSONResponse({"error": "Ses verisi boş"}, status_code=400)

        client = _speech.SpeechClient()
        response = client.recognize(
            config=_speech.RecognitionConfig(
                encoding=_speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                sample_rate_hertz=48000,
                language_code="tr-TR",
                enable_automatic_punctuation=True,
            ),
            audio=_speech.RecognitionAudio(content=_base64.b64decode(audio_b64)),
        )
        transcript = "".join(r.alternatives[0].transcript for r in response.results)
        return JSONResponse({"transcript": transcript.strip()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Sunucu Başlatıcı ───────────────────────────────────────────────────────

def run_server(host: str = "0.0.0.0", port: int = 8000):
    # Railway / Render / Fly.io → PORT env değişkenini öncelikli kullan
    import os as _os
    port = int(_os.environ.get("PORT", port))
    print(f"\nSunucu: http://{host}:{port}")
    print(f"API Docs: http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
