"""
KOBİ AI Platform — Analytical Multi-Agent LLM Chains
======================================================
Her agent için ayrı, yeniden kullanılabilir chain fonksiyonları.

TYF'den farklar:
  - VIEW_NAME / _COLUMN_NAMES_STR → Mikro tabloları ve kolon isimleri
  - Comparison planner: yarış/sporcu/kulüp → sipariş/ürün/kanal/müşteri/iade domain'i
  - Insight chain: yelken federasyonu asistanı → e-ticaret ERP analisti
  - system_prompt import: build_system_prompt (rag_service'ten, Mikro için yazılmış)
"""

import json
import logging
from typing import Dict, List, Tuple

from openai import OpenAI
from services.rag_service import build_system_prompt, fix_turkish_like_patterns

logger = logging.getLogger(__name__)

# ── SQLite mikro_ai.db — gerçek kolonlar (doğrulandı) ────────────────────
_COLUMN_NAMES_STR = """
⚠️ SQLite kullanılıyor: YEAR()/MONTH() yok → strftime('%Y',kolon). STRING_AGG yok → group_concat.
   COLLATE Turkish_CI_AS yok → LOWER(kolon) LIKE LOWER('%..%'). TOP N yok → LIMIT N.

SIPARISLER: sip_no, sip_Guid, sip_tarih, sip_eticaret_kanal_kodu,
  sip_musteri_kod, sip_evrakno_seri, sip_evrakno_sira,
  sip_durum (TEXT: 'Hazırlanıyor'|'Kargoya Verildi'|'Teslim Edildi'|'İptal'),
  sip_tutar, sip_kargo_no, sip_aciklama, sip_iptal, sip_hidden
  ⚠️ sip_durumu/sip_depono/sip_teslim_tarih YOK!

STOKLAR: sto_kod, sto_isim, sto_marka_kodu, sto_anagrup_kod, sto_altgrup_kod,
  sto_satis_fiyat1, sto_satis_fiyat2, sto_alis_fiyat, sto_birim, sto_min_stok,
  sto_iptal, sto_hidden
  ⚠️ sto_birim1_ad/sto_max_stok/sto_resim_url YOK! Gerçek stok: STOK_DEPO_DETAYLARI.sdp_stok_miktari

STOK_HAREKETLERI: sth_id, sth_stok_kod, sth_cari_kodu, sth_sip_uid,
  sth_fis_tarihi (tarih için bu kullan!), sth_birimfiyat, sth_tutar, sth_miktar,
  sth_iskonto1, sth_masraf1, sth_cins, sth_evrakno_seri, sth_evrakno_sira,
  sth_iptal, sth_hidden
  [cins: 8=E-ticaret satışı, 7=Fatura, 4=İade, 1=Alış]
  ⚠️ sth_tarih YOK! sth_giris_depo_no/sth_satirno/sth_miktar2 YOK!

CARI_HESAPLAR: cari_kod, cari_unvan1, cari_unvan2, cari_eposta (cari_EMail DEĞİL!),
  cari_tel, cari_sehir, cari_telegram_chat_id, cari_iptal, cari_hidden
  ⚠️ cari_grup_kodu/cari_bolge_kodu/cari_kaydagiristarihi YOK!

KARGO_GONDERILERI: kargo_id, kargo_evrakuid, kargo_sip_no, kargo_takip_no,
  kargo_firma (TEXT: 'Aras'|'MNG'|'Yurtiçi'|'PTT'|'Sürat'), kargo_durum (TEXT),
  kargo_gonderim_tarihi, kargo_teslim_tarihi, kargo_beklenen_teslim,
  kargo_gecikme_flag, kargo_musteri_bilgilendirildi, kargo_iptal, kargo_hidden
  ⚠️ kargo_sirkettipi/kargo_evraknosira/kargo_gonderitarihi YOK!

IADE_TALEPLERI: itlp_id, itlp_musteri_kodu, itlp_stok_kodu, itlp_miktari,
  itlp_aciklama, itlp_tarihi, itlp_tip, itlp_durum, itlp_evrak_sira,
  itlp_iptal, itlp_hidden
  [tip: 0=Standart, 1=Değişim, 2=Hasar]

E_TICARET_URUN_ESLEME: eu_stok_kodu, eu_eticaret_platform_id, eu_eticaret_urun_id, eu_iptal
  [platform: 'TRD'=Trendyol, 'HBS'=HepsiBurada, 'N11'=N11, 'CSP'=Kendi Site]

STOK_DEPO_DETAYLARI: sdp_id, sdp_depo_kod, sdp_depo_no,
  sdp_stok_miktari (gerçek stok!), sdp_sip_stok, sdp_min_stok, sdp_max_stok,
  sdp_iptal, sdp_hidden

STOK_FIYAT_DEGISIKLIKLERI: fid_stok_kod, fid_eskifiy_tutar, fid_yenifiy_tutar, fid_tarih, fid_iptal

JOIN KURALI: FK tanımlı değil, JOIN'leri her zaman açıkça yaz.
  SIPARISLER → STOK_HAREKETLERI : sip_evrakno_sira = sth_evrakno_sira (güvenli)
  SIPARISLER → CARI_HESAPLAR    : sip_musteri_kod = cari_kod
  SIPARISLER → KARGO_GONDERILERI: sip_Guid = kargo_evrakuid VEYA sip_no = kargo_sip_no
  STOKLAR    → STOK_HAREKETLERI : sto_kod = sth_stok_kod
  STOKLAR    → IADE_TALEPLERI   : sto_kod = itlp_stok_kodu
  STOKLAR    → STOK_DEPO_DETAYLARI: sto_kod = sdp_depo_kod
"""


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN 1 — SQL DESCRIPTION
# ─────────────────────────────────────────────────────────────────────────────

