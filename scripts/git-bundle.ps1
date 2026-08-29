[CmdletBinding()]
param([string]$OutputDirectory = "")

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

if (-not (Test-Path ".git")) { throw "Git repository is not initialized." }
if (-not (git rev-parse --verify HEAD 2>$null)) { throw "Create at least one commit first." }

if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot ".backups"
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $output | Out-Null
$bundle = Join-Path $output "multi-agent-platform-$(Get-Date -Format 'yyyyMMdd-HHmmss').bundle"

git bundle create $bundle --all
if ($LASTEXITCODE -ne 0) { throw "git bundle creation failed." }
git bundle verify $bundle
if ($LASTEXITCODE -ne 0) { throw "git bundle verification failed." }

Write-Host "Offline backup created: $bundle"
Write-Host "Restore with: git clone `"$bundle`" restored-project"
