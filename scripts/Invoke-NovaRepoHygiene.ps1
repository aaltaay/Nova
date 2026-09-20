<# Run cleanup with durable output and a truthful Task Scheduler result. #>
param([string]$RepoRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$result = 2
try {
    $RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
    $logDir = Join-Path $RepoRoot 'logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $logFile = Join-Path $logDir 'repo-hygiene.log'
    Add-Content -LiteralPath $logFile -Value ("=== " + (Get-Date -Format s) + " ===")
    Push-Location -LiteralPath $RepoRoot
    try {
        # Native stderr is diagnostic output, not a terminating PowerShell error.
        $ErrorActionPreference = 'Continue'
        $LASTEXITCODE = $null
        $output = & py -3 (Join-Path $RepoRoot 'tools\repo_hygiene.py') fix 2>&1
        $result = $LASTEXITCODE
        if ($null -eq $result) { $result = 2 }
        $ErrorActionPreference = 'Stop'
        $output | Out-File -LiteralPath $logFile -Append -Encoding utf8
    } finally { Pop-Location }
    Add-Content -LiteralPath $logFile -Value ("result=" + $result)
} catch {
    Write-Warning ("Repo maintenance failed: " + $_.Exception.Message)
    $result = 2
}
exit $result
