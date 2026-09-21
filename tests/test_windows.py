import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np

from webrag.config import Config
from webrag.indexer import build_index
from webrag.index_access import IndexAccess
from webrag.progress import Cancelled
from webrag.store import load_index, read_manifest, save_index, writer_lock


def fake_embeddings(texts, model, **kwargs):
    return np.ones((len(texts), 3), dtype=np.float32)


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "Notas com acentuação"
        self.source.mkdir()
        (self.source / "nota.md").write_text("# Acessibilidade\n\nUse contraste adequado e navegação por teclado.", encoding="utf-8")
        self.cfg = Config(self.source, self.root / "index", "test-model")
        self.embed = patch("webrag.indexer.embed_passages", side_effect=fake_embeddings)
        self.mock = self.embed.start()
        self.addCleanup(self.embed.stop)
        self.addCleanup(self.temp.cleanup)

    def build(self, **kwargs):
        return build_index(self.cfg, quiet=True, **kwargs)

    def test_unchanged_and_all_settings_invalidate(self):
        self.build()
        self.build()
        self.assertEqual(self.mock.call_count, 1)
        for field, value in (("embed_model", "other-model"), ("chunk_chars", 1000),
                             ("chunk_overlap", 100), ("chunk_min", 200)):
            self.cfg = replace(self.cfg, **{field: value})
            self.build()
        other = self.root / "Outra pasta"
        other.mkdir()
        (other / "nota.md").write_bytes((self.source / "nota.md").read_bytes())
        self.cfg = replace(self.cfg, source_dir=other)
        self.build()
        self.assertEqual(self.mock.call_count, 6)

    def test_failure_and_cancel_keep_previous_generation(self):
        self.build()
        previous = (self.cfg.index_dir / "CURRENT").read_text()
        with patch("webrag.store.np.save", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                self.build(rebuild=True)
        self.assertEqual((self.cfg.index_dir / "CURRENT").read_text(), previous)
        cancelled = threading.Event()
        def progress(event):
            if event.stage == "chunking":
                cancelled.set()
        with self.assertRaises(Cancelled):
            self.build(rebuild=True, progress=progress, cancel=cancelled.is_set)
        self.assertEqual((self.cfg.index_dir / "CURRENT").read_text(), previous)
        self.assertEqual(load_index(self.cfg.index_dir).manifest["documents"], 1)

    def test_exclusive_writer_and_recovery(self):
        with writer_lock(self.cfg.index_dir):
            with self.assertRaisesRegex(RuntimeError, "andamento"):
                self.build()
        self.build()

    def test_publication_failure_and_legacy_compatibility(self):
        self.build()
        old = load_index(self.cfg.index_dir)
        with patch("webrag.store.os.replace", side_effect=OSError("publication failed")):
            with self.assertRaises(OSError):
                self.build(rebuild=True)
        self.assertEqual(load_index(self.cfg.index_dir).manifest, old.manifest)
        legacy = self.root / "legacy"
        legacy.mkdir()
        (legacy / "chunks.jsonl").write_text("\n".join(json.dumps(c.to_dict()) for c in old.chunks), encoding="utf-8")
        np.save(legacy / "embeddings.npy", old.vectors)
        (legacy / "manifest.json").write_text(json.dumps(old.manifest), encoding="utf-8")
        self.assertEqual(load_index(legacy).manifest, old.manifest)

    def test_reload_uses_published_model(self):
        self.build()
        access = IndexAccess(lambda: self.cfg)
        first = access.get()
        self.cfg = replace(self.cfg, embed_model="new-model")
        self.assertIs(access.get(), first)
        self.assertEqual(access.get().embed_model, "test-model")
        self.build()
        self.assertIsNot(access.get(), first)
        self.assertEqual(access.get().embed_model, "new-model")

    def test_empty_missing_and_invalid_source(self):
        (self.source / "nota.md").unlink()
        with self.assertRaisesRegex(RuntimeError, "Nenhum conteúdo"):
            self.build()
        self.source.rmdir()
        with self.assertRaises(ValueError):
            self.build()
        with self.assertRaises(ValueError):
            build_index(replace(self.cfg, source_dir=None), quiet=True)

    def test_rebuild_repairs_invalid_pointer(self):
        self.build()
        (self.cfg.index_dir / "CURRENT").write_text("../outside")
        self.build(rebuild=True)
        self.assertEqual(load_index(self.cfg.index_dir).manifest["documents"], 1)

    def test_readers_and_cleanup(self):
        self.build()
        errors = []
        stop = threading.Event()
        def read():
            while not stop.is_set():
                try:
                    self.assertEqual(len(load_index(self.cfg.index_dir).chunks), 1)
                except Exception as exc:
                    errors.append(exc)
        reader = threading.Thread(target=read)
        reader.start()
        try:
            for _ in range(4):
                self.build(rebuild=True)
        finally:
            stop.set()
            reader.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(list((self.cfg.index_dir / "generations").iterdir())), 2)

    def test_http_sees_new_generation(self):
        from fastapi.testclient import TestClient
        from webrag.server import create_app
        self.build()
        with TestClient(create_app(self.cfg)) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/api/stats").json()["documents"], 1)
            (self.source / "extra.md").write_text("# Performance\n\nOtimizar imagens.", encoding="utf-8")
            self.build()
            self.assertEqual(client.get("/api/stats").json()["documents"], 2)
            with patch("webrag.retriever.embed_query", return_value=np.ones((3,), dtype=np.float32)):
                self.assertTrue(client.post("/api/search", json={"question": "imagens"}).json()["hits"])


