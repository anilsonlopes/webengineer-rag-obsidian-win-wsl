"""Configuração central, lida de variáveis de ambiente / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_SOURCE = r"G:\Meu Drive\ContextDirectory\Web Engineer"


@dataclass(frozen=True)
class Config:
    source_dir: Path
    index_dir: Path
    embed_model: str
    chunk_chars: int
    chunk_overlap: int
    chunk_min: int

    @classmethod
    def load(cls) -> "Config":
        source = os.getenv("WEBRAG_SOURCE_DIR", DEFAULT_SOURCE)
        index = os.getenv("WEBRAG_INDEX_DIR", str(PROJECT_ROOT / "data" / "index"))
        return cls(
            source_dir=Path(source).expanduser(),
            index_dir=Path(index).expanduser(),
            embed_model=os.getenv("WEBRAG_EMBED_MODEL", "intfloat/multilingual-e5-small"),
            chunk_chars=int(os.getenv("WEBRAG_CHUNK_CHARS", "1200")),
            chunk_overlap=int(os.getenv("WEBRAG_CHUNK_OVERLAP", "200")),
            chunk_min=int(os.getenv("WEBRAG_CHUNK_MIN", "400")),
        )
