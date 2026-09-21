"""Development .env and installed per-user configuration."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = r"G:\Meu Drive\ContextDirectory\Web Engineer"
DEFAULT_MODEL = "intfloat/multilingual-e5-small"


def user_data_dir() -> Path:
    base = Path(os.environ["LOCALAPPDATA"]) if "LOCALAPPDATA" in os.environ else Path.home() / ".local" / "share"
    return base / "WebEngineerRAG"


def configure_user_runtime() -> None:
    os.environ.setdefault("HF_HOME", str(user_data_dir() / "models"))


@dataclass(frozen=True)
class Config:
    source_dir: Path | None
    index_dir: Path
    embed_model: str = DEFAULT_MODEL
    chunk_chars: int = 1200
    chunk_overlap: int = 200
    chunk_min: int = 400

    def validate(self, *, require_source: bool = False) -> None:
        if not self.embed_model.strip():
            raise ValueError("Informe o modelo de embeddings.")
        if self.chunk_chars <= 0 or not 0 <= self.chunk_overlap < self.chunk_chars:
            raise ValueError("O tamanho dos trechos deve ser positivo e maior que a sobreposição.")
        if not 0 <= self.chunk_min <= self.chunk_chars:
            raise ValueError("O tamanho mínimo deve estar entre zero e o tamanho dos trechos.")
        if self.source_dir is not None and not self.source_dir.is_absolute():
            raise ValueError("Use um caminho absoluto para a pasta de conteúdo.")
        if require_source and (self.source_dir is None or not self.source_dir.is_dir()):
            raise ValueError("Selecione uma pasta de conteúdo existente e acessível.")
        if not self.index_dir.is_absolute():
            raise ValueError("Use um caminho absoluto para a pasta do índice.")
        if self.source_dir and self.source_dir.resolve() == self.index_dir.resolve():
            raise ValueError("A pasta do índice deve ser diferente da pasta de conteúdo.")

    @classmethod
    def load(cls, *, user: bool | None = None) -> "Config":
        if user is None:
            user = bool(getattr(sys, "frozen", False))
        if user:
            configure_user_runtime()
            path = user_data_dir() / "config.json"
            try:
                values = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(values, dict):
                    raise ValueError("A configuração deve ser um objeto JSON.")
            except FileNotFoundError:
                values = {}
            except (ValueError, OSError) as exc:
                raise ValueError(f"Não foi possível ler {path}: {exc}") from exc
            defaults = {"source_dir": "", "index_dir": str(user_data_dir() / "index")}
        else:
            env = dotenv_values(PROJECT_ROOT / ".env")
            values = {k.removeprefix("WEBRAG_").lower(): v for k, v in env.items() if v is not None}
            defaults = {"source_dir": DEFAULT_SOURCE, "index_dir": str(PROJECT_ROOT / "data" / "index")}
        def setting(name, default):
            return os.environ.get("WEBRAG_" + name.upper(), values.get(name, default))
        source = setting("source_dir", defaults["source_dir"])
        if not isinstance(source, str) or not isinstance(setting("index_dir", defaults["index_dir"]), str):
            raise ValueError("Configuração inválida: as pastas devem ser caminhos em texto.")
        if not isinstance(setting("embed_model", DEFAULT_MODEL), str):
            raise ValueError("Configuração inválida: o modelo deve ser um nome em texto.")
        cfg = cls(
            Path(source).expanduser().absolute() if source else None,
            Path(setting("index_dir", defaults["index_dir"])).expanduser().absolute(),
            str(setting("embed_model", DEFAULT_MODEL)),
            int(setting("chunk_chars", 1200)), int(setting("chunk_overlap", 200)),
            int(setting("chunk_min", 400)),
        )
        cfg.validate()
        return cfg

    def save_user(self) -> None:
        self.validate(require_source=True)
        folder = user_data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        values = asdict(self)
        values.update(source_dir=str(self.source_dir), index_dir=str(self.index_dir))
        fd, temporary = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(values, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, folder / "config.json")
        finally:
            Path(temporary).unlink(missing_ok=True)
