param([switch]$SkipDatabase)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
if (Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue) {
    throw 'Port 8000 or 5173 is already in use. Stop the existing preview before starting another.'
}
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
if (-not $SkipDatabase) {
    docker compose up -d --wait db
    if ($LASTEXITCODE -ne 0) { throw 'Postgres did not start. See docs/RUNBOOK.md for the Windows fallback.' }
}
Push-Location -LiteralPath (Join-Path $projectRoot 'backend')
try {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed.' }
    uv run --env-file ../.env alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed.' }
    uv run --env-file ../.env python seed.py
    if ($LASTEXITCODE -ne 0) { throw 'Demo seeding failed.' }
} finally { Pop-Location }
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
} finally { Pop-Location }
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'work') -Force | Out-Null
$apiProcess = Start-Process -FilePath 'uv' -ArgumentList @('run', '--env-file', '../.env', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'work/api.stdout.log') -RedirectStandardError (Join-Path $projectRoot 'work/api.stderr.log')
$webProcess = Start-Process -FilePath 'node' -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'work/web.stdout.log') -RedirectStandardError (Join-Path $projectRoot 'work/web.stderr.log')
$workerProcess = Start-Process -FilePath 'uv' -ArgumentList @('run', '--env-file', '../.env', 'python', 'worker.py') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'work/worker.stdout.log') -RedirectStandardError (Join-Path $projectRoot 'work/worker.stderr.log')
@{ api = $apiProcess.Id; web = $webProcess.Id; worker = $workerProcess.Id } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot 'work/local-processes.json')
Write-Output 'AgentShelf: http://localhost:5173 | API: http://localhost:8000/docs'
