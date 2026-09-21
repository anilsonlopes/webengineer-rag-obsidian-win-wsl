param([Parameter(Mandatory=$true)][string]$Installer)
$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$registryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WebEngineerRAG_is1'
if (Test-Path $registryKey) { throw 'Já existe uma instalação neste usuário. Execute este teste em um usuário limpo.' }
$installDir = Join-Path ([IO.Path]::GetTempPath()) ('webrag-install-' + [guid]::NewGuid().ToString('N'))
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'WebEngineerRAG-Smoke\Web Engineer RAG.lnk'
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Web Engineer RAG.lnk'
if (Test-Path -LiteralPath $desktopShortcut) { throw 'Um atalho existente seria alterado. Use um usuário limpo.' }
$dataDir = Join-Path $env:LOCALAPPDATA 'WebEngineerRAG'
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
$sentinel = Join-Path $dataDir ('installer-test-' + [guid]::NewGuid().ToString('N') + '.txt')
'Saved user data' | Set-Content -LiteralPath $sentinel
function Invoke-Setup([string]$Executable, [string[]]$SetupArgs) {
    $p = Start-Process -FilePath $Executable -ArgumentList $SetupArgs -WindowStyle Hidden -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installer failed: $($p.ExitCode)" }
}
$common = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/GROUP=WebEngineerRAG-Smoke', ('/DIR="{0}"' -f $installDir))
try {
    Invoke-Setup $Installer ($common + '/TASKS=desktopicon')
    if (-not (Test-Path -LiteralPath (Join-Path $installDir 'rag.exe'))) { throw 'CLI ausente.' }
    if (-not (Test-Path -LiteralPath (Join-Path $installDir 'WebEngineerRAG.exe'))) { throw 'Desktop ausente.' }
    if (-not (Test-Path -LiteralPath $shortcut)) { throw 'Atalho do menu Iniciar ausente.' }
    if (-not (Test-Path -LiteralPath $desktopShortcut)) { throw 'Atalho opcional ausente.' }
    & (Join-Path $installDir 'rag.exe') --help
    if ($LASTEXITCODE -ne 0) { throw 'CLI instalado falhou.' }
    Invoke-Setup $Installer ($common + '/TASKS=desktopicon')
    if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Atualização removeu dados do usuário.' }
    Invoke-Setup (Join-Path $installDir 'unins000.exe') @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    if ((Test-Path -LiteralPath $shortcut) -or (Test-Path -LiteralPath $desktopShortcut)) { throw 'Atalhos permaneceram após desinstalar.' }
    if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Desinstalação removeu dados do usuário.' }
    Invoke-Setup $Installer ($common + '/TASKS=')
    if (Test-Path -LiteralPath $desktopShortcut) { throw 'Atalho opcional criado mesmo desmarcado.' }
    if (-not (Test-Path -LiteralPath $shortcut)) { throw 'Atalho do menu Iniciar ausente na segunda instalação.' }
} finally {
    $uninstaller = Join-Path $installDir 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        Invoke-Setup $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    }
    Remove-Item -LiteralPath $sentinel -ErrorAction SilentlyContinue
}
Write-Host 'Instalação, atualização, atalhos e preservação dos dados: OK'
