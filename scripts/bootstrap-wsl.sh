#!/usr/bin/env bash
# Instala o servidor MCP deste projeto dentro do WSL (distro asc), sem sudo.
#
# Estratégia:
#   - o código-fonte continua sendo o daqui (/mnt/c/...), via PYTHONPATH — sem cópia,
#     sem risco de as duas versões divergirem;
#   - o venv fica no ext4 do WSL (~/.venvs/webrag), porque venv em /mnt/c é lento;
#   - o índice também é lido de /mnt/c, já que G: (o vault) não é montado no WSL.
#
# Uso:  wsl -d asc bash /mnt/c/Users/anils/projects/webengineer-rag/scripts/bootstrap-wsl.sh
set -euo pipefail

WIN_PROJECT="/mnt/c/Users/anils/projects/webengineer-rag"
VENV="$HOME/.venvs/webrag"
WRAPPER="$HOME/.local/bin/webrag-mcp"

command -v curl >/dev/null || { echo "curl é necessário"; exit 1; }
[ -d "$WIN_PROJECT/src/webrag" ] || { echo "projeto não encontrado em $WIN_PROJECT"; exit 1; }

echo "== 1/5 uv =="
if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
    # uv é um binário único instalado no ~/.local/bin — não precisa de sudo nem de
    # python3-venv (ele traz a própria implementação de venv).
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

echo "== 2/5 ambiente virtual =="
[ -d "$VENV" ] || uv venv "$VENV" --python 3.12
echo "venv: $VENV"

echo "== 3/5 dependências =="
# PyTorch CPU: no Linux o wheel padrão do PyPI embute CUDA (~2,5 GB).
VIRTUAL_ENV="$VENV" uv pip install torch --index-url https://download.pytorch.org/whl/cpu
VIRTUAL_ENV="$VENV" uv pip install -r "$WIN_PROJECT/requirements.txt"

echo "== 4/5 modelo de embedding =="
PYTHONPATH="$WIN_PROJECT/src" "$VENV/bin/python" - <<'PY'
import os
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
from sentence_transformers import SentenceTransformer
SentenceTransformer(os.getenv("WEBRAG_EMBED_MODEL", "intfloat/multilingual-e5-small"))
print("modelo em cache")
PY

echo "== 5/5 wrapper do servidor MCP =="
mkdir -p "$(dirname "$WRAPPER")"
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
# Servidor MCP da base Web Engineer. Gerado por scripts/bootstrap-wsl.sh.
# O índice vem de /mnt/c: quem indexa é o lado Windows, que enxerga o vault em G:.
export PYTHONPATH="$WIN_PROJECT/src"
export WEBRAG_INDEX_DIR="$WIN_PROJECT/data/index"
exec "$VENV/bin/python" -m webrag mcp
EOF
chmod +x "$WRAPPER"

echo
echo "Pronto. Registre no Claude Code deste WSL com:"
echo "  claude mcp add web-engineer -s user -- $WRAPPER"
