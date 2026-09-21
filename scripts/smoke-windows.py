"""Exercise actual frozen binaries, including a downloaded model and offline searches."""
import json
import os
from pathlib import Path
import queue
import socket
import time
from urllib.request import Request, urlopen
import subprocess
import sys
import tempfile
import threading


def execute(args, env, timeout=900):
    result = subprocess.run([str(a) for a in args], env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f"{args}: {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def check_mcp(cli, env):
    process = subprocess.Popen([str(cli), "mcp"], env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
    messages = queue.Queue()
    def reader():
        for line in process.stdout:
            messages.put(line)
    threading.Thread(target=reader, daemon=True).start()
    def send(value):
        process.stdin.write(json.dumps(value) + "\n")
        process.stdin.flush()
    def receive(request_id):
        while True:
            value = json.loads(messages.get(timeout=120))
            if value.get("id") == request_id:
                assert "error" not in value, value
                return value["result"]
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}})
        receive(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert any(t["name"] == "search_web_engineer" for t in receive(2)["tools"])
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "search_web_engineer", "arguments": {"question": "contraste"}}})
        result = receive(3)
        assert not result.get("isError"), result
        assert result["content"], result
    finally:
        process.terminate()
        process.wait(timeout=15)
        process.stdin.close()
        process.stdout.close()


def check_http(cli, env):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([str(cli), "serve", "--port", str(port)], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with urlopen(base + "/api/stats", timeout=2) as response:
                    assert json.load(response)["documents"] == 2
                break
            except OSError:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Frozen HTTP server did not become ready")
                time.sleep(0.1)
        request = Request(base + "/api/search", data=json.dumps({"question": "contraste"}).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=120) as response:
            assert json.load(response)["hits"]
    finally:
        process.terminate()
        process.wait(timeout=15)


def main():
    folder = Path(sys.argv[1]).resolve()
    cli = folder / "rag.exe"
    with tempfile.TemporaryDirectory(prefix="webrag-smoke-") as temporary:
        data = Path(temporary)
        source = data / "Notas com acentuação"
        source.mkdir()
        (source / "acessibilidade.md").write_text("# Acessibilidade\n\nUse contraste adequado e navegação por teclado.", encoding="utf-8")
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 200 Td (Optimize images for performance.) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(source / "performance.pdf")
        env = {k: v for k, v in os.environ.items() if not k.startswith("WEBRAG_") and k not in ("PYTHONPATH", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
        env.update(LOCALAPPDATA=str(data), HF_HOME=str(data / "models"), PYTHONIOENCODING="utf-8")
        execute([cli, "--help"], env, 60)
        execute([folder / "WebEngineerRAG.exe", "--smoke-test"], env, 60)
        user = data / "WebEngineerRAG"
        user.mkdir(exist_ok=True)
        (user / "config.json").write_text(json.dumps({"source_dir": str(source), "index_dir": str(data / "index")}), encoding="utf-8")
        execute([cli, "index"], env)
        env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        execute([cli, "index", "--rebuild"], env)
        stats = execute([cli, "stats"], env)
        assert "2" in stats, stats
        hits = json.loads(execute([cli, "query", "contraste", "--json"], env))
        assert hits and any(h["rel_path"] == "acessibilidade.md" for h in hits), hits
        check_http(cli, env)
        check_mcp(cli, env)
        execute([folder / "WebEngineerRAG.exe", "--smoke-test"], env, 60)
    print("Frozen desktop, CLI, Markdown/PDF, offline embeddings and MCP: OK")


if __name__ == "__main__":
    main()
