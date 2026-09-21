"""Chunking consciente da estrutura Markdown (quebra por cabeçalhos)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .loader import Document

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Chunk:
    id: str
    rel_path: str
    title: str
    pillar: str
    kind: str
    heading_path: list[str]
    ordinal: int  # posição do chunk dentro do documento
    text: str  # texto embutido (inclui a trilha de cabeçalhos)
    body: str  # apenas o corpo, sem a trilha

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def location(self) -> str:
        trail = " › ".join(self.heading_path)
        return f"{self.rel_path}" + (f" › {trail}" if trail else "")


def split_sections(text: str) -> list[tuple[list[str], str]]:
    """Divide o Markdown em (trilha de cabeçalhos, corpo)."""
    sections: list[tuple[list[str], str]] = []
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(([title for _, title in stack], body))
        buffer.clear()

    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        match = None if in_fence else HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, match.group(2)))
        else:
            buffer.append(line)

    flush()
    return sections


def coalesce_sections(sections: list[tuple[list[str], str]], min_chars: int,
                      max_chars: int) -> list[tuple[list[str], str]]:
    """Funde seções curtas com as seguintes.

    Notas em Obsidian têm muitos cabeçalhos com uma ou duas linhas embaixo — por
    exemplo um "### Core Web Vitals" seguido só de "Métricas essenciais do Google:".
    Isoladas, essas seções viram chunks sem informação suficiente para recuperar
    nada útil; fundidas com o que vem a seguir, viram um trecho respondível.
    """
    out: list[tuple[list[str], str]] = []
    path: list[str] | None = None
    parts: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal path, parts, size
        if path is not None:
            out.append((path, "\n\n".join(parts).strip()))
        path, parts, size = None, [], 0

    for section_path, body in sections:
        if path is None:
            path, parts, size = section_path, [body], len(body)
            continue
        if size < min_chars and size + len(body) <= max_chars:
            label = section_path[-1] if section_path else ""
            parts.append(f"**{label}**\n\n{body}" if label else body)
            size += len(body)
            continue
        flush()
        path, parts, size = section_path, [body], len(body)

    flush()
    return out


def _windows(body: str, max_chars: int, overlap: int) -> list[str]:
    """Quebra um corpo longo em janelas com sobreposição, respeitando parágrafos."""
    if len(body) <= max_chars:
        return [body]

    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    out: list[str] = []
    current: list[str] = []
    size = 0

    def emit() -> None:
        nonlocal current, size
        if current:
            out.append("\n\n".join(current).strip())
        current, size = [], 0

    for para in paragraphs:
        # Parágrafo isolado maior que a janela: fatia bruta com sobreposição.
        if len(para) > max_chars:
            emit()
            step = max(max_chars - overlap, 1)
            for start in range(0, len(para), step):
                out.append(para[start : start + max_chars].strip())
            continue

        if size + len(para) > max_chars and current:
            emit()
            # Reinjeta o final do chunk anterior como contexto.
            tail = out[-1][-overlap:] if overlap and out else ""
            if tail:
                current, size = [tail], len(tail)

        current.append(para)
        size += len(para) + 2

    emit()
    return [c for c in out if c.strip()]


def chunk_document(doc: Document, max_chars: int, overlap: int,
                   min_chars: int = 400) -> list[Chunk]:
    chunks: list[Chunk] = []
    sections = coalesce_sections(split_sections(doc.text), min_chars, max_chars)
    for heading_path, body in sections:
        for window in _windows(body, max_chars, overlap):
            ordinal = len(chunks)
            trail = " › ".join([doc.title, *heading_path])
            chunks.append(
                Chunk(
                    id=f"{doc.rel_path}#{ordinal}",
                    rel_path=doc.rel_path,
                    title=doc.title,
                    pillar=doc.pillar,
                    kind=doc.kind,
                    heading_path=heading_path,
                    ordinal=ordinal,
                    text=f"{trail}\n\n{window}",
                    body=window,
                )
            )
    return chunks


def chunk_documents(docs: list[Document], max_chars: int, overlap: int,
                    min_chars: int = 400) -> list[Chunk]:
    out: list[Chunk] = []
    for doc in docs:
        out.extend(chunk_document(doc, max_chars, overlap, min_chars))
    return out