def run_sql_description_chain(
    client: OpenAI,
    sql: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 100,
) -> Tuple[str, int, int]:
    """
    SQL'i okuyarak ne getirdiğini 1 cümleyle açıklar.
    Kullanıcının sorusundan BAĞIMSIZ — sadece SQL'e bakarak yorum yapar.
    Döner: (description_str, prompt_tokens, completion_tokens)
    """
    prompt = f"""Aşağıdaki SQL sorgusunu oku ve tam olarak ne getirdiğini 1 cümleyle açıkla.
Kullanıcının ne sorduğunu bilmiyorsun — sadece SQL'e bakarak yorum yap.
WHERE, GROUP BY, ORDER BY, JOIN koşullarına bakarak filtre ve sıralamayı yansıt.
KOBİ ERP tabloları kullanılıyor (SIPARISLER, STOKLAR, STOK_HAREKETLERI, vb.)
Teknik terim veya kolon adı kullanma, sade Türkçe yaz. SQL kodu yazma.
Sayısal değerlerde ₺ işareti kullan.

SQL:
{sql}

Örnekler:
- "Trendyol kanalından Mart 2025'teki sipariş sayısı ve toplam ciro getirildi."
- "En çok iade edilen 10 ürün, iade nedenleriyle listelendi."
- "Stok seviyesi minimum eşiğin altına düşen ürünler depo bazında sıralandı."
- "2024 ve 2025 yıllarına ait aylık ciro karşılaştırması yapıldı."
- "HepsiBurada'da en çok satan 20 ürün, adet ve tutar olarak getirildi."

Açıklama:"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        desc = response.choices[0].message.content.strip()
        return desc, response.usage.prompt_tokens, response.usage.completion_tokens
    except Exception as e:
        logger.error(f"SQL description chain hatası: {e}")
        return "Sorgu çalıştırıldı.", 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN 2 — COMPARISON PLANNER
# ─────────────────────────────────────────────────────────────────────────────

def run_comparison_planner_chain(
    client: OpenAI,
    question: str,
    rewritten_question: str,
    primary_sql: str,
    primary_result_summary: str,
    analytical_depth: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 700,
) -> Tuple[List[Dict], int, int]:
    """
    Soruya göre anlamlı e-ticaret karşılaştırmaları planlar.
    Anlamlı karşılaştırma yoksa boş liste döner.
    Döner: (comparison_plans: List[{description, sql_hint, rationale}], pt, ct)
    """
    max_comparisons = {"light": 1, "medium": 1, "deep": 2}.get(analytical_depth, 1)

    prompt = f"""Sen KOBİ ERP ve E-Ticaret veri analisti asistanısın.
Kullanıcı ANALİTİK MODU açarak soru sordu — karşılaştırmalı içgörü istiyor.

KULLANICI SORUSU: "{question}"
YENİDEN YAZILMIŞ: "{rewritten_question}"

ANA SQL:
{primary_sql}

ANA SORGU ÖZETI:
{primary_result_summary}

