[CmdletBinding()]
param(
    [string]$Message = "backup: $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    [switch]$SkipTests,
    [switch]$Push
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

function Test-GitHasCommit {
    git rev-parse --verify --quiet HEAD *> $null
    return $LASTEXITCODE -eq 0
}

function Clear-GitStaging {
    if (Test-GitHasCommit) {
        git reset --quiet
    } else {
        git rm --cached -r --quiet --ignore-unmatch .
    }
}

if (-not (Test-Path ".git")) {
    throw "Git repository is not initialized. Run: git init -b main"
}

if (-not $SkipTests) {
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    npm --prefix frontend run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
}

git add -A
if ($LASTEXITCODE -ne 0) { throw "git add failed." }

$staged = @(git diff --cached --name-only)
if (-not $staged.Count) {
    Write-Host "No changes to back up."
    exit 0
}

$oversized = @()
foreach ($relativePath in $staged) {
    if (-not (Test-Path -LiteralPath $relativePath -PathType Leaf)) { continue }
    $file = Get-Item -LiteralPath $relativePath
    if ($file.Length -gt 50MB) {
        $oversized += "$relativePath ($([math]::Round($file.Length / 1MB, 1)) MB)"
    }
}
if ($oversized.Count) {
    Clear-GitStaging
    throw "Files over 50 MB are not allowed in the backup:`n$($oversized -join "`n")"
}

$secretPatterns = @(
    'sk-[A-Za-z0-9_-]{24,}',
    '(?i)(?<![A-Za-z0-9_])api[_-]?key["'']?\s*[=:]\s*["'']([^"'']{12,})["'']',
    '(?-i)^\s*[A-Z0-9_]*API_KEY\s*=\s*(\S{12,})\s*$'
)
$allowedPlaceholders = @('secret-value', 'example-value', 'replace-me', 'your-api-key', 'test-api-key')
$secretHits = @()
foreach ($relativePath in $staged) {
    if (-not (Test-Path -LiteralPath $relativePath -PathType Leaf)) { continue }
    $extension = [IO.Path]::GetExtension($relativePath).ToLowerInvariant()
    if ($extension -notin @(".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".txt", ".env", ".yml", ".yaml", ".toml", ".ini", ".ps1", ".bat", ".sh")) { continue }
    $lines = Select-String -LiteralPath $relativePath -Pattern $secretPatterns -AllMatches -ErrorAction SilentlyContinue
    foreach ($line in $lines) {
        foreach ($match in $line.Matches) {
            $candidate = if ($match.Groups.Count -gt 1 -and $match.Groups[1].Value) { $match.Groups[1].Value } else { $match.Value }
            $normalized = $candidate.Trim().ToLowerInvariant()
            if ($allowedPlaceholders -contains $normalized -or $normalized -match '^(example|sample|dummy|test|replace|your)[-_]') { continue }
            $secretHits += $relativePath
        }
    }
}
if ($secretHits.Count) {
    $uniqueSecretHits = @($secretHits | Sort-Object -Unique)
    Clear-GitStaging
    throw "Possible secret detected. Review these files before committing:`n$($uniqueSecretHits -join "`n")"
}

$hasCommit = Test-GitHasCommit
$whitespaceIssues = @(git diff --cached --check 2>&1)
$whitespaceExitCode = $LASTEXITCODE
if ($whitespaceExitCode -ne 0) {
    if ($hasCommit) {
        Clear-GitStaging
        throw "Whitespace validation failed:`n$($whitespaceIssues -join "`n")"
    }

    $issueCount = $whitespaceIssues.Count
    Write-Warning "The initial baseline contains $issueCount pre-existing whitespace issue(s). The baseline will be committed once; later commits must pass whitespace validation."
}

git commit -m $Message
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

if ($Push) {
    $remote = git remote get-url origin 2>$null
    if (-not $remote) { throw "No origin remote is configured." }
    git push -u origin HEAD
    if ($LASTEXITCODE -ne 0) { throw "git push failed." }
}

git status --short --branch
