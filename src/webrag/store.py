"""Immutable index generations, atomically published; legacy indexes remain readable."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from filelock import FileLock, Timeout

from .chunker import Chunk

CHUNKS_FILE = "chunks.jsonl"
VECTORS_FILE = "embeddings.npy"
MANIFEST_FILE = "manifest.json"


@dataclass
class Index:
    chunks: list[Chunk]
    vectors: np.ndarray
    manifest: dict


def _lock(index_dir: Path, name: str) -> FileLock:
    index_dir.mkdir(parents=True, exist_ok=True)
    return FileLock(str(index_dir / name))


@contextmanager
def writer_lock(index_dir: Path):
    try:
        with _lock(index_dir, ".writer.lock").acquire(timeout=0):
            yield
    except Timeout as exc:
        raise RuntimeError("Já existe uma indexação em andamento nesta pasta.") from exc


def _active_dir(index_dir: Path) -> Path:
    try:
        generation = (index_dir / "CURRENT").read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return index_dir
    if not re.fullmatch(r"[0-9a-f]{32}", generation):
        raise ValueError("Referência do índice inválida. Reconstrua o índice.")
    return index_dir / "generations" / generation


def index_revision(index_dir: Path) -> str:
    with _lock(index_dir, ".publish.lock"):
        active = _active_dir(index_dir)
        stat = (active / MANIFEST_FILE).stat()
        return f"{active}:{stat.st_mtime_ns}:{stat.st_size}"


def read_manifest(index_dir: Path) -> dict:
    with _lock(index_dir, ".publish.lock"):
        return json.loads((_active_dir(index_dir) / MANIFEST_FILE).read_text(encoding="utf-8"))


def _remove_generation(folder: Path, index_dir: Path) -> None:
    # Refuse symlinks/junctions or paths outside the explicitly selected index.
    generations = (index_dir / "generations").resolve()
    if folder.resolve().parent == generations and not folder.is_symlink():
        shutil.rmtree(folder, ignore_errors=True)


def save_index(index_dir: Path, chunks: list[Chunk], vectors: np.ndarray,
               manifest: dict) -> None:
    generation = uuid.uuid4().hex
    folder = index_dir / "generations" / generation
    folder.mkdir(parents=True)
    published = False
    pointer = index_dir / (generation + ".tmp")
    try:
        with (folder / CHUNKS_FILE).open("w", encoding="utf-8") as stream:
            for chunk in chunks:
                stream.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
        np.save(folder / VECTORS_FILE, vectors)
        values = {**manifest, "saved_at": datetime.now(timezone.utc).isoformat()}
        (folder / MANIFEST_FILE).write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        _load_dir(folder)  # Validate the complete generation before publication.
        with pointer.open("w", encoding="ascii") as stream:
            stream.write(generation)
            stream.flush()
            os.fsync(stream.fileno())
        with _lock(index_dir, ".publish.lock"):
            try:
                previous = _active_dir(index_dir)
            except ValueError:
                previous = None  # A forced rebuild can repair a damaged CURRENT pointer.
            os.replace(pointer, index_dir / "CURRENT")
            published = True
            # Readers hold the publication lock while loading; keep one rollback generation.
            for old in (index_dir / "generations").iterdir():
                if old not in (folder, previous) and re.fullmatch(r"[0-9a-f]{32}", old.name):
                    _remove_generation(old, index_dir)
    finally:
        pointer.unlink(missing_ok=True)
        if not published:
            _remove_generation(folder, index_dir)


def index_exists(index_dir: Path) -> bool:
    try:
        with _lock(index_dir, ".publish.lock"):
            active = _active_dir(index_dir)
            return all((active / name).is_file() for name in (CHUNKS_FILE, VECTORS_FILE, MANIFEST_FILE))
    except (OSError, ValueError):
        return False


def _load_dir(folder: Path) -> Index:
    with (folder / CHUNKS_FILE).open(encoding="utf-8") as stream:
        chunks = [Chunk(**json.loads(line)) for line in stream if line.strip()]
    vectors = np.load(folder / VECTORS_FILE, allow_pickle=False)
    manifest = json.loads((folder / MANIFEST_FILE).read_text(encoding="utf-8"))
    if (vectors.ndim != 2 or len(chunks) != vectors.shape[0]
            or vectors.shape[1] != manifest["dimensions"] or not np.isfinite(vectors).all()):
        raise ValueError("Índice inconsistente. Reconstrua o índice.")
    return Index(chunks, vectors, manifest)


def load_index(index_dir: Path) -> Index:
    with _lock(index_dir, ".publish.lock"):
        try:
            return _load_dir(_active_dir(index_dir))
        except FileNotFoundError as exc:
            raise FileNotFoundError("Índice não encontrado. Use o aplicativo ou rode 'rag index' primeiro.") from exc
