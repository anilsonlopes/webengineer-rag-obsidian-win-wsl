# Bootstrap do RAG local — instala Python (se faltar), cria o venv e as dependências.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Get-PythonExe {
    foreach ($candidate in @('python', 'python3', 'py')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notlike '*WindowsApps*') {
            $version = & $cmd.Source --version 2>&1
            if ($LASTEXITCODE -eq 0) { return $cmd.Source }
        }
    }
    return $null
}

Write-Host '== 1/4 Python ==' -ForegroundColor Cyan
$python = Get-PythonExe
if (-not $python) {
    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        Write-Host 'Python não encontrado. Instalando via scoop...'
        scoop install python
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host 'Python não encontrado. Instalando via winget...'
        winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    } else {
        throw 'Instale o Python 3.10+ manualmente (https://python.org) e rode este script de novo.'
    }
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
    $python = Get-PythonExe
    if (-not $python) { throw 'Python instalado, mas fora do PATH. Abra um terminal novo e rode de novo.' }
}
Write-Host "Usando: $python  ($(& $python --version))" -ForegroundColor Green

Write-Host '== 2/4 Ambiente virtual ==' -ForegroundColor Cyan
if (-not (Test-Path '.venv')) { & $python -m venv .venv }
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
& $venvPy -m pip install --upgrade pip --quiet

Write-Host '== 3/4 Dependências ==' -ForegroundColor Cyan
# PyTorch CPU primeiro: evita baixar ~2,5 GB de wheels com CUDA.
& $venvPy -m pip install torch --index-url https://download.pytorch.org/whl/cpu
& $venvPy -m pip install -r requirements.txt
& $venvPy -m pip install -e . --no-deps

Write-Host '== 4/4 Baixando o modelo de embedding ==' -ForegroundColor Cyan
& $venvPy -c "from sentence_transformers import SentenceTransformer; import os; SentenceTransformer(os.getenv('WEBRAG_EMBED_MODEL','intfloat/multilingual-e5-small'))"

Write-Host ''
Write-Host 'Pronto. Próximos passos:' -ForegroundColor Green
Write-Host '  .\scripts\rag.ps1 index'
Write-Host '  .\scripts\rag.ps1 query "como medir Core Web Vitals?"'
Write-Host '  .\scripts\rag.ps1 serve      # http://127.0.0.1:8077'