class ConfigTests(unittest.TestCase):
    def test_user_config_precedence_and_validation(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCALAPPDATA": temporary}, clear=True):
            cfg = Config.load(user=True)
            self.assertIsNone(cfg.source_dir)
            cfg = replace(cfg, source_dir=Path(temporary))
            cfg.save_user()
            self.assertEqual(Config.load(user=True), cfg)
            with patch.dict(os.environ, {"WEBRAG_CHUNK_CHARS": "900"}):
                self.assertEqual(Config.load(user=True).chunk_chars, 900)
            with self.assertRaises(ValueError):
                replace(cfg, chunk_overlap=cfg.chunk_chars).save_user()
            self.assertEqual(Config.load(user=True), cfg)

    def test_corrupt_configuration_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCALAPPDATA": temporary}, clear=True):
            folder = Path(temporary) / "WebEngineerRAG"
            folder.mkdir()
            (folder / "config.json").write_text("not json")
            with self.assertRaisesRegex(ValueError, "config.json"):
                Config.load(user=True)


class EmbeddingTests(unittest.TestCase):
    def test_download_failure_can_be_retried_and_cached_model_is_offline(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock
        from webrag import embedder
        factory = Mock(side_effect=[OSError("missing"), OSError("offline"), OSError("missing"), object()])
        with patch.dict(sys.modules, {"sentence_transformers": SimpleNamespace(SentenceTransformer=factory)}), patch.dict(embedder._MODEL_CACHE, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "conexão"):
                embedder.get_model("retry-model")
            result = embedder.get_model("retry-model")
            self.assertIs(embedder.get_model("retry-model"), result)
            self.assertEqual(factory.call_count, 4)
        factory = Mock(return_value=object())
        with patch.dict(sys.modules, {"sentence_transformers": SimpleNamespace(SentenceTransformer=factory)}), patch.dict(embedder._MODEL_CACHE, {}, clear=True):
            embedder.get_model("offline-model")
            factory.assert_called_once_with("offline-model", local_files_only=True)

    def test_cancel_between_batches(self):
        from webrag.embedder import embed_passages
        from unittest.mock import Mock
        model = Mock()
        model.encode.side_effect = lambda texts, **kw: np.ones((len(texts), 3))
        cancel = threading.Event()
        with patch("webrag.embedder.get_model", return_value=model):
            with self.assertRaises(Cancelled):
                embed_passages(["x"] * 70, "model", progress=lambda _: cancel.set(), cancel=cancel.is_set)
        self.assertEqual(model.encode.call_count, 1)


class ServiceTests(unittest.TestCase):
    def test_port_conflict_does_not_touch_other_service(self):
        from webrag.local_service import LocalService
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            service = LocalService(lambda: None, port=sock.getsockname()[1])
            with self.assertRaisesRegex(RuntimeError, "ocupada"):
                service.start()
            self.assertNotEqual(sock.fileno(), -1)

    def test_start_stop_and_restart(self):
        from webrag.local_service import LocalService
        from urllib.request import urlopen
        with tempfile.TemporaryDirectory() as temporary:
            cfg = Config(None, Path(temporary))
            service = LocalService(lambda: cfg, port=0)
            try:
                url = service.start()
                self.assertEqual(urlopen(url, timeout=3).status, 200)
                self.assertEqual(service.start(), url)
                service.stop()
                self.assertEqual(urlopen(service.start(), timeout=3).status, 200)
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
