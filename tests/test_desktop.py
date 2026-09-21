import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from webrag.config import Config


@unittest.skipUnless(sys.platform == "win32", "Windows desktop")
class DesktopTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.folder), "HF_HOME": str(self.folder / "models")})
        self.env.start()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.env.stop)
        self.window = tk.Tk()
        self.window.withdraw()
        self.addCleanup(self.window.destroy)
        from webrag.desktop import Desktop
        self.app = Desktop(self.window)

    def test_first_run_save_and_layout(self):
        self.assertIn("Nenhum índice", self.app.summary.get())
        self.assertIn("não baixado", self.app.model_status.get())
        self.app.fields["source_dir"].set(str(self.folder))
        cfg = self.app.save()
        self.assertEqual(cfg, Config.load(user=True))
        self.app.toggle_advanced()
        self.window.update_idletasks()
        self.assertLessEqual(self.app.frame.winfo_reqwidth(), 800)
        self.assertLessEqual(self.app.frame.winfo_reqheight(), 810)

    def test_background_work_and_cooperative_cancel(self):
        started = threading.Event()
        finished = threading.Event()
        def task():
            started.set()
            self.app.cancel.wait(3)
            finished.set()
        self.app.start(task)
        self.assertTrue(started.wait(2))
        self.assertEqual(str(self.app.search_button["state"]), "disabled")
        self.app.request_cancel()
        self.assertTrue(finished.wait(2))
        deadline = time.monotonic() + 3
        while self.app.worker and time.monotonic() < deadline:
            self.window.update()
            time.sleep(0.02)
        self.assertIsNone(self.app.worker)
        self.assertEqual(str(self.app.search_button["state"]), "normal")


if __name__ == "__main__":
    unittest.main()
