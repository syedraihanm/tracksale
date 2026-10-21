[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$npxCommand = Get-Command 'npx.cmd' -ErrorAction SilentlyContinue

if (-not $npxCommand) {
    throw 'Node.js and npm are required to rebuild the local Tailwind stylesheet.'
}

Push-Location $projectRoot
try {
    & $npxCommand.Source --yes tailwindcss@3.4.17 `
        --input app/static/tailwind.input.css `
        --output app/static/tailwind.css `
        --config tailwind.config.cjs `
        --minify
    if ($LASTEXITCODE -ne 0) {
        throw "Tailwind CSS build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
