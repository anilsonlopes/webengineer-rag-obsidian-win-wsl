"""Persistência do índice: chunks (JSONL) + matriz de embeddings (NPY)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .chunker import Chunk

CHUNKS_FILE = "chunks.jsonl"
VECTORS_FILE = "embeddings.npy"
MANIFEST_FILE = "manifest.json"


@dataclass
class Index:
    chunks: list[Chunk]
    vectors: np.ndarray
    manifest: dict


def save_index(index_dir: Path, chunks: list[Chunk], vectors: np.ndarray,
               manifest: dict) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    with (index_dir / CHUNKS_FILE).open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
    np.save(index_dir / VECTORS_FILE, vectors)
    manifest = {**manifest, "saved_at": datetime.now(timezone.utc).isoformat()}
    (index_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def index_exists(index_dir: Path) -> bool:
    return all((index_dir / name).exists() for name in (CHUNKS_FILE, VECTORS_FILE, MANIFEST_FILE))


def load_index(index_dir: Path) -> Index:
    if not index_exists(index_dir):
        raise FileNotFoundError(
            f"Índice não encontrado em {index_dir}. Rode `rag index` primeiro."
        )
    chunks: list[Chunk] = []
    with (index_dir / CHUNKS_FILE).open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                chunks.append(Chunk(**json.loads(line)))
    vectors = np.load(index_dir / VECTORS_FILE)
    manifest = json.loads((index_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    if len(chunks) != vectors.shape[0]:
        raise ValueError(
            f"Índice inconsistente: {len(chunks)} chunks para {vectors.shape[0]} vetores. "
            "Rode `rag index --rebuild`."
        )
    return Index(chunks=chunks, vectors=vectors, manifest=manifest)
