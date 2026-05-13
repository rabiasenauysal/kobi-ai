"""
KOBİ AI Platform — Pipeline Routes
/pipeline prefix'li yönetim endpoint'leri.
api.py'ye dahil edilir: from pipeline_routes import router as pipeline_router
"""

import os
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from services.db import query as db_query

router = APIRouter(prefix="/pipeline")
security = HTTPBasic()

PIPELINE_PIN = os.environ.get("PIPELINE_PIN", "pipeline123")


def check_pipeline_pin(credentials: HTTPBasicCredentials = Depends(security)):
    correct = secrets.compare_digest(credentials.password, PIPELINE_PIN)
    if not correct:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı şifre",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


# ── Genel Pipeline Sayfası ─────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def pipeline_page(auth: bool = Depends(check_pipeline_pin)):
    html_path = Path(__file__).parent / "static" / "pipeline.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>KOBİ AI — Pipeline Yönetim</h1><a href='/docs'>API Docs</a>",
        status_code=200,
    )


# ── Veritabanı Sağlık Kontrolü ────────────────────────────────────────────

@router.get("/db-health")
async def db_health(auth: bool = Depends(check_pipeline_pin)):
    try:
        counts = {}
        for tbl in ["SIPARISLER", "STOKLAR", "STOK_HAREKETLERI",
                    "CARI_HESAPLAR", "KARGO_GONDERILERI", "IADE_TALEPLERI"]:
            try:
                r = db_query(f"SELECT COUNT(*) AS n FROM {tbl}")
                counts[tbl] = r[0]["n"] if r else 0
            except Exception:
                counts[tbl] = -1

        return {"status": "ok", "row_counts": counts}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


# ── Sipariş Özeti ──────────────────────────────────────────────────────────

@router.get("/orders/summary")
async def orders_summary(days: int = 30, auth: bool = Depends(check_pipeline_pin)):
    try:
        rows = db_query("""
            SELECT s.sip_eticaret_kanal_kodu AS kanal,
                   COUNT(DISTINCT s.sip_Guid) AS siparis_sayisi,
                   ROUND(SUM(sth.sth_birimfiyat * sth.sth_miktar), 2) AS toplam_ciro
            FROM SIPARISLER s
            LEFT JOIN STOK_HAREKETLERI sth ON s.sip_evrakno_sira = sth.sth_evrakno_sira
                AND sth.sth_iptal=0 AND sth.sth_cins=8
            WHERE s.sip_iptal=0
              AND date(s.sip_tarih) >= date('now', ? || ' days')
            GROUP BY s.sip_eticaret_kanal_kodu
            ORDER BY toplam_ciro DESC
        """, (f"-{abs(days)}",))
        return {"days": days, "channels": rows}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Stok Kritik Uyarı ─────────────────────────────────────────────────────

@router.get("/stock/critical")
async def stock_critical(auth: bool = Depends(check_pipeline_pin)):
    try:
        rows = db_query("""
            SELECT st.sto_kod, st.sto_isim, st.sto_min_stok,
                   COALESCE(sdp.sdp_stok_miktari, 0) AS mevcut_stok,
                   st.sto_min_stok - COALESCE(sdp.sdp_stok_miktari, 0) AS eksik_miktar
            FROM STOKLAR st
            LEFT JOIN STOK_DEPO_DETAYLARI sdp ON st.sto_kod = sdp.sdp_depo_kod
            WHERE st.sto_iptal=0 AND st.sto_min_stok > 0
              AND COALESCE(sdp.sdp_stok_miktari, 0) < st.sto_min_stok
            ORDER BY eksik_miktar DESC
            LIMIT 50
        """)
        return {"critical_count": len(rows), "items": rows}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Son İade Talepleri ────────────────────────────────────────────────────

@router.get("/returns/recent")
async def returns_recent(limit: int = 50, auth: bool = Depends(check_pipeline_pin)):
    try:
        rows = db_query("""
            SELECT i.itlp_tarihi, i.itlp_musteri_kodu, i.itlp_stok_kodu,
                   st.sto_isim, i.itlp_miktari, i.itlp_aciklama, i.itlp_tip
            FROM IADE_TALEPLERI i
            LEFT JOIN STOKLAR st ON i.itlp_stok_kodu = st.sto_kod
            WHERE i.itlp_iptal=0
            ORDER BY i.itlp_tarihi DESC
            LIMIT ?
        """, (limit,))
        return {"total": len(rows), "returns": rows}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Entity Cache Yenile ────────────────────────────────────────────────────

@router.post("/entity-cache/reload")
async def reload_entity_cache(auth: bool = Depends(check_pipeline_pin)):
    try:
        import api as _api
        if _api.rag_service and hasattr(_api.rag_service, "entity_cache"):
            _api.rag_service.entity_cache.clear()
            _api.rag_service.entity_cache.load()
            stats = _api.rag_service.entity_cache.get_stats()
            return {"success": True, "stats": stats}
        return {"success": False, "message": "Entity cache bulunamadı"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Schema Yenile ─────────────────────────────────────────────────────────

@router.post("/schema/reload")
async def reload_schema(auth: bool = Depends(check_pipeline_pin)):
    try:
        from services.schema_extractor import SchemaExtractor
        from services.vector_store import VectorStore

        extractor = SchemaExtractor(use_manual_schema=True)
        chunks = extractor.extract_and_chunk()

        store = VectorStore()
        store.delete_collection()
        store.create_collection(vector_size=1536)

        n_tables = store.add_documents(chunks["table_chunks"])
        n_joins  = store.add_documents(chunks["join_chunks"])

        info = store.get_collection_info()
        return {
            "success": True,
            "table_chunks": n_tables,
            "join_chunks": n_joins,
            "collection": info,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Kullanım Logları ──────────────────────────────────────────────────────

@router.get("/usage/logs")
async def usage_logs(limit: int = 100, auth: bool = Depends(check_pipeline_pin)):
    try:
        rows = db_query("""
            SELECT id, question, status, user_id, session_id,
                   generated_sql, row_count, ai_model,
                   prompt_tokens, completion_tokens, total_tokens,
                   response_time_ms, error_message, created_at
            FROM ChatbotUsageLogs
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return {"total": len(rows), "logs": rows}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/usage/stats")
async def usage_stats(days: int = 7, auth: bool = Depends(check_pipeline_pin)):
    try:
        rows = db_query("""
            SELECT COUNT(*) AS toplam_sorgu,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS basarili,
                   SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) AS basarisiz,
                   ROUND(AVG(CAST(response_time_ms AS REAL)), 1) AS ort_yanit_ms,
                   SUM(COALESCE(total_tokens, 0)) AS toplam_token,
                   MIN(created_at) AS ilk_sorgu,
                   MAX(created_at) AS son_sorgu
            FROM ChatbotUsageLogs
            WHERE date(created_at) >= date('now', ? || ' days')
        """, (f"-{abs(days)}",))
        return {"days": days, "stats": rows[0] if rows else {}}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