GÖREV: Bu sorguya en fazla {max_comparisons} adet anlamlı karşılaştırma öner.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ KRİTİK KURAL: KÜME TUTARLILIĞI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Karşılaştırma SQL'i, PRIMARY SQL'deki AYNI ürün/kanal/müşteri kümesi üzerinde çalışmalı.
Farklı bir filtre uygulayarak FARKLI bir küme getirme.

❌ YANLIŞ: Primary "Trendyol Mart 2025 cirosu" → karşılaştırma "tüm kanalların Mart cirosu"
✅ DOĞRU:  Primary "Trendyol Mart 2025 cirosu" → karşılaştırma "Trendyol Mart 2024 cirosu"

❌ YANLIŞ: Primary "en çok satan 10 ürün" → karşılaştırma "tüm ürünlerin iade sayısı"
✅ DOĞRU:  Primary "en çok satan 10 ürün" → karşılaştırma "bu 10 ürünün iade oranı"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

E-TİCARET KARŞILAŞTIRMA KALIPLARI:

1. TARİH/DÖNEM VARSA → önceki dönemle karşılaştır (neredeyse her zaman yapılmalı)
   Örnek: "Mart 2025 siparişleri" → Mart 2024 siparişleri (yıllık büyüme)
   Örnek: "Bu ay ciro" → Geçen ay ciro (aylık değişim)
   Örnek: "Q1 2025 satışları" → Q1 2024 satışları

2. KANAL SORGUSU (Trendyol/HepsiBurada/N11)
   → Aynı metriği bir diğer kanalla karşılaştır
   Örnek: "Trendyol Mart cirosu" → HepsiBurada Mart cirosu
   → VEYA aynı kanalın önceki dönem performansı

3. ÜRÜN SORGUSU (en çok satan, en çok iade, fiyat değişimi)
   → Aynı ürün grubunun iade/stok/satış ilişkisi
   Örnek: "En çok satan 10 ürün" → Bu 10 ürünün iade oranı
   Örnek: "Fiyatı en çok artan ürünler" → Bu ürünlerin satış hacmindeki değişim

4. MÜŞTERİ SORGUSU
   → Aynı müşteri grubunun farklı bir metriği
   Örnek: "En çok sipariş veren müşteriler" → Bu müşterilerin iade oranı
   Örnek: "Yeni müşteriler" → Bu müşterilerin ortalama sepet tutarı

5. STOK / KRİTİK STOK SORGUSU
   → Kritik stoktaki ürünlerin son dönem satış hızı
   → VEYA bu ürünlerin hangi kanalda daha çok satıldığı

6. İADE SORGUSU
   → İade edilen ürünlerin aynı dönem satış sayısı (iade oranı hesabı)
   → VEYA iade nedenlerinin dağılımı

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANLAMSIZ KARŞILAŞTIRMA ÖRNEKLERİ (YAPMA):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Sipariş sayısı sorulduysa → müşteri demografisi ekleme (alakasız)
- Kanal cirosu sorulduysa → stok detayı ekleme (alakasız)
- Bağlamla alakasız, "ilginç olur" diye rastgele metrik ekleme

FORMAT — Sadece JSON döndür:

{{
  "comparisons": [
    {{
      "description": "Kullanıcıya gösterilecek kısa açıklama (Türkçe, max 10 kelime)",
      "sql_hint": "SQL üretmek için Türkçe ipucu (ne sorulacağı, hangi tablo/kolon)",
      "rationale": "Neden bu karşılaştırma anlamlı (iç not)"
    }}
  ]
}}

Anlamlı karşılaştırma gerçekten yoksa: {{"comparisons": []}}

