"""Busca híbrida: densa (embeddings) + léxica (BM25), fundidas por RRF."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .chunker import Chunk
from .embedder import embed_query
from .store import Index

TOKEN_RE = re.compile(r"[0-9a-z]+")

# Stopwords PT/EN mínimas — só o que realmente polui BM25.
STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e", "em",
    "essa", "esse", "esta", "este", "eu", "for", "isso", "ja", "mais", "mas", "na",
    "nas", "no", "nos", "num", "numa", "o", "os", "ou", "para", "pela", "pelo", "por",
    "que", "se", "sem", "ser", "seu", "sua", "tem", "um", "uma", "and", "for", "from",
    "in", "is", "of", "on", "that", "the", "to", "with",
}


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return [t for t in TOKEN_RE.findall(stripped) if t not in STOPWORDS and len(t) > 1]


class BM25:
    """BM25 Okapi — implementação enxuta, suficiente para corpora pequenos."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_freqs = [Counter(doc) for doc in corpus]
        self.doc_lens = np.array([len(doc) for doc in corpus], dtype=np.float32)
        self.avg_len = float(self.doc_lens.mean()) if len(corpus) else 0.0
        n = len(corpus)
        df: Counter[str] = Counter()
        for doc in corpus:
            df.update(set(doc))
        self.idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        out = np.zeros(len(self.doc_freqs), dtype=np.float32)
        if not self.avg_len:
            return out
        norm = self.k1 * (1 - self.b + self.b * self.doc_lens / self.avg_len)
        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            tf = np.array([freqs.get(term, 0) for freqs in self.doc_freqs], dtype=np.float32)
            out += idf * (tf * (self.k1 + 1)) / (tf + norm)
        return out


@dataclass
class Hit:
    chunk: Chunk
    score: float
    dense_rank: int | None
    lexical_rank: int | None

    def to_dict(self) -> dict:
        return {
            "id": self.chunk.id,
            "score": round(self.score, 5),
            "location": self.chunk.location,
            "rel_path": self.chunk.rel_path,
            "title": self.chunk.title,
            "pillar": self.chunk.pillar,
            "heading_path": self.chunk.heading_path,
            "text": self.chunk.body,
        }


class Retriever:
    def __init__(self, index: Index, embed_model: str):
        self.index = index
        self.embed_model = embed_model
        self._bm25 = BM25([tokenize(c.text) for c in index.chunks])
        self._by_doc: dict[str, list[int]] = {}
        for i, chunk in enumerate(index.chunks):
            self._by_doc.setdefault(chunk.rel_path, []).append(i)

    def search(self, query: str, top_k: int = 6, pillar: str | None = None,
               rrf_k: int = 60, pool: int = 40) -> list[Hit]:
        dense = self.index.vectors @ embed_query(query, self.embed_model)
        lexical = self._bm25.scores(tokenize(query))

        allowed = None
        if pillar:
            needle = pillar.lower()
            allowed = {
                i for i, c in enumerate(self.index.chunks)
                if needle in c.pillar.lower() or needle in c.rel_path.lower()
            }
            if not allowed:
                return []

        def ranked(scores: np.ndarray) -> list[int]:
            order = np.argsort(-scores)
            if allowed is not None:
                order = [i for i in order if i in allowed]
            return [int(i) for i in order[:pool] if scores[i] > 0]

        dense_order = ranked(dense)
        lexical_order = ranked(lexical)
        dense_rank = {idx: r for r, idx in enumerate(dense_order)}
        lexical_rank = {idx: r for r, idx in enumerate(lexical_order)}

        fused: dict[int, float] = {}
        for ranks in (dense_rank, lexical_rank):
            for idx, rank in ranks.items():
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)

        best = sorted(fused.items(), key=lambda kv: -kv[1])[:top_k]
        return [
            Hit(
                chunk=self.index.chunks[idx],
                score=score,
                dense_rank=dense_rank.get(idx),
                lexical_rank=lexical_rank.get(idx),
            )
            for idx, score in best
        ]

    def neighbors(self, chunk: Chunk, window: int = 1) -> list[Chunk]:
        """Chunks vizinhos do mesmo arquivo — dão contexto ao redor do trecho."""
        siblings = self._by_doc.get(chunk.rel_path, [])
        position = next(
            (p for p, i in enumerate(siblings) if self.index.chunks[i].id == chunk.id), None
        )
        if position is None:
            return [chunk]
        lo = max(0, position - window)
        hi = min(len(siblings), position + window + 1)
        return [self.index.chunks[i] for i in siblings[lo:hi]]
