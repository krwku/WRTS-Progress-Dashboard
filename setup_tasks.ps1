<#
.SYNOPSIS
    Sets up Windows Task Scheduler tasks and firewall rule for the WRTS Dashboard.

.DESCRIPTION
    Creates three scheduled tasks:
      - WRTS_FetchWeekly     : Runs fetch_data.py once per week
      - WRTS_FetchStartup    : Runs fetch_data.py once at PC startup (after delay)
      - WRTS_StreamlitStartup: Starts the Streamlit dashboard at PC startup (after delay)

    Also adds a Windows Firewall inbound rule to allow LAN access to the dashboard.
    Must be run as Administrator.

.PARAMETER WeeklyDay
    Day of week for the weekly fetch (default: MON).
    Valid values: MON, TUE, WED, THU, FRI, SAT, SUN

.PARAMETER WeeklyTime
    Time for the weekly fetch in HH:MM 24-hour format (default: 06:00).

.PARAMETER FetchDelay
    Startup delay in seconds before running fetch_data.py on boot (default: 60).

.PARAMETER StreamlitDelay
    Startup delay in seconds before starting Streamlit on boot (default: 90).

.PARAMETER Port
    Port for the Streamlit dashboard (default: 8501).

.PARAMETER PythonExe
    Full path to python.exe. Auto-detected via where.exe if not specified.

.PARAMETER ProjectDir
    Project directory containing app.py and fetch_data.py.
    Defaults to the directory containing this script.

.EXAMPLE
    powershell.exe -ExecutionPolicy Bypass -File setup_tasks.ps1
    powershell.exe -ExecutionPolicy Bypass -File setup_tasks.ps1 -WeeklyDay FRI -WeeklyTime "08:00"
#>

[CmdletBinding()]
param(
    [string] $WeeklyDay      = "MON",
    [string] $WeeklyTime     = "06:00",
    [int]    $FetchDelay     = 60,
    [int]    $StreamlitDelay = 90,
    [int]    $Port           = 8501,
    [string] $PythonExe      = "",
    [string] $ProjectDir     = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Derive project dir from script location if not specified
if (-not $ProjectDir) {
    $ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    if (-not $ProjectDir) {
        $ProjectDir = (Get-Location).Path
    }
}

# ── Admin check ────────────────────────────────────────────────────────────────

$currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "ERROR: This script must be run as Administrator. Right-click PowerShell and select Run as administrator."
    exit 1
}

Write-Host "[OK] Running as Administrator" -ForegroundColor Green

# ── Resolve Python executable ──────────────────────────────────────────────────

if (-not $PythonExe) {
    try {
        $found = where.exe python 2>$null
        if ($found) {
            $PythonExe = ($found | Select-Object -First 1).Trim()
        }
    } catch {
        $PythonExe = ""
    }
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    Write-Error "ERROR: Python executable not found. Install Python and ensure it is on your PATH, or pass -PythonExe 'C:\path\to\python.exe'."
    exit 1
}

Write-Host "[OK] Python: $PythonExe" -ForegroundColor Green

# ── Resolve project directory ──────────────────────────────────────────────────

if (-not (Test-Path $ProjectDir)) {
    Write-Error "ERROR: Project directory not found: $ProjectDir"
    exit 1
}

$ProjectDir = (Resolve-Path $ProjectDir).Path
Write-Host "[OK] Project directory: $ProjectDir" -ForegroundColor Green

# ── Helper: register or replace a scheduled task ──────────────────────────────

