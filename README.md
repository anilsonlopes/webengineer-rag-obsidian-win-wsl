# Web Engineer · RAG local

RAG (Retrieval-Augmented Generation) 100% local sobre o vault Obsidian
`G:\Meu Drive\ContextDirectory\Web Engineer` — 36 notas em português distribuídas em
7 pilares (Acessibilidade, Performance, Sustentabilidade, UX Engineering,
Product Discovery, Qualidade & DX, Manifesto) mais os PDFs de `_crawler/`.

Três formas de consultar: **CLI**, **servidor MCP** (o próprio Claude Code busca no vault)
e **API HTTP + UI web** em `localhost`.

## Por que o projeto mora fora do Google Drive

O `.venv` com PyTorch passa de 1 GB. Deixá-lo dentro de `G:\Meu Drive` faria o Drive
sincronizar milhares de arquivos binários. O código e o índice ficam em
`C:\Users\anils\projects\webengineer-rag`; o caminho do conteúdo é configurável
em `.env` (`WEBRAG_SOURCE_DIR`).

## Como funciona

```
vault (.md/.pdf)
  └─ loader.py      lê Markdown (tira frontmatter) e PDF (pypdf)
  └─ chunker.py     quebra por cabeçalho ## / ###, mantendo a trilha "arquivo › seção"
                    e janelas de ~1200 chars com 200 de sobreposição
  └─ embedder.py    intfloat/multilingual-e5-small — roda na CPU, offline, sem chave
  └─ store.py       chunks.jsonl + embeddings.npy + manifest.json
  └─ retriever.py   busca híbrida: cosseno (denso) + BM25 (léxico), fundidos por RRF
```

Não há etapa de geração por LLM: o sistema **recupera**, e quem sintetiza é o Claude Code
lendo os trechos pelo MCP. Isso é de propósito — o plano Claude Max não inclui créditos da
API (é cobrança à parte), então uma síntese via API custaria dinheiro a cada pergunta,
enquanto pelo MCP a mesma resposta sai dentro da assinatura que você já tem.

A busca híbrida importa aqui: o conteúdo é em português e cheio de termos técnicos em
inglês (*Core Web Vitals*, *code-splitting*, *WCAG*). O BM25 acerta o termo exato, o
embedding acerta a paráfrase; o RRF combina os dois rankings sem precisar calibrar pesos.

## Instalação

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

O script instala Python (via scoop ou winget) se não houver, cria o `.venv`, instala
PyTorch **CPU** (evita ~2,5 GB de wheels CUDA) e baixa o modelo de embedding (~120 MB).
Só o primeiro uso precisa de internet.

## Uso

```powershell
.\scripts\rag.ps1 index                                  # constrói o índice
.\scripts\rag.ps1 index --rebuild                        # refaz do zero após editar notas
.\scripts\rag.ps1 stats                                  # o que está indexado
.\scripts\rag.ps1 query "como medir Core Web Vitals?"    # trechos, sem LLM
.\scripts\rag.ps1 query "contraste de cores" -p Acessibilidade --full
.\scripts\rag.ps1 serve                                  # http://127.0.0.1:8077
```

Nada sai da máquina em nenhum desses comandos.

## Servidor MCP no Claude Code (WSL `asc`)

O Claude Code roda no WSL, então o servidor MCP vive lá. Instalação sem `sudo`:

```bash
wsl -d asc bash /mnt/c/Users/anils/projects/webengineer-rag/scripts/bootstrap-wsl.sh
```

Depois, dentro da `asc`:

```bash
claude mcp add web-engineer -s user -- ~/.local/bin/webrag-mcp
```

### Por que Windows indexa e o WSL só consulta

Na `asc`, `G:` **não está montado** (só `/mnt/c`) e montá-lo exigiria senha de `sudo` —
e `G:` é o drive virtual do Google Drive, que o `drvfs` monta de forma pouco confiável.
Mas o índice é autocontido: a busca só lê `chunks.jsonl` + `embeddings.npy`, nunca o
vault. Então a divisão fica natural:

| Onde | O que faz | Precisa do vault? |
|---|---|---|
| Windows | `index`, `query`, UI web | sim — enxerga `G:` |
| WSL `asc` | servidor MCP | não — lê o índice por `/mnt/c` |

Consequência prática: **depois de editar notas no Obsidian, rode `index --rebuild` no
Windows**; o MCP na `asc` passa a ver o conteúdo novo na próxima consulta.

O bootstrap do WSL não duplica o código — usa `PYTHONPATH` apontando para este mesmo
diretório em `/mnt/c`, então não existe uma segunda cópia para divergir. Só o venv fica
no ext4 (`~/.venvs/webrag`), porque venv em `/mnt/c` é lento. As dependências vêm via
[uv](https://docs.astral.sh/uv/), que é um binário único em `~/.local/bin` e traz a
própria implementação de venv — foi o que contornou a falta de `python3.12-venv` e de
`pip3` na distro, ambos instaláveis só com `sudo`.

Se um dia você quiser indexar de dentro do WSL também, aí sim precisa da senha:

```bash
sudo mkdir -p /mnt/g && sudo mount -t drvfs G: /mnt/g
```

Ferramentas expostas:

| Ferramenta | O que faz |
|---|---|
| `search_web_engineer(question, top_k, pillar)` | busca híbrida, devolve trechos com origem |
| `read_web_engineer_document(rel_path)` | conteúdo completo de uma nota |
| `list_web_engineer_documents()` | catálogo agrupado por pilar |

## API HTTP

`.\scripts\rag.ps1 serve` sobe em `127.0.0.1:8077`:

- `GET /` — UI de busca (light/dark automático)
- `GET /api/stats` — metadados do índice
- `POST /api/search` — `{"question": "...", "top_k": 6, "pillar": null}`

## Configuração (`.env`)

| Variável | Padrão | Para quê |
|---|---|---|
| `WEBRAG_SOURCE_DIR` | `G:\Meu Drive\ContextDirectory\Web Engineer` | conteúdo a indexar |
| `WEBRAG_INDEX_DIR` | `data/index` | onde o índice é gravado |
| `WEBRAG_EMBED_MODEL` | `intfloat/multilingual-e5-small` | troque por `-base` se quiser mais qualidade |
| `WEBRAG_CHUNK_CHARS` / `_OVERLAP` | `1200` / `200` | granularidade dos trechos |
| `WEBRAG_CHUNK_MIN` | `400` | seções menores que isso são fundidas com a seguinte |

Trocar `WEBRAG_EMBED_MODEL` exige `index --rebuild` (dimensões diferentes).

## Reindexar

O índice é um retrato do vault. Depois de editar notas no Obsidian, rode
`.\scripts\rag.ps1 index --rebuild` **no Windows**. Sem `--rebuild` o comando compara o
SHA-1 de cada arquivo e não faz nada se nada mudou. Com 37 arquivos leva ~30s na CPU.

## Estender para o resto do ContextDirectory

Aponte `WEBRAG_SOURCE_DIR` para `G:\Meu Drive\ContextDirectory` e reindexe — o loader já
ignora `.obsidian`, `.trash` e `node_modules`, e o campo `pillar` passa a ser a pasta de
primeiro nível (ASC, Notes, Discovery Contínuo…), continuando a funcionar como filtro.
