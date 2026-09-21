"""Embeddings locais via sentence-transformers (família E5, multilíngue)."""

from __future__ import annotations

import logging
import os

# Silencia barras de progresso e telemetria do Hugging Face antes de qualquer import pesado.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

from .progress import checkpoint, report

_MODEL_CACHE: dict[str, object] = {}

# Bibliotecas que logam em nível INFO a cada carga do modelo. Além do ruído, isso é
# perigoso no servidor MCP: stdout precisa carregar só o protocolo JSON-RPC.
_NOISY_LOGGERS = (
    "httpx", "httpcore", "urllib3", "filelock",
    "huggingface_hub", "transformers", "sentence_transformers",
)


def _quiet() -> None:
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)


def _needs_e5_prefix(model_name: str) -> bool:
    return "e5" in model_name.lower()


def get_model(model_name: str, *, progress=None, cancel=None):
    """Carrega (e memoiza) o modelo.

    Tenta primeiro o cache local: sem isso, o sentence-transformers revalida cada
    arquivo contra o Hugging Face a toda carga — dezenas de requisições HTTP que
    tornam cada consulta lenta e dependente de rede. Só cai para o download online
    quando o modelo ainda não foi baixado.
    """
    checkpoint(cancel)
    report(progress, "model", "Verificando modelo local…")
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]

    _quiet()
    from sentence_transformers import SentenceTransformer

    _quiet()
    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except OSError:
        checkpoint(cancel)
        report(progress, "download", "Baixando modelo. É necessária internet; o cancelamento será aplicado após esta etapa.")
        try:
            model = SentenceTransformer(model_name)
        except OSError as exc:
            raise RuntimeError("Não foi possível baixar o modelo. Verifique a conexão e tente novamente.") from exc

    checkpoint(cancel)
    _MODEL_CACHE[model_name] = model
    return model


def embed_passages(texts: list[str], model_name: str, batch_size: int = 32,
                   show_progress: bool = True, *, progress=None, cancel=None) -> np.ndarray:
    model = get_model(model_name, progress=progress, cancel=cancel)
    if _needs_e5_prefix(model_name):
        texts = [f"passage: {t}" for t in texts]
    batches = []
    for start in range(0, len(texts), batch_size):
        checkpoint(cancel)
        batch = model.encode(texts[start:start + batch_size], batch_size=batch_size,
                             convert_to_numpy=True, normalize_embeddings=True,
                             show_progress_bar=show_progress and progress is None)
        batches.append(batch)
        done = min(start + batch_size, len(texts))
        report(progress, "embedding", f"Gerando embeddings: {done}/{len(texts)} trechos", done, len(texts))
    checkpoint(cancel)
    return np.concatenate(batches).astype(np.float32)


def embed_query(text: str, model_name: str) -> np.ndarray:
    model = get_model(model_name)
    if _needs_e5_prefix(model_name):
        text = f"query: {text}"
    vector = model.encode(
        [text], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
    )
    return vector.astype(np.float32)[0]


def model_status(model_name: str) -> str:
    if model_name in _MODEL_CACHE:
        return "Modelo verificado e pronto para uso offline."
    from huggingface_hub import try_to_load_from_cache
    cached = try_to_load_from_cache(model_name, "config.json")
    if isinstance(cached, str):
        return "Cache do modelo encontrado; será verificado antes do uso."
    return "Modelo ainda não baixado. A primeira indexação fará o download."
