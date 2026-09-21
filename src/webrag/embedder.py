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


def get_model(model_name: str):
    """Carrega (e memoiza) o modelo.

    Tenta primeiro o cache local: sem isso, o sentence-transformers revalida cada
    arquivo contra o Hugging Face a toda carga — dezenas de requisições HTTP que
    tornam cada consulta lenta e dependente de rede. Só cai para o download online
    quando o modelo ainda não foi baixado.
    """
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]

    _quiet()
    from sentence_transformers import SentenceTransformer

    _quiet()
    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except Exception:  # 1o uso, cache limpo ou modelo trocado no .env
        model = SentenceTransformer(model_name)

    _MODEL_CACHE[model_name] = model
    return model


def embed_passages(texts: list[str], model_name: str, batch_size: int = 32,
                   show_progress: bool = True) -> np.ndarray:
    model = get_model(model_name)
    if _needs_e5_prefix(model_name):
        texts = [f"passage: {t}" for t in texts]
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=show_progress,
    )
    return vectors.astype(np.float32)


def embed_query(text: str, model_name: str) -> np.ndarray:
    model = get_model(model_name)
    if _needs_e5_prefix(model_name):
        text = f"query: {text}"
    vector = model.encode(
        [text], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
    )
    return vector.astype(np.float32)[0]
