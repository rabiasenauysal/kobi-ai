# ============================================================
# KOBİ AI Platform — Dockerfile
# Python 3.11 slim + SQLite (dahili) + ChromaDB
# Railway / Render / Fly.io uyumlu
# ============================================================

FROM python:3.11-slim

# ─── Sistem bağımlılıkları ───────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        sqlite3 \
        curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─── Python bağımlılıkları (önce kopyala — layer cache) ─────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Uygulama kaynak dosyaları ───────────────────────────────
COPY config/            config/
COPY services/          services/
COPY static/            static/
COPY routers/           routers/
COPY db/                db/
COPY api.py             .
COPY main.py            .
COPY start.sh           .

# ─── ChromaDB dizini (runtime'da oluşturulacak) ──────────────
RUN mkdir -p db/chroma_db

# ─── Çalıştırma izinleri ─────────────────────────────────────
RUN chmod +x start.sh

# ─── Port (Railway PORT env'i override eder) ─────────────────
EXPOSE 8000

# ─── Başlatma ─────────────────────────────────────────────────
CMD ["./start.sh"]