# KOBİ AI — Yapay Zeka Destekli Operasyon Platformu

> **AI Akademi Hackathon 2026** — 6 ajanın tamamını kapsayan üretim kalitesi demo

KOBİ'lerin günlük operasyonlarını yapay zeka ile otomatikleştiren, Türkçe doğal dil anlayan entegre platform.

---

## 🎯 Kapsanan Senaryolar

| # | Senaryo | Uygulama |
|---|---------|----------|
| 1 | **Müşteri İletişim Otomasyonu** | Telegram bot — doğal dil sipariş/kargo sorgusu, 7/24 otomatik yanıt |
| 2 | **Ürün & Sipariş Takibi** | Canlı dashboard — bugünkü siparişler, bekleyen, kargodaki |
| 3 | **Kargo Süreç Yönetimi** | Geciken kargo tespiti, yöneticiye otomatik Telegram bildirimi |
| 4 | **Stok & Envanter Yönetimi** | Kritik stok uyarısı, AI destekli tedarikçi mail taslağı |
| 5 | **İş Akışı & Görev Yönetimi** | Her sabah 08:00 rol bazlı görev listesi Telegram'a otomatik gönderim |
| 6 | **Analitik & İçgörü** | 30/90/365 gün trend, kanal dağılımı, SQL chat asistanı |

---

## 🏗️ Mimari

```
Frontend (Vanilla JS + Tailwind CSS)
    ↕
FastAPI Backend
    ├── SQL Agent (LangGraph + GPT-4o-mini + ChromaDB RAG)
    ├── Telegram Bot (Webhook — doğal dil → SQL)
    ├── APScheduler (08:00 sabah görevi, 30dk kargo, 60dk stok)
    └── SQLite (demo verisi — 8.600+ sipariş, 100 ürün, 5 kanal)
```

**Stack:** Python · FastAPI · SQLite · ChromaDB · OpenAI GPT-4o-mini · LangGraph · APScheduler · Telegram Bot API

---

## 🚀 Yerel Kurulum

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. .env dosyası oluştur
cp .env.example .env
# OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID ekle

# 3. ChromaDB schema embedding (bir kez)
python main.py setup

# 4. Başlat
python main.py web
# → http://localhost:8000
```

---

## ☁️ Railway Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app)

Environment variables:
```
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=...
```

---

## 📁 Proje Yapısı

```
├── api.py                  # FastAPI uygulama + tüm route'lar
├── main.py                 # CLI giriş noktası (web/setup/seed)
├── services/
│   ├── sql_agent.py        # LangGraph Text-to-SQL ajanı
│   ├── rag_service.py      # RAG-First sorgu servisi
│   ├── telegram_bot.py     # Telegram webhook handler
│   ├── alert_service.py    # Kargo/stok/görev bildirimleri
│   ├── scheduler.py        # APScheduler zamanlanmış görevler
│   └── chromadb_store.py   # Vector store (self-healing)
├── routers/
│   ├── dashboard_routes.py # KPI, sipariş, kargo, stok, görev API'leri
│   └── telegram_routes.py  # Telegram webhook endpoint'leri
├── static/
│   ├── index.html          # Tek sayfa uygulama
│   └── app.js              # Frontend logic
└── db/
    ├── kobi_demo.db        # Demo SQLite veritabanı
    └── seed.py             # Sentetik veri üretici
```

---

## 💬 Telegram Bot Komutları

```
/start  — Karşılama & yardım menüsü
/rapor  — Günlük operasyon raporu
/stok   — Kritik stok listesi
/kargo  — Geciken kargolar
/gorev  — Bugünkü aktif görevler

[Doğal dil] → "Bugün kaç sipariş geldi?"
             → "Trendyol'dan son 30 günün cirosu ne?"
             → "Hangi ürünler kritik stok seviyesinde?"
```

---

*Demo verisi tamamen sentetiktir. Gerçek kişi, işletme veya işlem bilgisi içermez.*
