# Atalho: roda a CLI dentro do venv sem precisar ativar nada.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    throw "Ambiente não encontrado. Rode primeiro: powershell -ExecutionPolicy Bypass -File $root\scripts\bootstrap.ps1"
}
& $venvPy -m webrag @args
exit $LASTEXITCODE
