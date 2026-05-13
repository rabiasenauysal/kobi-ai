"""
KOBİ AI Platform — Sohbet Geçmişi (Conversation Memory)

Her session için runtime boyunca konuşma geçmişini tutar.
Sunucu yeniden başlatılınca sıfırlanır — kalıcı depolama yok.

Kullanım:
    memory = ConversationMemory(max_turns=10)

    memory.add_turn(
        session_id="abc123",
        user_question="Trendyol Mart 2025 cirosu nedir?",
        sql="SELECT SUM(sth_tutar) FROM ... WHERE sip_eticaret_kanal_kodu='Trendyol'",
        sql_description="Trendyol Mart 2025 toplam cirosu getirildi."
    )

    messages = memory.build_messages(
        session_id="abc123",
        system_prompt="...",
        schema_context="...",
        user_question="Peki HepsiBurada'da nasıl?"
    )
"""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Session bazlı konuşma geçmişi yöneticisi.

    Hafıza Döngüsü:
        1. build_messages()  → OpenAI'ya gönderilecek mesaj listesini hazırla
        2. [OpenAI'dan SQL gelir]
        3. add_turn()        → Soruyu ve üretilen SQL'i geçmişe kaydet
        4. Sonraki soruda tekrar build_messages() → geçmiş dahil
    """

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._store: Dict[str, List[Dict[str, str]]] = {}

    # ── Geçmişe Ekleme ────────────────────────────────────────────────

    def add_turn(
        self,
        session_id: str,
        user_question: str,
        sql: str,
        sql_description: str = "",
    ) -> None:
        """
        Bir sohbet turunu geçmişe ekler.

        Args:
            session_id:      Kullanıcının oturum kimliği
            user_question:   Kullanıcının doğal dil sorusu
            sql:             Üretilen ve başarıyla çalışan SQL
            sql_description: SQL'in ne getirdiğinin kısa açıklaması
        """
        if session_id not in self._store:
            self._store[session_id] = []

        history = self._store[session_id]

        # Kullanıcı mesajı
        history.append({
            "role": "user",
            "content": user_question,
        })

        # Asistan cevabı: SQL içerik özetiyle birlikte
        # Model, "Bu ürünler", "aynı kanal", "bu müşteri" gibi referansları
        # bir sonraki soruda SQL'den çözebilir.
        assistant_content = sql_description or "Sorgu çalıştırıldı."

        if sql and not sql.strip().startswith("--"):
            # KOBİ ERP bağlamı için önemli filtreleri özetle
            import re
            hints = []

            # Kanal filtresi
            kanal_hits = re.findall(
                r"sip_eticaret_kanal_kodu\s*=\s*'([^']+)'",
                sql, re.IGNORECASE
            )
            if kanal_hits:
                hints.append(f"Kanal: {', '.join(kanal_hits)}")

            # Tarih filtresi (YEAR/MONTH veya BETWEEN)
            year_hits = re.findall(r'YEAR\s*\([^)]+\)\s*=\s*(\d{4})', sql, re.IGNORECASE)
            if year_hits:
                hints.append(f"Yıl: {', '.join(set(year_hits))}")

            month_hits = re.findall(r'MONTH\s*\([^)]+\)\s*=\s*(\d{1,2})', sql, re.IGNORECASE)
            if month_hits:
                hints.append(f"Ay: {', '.join(set(month_hits))}")

            # LIKE aramaları (ürün/müşteri adı)
            like_hits = re.findall(r"LIKE\s+'([^']+)'", sql, re.IGNORECASE)
            if like_hits:
                clean = [h.replace('%', '').strip() for h in like_hits[:3] if len(h.replace('%', '').strip()) > 1]
                if clean:
                    hints.append(f"Filtre: {', '.join(clean)}")

            # Müşteri/Cari kodu — equality filter (sonraki soruda bağlam için kritik)
            cari_hits = re.findall(
                r"(?:cari_kod|sip_musteri_kod|itlp_musteri_kodu|sth_cari_kodu)\s*=\s*'([^']+)'",
                sql, re.IGNORECASE
            )
            if cari_hits:
                hints.append(f"Müşteri kodu: {', '.join(dict.fromkeys(cari_hits))}")

            # Ürün kodu — equality filter
            stok_hits = re.findall(
                r"(?:(?:st\.|sth\.|i\.|eu\.)?sto_kod|sth_stok_kod|itlp_stok_kodu|eu_stok_kodu)\s*=\s*'([^']+)'",
                sql, re.IGNORECASE
            )
            if stok_hits:
                hints.append(f"Ürün kodu: {', '.join(dict.fromkeys(stok_hits))}")

            if hints:
                assistant_content += "\n[Bağlam: " + " | ".join(hints) + "]"
            assistant_content += f"\n\n[SQL]\n{sql}"

        history.append({
            "role": "assistant",
            "content": assistant_content,
        })

        # Kayan pencere: max_turns'u aşarsa en eski turu sil
        max_messages = self.max_turns * 2
        if len(history) > max_messages:
            self._store[session_id] = history[-max_messages:]

        logger.debug(
            f"[Memory] Session={session_id} | "
            f"Geçmiş: {len(self._store[session_id])} mesaj"
        )

    # ── Mesaj Listesi Oluşturma ───────────────────────────────────────

    def build_messages(
        self,
        session_id: str,
        system_prompt: str,
        schema_context: str,
        user_question: str,
        voice: bool = False,
    ) -> List[Dict[str, str]]:
        """
        OpenAI'ya gönderilecek tam mesaj listesini döner.

        Yapı:
            [system: kurallar + rag schema context]  ← asla silinmez
            [user: geçmiş soru 1]
            [assistant: geçmiş SQL 1]
            ...
            [user: şimdiki soru]
        """
        system_content = system_prompt
        if schema_context:
            system_content += f"\n\n### VERİTABANI ŞEMA BAĞLAMI (RAG):\n{schema_context}"

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_content}
        ]

        # Geçmiş mesajları ekle
        history = self._store.get(session_id, [])
        messages.extend(history)

        # Şimdiki kullanıcı sorusu
        last_user_content = (
            f"{user_question}\n\n"
            "Eğer bu soru veritabanıyla ilgiliyse sadece SQL ver. "
            "Değilse --VOICE_CHAT: formatını kullan. Markdown bloğu kullanma."
        )
        messages.append({
            "role": "user",
            "content": last_user_content,
        })

        return messages

    # ── Yardımcı Metodlar ────────────────────────────────────────────

    def clear(self, session_id: str) -> None:
        """Bir session'ın geçmişini temizle."""
        self._store.pop(session_id, None)
        logger.info(f"[Memory] Session={session_id} geçmişi temizlendi.")

    def get_turn_count(self, session_id: str) -> int:
        """Bir session'da kaç tur var."""
        messages = self._store.get(session_id, [])
        return len(messages) // 2

    def all_sessions(self) -> List[str]:
        """Aktif session listesi."""
        return list(self._store.keys())

    def hydrate_from_db(self, session_id: str, db_messages: list) -> None:
        """DB'deki mesajlardan RAM geçmişini yeniden oluştur (server restart sonrası)."""
        if session_id in self._store:
            return  # Already in RAM, skip
        history = []
        for msg in db_messages:
            role      = msg.get("role", "")
            content   = msg.get("content", "") or ""
            sql_query = msg.get("sql_query") or ""
            if role == "user":
                history.append({"role": "user", "content": content})
            elif role == "assistant":
                assistant_content = content
                if sql_query:
                    assistant_content += f"\n\n[SQL]\n{sql_query}"
                history.append({"role": "assistant", "content": assistant_content})
        if history:
            max_messages = self.max_turns * 2
            self._store[session_id] = history[-max_messages:]
            logger.info(
                f"[Memory] Session={session_id} DB'den {len(history)} mesaj yüklendi (hydrate)."
            )