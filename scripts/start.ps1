<#
Starts the whole Heimdall stack for local development.

Invoked by start.bat at the repository root. Each service runs in its own
console window so its logs stay readable and it can be stopped individually.
#>

[CmdletBinding()]
param(
    [int] $ApiPort = 8000,
    [int] $WebPort = 5173,
    # Skip the database container and migrations, for when they are already up.
    [switch] $NoDatabase
)

# Native tools here write progress to stderr. PowerShell turns redirected
# native stderr into error records, so failures are detected by checking
# $LASTEXITCODE explicitly rather than by letting errors terminate.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

function Write-Step($text) { Write-Host "`n:: $text" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "   $text" -ForegroundColor DarkGray }
function Write-Fail($text) { Write-Host "   $text" -ForegroundColor Red }

Write-Host "Heimdall - local development" -ForegroundColor White

# --- Ports ------------------------------------------------------------------
# A port already in use is the most common reason a start fails, and the error
# Windows gives ("WinError 10013") does not say so. Check first and name the
# process holding it.
Write-Step "Checking ports"
$blocked = $false
foreach ($port in @($ApiPort, $WebPort)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) {
        $owner = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        Write-Fail "Port $port is already in use by $($owner.Name) (PID $($conn.OwningProcess))."
        $blocked = $true
    }
    else {
        Write-Ok "Port $port is free."
    }
}
if ($blocked) {
    Write-Host "`nRun stop.bat to free them, then start again." -ForegroundColor Yellow
    exit 1
}

# --- Database ---------------------------------------------------------------
if (-not $NoDatabase) {
    Write-Step "Database"
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Docker is not running. Start Docker Desktop, then try again."
        exit 1
    }

    Push-Location $root
    try {
        docker compose up -d db *> $null
        if ($LASTEXITCODE -ne 0) { Write-Fail "Could not start the database container."; exit 1 }

        Write-Ok "Waiting for PostgreSQL to accept connections..."
        $healthy = $false
        foreach ($attempt in 1..30) {
            $state = (docker inspect -f "{{.State.Health.Status}}" heimdall-db 2>$null)
            if ($state -eq "healthy") { $healthy = $true; break }
            Start-Sleep -Seconds 2
        }
        if (-not $healthy) {
            Write-Fail "The database did not become healthy. Check: docker compose logs db"
            exit 1
        }
        Write-Ok "PostgreSQL is healthy on port 5433."
    }
    finally { Pop-Location }

    # Migrations are a deliberate step, never something the application performs
    # at startup or during a request.
    Write-Step "Migrations"
    Push-Location (Join-Path $root "backend")
    try {
        # Left unredirected on purpose: alembic logs to stderr, and redirecting it
        # inside PowerShell would wrap each line as an error.
        uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) { Write-Fail "Migrations failed."; exit 1 }
        Write-Ok "Schema is at head."
    }
    finally { Pop-Location }
}

# --- Frontend dependencies --------------------------------------------------
$frontend = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Step "Installing frontend dependencies (first run only)"
    Push-Location $frontend
    try {
        npm install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Write-Fail "npm install failed."; exit 1 }
    }
    finally { Pop-Location }
}

# --- Services ---------------------------------------------------------------
# Separate windows, titled so stop.ps1 and a human can both find them.
Write-Step "Starting services"

Start-Process -FilePath "cmd.exe" -ArgumentList @(
    "/k", "title Heimdall API && cd /d `"$root\backend`" && uv run uvicorn app.main:app --host 127.0.0.1 --port $ApiPort --reload"
)
Write-Ok "API starting on http://127.0.0.1:$ApiPort"

Start-Process -FilePath "cmd.exe" -ArgumentList @(
    "/k", "title Heimdall Web && cd /d `"$root\frontend`" && npm run dev"
)
Write-Ok "Web starting on http://localhost:$WebPort"

# --- Wait for the API to answer ---------------------------------------------
Write-Step "Waiting for the API"
$up = $false
foreach ($attempt in 1..30) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $up = $true; break }
    }
    catch { }
}
if ($up) { Write-Ok "API is answering /health." }
else { Write-Fail "The API did not answer in 30s. Check the 'Heimdall API' window." }

Write-Host ""
Write-Host "  Web         http://localhost:$WebPort" -ForegroundColor White
Write-Host "  API         http://127.0.0.1:$ApiPort" -ForegroundColor White
Write-Host "  API docs    http://127.0.0.1:$ApiPort/docs" -ForegroundColor White
Write-Host "  Database    localhost:5433" -ForegroundColor White
Write-Host ""
Write-Host "  Run stop.bat to shut everything down and free the ports." -ForegroundColor DarkGray
Write-Host ""
