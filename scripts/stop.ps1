<#
Stops the Heimdall stack and frees its ports.

Invoked by stop.bat at the repository root. Safe to run at any time, including
when nothing is running.

Only processes that are recognisably part of this project are stopped. A port
can be held by something unrelated, and killing whatever happens to own a port
number is how an unrelated editor or database loses its work.
#>

[CmdletBinding()]
param(
    [int] $ApiPort = 8000,
    [int] $WebPort = 5173,
    # Leave the PostgreSQL container running.
    [switch] $KeepDatabase,
    # Stop a matching process even when its command line is not recognisable.
    [switch] $Force
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

function Write-Step($text) { Write-Host "`n:: $text" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "   $text" -ForegroundColor DarkGray }
function Write-Warn($text) { Write-Host "   $text" -ForegroundColor Yellow }

Write-Host "Heimdall - stopping" -ForegroundColor White

# Anything whose command line names this project, its servers or its repository
# path. Everything else is left alone.
$ownPattern = "uvicorn|app\.main|vite|npm run dev|Heimdall"

function Get-ProcessTree([int] $ProcessId) {
    $seen = @{}
    $queue = [System.Collections.Queue]::new()
    $queue.Enqueue($ProcessId)
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        if ($seen.ContainsKey($current)) { continue }
        $seen[$current] = $true
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$current" -ErrorAction SilentlyContinue |
            ForEach-Object { $queue.Enqueue([int] $_.ProcessId) }
    }
    return $seen.Keys
}

function Stop-Port([int] $Port, [string] $Label) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) { Write-Ok "$Label (port $Port): nothing listening."; return }

    foreach ($connection in $connections) {
        $ownerPid = [int] $connection.OwningProcess
        $info = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
        if (-not $info) { continue }

        $command = "$($info.CommandLine)"
        $isOurs = $command -match $ownPattern

        if (-not $isOurs -and -not $Force) {
            Write-Warn "$Label (port $Port) is held by $($info.Name) (PID $ownerPid), which does not look like Heimdall."
            Write-Warn "  $($command.Substring(0, [Math]::Min(110, $command.Length)))"
            Write-Warn "  Left running. Use: stop.bat -Force  to stop it anyway."
            continue
        }

        # The console window is the ancestor; children are the reloader and the
        # worker. Stop children first so the parent does not respawn them.
        $tree = @(Get-ProcessTree -ProcessId $ownerPid) + $ownerPid | Select-Object -Unique
        $stopped = 0
        foreach ($target in ($tree | Sort-Object -Descending)) {
            try { Stop-Process -Id $target -Force -ErrorAction Stop; $stopped++ } catch { }
        }
        Write-Ok "$Label (port $Port): stopped $($info.Name) (PID $ownerPid) and $($stopped - 1) child process(es)."
    }
}

Write-Step "Application servers"
Stop-Port -Port $ApiPort -Label "API"
Stop-Port -Port $WebPort -Label "Web"

# A crashed or backgrounded server can outlive its port binding, and an orphan
# holds the port the next start needs. Sweep for any that remain.
Write-Step "Orphaned servers"
# Parenthesised deliberately: `-and` binds tighter than `-or`, so the obvious
# spelling would match any uvicorn on the machine, including another project's.
$orphans = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='uv.exe' OR Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $command = "$($_.CommandLine)"
        ($command -match "uvicorn app\.main") -or
        (($command -match "uvicorn|vite") -and ($command -match [regex]::Escape($root)))
    }

if (-not $orphans) { Write-Ok "None found." }
else {
    foreach ($orphan in $orphans) {
        try {
            Stop-Process -Id $orphan.ProcessId -Force -ErrorAction Stop
            Write-Ok "Stopped $($orphan.Name) (PID $($orphan.ProcessId))."
        }
        catch { }
    }
}

# The `cmd /k` console windows start.ps1 opened are ancestors of the servers,
# not descendants, so stopping the server tree leaves them sitting at an idle
# prompt. They are matched by the exact titles start.ps1 gave them.
Write-Step "Console windows"
$windows = Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
    Where-Object { "$($_.CommandLine)" -match "title Heimdall (API|Web)" }

if (-not $windows) { Write-Ok "None open." }
else {
    foreach ($window in $windows) {
        try {
            Stop-Process -Id $window.ProcessId -Force -ErrorAction Stop
            Write-Ok "Closed window (PID $($window.ProcessId))."
        }
        catch { }
    }
}

# --- Database ---------------------------------------------------------------
Write-Step "Database"
if ($KeepDatabase) {
    Write-Ok "Left running (-KeepDatabase)."
}
else {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Ok "Docker is not running; nothing to stop."
    }
    else {
        Push-Location $root
        try {
            docker compose stop db *> $null
            Write-Ok "Container stopped. Data is kept in the heimdall-db-data volume."
        }
        finally { Pop-Location }
    }
}

# --- Confirm ----------------------------------------------------------------
Write-Step "Ports"
$stillHeld = $false
foreach ($port in @($ApiPort, $WebPort)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $owner = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        Write-Warn "Port $port is still held by $($owner.Name) (PID $($conn.OwningProcess))."
        $stillHeld = $true
    }
    else { Write-Ok "Port $port is free." }
}

Write-Host ""
if ($stillHeld) { Write-Host "  Some ports are still in use. See the warnings above." -ForegroundColor Yellow }
else { Write-Host "  Everything is stopped." -ForegroundColor White }
Write-Host ""
