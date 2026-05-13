"""
KOBİ AI Platform — Schema Extraction & Qdrant Yükleme Servisi

3 KATMANLI RAG CHUNK STRATEJİSİ:
  1. Tablo chunk'ları (34 tablo × 1 chunk = 34 chunk)
     → Tablo ne işe yarar, hangi kolonlar var, nasıl filtrelenir
  2. JOIN chunk'ları (17 ilişki × 1 chunk = 17 chunk)
     → Tablolar arasında nasıl JOIN yapılır
  3. Query pattern chunk'ları (11 sorgu şablonu)
     → Sık sorulan sorular için hazır SQL şablonları
  
  TOPLAM: ~62 chunk → Qdrant'a yüklenir

Bu sayede "kanal bazlı ciro" sorusu geldiğinde Qdrant:
  - SIPARISLER tablo chunk'ını bulur (sip_eticaret_kanal_kodu)
  - STOK_HAREKETLERI tablo chunk'ını bulur (sth_tutar, sth_cins=8)
  - JOIN chunk'ını bulur (sip_Guid = sth_sip_uid)
  - Kanal ciro query pattern chunk'ını bulur
"""

from typing import List, Dict, Any
from services.manual_schema import (
    ManualSchemaGraph,
    generate_manual_join_chunks,
    generate_manual_table_chunks,
    generate_query_pattern_chunks,
    ALL_TABLES,
    PRIMARY_TABLES,
)
from config.settings import get_settings


class SchemaExtractor:
    """Veritabanı şemasını chunk'lara çevirir ve Qdrant'a hazırlar."""

    def __init__(self, use_manual_schema: bool = True):
        self.settings = get_settings()
        self.use_manual = use_manual_schema
        self.target_tables = ALL_TABLES
        self.main_table = "SIPARISLER"

        print(f"✅ SchemaExtractor başlatıldı (3 katmanlı RAG)")
        print(f"   Mod: {'Manuel İlişkiler' if use_manual_schema else 'SQLAlchemy Reflection'}")
        print(f"   Tablo: {len(PRIMARY_TABLES)} birincil + {len(ALL_TABLES)-len(PRIMARY_TABLES)} referans = {len(ALL_TABLES)} toplam")

    def extract_and_chunk(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        3 katmanlı chunk üretimi.

        Returns:
            {
                "table_chunks":   [...],  # Tablo açıklamaları
                "join_chunks":    [...],  # JOIN yolları
                "pattern_chunks": [...],  # Sorgu şablonları
            }
        """
        print(f"\n🔍 Schema chunk'ları hazırlanıyor...")

        if self.use_manual:
            # KATMAN 1: Tablo chunk'ları
            table_docs = generate_manual_table_chunks(
                tables=self.target_tables,
                main_table=self.main_table,
            )
            print(f"   ✓ {len(table_docs)} tablo chunk'ı")

            # KATMAN 2: JOIN chunk'ları
            join_docs = generate_manual_join_chunks(
                tables=self.target_tables,
                main_table=self.main_table,
            )
            print(f"   ✓ {len(join_docs)} JOIN chunk'ı")

            # KATMAN 3: Query pattern chunk'ları
            pattern_docs = generate_query_pattern_chunks()
            print(f"   ✓ {len(pattern_docs)} query pattern chunk'ı")

        else:
            # SQLAlchemy reflection modu (FK'lı DB'ler için)
            from utils.join_chunking import (
                extract_schema, build_schema_graph,
                generate_join_chunks, table_descriptions,
            )
            metadata = extract_schema(
                self.settings.sqlalchemy_connection_string,
                tables=self.target_tables,
            )
            table_docs   = table_descriptions(metadata, main_table=self.main_table)
            join_docs    = generate_join_chunks(build_schema_graph(metadata), main_table=self.main_table)
            pattern_docs = generate_query_pattern_chunks()
            print(f"   ✓ {len(table_docs)} tablo, {len(join_docs)} JOIN, {len(pattern_docs)} pattern")

        table_chunks   = self._format_table_chunks(table_docs)
        join_chunks    = self._format_join_chunks(join_docs)
        pattern_chunks = self._format_pattern_chunks(pattern_docs)

        total = len(table_chunks) + len(join_chunks) + len(pattern_chunks)
        print(f"   📦 TOPLAM: {total} chunk → Qdrant'a yüklenecek")

        return {
            "table_chunks":   table_chunks,
            "join_chunks":    join_chunks,
            "pattern_chunks": pattern_chunks,
        }

    def _format_table_chunks(self, table_docs: List[Dict]) -> List[Dict[str, Any]]:
        chunks = []
        for doc in table_docs:
            chunks.append({
                "description": doc["description"],
                "metadata": {
                    "type":           doc["type"],
                    "table_name":     doc["table_name"],
                    "columns":        ",".join(doc.get("columns", [])),
                    "chunk_category": "table_description",
                },
            })
        return chunks

    def _format_join_chunks(self, join_docs: List[Dict]) -> List[Dict[str, Any]]:
        chunks = []
        for doc in join_docs:
            chunks.append({
                "description": doc["description"],
                "metadata": {
                    "type":           doc["type"],
                    "source_table":   doc["source_table"],
                    "target_table":   doc["target_table"],
                    "path":           ",".join(doc["path"]),
                    "chunk_category": "join_path",
                },
            })
        return chunks

    def _format_pattern_chunks(self, pattern_docs: List[Dict]) -> List[Dict[str, Any]]:
        chunks = []
        for doc in pattern_docs:
            chunks.append({
                "description": doc["description"],
                "metadata": {
                    "type":           "query_pattern",
                    "source_table":   doc.get("source_table", ""),
                    "target_table":   doc.get("target_table", ""),
                    "chunk_category": "query_pattern",
                },
            })
        return chunks

    def print_summary(self, chunks_dict: Dict[str, List]):
        print("\n" + "=" * 70)
        print("📋 CHUNK ÖZETİ")
        print("=" * 70)
        print(f"\nTablo chunk'ları    : {len(chunks_dict['table_chunks'])}")
        print(f"JOIN chunk'ları     : {len(chunks_dict['join_chunks'])}")
        print(f"Pattern chunk'ları  : {len(chunks_dict.get('pattern_chunks', []))}")
        total = sum(len(v) for v in chunks_dict.values())
        print(f"TOPLAM              : {total}")

        print("\n🔹 TABLO CHUNK ÖRNEĞİ (ilk 3):")
        for i, c in enumerate(chunks_dict["table_chunks"][:3], 1):
            print(f"\n{i}. {c['metadata']['table_name']} [{c['metadata']['type']}]")
            print(f"   {c['description'][:120]}...")

        print("\n🔹 JOIN CHUNK ÖRNEĞİ (ilk 5):")
        for i, c in enumerate(chunks_dict["join_chunks"][:5], 1):
            print(f"\n{i}. {c['metadata']['source_table']} → {c['metadata']['target_table']}")
            print(f"   {c['description'][:100]}...")

        print("\n🔹 PATTERN CHUNK ÖRNEĞİ (ilk 3):")
        for i, c in enumerate(chunks_dict.get("pattern_chunks", [])[:3], 1):
            print(f"\n{i}. {c['metadata']['source_table']}")
            print(f"   {c['description'][:100]}...")

        print("\n" + "=" * 70)


if __name__ == "__main__":
    from config.settings import print_config
    print("🚀 Schema Extraction Test — 3 Katmanlı RAG")
    print_config()
    extractor = SchemaExtractor()
    chunks = extractor.extract_and_chunk()
    extractor.print_summary(chunks)