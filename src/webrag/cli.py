"""CLI do RAG local: index, query, stats, serve, mcp."""

from __future__ import annotations

import argparse
import json
import sys

from .config import Config
from .indexer import build_index
from .store import load_index


def _retriever(cfg: Config):
    from .retriever import Retriever

    index = load_index(cfg.index_dir)
    return Retriever(index, index.manifest["embed_model"])


def cmd_index(cfg: Config, args) -> int:
    build_index(cfg, rebuild=args.rebuild)
    return 0


def cmd_query(cfg: Config, args) -> int:
    hits = _retriever(cfg).search(args.question, top_k=args.top_k, pillar=args.pillar)
    if args.json:
        print(json.dumps([h.to_dict() for h in hits], ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print("Nenhum trecho relevante encontrado.")
        return 1
    for i, hit in enumerate(hits, start=1):
        print(f"\n\033[1m[{i}] {hit.chunk.location}\033[0m  (score {hit.score:.4f})")
        body = hit.chunk.body.strip()
        print(body if args.full else (body[:700] + ("…" if len(body) > 700 else "")))
    print()
    return 0


def cmd_stats(cfg: Config, args) -> int:
    index = load_index(cfg.index_dir)
    m = index.manifest
    print(f"Origem      : {m['source_dir']}")
    print(f"Índice      : {cfg.index_dir}")
    print(f"Modelo      : {m['embed_model']} ({m['dimensions']}d)")
    print(f"Documentos  : {m['documents']}")
    print(f"Chunks      : {m['chunks']}  (~{m['chunk_chars']} chars, overlap {m['chunk_overlap']})")
    print(f"Gerado em   : {m.get('saved_at', '?')}")
    print("Pilares     :")
    for pillar in m["pillars"]:
        count = sum(1 for c in index.chunks if c.pillar == pillar)
        print(f"  - {pillar} ({count} chunks)")
    return 0


def cmd_serve(cfg: Config, args) -> int:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(cfg), host=args.host, port=args.port, log_level="info")
    return 0


def cmd_mcp(cfg: Config, args) -> int:
    from .mcp_server import run

    run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag", description="RAG local sobre o conteúdo de Web Engineer."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="(Re)constrói o índice a partir do vault")
    p_index.add_argument("--rebuild", action="store_true", help="Refaz do zero")
    p_index.set_defaults(func=cmd_index)

    p_query = sub.add_parser("query", help="Busca trechos relevantes (sem LLM)")
    p_query.add_argument("question")
    p_query.add_argument("-k", "--top-k", type=int, default=6)
    p_query.add_argument("-p", "--pillar", help="Filtra por pilar/pasta, ex: 'Performance'")
    p_query.add_argument("--full", action="store_true", help="Mostra o trecho inteiro")
    p_query.add_argument("--json", action="store_true")
    p_query.set_defaults(func=cmd_query)

    p_stats = sub.add_parser("stats", help="Mostra o estado do índice")
    p_stats.set_defaults(func=cmd_stats)

    p_serve = sub.add_parser("serve", help="Sobe a API HTTP + UI web local")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8077)
    p_serve.set_defaults(func=cmd_serve)

    p_mcp = sub.add_parser("mcp", help="Roda o servidor MCP (stdio) para o Claude Code")
    p_mcp.set_defaults(func=cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        cfg = Config.load()
        return args.func(cfg, args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
