# Build on Windows x64 with Python 3.12; entrypoints share one dependency folder.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
binaries, datas, hiddenimports = [], [(str(root / "src/webrag/web"), "webrag/web")], []
for package in ("sentence_transformers", "transformers", "tokenizers", "mcp", "uvicorn"):
    data, binary, imports = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += imports
for package in ("sentence-transformers", "torch", "numpy", "pypdf", "fastapi", "mcp", "filelock"):
    datas += copy_metadata(package, recursive=True)
a = Analysis([str(root / "packaging/desktop_entry.py"), str(root / "packaging/cli_entry.py")],
             pathex=[str(root / "src")], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=["pytest", "IPython", "matplotlib", "torchvision", "torchaudio"])
pyz = PYZ(a.pure)
desktop_scripts = [s for s in a.scripts if s[0] != "cli_entry"]
cli_scripts = [s for s in a.scripts if s[0] != "desktop_entry"]
desktop = EXE(pyz, desktop_scripts, [], exclude_binaries=True, name="WebEngineerRAG", console=False,
              icon=str(root / "packaging/icon.ico"))
cli = EXE(pyz, cli_scripts, [], exclude_binaries=True, name="rag", console=True,
          icon=str(root / "packaging/icon.ico"))
coll = COLLECT(desktop, cli, a.binaries, a.datas, name="WebEngineerRAG")
