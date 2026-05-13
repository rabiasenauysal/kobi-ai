"""
KOBİ AI Platform — Uygulama Giriş Noktası

Kullanım:
  python main.py web      → Web sunucusunu başlat (varsayılan)
  python main.py setup    → ChromaDB vector DB'yi kur (ilk kurulumda bir kez)
  python main.py seed     → SQLite veritabanını sentetik veri ile doldur
  python main.py stats    → Kullanım istatistiklerini göster
  python main.py health   → Bağlantıları test et
  python main.py db-init  → ChatbotUsageLogs / ChatMessages tablolarını oluştur
"""

import sys
import os
from datetime import datetime

# Windows terminal encoding fix
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')


def cmd_web():
    """FastAPI web sunucusunu başlat."""
    from api import run_server
    run_server()


def cmd_seed():
    """SQLite veritabanını sentetik veri ile doldur."""
    print("\n" + "=" * 65)
    print("  KOBİ AI — VERİTABANI SEED")
    print("=" * 65)
    from db.seed import seed
    seed()
    print("=" * 65 + "\n")


def cmd_setup():
    """
    ChromaDB vector database'i kur ve schema chunk'larını yükle.
    İLK KURULUMDA BİR KEZ çalıştırılır.
    Veritabanı şeması değişince tekrar çalıştırılabilir.
    """
    print("\n" + "=" * 65)
    print("  KOBİ AI — CHROMADB KURULUMU (RAG-First)")
    print("=" * 65)

    from config.settings import print_config
    print_config()

    # 1. Log tablolarını oluştur
    print("\n[0/4] Log tabloları kontrol ediliyor...")
    cmd_db_init(silent=True)

    # 2. Schema chunk'larını üret
    print("\n[1/4] Schema chunk'ları hazırlanıyor...")
    from services.schema_extractor import SchemaExtractor
    extractor = SchemaExtractor(use_manual_schema=True)
    chunks    = extractor.extract_and_chunk()
    total     = len(chunks["table_chunks"]) + len(chunks["join_chunks"])
    print(f"  {len(chunks['table_chunks'])} tablo chunk + {len(chunks['join_chunks'])} JOIN chunk = {total} toplam")

    # 3. ChromaDB collection'ı sıfırla
    print("\n[2/4] ChromaDB collection sıfırlanıyor...")
    from services.vector_store import VectorStore
    store = VectorStore()
    store.delete_collection()
    store.create_collection(vector_size=1536)
    print("  Collection oluşturuldu")

    # 4. Chunk'ları yükle
    print("\n[3/4] Chunk'lar ChromaDB'ye yükleniyor...")
    n1 = store.add_documents(chunks["table_chunks"])
    n2 = store.add_documents(chunks["join_chunks"])
    n3 = store.add_documents(chunks.get("pattern_chunks", []))
    print(f"  Tablo: {n1} | JOIN: {n2} | Pattern: {n3} -> Toplam: {n1+n2+n3} doküman")

    # 5. Test arama
    print("\n[4/4] Test araması yapılıyor...")
    results = store.search("kanal bazlı ciro Trendyol satış", limit=3)
    print(f"  {len(results)} sonuç bulundu")
    if results:
        print(f"  En yakın: {results[0]['text'][:80]}...")

    info = store.get_collection_info()
    print(f"\n  Collection: {info.get('name')}")
    print(f"  Toplam vektör: {info.get('points_count')}")

    print("\n" + "=" * 65)
    print("  KURULUM TAMAMLANDI — Simdi 'python main.py web' calistirin")
    print("=" * 65 + "\n")


def cmd_db_init(silent: bool = False):
    """ChatbotUsageLogs ve ChatMessages tablolarını oluştur."""
    if not silent:
        print("\n" + "=" * 65)
        print("  KOBİ AI — DB TABLO BAŞLATMA")
        print("=" * 65)

    try:
        from services.usage_logger import UsageLogger
        logger = UsageLogger()  # __init__ içinde _ensure_tables() çağrılır
        if not silent:
            print("  ChatbotUsageLogs ve ChatMessages tabloları hazır")
            print("=" * 65 + "\n")
    except Exception as e:
        print(f"  DB init hatası: {e}")


