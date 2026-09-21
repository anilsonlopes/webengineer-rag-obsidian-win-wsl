"""Indexing pipeline shared by CLI and desktop."""
from __future__ import annotations

from .chunker import chunk_document
from .config import Config
from .embedder import embed_passages
from .loader import load_documents
from .progress import CancelCallback, ProgressCallback, checkpoint, report
from .store import index_exists, read_manifest, save_index, writer_lock


def index_settings(cfg: Config) -> dict:
    return {"source_dir": str(cfg.source_dir.resolve()) if cfg.source_dir else "",
            "embed_model": cfg.embed_model, "chunk_chars": cfg.chunk_chars,
            "chunk_overlap": cfg.chunk_overlap, "chunk_min": cfg.chunk_min}


def build_index(cfg: Config, rebuild: bool = False, quiet: bool = False,
                progress: ProgressCallback | None = None,
                cancel: CancelCallback | None = None) -> dict:
    cfg.validate(require_source=True)
    def emit(event):
        if not quiet:
            print(event.message, flush=True)
        if progress:
            progress(event)
    with writer_lock(cfg.index_dir):
        checkpoint(cancel)
        report(emit, "reading", f"Lendo conteúdo de: {cfg.source_dir}")
        docs = load_documents(cfg.source_dir, progress=emit, cancel=cancel)
        checkpoint(cancel)
        current = {d.rel_path: d.sha1 for d in docs}
        settings = index_settings(cfg)
        if not rebuild and index_exists(cfg.index_dir):
            previous = read_manifest(cfg.index_dir)
            if (all(previous.get(k) == v for k, v in settings.items())
                    and {f["path"]: f["sha1"] for f in previous.get("files", [])} == current):
                report(emit, "done", "Nada mudou desde a última indexação — índice mantido.")
                return previous
        chunks = []
        for i, doc in enumerate(docs):
            checkpoint(cancel)
            chunks.extend(chunk_document(doc, cfg.chunk_chars, cfg.chunk_overlap, cfg.chunk_min))
            report(emit, "chunking", f"Dividindo documentos: {i + 1}/{len(docs)}", i + 1, len(docs))
        if not chunks:
            raise RuntimeError("Nenhum conteúdo indexável encontrado. Selecione uma pasta com Markdown ou PDFs com texto.")
        vectors = embed_passages([c.text for c in chunks], cfg.embed_model,
                                 show_progress=not quiet, progress=emit, cancel=cancel)
        checkpoint(cancel)
        manifest = {**settings, "dimensions": int(vectors.shape[1]), "documents": len(docs),
                    "chunks": len(chunks),
                    "files": [{"path": d.rel_path, "sha1": d.sha1, "kind": d.kind} for d in docs],
                    "pillars": sorted({d.pillar for d in docs})}
        report(emit, "saving", "Gravando e validando o índice…")
        save_index(cfg.index_dir, chunks, vectors, manifest)
        report(emit, "done", f"Índice concluído: {len(docs)} documentos, {len(chunks)} trechos.")
        return read_manifest(cfg.index_dir)
