"""Portuguese desktop setup wizard; all long-running work stays off the Tk thread."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .config import Config, configure_user_runtime, user_data_dir
from .local_service import LocalService
from .progress import Cancelled, Progress


class Desktop:
    def __init__(self, window: tk.Tk):
        self.window = window
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.closing = False
        self.service = LocalService(lambda: Config.load(user=True))
        window.title("Web Engineer RAG")
        window.geometry("800x640")
        window.minsize(720, 600)
        window.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(window)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        self.frame = ttk.Frame(window, padding=24)
        self.frame.pack(fill="both", expand=True)
        ttk.Label(self.frame, text="Sua base de conhecimento, local.", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.frame, text="Escolha o conteúdo, prepare o modelo e crie seu índice de busca.", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 16))
        try:
            cfg = Config.load(user=True)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Configuração inválida", str(exc), parent=window)
            cfg = Config(None, user_data_dir() / "index")
        self.fields = {name: tk.StringVar(value=str(getattr(cfg, name) or ""))
                       for name in ("source_dir", "index_dir", "embed_model", "chunk_chars", "chunk_overlap", "chunk_min")}
        self.controls = []
        source = ttk.LabelFrame(self.frame, text="1. Pasta de conteúdo", padding=12)
        source.pack(fill="x")
        self.entry(source, "source_dir", browse=True)
        ttk.Label(source, text="Notas Markdown e PDFs com texto. Os arquivos originais não são alterados.").pack(anchor="w", pady=(6, 0))
        self.advanced = ttk.LabelFrame(self.frame, text="Opções avançadas", padding=12)
        toggle = ttk.Button(self.frame, text="Mostrar / ocultar opções avançadas", command=self.toggle_advanced)
        toggle.pack(anchor="w", pady=8)
        self.controls.append(toggle)
        for label, name in (("Pasta do índice", "index_dir"), ("Modelo", "embed_model")):
            ttk.Label(self.advanced, text=label).pack(anchor="w")
            self.entry(self.advanced, name, browse=name == "index_dir")
        row = ttk.Frame(self.advanced)
        row.pack(fill="x", pady=(8, 0))
        for label, name in (("Tamanho", "chunk_chars"), ("Sobreposição", "chunk_overlap"), ("Mínimo", "chunk_min")):
            ttk.Label(row, text=label).pack(side="left", padx=(0, 5))
            entry = ttk.Entry(row, textvariable=self.fields[name], width=8)
            entry.pack(side="left", padx=(0, 12))
            self.controls.append(entry)
        self.action_frame = ttk.LabelFrame(self.frame, text="2. Preparar e indexar", padding=12)
        self.action_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(self.action_frame, text="O modelo precisa de internet apenas no primeiro download.").pack(anchor="w")
        self.model_status = tk.StringVar(value="Modelo ainda não verificado.")
        ttk.Label(self.action_frame, textvariable=self.model_status).pack(anchor="w", pady=(4, 0))
        buttons = ttk.Frame(self.action_frame)
        buttons.pack(fill="x", pady=(10, 0))
        for label, command in (("Salvar configuração", self.save), ("Baixar / verificar modelo", self.download),
                               ("Atualizar índice", self.index), ("Reconstruir", lambda: self.index(True))):
            button = ttk.Button(buttons, text=label, command=command)
            button.pack(side="left", padx=(0, 6))
            self.controls.append(button)
        self.status = tk.StringVar(value="Selecione a pasta de conteúdo para começar.")
        ttk.Label(self.frame, textvariable=self.status, wraplength=710).pack(anchor="w", pady=(0, 6))
        self.bar = ttk.Progressbar(self.frame, mode="indeterminate")
        self.bar.pack(fill="x")
        self.summary = tk.StringVar()
        ttk.Label(self.frame, textvariable=self.summary, wraplength=710).pack(anchor="w", pady=12)
        footer = ttk.Frame(self.frame)
        footer.pack(fill="x", side="bottom")
        self.search_button = ttk.Button(footer, text="3. Abrir busca", command=self.search)
        self.search_button.pack(side="left")
        self.controls.append(self.search_button)
        ttk.Button(footer, text="Abrir logs", command=self.open_logs).pack(side="left", padx=8)
        self.cancel_button = ttk.Button(footer, text="Cancelar", command=self.request_cancel, state="disabled")
        self.cancel_button.pack(side="right")
        overrides = [name for name in self.fields if "WEBRAG_" + name.upper() in os.environ]
        if overrides:
            self.status.set("Variáveis de ambiente têm prioridade: " + ", ".join(overrides))
        self.refresh()
        window.after(100, self.poll)

    def entry(self, parent, name, browse=False):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        entry = ttk.Entry(row, textvariable=self.fields[name])
        entry.pack(side="left", fill="x", expand=True)
        self.controls.append(entry)
        if browse:
            def choose():
                selected = filedialog.askdirectory(parent=self.window, title="Selecionar pasta", mustexist=True)
                if selected:
                    self.fields[name].set(selected)
            button = ttk.Button(row, text="Selecionar…", command=choose)
            button.pack(side="right", padx=(8, 0))
            self.controls.append(button)

    def toggle_advanced(self):
        if self.advanced.winfo_manager():
            self.advanced.pack_forget()
            self.window.geometry("800x640")
        else:
            self.advanced.pack(fill="x", before=self.action_frame, pady=(0, 12))
            self.window.geometry("800x810")

    def save(self):
        try:
            values = {name: value.get().strip() for name, value in self.fields.items()}
            if not values["source_dir"] or not values["index_dir"]:
                raise ValueError("Informe as pastas de conteúdo e do índice.")
            cfg = Config(Path(values["source_dir"]).expanduser(), Path(values["index_dir"]).expanduser(),
                         values["embed_model"], int(values["chunk_chars"]),
                         int(values["chunk_overlap"]), int(values["chunk_min"]))
            cfg.save_user()
            effective = Config.load(user=True)
            effective.validate(require_source=True)
            for name, field in self.fields.items():
                field.set(str(getattr(effective, name) or ""))
            self.status.set("Configuração salva. Próximo passo: atualizar o índice.")
            self.refresh()
            return effective
        except (ValueError, OSError) as exc:
            messagebox.showerror("Revisar configuração", str(exc), parent=self.window)
            return None

    def start(self, operation):
        if self.worker:
            return
        self.cancel.clear()
        for widget in self.controls:
            widget.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        def work():
            try:
                operation()
            except Cancelled as exc:
                self.events.put(("cancelled", str(exc)))
            except Exception as exc:
                logging.exception("Falha na operação")
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("finished", None))
        self.worker = threading.Thread(target=work, daemon=False)
        self.worker.start()

    def download(self):
        cfg = self.save()
        if cfg:
            def operation():
                from .embedder import get_model
                get_model(cfg.embed_model, progress=self.events.put, cancel=self.cancel.is_set)
                self.events.put(("message", "Modelo pronto para uso offline. Atualize o índice para continuar."))
            self.start(operation)

    def index(self, rebuild=False):
        cfg = self.save()
        if cfg:
            def operation():
                from .indexer import build_index
                build_index(cfg, rebuild=rebuild, quiet=True, progress=self.events.put, cancel=self.cancel.is_set)
            self.start(operation)

    def search(self):
        # Search the saved configuration; unsaved form edits do not redirect a running index.
        def operation():
            from .store import load_index
            load_index(Config.load(user=True).index_dir)
            url = self.service.start()
            self.events.put(("open", url))
        self.start(operation)

    def refresh(self):
        try:
            from .store import read_manifest
            from .indexer import index_settings
            cfg = Config.load(user=True)
            from .embedder import model_status
            self.model_status.set(model_status(cfg.embed_model))
            manifest = read_manifest(cfg.index_dir)
            stale = any(manifest.get(k) != v for k, v in index_settings(cfg).items())
            label = "Configuração alterada: atualize o índice." if stale else "Índice pronto para busca."
            self.summary.set(f"{label}\n{manifest['documents']} documentos · {manifest['chunks']} trechos\n"
                             f"Última atualização: {manifest.get('saved_at', '—')}\nOrigem: {manifest['source_dir']}")
        except FileNotFoundError:
            self.summary.set("Nenhum índice criado. Configure a pasta e clique em Atualizar índice.")
        except (ValueError, OSError, KeyError) as exc:
            self.summary.set(f"Índice ou configuração precisa de atenção: {exc}")

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if isinstance(event, Progress):
                    self.status.set(event.message)
                    if event.total:
                        self.bar.stop()
                        self.bar.configure(mode="determinate", maximum=event.total, value=event.completed or 0)
                    else:
                        self.bar.configure(mode="indeterminate")
                        self.bar.start()
                else:
                    kind, value = event
                    if kind == "finished":
                        self.worker.join()
                        self.worker = None
                        self.bar.stop()
                        self.bar.configure(mode="determinate", value=0)
                        for widget in self.controls:
                            widget.configure(state="normal")
                        self.cancel_button.configure(state="disabled")
                        self.refresh()
                    elif kind == "error":
                        self.status.set("Operação não concluída. Corrija o problema e tente novamente.")
                        if not self.closing:
                            messagebox.showerror("Não foi possível concluir", value, parent=self.window)
                    elif kind == "open":
                        if not self.closing:
                            webbrowser.open(value)
                            self.status.set("Busca aberta no navegador. Mantenha este aplicativo aberto durante o uso.")
                    else:
                        self.status.set(value)
        except queue.Empty:
            pass
        if self.closing and not self.worker:
            self.service.stop()
            self.window.destroy()
            return
        self.window.after(100, self.poll)

    def request_cancel(self):
        self.cancel.set()
        self.status.set("Cancelando após a etapa atual. Um download em andamento precisa terminar.")
        self.cancel_button.configure(state="disabled")

    def close(self):
        self.closing = True
        if self.worker:
            self.request_cancel()
        else:
            self.service.stop()
            self.window.destroy()

    def open_logs(self):
        os.startfile(str(user_data_dir() / "logs"))


def main():
    configure_user_runtime()
    logs = user_data_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
        logs / "desktop.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")])
    # --windowed executables have no stdout/stderr; third-party libraries expect streams.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(logs / "runtime.log", "a", encoding="utf-8"))
    logging.info("Inicializando Tk")
    window = tk.Tk()
    if "--smoke-test" in sys.argv:
        window.withdraw()
    window.report_callback_exception = lambda *error: logging.error("Erro na interface", exc_info=error)
    logging.info("Inicializando janela desktop")
    app = Desktop(window)
    logging.info("Interface pronta")
    if "--smoke-test" in sys.argv:
        window.after(200, app.close)
    window.mainloop()


if __name__ == "__main__":
    main()
