<#
.SYNOPSIS
    Stops the WRTS Streamlit dashboard and any running fetch_data.py process.

.DESCRIPTION
    Finds and terminates:
      - Streamlit server processes (matched by process name)
      - fetch_data.py processes (matched by command line)
    Does NOT require Administrator privileges.

.EXAMPLE
    powershell.exe -ExecutionPolicy Bypass -File stop_services.ps1
#>

$ErrorActionPreference = "Continue"

# Derive script directory for lock file path
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = (Get-Location).Path }

Write-Host "Stopping WRTS services..." -ForegroundColor Cyan

# ── Stop Streamlit ─────────────────────────────────────────────────────────────

$streamlitProcs = Get-Process | Where-Object { $_.Name -like "*streamlit*" }
if ($streamlitProcs) {
    $streamlitProcs | Stop-Process -Force
    Write-Host "  [OK] Stopped $($streamlitProcs.Count) Streamlit process(es)." -ForegroundColor Green
} else {
    Write-Host "  [--] No Streamlit processes found." -ForegroundColor Gray
}

# ── Stop fetch_data.py ─────────────────────────────────────────────────────────

$fetchProcs = Get-WmiObject Win32_Process |
    Where-Object { $_.CommandLine -like "*fetch_data*" }

if ($fetchProcs) {
    foreach ($proc in $fetchProcs) {
        try {
            Stop-Process -Id $proc.ProcessId -Force
            Write-Host "  [OK] Stopped fetch_data.py (PID $($proc.ProcessId))." -ForegroundColor Green
        } catch {
            Write-Host "  [!!] Could not stop PID $($proc.ProcessId): $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "  [--] No fetch_data.py processes found." -ForegroundColor Gray
}

# ── Remove stale lock file if present ─────────────────────────────────────────

$lockFile = Join-Path $ScriptDir ".fetch.lock"
if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force
    Write-Host "  [OK] Removed stale lock file: .fetch.lock" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
