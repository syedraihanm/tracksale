[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$uvCommand = Get-Command 'uv.exe' -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    if (-not $uvCommand) {
        throw 'Build Python was not found. Install uv, then run: uv sync --locked --no-dev'
    }
    Push-Location $projectRoot
    try {
        & $uvCommand.Source sync --locked --no-dev
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
}

$pyinstallerCheck = & $pythonPath -c 'import PyInstaller' 2>$null
if ($LASTEXITCODE -ne 0) {
    if (-not $uvCommand) {
        throw 'PyInstaller is missing. Install uv, then rerun this build script.'
    }
    & $uvCommand.Source pip install --python $pythonPath 'pyinstaller==6.22.3'
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed with exit code $LASTEXITCODE." }
}

$makensisCommand = Get-Command 'makensis.exe' -ErrorAction SilentlyContinue
$makensisCandidates = @(
    $(if ($makensisCommand) { $makensisCommand.Source }),
    (Join-Path $env:LOCALAPPDATA 'Programs\NSIS\makensis.exe'),
    (Join-Path $env:ProgramFiles 'NSIS\makensis.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'NSIS\makensis.exe'),
    (Join-Path $projectRoot 'build\tools\nsis-portable\nsis-3.13\makensis.exe'),
    (Join-Path $projectRoot 'build\tools\nsis-portable\makensis.exe')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }

if (-not $makensisCandidates) {
    throw 'NSIS was not found. Install Nullsoft Install System 3.13, then rerun this script.'
}
$makensis = $makensisCandidates | Select-Object -First 1
$env:NSISDIR = Split-Path -Parent $makensis

Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path (Join-Path $projectRoot 'dist') -Force | Out-Null
    & $pythonPath -m PyInstaller --noconfirm --clean --distpath (Join-Path $projectRoot 'dist') --workpath (Join-Path $projectRoot 'build\pyinstaller') (Join-Path $projectRoot 'packaging\pos_app.spec')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

    & $makensis (Join-Path $projectRoot 'packaging\windows_installer.nsi')
    if ($LASTEXITCODE -ne 0) { throw "NSIS failed with exit code $LASTEXITCODE." }

    $installerPath = Join-Path $projectRoot 'dist\AmeeMobilesSetup.exe'
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
        throw 'The setup executable was not created.'
    }
    Write-Host "Installer created: $installerPath"
} finally {
    Pop-Location
}
