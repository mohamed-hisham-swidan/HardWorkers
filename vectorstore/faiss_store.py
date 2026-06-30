"""Thread-safe FAISS inner-product index with atomic persistence.

Design decisions:
- IndexFlatIP (exact inner-product search after L2 normalisation ≡ cosine).
- Atomic save: write to *.tmp then os.replace() to prevent partial writes.
- Per-operation LRU embedding cache capped at config.cache_size entries.
- Lock guards both the FAISS index and the parallel metadata list.
"""

from __future__ import annotations

import os
import pickle
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

import faiss

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer
import numpy as np

# sentence_transformers imported lazily in _encoder_instance (saves ~30s on startup)
from config.settings import VectorConfig
from models.domain import SearchResult, UserFact
from utils.logging_setup import get_logger

log = get_logger("vectorstore.faiss_store")


class VectorStore:
    _INDEX_FILENAME = "index.faiss"
    _META_FILENAME = "metadata.pkl"

    def __init__(self, config: VectorConfig) -> None:
        self._cfg = config
        self._idx_path = config.index_dir / self._INDEX_FILENAME
        self._meta_path = config.index_dir / self._META_FILENAME

        self._encoder: SentenceTransformer | None = None
        self._index: faiss.Index
        self._meta: list[dict] = []
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()
        self._lock = threading.RLock()

        config.index_dir.mkdir(parents=True, exist_ok=True)
        if not self._load():
            self._index = faiss.IndexFlatIP(config.dimension)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        with self._lock:
            return self._index.ntotal

    def add_fact(self, fact: UserFact) -> None:
        vec = self._encode(fact.to_embedding_text())
        with self._lock:
            self._index.add(vec.reshape(1, -1))
            self._meta.append({"fact_id": fact.id, "key": fact.key, "value": fact.value})
        log.debug("Fact added to index: %r (total=%d)", fact.key, self._index.ntotal)

    def search(
        self,
        query: str,
        limit: int | None = None,
        threshold: float | None = None,
    ) -> list[SearchResult]:
        limit = limit or self._cfg.search_limit
        threshold = threshold if threshold is not None else self._cfg.similarity_threshold

        with self._lock:
            if self._index.ntotal == 0:
                return []
            n = min(limit, self._index.ntotal)

        vec = self._encode(query)
        with self._lock:
            scores, indices = self._index.search(vec.reshape(1, -1), n)

        results: list[SearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or float(score) < threshold or idx >= len(self._meta):
                continue
            m = self._meta[idx]
            results.append(SearchResult(score=float(score), key=m["key"], value=m["value"]))
        return results

    def rebuild(self, facts: list[UserFact]) -> None:
        log.info("Rebuilding vector index from %d facts", len(facts))
        with self._lock:
            self._index = faiss.IndexFlatIP(self._cfg.dimension)
            self._meta = []
        for fact in facts:
            self.add_fact(fact)
        log.info("Vector index rebuilt — %d vectors", self.size)

    def save(self) -> None:
        """Atomically persist index and metadata to disk."""
        tmp_idx = self._idx_path.with_suffix(".faiss.tmp")
        tmp_meta = self._meta_path.with_suffix(".pkl.tmp")
        try:
            with self._lock:
                faiss.write_index(self._index, str(tmp_idx))
                with open(tmp_meta, "wb") as fh:
                    pickle.dump(self._meta, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_idx, self._idx_path)
            os.replace(tmp_meta, self._meta_path)
            log.info("Vector index saved — %d vectors", self.size)
        except Exception as exc:
            log.error("Failed to save vector index: %s", exc)
            for tmp in (tmp_idx, tmp_meta):
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
            raise

    def close(self) -> None:
        with self._lock:
            self._cache.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _encoder_instance(self) -> SentenceTransformer:
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(self._cfg.model_name)
        return self._encoder

    def _encode(self, text: str) -> np.ndarray:
        key = hash(text) & 0xFFFFFFFF
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached

        vec = self._encoder_instance().encode(text, convert_to_tensor=False).astype("float32")
        faiss.normalize_L2(vec.reshape(1, -1))

        with self._lock:
            if len(self._cache) >= self._cfg.cache_size:
                self._cache.popitem(last=False)
            self._cache[key] = vec
        return vec

    def _load(self) -> bool:
        if not self._idx_path.exists() or not self._meta_path.exists():
            return False
        try:
            self._index = faiss.read_index(str(self._idx_path))
            with open(self._meta_path, "rb") as fh:
                self._meta = pickle.load(fh)
            log.info("Vector index loaded — %d vectors", self._index.ntotal)
            return True
        except Exception as exc:
            log.warning("Cannot load vector index (%s) — starting fresh", exc)
            return False
