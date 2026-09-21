"""Servidor MCP (stdio) que expõe a base Web Engineer como ferramentas.

Registre no Claude Code com:
    claude mcp add web-engineer -- <caminho>/.venv/Scripts/python.exe -m webrag mcp
"""

from __future__ import annotations


try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ModuleNotFoundError:  # mcp 1.x, onde a classe se chamava FastMCP
    from mcp.server.fastmcp import FastMCP as _Server

from . import __version__
from .config import Config
from .index_access import IndexAccess

mcp = _Server(
    "web-engineer-rag",
    instructions=(
        "Base de conhecimento Web Engineer: notas em português sobre acessibilidade, "
        "performance, sustentabilidade, UX engineering, product discovery e qualidade/DX. "
        "Use search_web_engineer antes de responder qualquer pergunta sobre esses temas."
    ),
    version=__version__,
)


_access = IndexAccess(Config.load)
_retriever = _access.get


@mcp.tool()
def search_web_engineer(question: str, top_k: int = 6, pillar: str | None = None) -> str:
    """Busca trechos relevantes na base de conhecimento Web Engineer (notas em português
    sobre acessibilidade, performance, sustentabilidade, UX engineering, product discovery
    e qualidade/DX). Use antes de responder qualquer pergunta sobre esses temas.

    Args:
        question: a pergunta ou tema, em linguagem natural.
        top_k: quantos trechos retornar (padrão 6).
        pillar: filtro opcional por pasta/pilar, ex. "Performance" ou "Acessibilidade".
    """
    hits = _retriever().search(question, top_k=top_k, pillar=pillar)
    if not hits:
        return "Nenhum trecho relevante encontrado."
    return "\n\n---\n\n".join(
        f"[{i}] {hit.chunk.location} (score {hit.score:.4f})\n{hit.chunk.body}"
        for i, hit in enumerate(hits, start=1)
    )


@mcp.tool()
def read_web_engineer_document(rel_path: str) -> str:
    """Devolve o conteúdo completo de um documento da base, pelo caminho relativo
    (ex.: "2. Performance/1. Otimização de imagens.md") retornado por search_web_engineer."""
    retriever = _retriever()
    chunks = [c for c in retriever.index.chunks if c.rel_path == rel_path]
    if not chunks:
        available = sorted({c.rel_path for c in retriever.index.chunks})
        return f"Documento não encontrado: {rel_path}\n\nDisponíveis:\n" + "\n".join(available)
    return f"# {chunks[0].title}\n\n" + "\n\n".join(c.body for c in sorted(chunks, key=lambda c: c.ordinal))


@mcp.tool()
def list_web_engineer_documents() -> str:
    """Lista todos os documentos indexados na base Web Engineer, agrupados por pilar."""
    retriever = _retriever()
    by_pillar: dict[str, set[str]] = {}
    for chunk in retriever.index.chunks:
        by_pillar.setdefault(chunk.pillar, set()).add(chunk.rel_path)
    lines = []
    for pillar in sorted(by_pillar):
        lines.append(f"## {pillar}")
        lines.extend(f"- {path}" for path in sorted(by_pillar[pillar]))
        lines.append("")
    return "\n".join(lines)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
