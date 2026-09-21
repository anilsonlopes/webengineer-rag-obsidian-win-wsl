"""Pipeline de indexação: ler → chunkar → embutir → gravar."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .chunker import chunk_documents
from .config import Config
from .embedder import embed_passages
from .loader import Document, load_documents
from .store import MANIFEST_FILE, index_exists, save_index


def _fingerprint(docs: list[Document]) -> dict[str, str]:
    return {d.rel_path: d.sha1 for d in docs}


def _stored_fingerprint(index_dir: Path) -> dict[str, str] | None:
    try:
        manifest = json.loads((index_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {f["path"]: f["sha1"] for f in manifest.get("files", [])}


def build_index(cfg: Config, rebuild: bool = False, quiet: bool = False) -> dict:
    def log(msg: str) -> None:
        if not quiet:
            print(msg, flush=True)

    started = time.perf_counter()
    log(f"Lendo conteúdo de: {cfg.source_dir}")
    docs = load_documents(cfg.source_dir)
    log(f"  {len(docs)} documento(s) carregado(s)")

    current = _fingerprint(docs)
    if not rebuild and index_exists(cfg.index_dir) and _stored_fingerprint(cfg.index_dir) == current:
        log("Nada mudou desde a última indexação — índice mantido (use --rebuild para forçar).")
        return json.loads((cfg.index_dir / MANIFEST_FILE).read_text(encoding="utf-8"))

    chunks = chunk_documents(docs, cfg.chunk_chars, cfg.chunk_overlap, cfg.chunk_min)
    log(f"  {len(chunks)} chunk(s) gerado(s)")
    if not chunks:
        raise RuntimeError("Nenhum conteúdo indexável encontrado.")

    log(f"Gerando embeddings com {cfg.embed_model} (local)...")
    vectors = embed_passages([c.text for c in chunks], cfg.embed_model, show_progress=not quiet)

    manifest = {
        "source_dir": str(cfg.source_dir),
        "embed_model": cfg.embed_model,
        "dimensions": int(vectors.shape[1]),
        "documents": len(docs),
        "chunks": len(chunks),
        "chunk_chars": cfg.chunk_chars,
        "chunk_overlap": cfg.chunk_overlap,
        "chunk_min": cfg.chunk_min,
        "files": [{"path": d.rel_path, "sha1": d.sha1, "kind": d.kind} for d in docs],
        "pillars": sorted({d.pillar for d in docs}),
    }
    save_index(cfg.index_dir, chunks, vectors, manifest)
    log(f"Índice gravado em {cfg.index_dir} ({time.perf_counter() - started:.1f}s)")
    return manifest
