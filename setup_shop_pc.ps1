[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDirectory = Join-Path $env:LOCALAPPDATA 'AmeeMobiles\logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory 'setup.log'
$transcriptStarted = $false

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Step
    )

    Write-Host "`n$Step"
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE. See $logPath"
    }
}

try {
    Start-Transcript -Path $logPath -Append | Out-Null
    $transcriptStarted = $true
    Set-Location -LiteralPath $projectRoot

    $requiredFiles = @(
        'pyproject.toml', 'uv.lock', 'alembic.ini',
        'run_server.bat', 'start_app_silent.vbs', 'launch_pos_app.bat',
        'launch_pos_app_silent.vbs', 'app\static\app.ico'
    )
    foreach ($relativePath in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath) -PathType Leaf)) {
            throw "Required project file is missing: $relativePath"
        }
    }

    Write-Host "Project folder: $projectRoot"
    Write-Host 'This setup installs the app runtime and creates an empty shop database when none exists.'
    Write-Host 'It does not run sample seeding or import data.'

    $uvCommand = Get-Command 'uv.exe' -ErrorAction SilentlyContinue
    if ($uvCommand) {
        $uvPath = $uvCommand.Source
    } else {
        $uvDirectory = Join-Path $env:USERPROFILE '.local\bin'
        $uvPath = Join-Path $uvDirectory 'uv.exe'
        if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
            Write-Host "Installing uv for this Windows user..."
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            New-Item -ItemType Directory -Path $uvDirectory -Force | Out-Null
            $env:UV_INSTALL_DIR = $uvDirectory
            $installerPath = Join-Path $env:TEMP ("uv-install-{0}.ps1" -f [guid]::NewGuid().ToString('N'))
            try {
                Invoke-WebRequest -UseBasicParsing -Uri 'https://astral.sh/uv/install.ps1' -OutFile $installerPath
                if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf) -or (Get-Item -LiteralPath $installerPath).Length -eq 0) {
                    throw 'Could not download the official uv installer.'
                }
                & $installerPath
            } finally {
                Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
            }
        }
    }

    if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
        throw "uv was not installed at the expected location: $uvPath"
    }

    $pythonRequest = $null
    $systemPython = & $uvPath python find --system '3.12' 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($systemPython -join ''))) {
        $pythonRequest = ($systemPython | Select-Object -Last 1).Trim()
        Write-Host "Using existing Python 3.12: $pythonRequest"
    } else {
        $pythonInstallDirectory = Join-Path $env:LOCALAPPDATA 'AmeeMobiles\python'
        New-Item -ItemType Directory -Path $pythonInstallDirectory -Force | Out-Null
        $env:UV_PYTHON_INSTALL_DIR = $pythonInstallDirectory
        Write-Host "`nInstalling managed Python 3.12"
        & $uvPath python install '3.12' '--no-bin'
        $pythonInstallExit = $LASTEXITCODE
        $managedPython = Get-ChildItem -LiteralPath $pythonInstallDirectory -Directory -Filter 'cpython-3.12.*-windows-*' |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'python.exe' } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if (-not $managedPython) {
            throw "Managed Python 3.12 was not installed (uv exit code $pythonInstallExit). See $logPath"
        }
        $managedPythonVersion = & $managedPython '--version'
        if ($LASTEXITCODE -ne 0 -or $managedPythonVersion -notmatch '^Python 3\.12\.') {
            throw "The installed Python did not report version 3.12: $managedPythonVersion"
        }
        if ($pythonInstallExit -ne 0) {
            Write-Host 'uv could not create its minor-version link; using the installed Python executable directly.'
        }
        $pythonRequest = $managedPython
    }

    Invoke-Checked -Executable $uvPath -Arguments @('sync', '--python', $pythonRequest, '--locked', '--no-dev') -Step 'Installing application dependencies'

    $envFile = Join-Path $projectRoot '.env'
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        Write-Host "`nCreating local application secrets and database settings..."
        $keyOutput = & $uvPath run --project $projectRoot --python $pythonRequest --no-sync python (Join-Path $projectRoot 'scripts\gen_key.py')
        if ($LASTEXITCODE -ne 0) {
            throw "Could not generate application secrets. See $logPath"
        }
        $passcodeLine = $keyOutput | Where-Object { $_ -like 'PASSCODE_ENCRYPTION_KEY=*' } | Select-Object -First 1
        $secretLine = $keyOutput | Where-Object { $_ -like 'SECRET_KEY=*' } | Select-Object -First 1
        if (-not $passcodeLine -or -not $secretLine) {
            throw 'The key generator returned incomplete secrets.'
        }
        $environment = @(
            'APP_ENV=production',
            $secretLine,
            $passcodeLine,
            'DATABASE_URL=sqlite:///data/shop.db',
            'BACKUP_DIR=backups',
            'COOKIE_SECURE=false'
        )
        Set-Content -LiteralPath $envFile -Value $environment -Encoding Ascii
    } elseif ((Get-Content -LiteralPath $envFile -Raw) -match 'change-this-in-production|dev-insecure-secret-key') {
        throw 'The existing .env contains example secrets. Replace them before setup; this script will not overwrite an existing .env.'
    }

    New-Item -ItemType Directory -Path (Join-Path $projectRoot 'data') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $projectRoot 'backups') -Force | Out-Null
    Invoke-Checked -Executable $uvPath -Arguments @('run', '--project', $projectRoot, '--no-sync', 'alembic', 'upgrade', 'head') -Step 'Preparing the shop database'

    $desktopDirectory = [Environment]::GetFolderPath('Desktop')
    $desktopShortcutPath = Join-Path $desktopDirectory 'Amee Mobiles POS.lnk'
    $desktopVbs = Join-Path $projectRoot 'launch_pos_app_silent.vbs'
    $wshShell = New-Object -ComObject WScript.Shell
    $desktopShortcut = $wshShell.CreateShortcut($desktopShortcutPath)
    $desktopShortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
    $desktopShortcut.Arguments = '//B //NoLogo ' + [char]34 + $desktopVbs + [char]34
    $desktopShortcut.WorkingDirectory = $projectRoot
    $desktopShortcut.IconLocation = (Join-Path $projectRoot 'app\static\app.ico') + ',0'
    $desktopShortcut.Description = 'Amee Mobiles - Repair Desk POS'
    $desktopShortcut.WindowStyle = 7
    $desktopShortcut.Save()

    $startupDirectory = [Environment]::GetFolderPath('Startup')
    $startupShortcutPath = Join-Path $startupDirectory 'AmeeMobilesServer.lnk'
    $serverVbs = Join-Path $projectRoot 'start_app_silent.vbs'
    $startupShortcut = $wshShell.CreateShortcut($startupShortcutPath)
    $startupShortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
    $startupShortcut.Arguments = '//B //NoLogo ' + [char]34 + $serverVbs + [char]34
    $startupShortcut.WorkingDirectory = $projectRoot
    $startupShortcut.Description = 'Start Amee Mobiles Server Silently'
    $startupShortcut.WindowStyle = 7
    $startupShortcut.Save()

    Write-Host "`nSetup complete. Desktop shortcut: $desktopShortcutPath"
    Write-Host 'The server will start when this Windows user signs in.'
    Write-Host 'Double-click Amee Mobiles POS to open the shop app.'
    Write-Host 'On a new database, complete the first-run shop name and Shop PIN setup in the app.'
} catch {
    Write-Host "`nSETUP FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Details: $logPath"
    exit 1
} finally {
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
}
