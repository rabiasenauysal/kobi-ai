"""
KOBİ AI Platform — ChromaDB Vector Store
Qdrant yerine ChromaDB kullanır (Docker gerektirmez, deploy'a uygun).
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config.settings import get_settings


class VectorStore:
    """ChromaDB tabanlı vector store — Qdrant'ın drop-in yedeği."""

    def __init__(self):
        self.settings = get_settings()
        self.openai_client = OpenAI(api_key=self.settings.openai_api_key)
        self.collection_name = self.settings.qdrant_collection_name

        import os, shutil, chromadb
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        chroma_path = Path(__file__).parent.parent / "db" / "chroma_db"

        self._client = self._make_client(str(chroma_path), chromadb)
        self._col = self._safe_get_or_create(str(chroma_path), chromadb)
        print(f"✅ ChromaDB VectorStore başlatıldı ({chroma_path})")
        print(f"   Collection: {self.collection_name} — {self._col.count()} doküman")

    def _make_client(self, path: str, chromadb):
        import chromadb as _c
        return _c.PersistentClient(
            path=path,
            settings=_c.Settings(anonymized_telemetry=False),
        )

    def _safe_get_or_create(self, chroma_path: str, chromadb):
        """get_or_create_collection — bozuk DB olursa otomatik sıfırla."""
        import shutil, chromadb as _c
        try:
            return self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except (KeyError, Exception) as e:
            print(f"⚠️  ChromaDB okuma hatası ({e}). Dizin sıfırlanıyor ve yeniden oluşturuluyor…")
            # Bağlantıyı kapat (best-effort)
            try:
                self._client._system.stop()
            except Exception:
                pass
            # Dizini sil
            p = Path(chroma_path)
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
            p.mkdir(parents=True, exist_ok=True)
            # Yeni client + collection
            self._client = _c.PersistentClient(
                path=chroma_path,
                settings=_c.Settings(anonymized_telemetry=False),
            )
            col = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            print("✅ ChromaDB dizini sıfırlandı. Schema yeniden yükleniyor…")
            self._auto_embed()
            return col

    def _auto_embed(self):
        """Boş collection'a schema chunk'larını otomatik yükle."""
        try:
            from services.schema_extractor import SchemaExtractor
            extractor = SchemaExtractor(use_manual_schema=True)
            chunks = extractor.extract_and_chunk()
            all_docs = (
                chunks.get("table_chunks", []) +
                chunks.get("join_chunks", []) +
                chunks.get("pattern_chunks", [])
            )
            if all_docs:
                n = self.add_documents(all_docs)
                print(f"✅ Otomatik re-embed tamamlandı — {n} chunk yüklendi")
        except Exception as e:
            print(f"⚠️  Otomatik re-embed başarısız: {e}. 'python main.py setup' komutunu çalıştırın.")

    # ── Koleksiyon yönetimi ──────────────────────────────────────────────────

    def create_collection(self, vector_size: int = 1536) -> None:
        self._col = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_collection(self) -> None:
        try:
            self._client.delete_collection(self.collection_name)
            print(f"🗑️  Collection '{self.collection_name}' silindi")
        except Exception as e:
            print(f"⚠️  Collection silinemedi: {e}")
        self._col = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Embedding ────────────────────────────────────────────────────────────

    def get_embedding(self, text: str) -> List[float]:
        response = self.openai_client.embeddings.create(
            model=self.settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    # ── Doküman ekleme ───────────────────────────────────────────────────────

    def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        if not documents:
            return 0

        texts, embeddings, ids, metadatas = [], [], [], []

        for doc in documents:
            text = doc.get("description", "")
            if not text:
                continue
            emb = self.get_embedding(text)
            texts.append(text)
            embeddings.append(emb)
            ids.append(str(uuid.uuid4()))
            metadatas.append(doc.get("metadata", {}))

        if texts:
            self._col.add(
                documents=texts,
                embeddings=embeddings,
                ids=ids,
                metadatas=metadatas,
            )
            print(f"✅ {len(texts)} doküman ChromaDB'ye eklendi")

        return len(texts)

    # ── Arama ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if limit is None:
            limit = self.settings.top_k_results

        query_emb = self.get_embedding(query)

        results = self._col.query(
            query_embeddings=[query_emb],
            n_results=min(limit, max(1, self._col.count())),
        )

        docs = []
        if results and results.get("documents"):
            for text, dist, meta in zip(
                results["documents"][0],
                results["distances"][0],
                results["metadatas"][0],
            ):
                docs.append({
                    "text": text,
                    "score": 1.0 - dist,  # cosine distance → similarity
                    "metadata": meta or {},
                })

        return docs

    # ── Bilgi ────────────────────────────────────────────────────────────────

    def get_collection_info(self) -> Dict[str, Any]:
        try:
            return {
                "name": self.collection_name,
                "points_count": self._col.count(),
                "vectors_count": self._col.count(),
                "status": "green",
            }
        except Exception as e:
            return {"error": str(e)}