JSON:"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content.strip()

        # Markdown fence temizle
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.lower().startswith("json"):
                content = content[4:]
            content = content.strip()

        parsed = json.loads(content)
        plans  = parsed.get("comparisons", [])[:max_comparisons]

        logger.info(f"Comparison planner: {len(plans)} karşılaştırma planlandı")
        for p in plans:
            logger.debug(f"  ✓ {p.get('description')} | {p.get('rationale', '')}")

        return plans, response.usage.prompt_tokens, response.usage.completion_tokens

    except Exception as e:
        logger.error(f"Comparison planner chain hatası: {e}")
        return [], 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN 3 — SECONDARY SQL GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_secondary_sql_chain(
    client: OpenAI,
    original_question: str,
    primary_sql: str,
    comparison_description: str,
    sql_hint: str,
    model: str,
    max_tokens: int = 600,
) -> Tuple[str, int, int]:
    """
    Bir karşılaştırma planı için SQL üretir.
    KOBİ ERP sistem promptunu kullanır (rag_service.build_system_prompt).
    Döner: (sql_str, prompt_tokens, completion_tokens)
    """
    system_prompt = build_system_prompt(original_question)

    user_prompt = f"""ANA SORU: {original_question}

ANA SQL (bağlam için — kopyalama, sadece karşılaştırma sorgusunu yaz):
{primary_sql}

YAPILACAK KARŞILAŞTIRMA: {comparison_description}
İPUCU: {sql_hint}

KURALLAR:
- Sadece bu karşılaştırma için yeni bir SQL yaz
- Ana SQL'i kopyalama
- Sadece SQL kodunu ver, markdown veya açıklama yazma
- Her sorguda [prefix]_iptal = 0 AND [prefix]_hidden = 0 filtresi ekle
- JOIN'leri açıkça yaz (FK tanımlı değil)
- Mevcut tablolar ve kolonlar:
{_COLUMN_NAMES_STR}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        sql = response.choices[0].message.content.strip()

        # Markdown fence temizle
        if sql.startswith("```"):
            sql = sql.split("```")[1]
            if sql.lower().startswith("sql"):
                sql = sql[3:]
            sql = sql.strip()
        if sql.endswith("```"):
            sql = sql[:-3].strip()

        # Türkçe LIKE fix
        sql = fix_turkish_like_patterns(sql)

        logger.debug(f"Secondary SQL üretildi: {sql[:100]}...")
        return sql, response.usage.prompt_tokens, response.usage.completion_tokens

    except Exception as e:
        logger.error(f"Secondary SQL chain hatası: {e}")
        return "", 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN 4 — INSIGHT & NARRATIVE
# ─────────────────────────────────────────────────────────────────────────────

def run_insight_chain(
    client: OpenAI,
    question: str,
    primary_description: str,
    primary_result_summary: str,
    secondary_summaries: List[Dict],
    analytical_depth: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 400,
) -> Tuple[str, int, int]:
    """
    Tüm sorgu sonuçlarını alır, Türkçe doğal dil özet + içgörü yazar.
    Döner: (insight_str, prompt_tokens, completion_tokens)
    """
    secondary_text  = ""
    has_comparisons = False

    for i, sec in enumerate(secondary_summaries, 1):
        if sec.get("success"):
            has_comparisons = True
            secondary_text += (
                f"\nKARŞILAŞTIRMA {i} — {sec.get('description', '')}\n"
                f"Ne getirildi: {sec.get('sql_description', '')}\n"
                f"Veri: {sec.get('summary', '')}\n"
            )

    comparison_instruction = (
        "Karşılaştırma verisi var — iki sonucu harmanlayarak rakamsal farkı, "
        "büyüme/düşüş yüzdesini ve trendi somut olarak belirt."
        if has_comparisons
        else "Ana veriyi kısaca özetle, en dikkat çekici rakamı vurgula."
    )

    prompt = f"""Sen KOBİ ERP ve E-Ticaret veri analisti asistanısın.

KULLANICI SORUSU: "{question}"

ANA SORGU — Ne getirildi: {primary_description}
ANA VERİ: {primary_result_summary}
{secondary_text}

GÖREV: En fazla 2-3 cümle. Düz paragraf olarak yaz.
{comparison_instruction}

KURALLAR:
❌ "KARŞILAŞTIRMA:", "İÇGÖRÜ:", "Analiz:", "Sonuç:" gibi etiket/başlık kullanma
❌ "Dikkat çekici", "ilginç", "Bu durum gösteriyor ki" gibi dolgu ifadeler kullanma
❌ Tabloda zaten görünen ham değerleri tekrar sayma
✅ Somut rakam, yüzde fark, artış/azalış miktarı belirt
✅ Mümkünse iş etkisi: "Bu hız sürdüğünde...", "Bu oran sektör ortalamasının..."
✅ ₺ işareti kullan, binlik ayraç ekle (örn: ₺1.250.000)
✅ Sadece düz Türkçe cümle yaz, başka hiçbir şey yok

FORMAT: Düz paragraf."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen KOBİ ERP ve E-Ticaret veri analisti asistanısın. "
                        "Kısa, net, rakamsal Türkçe yorumlar yapıyorsun. "
                        "Markdown kullanmıyorsun."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        insight = response.choices[0].message.content.strip()
        logger.info("Insight üretildi.")
        return insight, response.usage.prompt_tokens, response.usage.completion_tokens

    except Exception as e:
        logger.error(f"Insight chain hatası: {e}")
        return primary_result_summary, 0, 0