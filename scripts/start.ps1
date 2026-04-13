#Requires -Version 5.1
<#
.SYNOPSIS
    Start the AI Digital Twin DR platform (Windows PowerShell / Docker Desktop).
.DESCRIPTION
    Checks prerequisites, warns about slow paths, then launches all services
    via Docker Compose. Waits for health checks and prints service URLs.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Header($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)   { Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg)   { Write-Host "    [FAIL] $msg" -ForegroundColor Red }

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# ── 1. check Docker Desktop ───────────────────────────────────────────────────
Write-Header "Checking Docker"
try {
    $dockerVersion = docker version --format "{{.Server.Version}}" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon not reachable" }
    Write-Ok "Docker $dockerVersion is running"
} catch {
    Write-Fail "Docker Desktop is not running or not installed."
    Write-Host "    Download: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    exit 1
}

# ── 2. check docker compose v2 plugin ────────────────────────────────────────
try {
    $composeVersion = docker compose version --short 2>&1
    if ($LASTEXITCODE -ne 0) { throw "not found" }
    Write-Ok "docker compose $composeVersion available"
} catch {
    Write-Fail "docker compose (v2) not found. Update Docker Desktop."
    exit 1
}

# ── 3. warn if project is inside a WSL UNC path ───────────────────────────────
if ($ProjectRoot -match "^\\\\wsl") {
    Write-Warn "Project is under a WSL path ($ProjectRoot)."
    Write-Warn "For best performance, run from inside WSL2: bash scripts/start.sh"
}

# ── 4. check .env exists ──────────────────────────────────────────────────────
Write-Header "Checking configuration"
if (-not (Test-Path "$ProjectRoot\.env")) {
    Write-Fail ".env file not found."
    Write-Host "    Rename .env.example to .env and edit the secrets." -ForegroundColor Yellow
    exit 1
}
Write-Ok ".env found"

# ── 5. check Ollama on host ───────────────────────────────────────────────────
Write-Header "Checking Ollama (host)"
try {
    Invoke-WebRequest -Uri "http://localhost:11434" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop | Out-Null
    Write-Ok "Ollama is reachable at http://localhost:11434"
} catch {
    Write-Warn "Ollama not reachable at http://localhost:11434"
    Write-Warn "Start Ollama, then pull models:"
    Write-Warn "  ollama pull nomic-embed-text && ollama pull llama3"
    Write-Warn "(Continuing — embedding features will fail until Ollama is running)"
}

# ── 6. ensure Windows path conversion for bind mounts ────────────────────────
$env:COMPOSE_CONVERT_WINDOWS_PATHS = "1"

# ── 7. build and start ────────────────────────────────────────────────────────
Write-Header "Starting services (first run downloads images — may take several minutes)"
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose failed. Check output above."
    exit 1
}

# ── 8. wait for backend health ────────────────────────────────────────────────
Write-Header "Waiting for backend to be healthy"
$maxWait = 120; $waited = 0; $healthy = $false
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 5; $waited += 5
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $healthy = $true; break }
    } catch {}
    Write-Host "    ... waiting ($waited / $maxWait s)" -ForegroundColor DarkGray
}
if ($healthy) { Write-Ok "Backend is healthy" }
else { Write-Warn "Backend health check timed out. Run: docker compose logs backend" }

# ── 9. print URLs ─────────────────────────────────────────────────────────────
Write-Header "Services are up!"
Write-Host ""
Write-Host "  Frontend (3D Dashboard) : http://localhost:3000" -ForegroundColor White
Write-Host "  Backend API (FastAPI)   : http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs (Swagger)      : http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Neo4j Browser           : http://localhost:7474" -ForegroundColor White
Write-Host "  VictoriaMetrics         : http://localhost:8428" -ForegroundColor White
Write-Host "  Qdrant Dashboard        : http://localhost:6333/dashboard" -ForegroundColor White
Write-Host ""
Write-Host "  Ingest sample data : .\scripts\ingest.ps1" -ForegroundColor DarkGray
Write-Host "  Stop all services  : docker compose down" -ForegroundColor DarkGray
Write-Host ""
