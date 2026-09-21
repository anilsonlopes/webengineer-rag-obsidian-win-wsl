param([string]$Python = 'python', [string]$Iscc = '')
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
Set-Location $projectDir
& $Python -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8, 'Use Python 3.12 x64'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 é necessário para o build.' }
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam.' }
& $Python -m PyInstaller --noconfirm packaging/webrag.spec
if ($LASTEXITCODE -ne 0) { throw 'O empacotamento falhou.' }
& $Python scripts/smoke-windows.py dist/WebEngineerRAG
if ($LASTEXITCODE -ne 0) { throw 'A verificação dos executáveis falhou.' }
$version = & $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
if (-not $Iscc) {
    $Iscc = @(
        (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Inno Setup 6\ISCC.exe'),
        (Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'Inno Setup 6\ISCC.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Iscc) { throw 'Inno Setup 6 não encontrado. Informe -Iscc com o caminho de ISCC.exe.' }
& $Iscc "/DAppVersion=$version" installer/webrag.iss
if ($LASTEXITCODE -ne 0) { throw 'A compilação do instalador falhou.' }
$installer = Join-Path $projectDir "dist\WebEngineerRAG-Setup-$version.exe"
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  WebEngineerRAG-Setup-$version.exe" | Set-Content -LiteralPath "$installer.sha256" -Encoding ascii
Write-Host "Instalador gerado: $installer"