def cmd_stats():
    """Kullanım istatistiklerini göster."""
    print("\n" + "=" * 65)
    print("  KOBİ AI — KULLANIM İSTATİSTİKLERİ")
    print("=" * 65)

    from services.usage_logger import UsageLogger
    logger = UsageLogger()

    for days in [1, 7, 30]:
        stats = logger.get_usage_stats(days=days)
        print(f"\n  Son {days} gün:")
        print(f"    Toplam Sorgu  : {stats.get('total_queries', 0)}")
        print(f"    Basarili      : {stats.get('successful_queries', 0)}")
        print(f"    Basari Orani  : {stats.get('success_rate', 0):.1f}%")
        print(f"    Toplam Token  : {stats.get('total_tokens', 0):,}")
        print(f"    Maliyet (USD) : ${stats.get('total_cost_usd', 0):.4f}")
        print(f"    Ort. Yanit    : {stats.get('avg_response_time_ms', 0):.0f}ms")

    print("\n  Son 5 Sorgu:")
    recent = logger.get_recent_logs(limit=5)
    for i, log in enumerate(recent, 1):
        status = "OK" if log.get("status") == "success" else "FAIL"
        print(f"  {i}. [{status}] {str(log.get('question', ''))[:50]}")

    print("=" * 65 + "\n")


def cmd_health():
    """Tüm bağlantıları test et."""
    print("\n" + "=" * 65)
    print("  KOBİ AI — BAĞLANTI TESTİ")
    print("=" * 65)

    # SQLite
    print("\n[1] SQLite bağlantısı...")
    try:
        from services.sql_executor import SQLExecutor
        executor = SQLExecutor()
        result   = executor.execute_query("SELECT COUNT(*) AS n FROM SIPARISLER WHERE sip_iptal=0")
        if result.success:
            n = result.data[0]["n"] if result.data else 0
            print(f"  Baglanildi — SIPARISLER: {n:,} aktif kayit")
        else:
            print(f"  SQL hatasi: {result.error}")
    except Exception as e:
        print(f"  Baglantihatasi: {e}")

    # Log Tabloları
    print("\n[2] Log tabloları...")
    try:
        from services.usage_logger import UsageLogger
        logger = UsageLogger()
        stats  = logger.get_usage_stats(days=1)
        print(f"  ChatbotUsageLogs eriselebilir — Bugun: {stats.get('total_queries', 0)} sorgu")
    except Exception as e:
        print(f"  Log tablo hatasi: {e}")

    # ChromaDB
    print("\n[3] ChromaDB bağlantısı...")
    try:
        from services.vector_store import VectorStore
        store = VectorStore()
        info  = store.get_collection_info()
        if "error" not in info:
            cnt = info.get("points_count", 0)
            print(f"  Baglanildi — {cnt} vektor")
            if cnt == 0:
                print(f"  ChromaDB bos — 'python main.py setup' calistirin")
        else:
            print(f"  ChromaDB: {info.get('error')} (setup calistirilmamis olabilir)")
    except Exception as e:
        print(f"  ChromaDB hatasi: {e}")

    # OpenAI
    print("\n[4] OpenAI bağlantısı...")
    try:
        from config.settings import get_settings
        from openai import OpenAI
        settings = get_settings()
        client   = OpenAI(api_key=settings.openai_api_key)
        resp     = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Merhaba"}],
            max_tokens=5,
        )
        print(f"  OpenAI baglanildi")
    except Exception as e:
        print(f"  OpenAI hatasi: {e}")

    # Telegram
    print("\n[5] Telegram bot durumu...")
    try:
        from services.telegram_bot import get_bot_info
        info = get_bot_info()
        if info:
            print(f"  Bot aktif — @{info.get('username')}")
        else:
            print(f"  Token ayarlanmamis veya gecersiz")
    except Exception as e:
        print(f"  Telegram hatasi: {e}")

    print("\n" + "=" * 65 + "\n")


def print_usage():
    print("""
KOBİ AI PLATFORM — KULLANIM

  python main.py web       Web sunucusunu baslat
  python main.py seed      SQLite veritabanini doldur (ilk kurulum)
  python main.py setup     ChromaDB'yi kur (ilk kurulum)
  python main.py stats     Istatistikleri goster
  python main.py health    Baglantiları test et
  python main.py db-init   Log tablolarini olustur

Ilk kurulum sirasi:
  1. .env dosyasini duzenle (OPENAI_API_KEY)
  2. python main.py seed   (sentetik veri)
  3. python main.py setup  (ChromaDB + log tablolari)
  4. python main.py web
  5. Tarayici: http://localhost:8000
""")


def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "web"

    dispatch = {
        "web":     cmd_web,
        "seed":    cmd_seed,
        "setup":   cmd_setup,
        "stats":   cmd_stats,
        "health":  cmd_health,
        "db-init": cmd_db_init,
    }

    if cmd in dispatch:
        dispatch[cmd]()
    else:
        print(f"Bilinmeyen komut: {cmd}")
        print_usage()


if __name__ == "__main__":
    main()
