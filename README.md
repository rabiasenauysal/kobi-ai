# 🤖 KOBİ AI — Yapay Zeka Destekli Operasyon Platformu

<div align="center">

**AI Akademi Hackathon 2026**

[![Live Demo](https://img.shields.io/badge/🌐_Canlı_Demo-kobi--ai-brightgreen?style=for-the-badge)](https://kobi-ai-production.up.railway.app)
[![GitHub](https://img.shields.io/badge/GitHub-kobi--ai-black?style=for-the-badge&logo=github)](https://github.com/rabiasenauysal/kobi-ai)
[![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)

*KOBİ'lerin günlük operasyonlarını yapay zeka ile otomatikleştiren, Türkçe doğal dil anlayan entegre platform.*

</div>

---

## 🎯 Problem & Çözüm

| | |
|---|---|
| **Problem** | KOBİ'ler sipariş, kargo, stok ve müşteri iletişimini birbirinden kopuk, manuel araçlarla yönetiyor. |
| **Çözüm** | Telegram botu, canlı dashboard ve doğal dil SQL asistanıyla tüm operasyonu tek platformda otomatikleştiriyoruz. |

---

## ✅ Kapsanan 6 Senaryo

| # | Senaryo | Nasıl Çalışır |
|---|---------|--------------|
| 1 | **Müşteri İletişim Otomasyonu** | Telegram bot — doğal dil sipariş/kargo sorgusu, 7/24 otomatik yanıt |
| 2 | **Ürün & Sipariş Takibi** | Canlı dashboard — bugünkü siparişler, bekleyen, kargodaki |
| 3 | **Kargo Süreç Yönetimi** | Geciken kargo tespiti, yöneticiye otomatik Telegram bildirimi |
| 4 | **Stok & Envanter Yönetimi** | Kritik stok uyarısı, AI destekli tedarikçi mail taslağı |
| 5 | **İş Akışı & Görev Yönetimi** | Her sabah 08:00 rol bazlı görev listesi Telegram'a otomatik gönderim |
| 6 | **Analitik & İçgörü** | 30/90/365 gün trend, kanal dağılımı, doğal dil SQL chat asistanı |

---

## 🏗️ Mimari

```
Frontend (Vanilla JS + Tailwind CSS)
        ↕
FastAPI Backend  ←→  Railway Cloud (Production)
    ├── SQL Agent (LangGraph + GPT-4o-mini + ChromaDB RAG)
    ├── Telegram Bot (Webhook — doğal dil → SQL → cevap)
    ├── APScheduler (08:00 sabah görevi · 30dk kargo · 60dk stok)
    └── SQLite (8.600+ sipariş · 100 ürün · 5 e-ticaret kanalı)
```

**Tech Stack:**
`Python` · `FastAPI` · `SQLite` · `ChromaDB` · `OpenAI GPT-4o-mini` · `LangGraph` · `APScheduler` · `Telegram Bot API` · `Railway`

---

## 🚀 Yerel Kurulum

```bash
# 1. Repoyu klonla
git clone https://github.com/rabiasenauysal/kobi-ai.git
cd kobi-ai

# 2. Bağımlılıkları kur
pip install -r requirements.txt

# 3. .env dosyası oluştur
cp .env.example .env
# OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID ekle

# 4. ChromaDB schema embedding (bir kez)
python main.py setup

# 5. Başlat
python main.py web
# → http://localhost:8000
```

---

## ☁️ Railway ile Deploy Edildi

Proje Railway üzerinde containerize edilmiş olarak çalışmaktadır.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

```env
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=...
```

---

## 💬 Telegram Bot

**@mikroai_bot** — Telegram'da arayın ve test edin!

```
/start  → Karşılama & yardım menüsü
/rapor  → Günlük operasyon raporu
/stok   → Kritik stok listesi
/kargo  → Geciken kargolar
/gorev  → Bugünkü aktif görevler

Doğal dil örnekleri:
  "Bugün kaç sipariş geldi?"
  "Trendyol'dan son 30 günün cirosu ne?"
  "Hangi ürünler kritik stok seviyesinde?"
  "Bekleyen siparişleri listele"
```

---

## 📁 Proje Yapısı

```
├── api.py                    # FastAPI uygulama + tüm route'lar
├── main.py                   # CLI giriş noktası (web/setup/seed)
├── Dockerfile                # Railway container tanımı
├── services/
│   ├── rag_service.py        # RAG-First sorgu servisi (konuşma hafızası)
│   ├── sql_agent.py          # LangGraph Text-to-SQL ajanı
│   ├── telegram_bot.py       # Telegram webhook handler
│   ├── alert_service.py      # Kargo/stok/görev bildirimleri
│   ├── scheduler.py          # APScheduler zamanlanmış görevler
│   └── chromadb_store.py     # Vector store (self-healing)
├── routers/
│   ├── dashboard_routes.py   # KPI, sipariş, kargo, stok, görev API'leri
│   └── telegram_routes.py    # Telegram webhook endpoint'leri
├── static/
│   ├── index.html            # Tek sayfa uygulama
│   └── app.js                # Frontend logic
└── db/
    ├── kobi_demo.db          # Demo SQLite veritabanı
    └── seed.py               # Sentetik veri üretici (8.600+ kayıt)
```

---

<div align="center">

*Demo verisi tamamen sentetiktir. Gerçek kişi, işletme veya işlem bilgisi içermez.*

**Geliştirici:** Rabia Sena Uysal · AI Akademi Hackathon 2026

</div>
