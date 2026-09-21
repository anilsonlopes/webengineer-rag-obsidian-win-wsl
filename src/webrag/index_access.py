"""Reload published indexes without mixing model and vector generations."""
from threading import Lock
from .store import index_revision, load_index


class IndexAccess:
    def __init__(self, config):
        self.config = config
        self._key = None
        self._retriever = None
        self._lock = Lock()

    def get(self):
        from .retriever import Retriever
        cfg = self.config()
        with self._lock:
            key = (str(cfg.index_dir), index_revision(cfg.index_dir))
            if key != self._key:
                index = load_index(cfg.index_dir)
                self._retriever = Retriever(index, index.manifest["embed_model"])
                self._key = key
            return self._retriever
