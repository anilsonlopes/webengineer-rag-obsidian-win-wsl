import logging
import multiprocessing
import sys
from webrag.desktop import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except Exception as exc:
        logging.exception("Não foi possível iniciar o aplicativo")
        if "--smoke-test" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Não foi possível iniciar: {exc}\nConsulte os logs em %LOCALAPPDATA%\\WebEngineerRAG\\logs.", "Web Engineer RAG", 16)
        raise SystemExit(1)
