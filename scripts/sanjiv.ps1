param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("install", "services", "migrate", "seed", "start", "dev", "workers", "verify", "full", "preflight", "demo", "offline", "stop", "cleanup")]
    [string]$Command
)

$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repositoryRoot
try {
    node scripts/sanjiv.mjs $Command
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
