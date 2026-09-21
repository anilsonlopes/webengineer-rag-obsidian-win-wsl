"""Leitura do vault: Markdown (Obsidian) e PDF."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules", "__pycache__"}
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Document:
    rel_path: str
    abs_path: Path
    title: str
    pillar: str
    text: str
    kind: str  # "md" | "pdf"
    sha1: str


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def _strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def _read_markdown(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return _strip_frontmatter(raw).strip()


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            content = page.extract_text() or ""
        except Exception:  # página corrompida não deve derrubar a indexação
            content = ""
        content = content.strip()
        if content:
            pages.append(f"## Página {i}\n\n{content}")
    return "\n\n".join(pages)


def load_documents(source_dir: Path) -> list[Document]:
    """Percorre o diretório e devolve todos os documentos legíveis."""
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Diretório de origem não encontrado: {source_dir}")

    docs: list[Document] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(source_dir).parts):
            continue

        suffix = path.suffix.lower()
        if suffix == ".md":
            text, kind = _read_markdown(path), "md"
        elif suffix == ".pdf":
            text, kind = _read_pdf(path), "pdf"
        else:
            continue

        if not text.strip():
            continue

        rel = path.relative_to(source_dir).as_posix()
        parts = rel.split("/")
        pillar = parts[0] if len(parts) > 1 else "(raiz)"
        docs.append(
            Document(
                rel_path=rel,
                abs_path=path,
                title=path.stem,
                pillar=pillar,
                text=text,
                kind=kind,
                sha1=_sha1(text),
            )
        )
    return docs
