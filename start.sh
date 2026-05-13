#!/bin/bash
# ============================================================
# KOBİ AI Platform — Startup Script
# Railway / Render / Fly.io ortamlarında otomatik kurulum
# ============================================================
set -e

echo ""
echo "======================================================"
echo "  KOBİ AI PLATFORM — BAŞLATILIYOR"
echo "======================================================"

# ─── 1. SQLite DB kontrolü ───────────────────────────────────
if [ ! -f "db/kobi_demo.db" ] || [ ! -s "db/kobi_demo.db" ]; then
    echo "[1/3] Demo veritabanı oluşturuluyor..."
    python main.py seed
    echo "      ✅ Veritabanı hazır"
else
    echo "[1/3] ✅ Veritabanı mevcut ($(du -sh db/kobi_demo.db 2>/dev/null | cut -f1))"
fi

# ─── 2. ChromaDB setup (schema embedding) ────────────────────
CHROMA_COUNT=0
if [ -d "db/chroma_db" ]; then
    # chroma.sqlite3 varsa ve boş değilse sayıyı al
    if [ -f "db/chroma_db/chroma.sqlite3" ]; then
        CHROMA_COUNT=$(sqlite3 db/chroma_db/chroma.sqlite3 \
            "SELECT COUNT(*) FROM embeddings;" 2>/dev/null || echo "0")
    fi
fi

if [ "$CHROMA_COUNT" -lt "10" ] 2>/dev/null; then
    echo "[2/3] ChromaDB schema kurulumu başlatılıyor..."
    echo "      (Bu işlem ~30 saniye sürebilir — OpenAI embedding)"
    python main.py setup
    echo "      ✅ ChromaDB hazır"
else
    echo "[2/3] ✅ ChromaDB mevcut ($CHROMA_COUNT embedding)"
fi

# ─── 3. Web sunucu ───────────────────────────────────────────
echo "[3/3] Web sunucu başlatılıyor..."
echo "======================================================"
echo ""
exec python main.py web
