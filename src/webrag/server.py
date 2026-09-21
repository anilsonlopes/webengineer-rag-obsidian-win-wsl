"""API HTTP local + UI web estática."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import Config
from .store import load_index

WEB_DIR = Path(__file__).parent / "web"


class SearchRequest(BaseModel):
    question: str
    top_k: int = 6
    pillar: str | None = None


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Web Engineer RAG", version="0.1.0")

    @lru_cache(maxsize=1)
    def retriever():
        from .retriever import Retriever

        return Retriever(load_index(cfg.index_dir), cfg.embed_model)

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/stats")
    def stats() -> dict:
        manifest = dict(retriever().index.manifest)
        manifest.pop("files", None)
        return manifest

    @app.post("/api/search")
    def search(req: SearchRequest) -> dict:
        if not req.question.strip():
            raise HTTPException(400, "Pergunta vazia.")
        hits = retriever().search(req.question, top_k=req.top_k, pillar=req.pillar)
        return {"hits": [h.to_dict() for h in hits]}

    return app