function Register-WRTSTask {
    param(
        [string] $TaskName,
        [string] $Description,
        [object] $Trigger,
        [string] $Command,
        [string] $Arguments,
        [string] $WorkingDir
    )

    # Remove existing task if present (idempotent)
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  Replaced existing task: $TaskName" -ForegroundColor Yellow
    }

    $action   = New-ScheduledTaskAction -Execute $Command -Argument $Arguments -WorkingDirectory $WorkingDir
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable

    # Run as SYSTEM so it works whether or not a user is logged in
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    Register-ScheduledTask `
        -TaskName    $TaskName `
        -Description $Description `
        -Action      $action `
        -Trigger     $Trigger `
        -Settings    $settings `
        -Principal   $principal `
        -Force | Out-Null

    Write-Host "  [OK] Registered: $TaskName" -ForegroundColor Green
}

# ── Task 1: Weekly fetch ───────────────────────────────────────────────────────

Write-Host ""
Write-Host "Registering WRTS_FetchWeekly ($WeeklyDay at $WeeklyTime)..."

$weeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $WeeklyTime

Register-WRTSTask `
    -TaskName    "WRTS_FetchWeekly" `
    -Description "WRTS: Fetch student progress data weekly ($WeeklyDay $WeeklyTime)" `
    -Trigger     $weeklyTrigger `
    -Command     $PythonExe `
    -Arguments   "fetch_data.py" `
    -WorkingDir  $ProjectDir

# ── Task 2: Startup fetch (with delay) ────────────────────────────────────────

Write-Host "Registering WRTS_FetchStartup (startup + ${FetchDelay}s delay)..."

$startupFetchTrigger = New-ScheduledTaskTrigger -AtStartup
$startupFetchTrigger.Delay = "PT${FetchDelay}S"

Register-WRTSTask `
    -TaskName    "WRTS_FetchStartup" `
    -Description "WRTS: Fetch student progress data at PC startup (${FetchDelay}s delay)" `
    -Trigger     $startupFetchTrigger `
    -Command     $PythonExe `
    -Arguments   "fetch_data.py" `
    -WorkingDir  $ProjectDir

# ── Task 3: Streamlit startup (with delay) ────────────────────────────────────

Write-Host "Registering WRTS_StreamlitStartup (startup + ${StreamlitDelay}s delay)..."

# Find streamlit.exe next to python.exe, fall back to python -m streamlit
$StreamlitExe = Join-Path (Split-Path $PythonExe) "Scripts\streamlit.exe"
if (-not (Test-Path $StreamlitExe)) {
    $StreamlitCmd  = $PythonExe
    $StreamlitArgs = "-m streamlit run app.py --server.address 0.0.0.0 --server.port $Port --server.headless true"
} else {
    $StreamlitCmd  = $StreamlitExe
    $StreamlitArgs = "run app.py --server.address 0.0.0.0 --server.port $Port --server.headless true"
}

$startupStreamlitTrigger = New-ScheduledTaskTrigger -AtStartup
$startupStreamlitTrigger.Delay = "PT${StreamlitDelay}S"

Register-WRTSTask `
    -TaskName    "WRTS_StreamlitStartup" `
    -Description "WRTS: Start Streamlit dashboard at PC startup (${StreamlitDelay}s delay)" `
    -Trigger     $startupStreamlitTrigger `
    -Command     $StreamlitCmd `
    -Arguments   $StreamlitArgs `
    -WorkingDir  $ProjectDir

# ── Firewall rule ──────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Configuring Windows Firewall rule for port $Port..."

$existingRule = Get-NetFirewallRule -DisplayName "WRTS_Dashboard" -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "  Firewall rule 'WRTS_Dashboard' already exists -- skipping." -ForegroundColor Yellow
} else {
    New-NetFirewallRule `
        -DisplayName "WRTS_Dashboard" `
        -Direction   Inbound `
        -Protocol    TCP `
        -LocalPort   $Port `
        -Action      Allow `
        -Description "Allow LAN access to WRTS Streamlit dashboard on port $Port" | Out-Null
    Write-Host "  [OK] Firewall rule created: WRTS_Dashboard (TCP $Port inbound)" -ForegroundColor Green
}

# ── Summary ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================"
Write-Host "  WRTS Task Scheduler Setup Complete"
Write-Host "========================================"
Write-Host "  WRTS_FetchWeekly      : Every $WeeklyDay at $WeeklyTime"
Write-Host "  WRTS_FetchStartup     : At startup + ${FetchDelay}s delay"
Write-Host "  WRTS_StreamlitStartup : At startup + ${StreamlitDelay}s delay"
Write-Host "  Firewall port         : TCP $Port (inbound, LAN)"
Write-Host ""
Write-Host "  Dashboard URL (this PC) : http://localhost:$Port"
Write-Host "  Dashboard URL (LAN)     : http://<this-PC-IP>:$Port"
Write-Host ""
Write-Host "  To find this PC's IP    : run  ipconfig  and look for IPv4 Address"
Write-Host "  To stop services        : run stop_services.ps1 via PowerShell"
Write-Host "========================================"
