# InfraWatch — Instalador de Agente Windows
# Ejecutar como Administrador en PowerShell:
# 
# Opcion 1 — Descarga directa:
#   irm http://TU_SERVIDOR:8000/static/agents/windows/install.ps1 | iex
#
# Opcion 2 — Con parametros:
#   $env:INFRAWATCH_SERVER="http://192.168.1.100:8000"; irm http://TU_SERVIDOR:8000/static/agents/windows/install.ps1 | iex
#
# Opcion 3 — Descarga manual y ejecuta:
#   Set-ExecutionPolicy Bypass -Scope Process
#   .\install.ps1 -ServerUrl "http://192.168.1.100:8000"

param(
    [string]$ServerUrl = $env:INFRAWATCH_SERVER,
    [int]$Interval     = 60
)

$ErrorActionPreference = "Stop"

function Write-Banner {
    Write-Host ""
    Write-Host "  ___        __          _       _       _     " -ForegroundColor Cyan
    Write-Host " |_ _|_ __  / _|_ __ __ _| |   _ | | __ _| |_ ___| |__  " -ForegroundColor Cyan
    Write-Host "  | || '_ \| |_| '__/ _\`| |  | || |/ _\`| __/ __| '_ \ " -ForegroundColor Cyan
    Write-Host "  | || | | |  _| | | (_| | |  |__   _| (_| | || (__| | | |" -ForegroundColor Cyan
    Write-Host " |___|_| |_|_| |_|  \__,_|_|     |_|  \__,_|\__\___|_| |_|" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Agente Windows v1.0" -ForegroundColor White
    Write-Host ""
}

Write-Banner

# Validate server URL
if (-not $ServerUrl) {
    Write-Host "ERROR: Falta la URL del servidor InfraWatch" -ForegroundColor Red
    Write-Host ""
    Write-Host "Uso:" -ForegroundColor Yellow
    Write-Host '  $env:INFRAWATCH_SERVER="http://192.168.1.100:8000"' -ForegroundColor White
    Write-Host '  irm http://192.168.1.100:8000/static/agents/windows/install.ps1 | iex' -ForegroundColor White
    exit 1
}

# Check admin
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: Ejecuta PowerShell como Administrador" -ForegroundColor Red
    exit 1
}

$AgentDir   = "C:\ProgramData\InfraWatch"
$AgentScript = "$AgentDir\infrawatch-agent.ps1"

Write-Host "[1/4] Creando directorio de agente..." -ForegroundColor Cyan
New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null
Write-Host "  OK: $AgentDir" -ForegroundColor Green

Write-Host "[2/4] Descargando script del agente..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri "$ServerUrl/static/agents/windows/infrawatch-agent.ps1" `
        -OutFile $AgentScript -TimeoutSec 30 -UseBasicParsing -ErrorAction Stop
    Write-Host "  OK: Script descargado" -ForegroundColor Green
} catch {
    Write-Host "  WARN: No se pudo descargar del servidor, buscando local..." -ForegroundColor Yellow
    $localScript = Join-Path (Split-Path $MyInvocation.MyCommand.Path) "infrawatch-agent.ps1"
    if (Test-Path $localScript) {
        Copy-Item $localScript $AgentScript -Force
        Write-Host "  OK: Script copiado desde directorio local" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: No se encontró infrawatch-agent.ps1" -ForegroundColor Red
        Write-Host "  Descarga manualmente y colócalo en $AgentDir" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "[3/4] Configurando política de ejecución..." -ForegroundColor Cyan
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force -ErrorAction SilentlyContinue
Write-Host "  OK" -ForegroundColor Green

Write-Host "[4/4] Instalando tarea programada..." -ForegroundColor Cyan
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$AgentScript`" -ServerUrl `"$ServerUrl`" -Interval $Interval"

$triggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5))
)
$settings  = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Unregister-ScheduledTask -TaskName "InfraWatchAgent" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "InfraWatchAgent" -Action $action -Trigger $triggers[0] `
    -Settings $settings -Principal $principal -Description "InfraWatch Monitoring Agent" | Out-Null
Start-ScheduledTask -TaskName "InfraWatchAgent"
Write-Host "  OK: Tarea 'InfraWatchAgent' creada e iniciada" -ForegroundColor Green

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   ✅  Agente InfraWatch instalado correctamente      ║" -ForegroundColor Green
Write-Host "╠══════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "║  Servidor : $ServerUrl" -ForegroundColor Cyan
Write-Host "║  Hostname : $($env:COMPUTERNAME)" -ForegroundColor Cyan
Write-Host "║  Intervalo: ${Interval}s" -ForegroundColor Cyan
Write-Host "╠══════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "║  Logs     : C:\ProgramData\InfraWatch\agent.log" -ForegroundColor White
Write-Host "║  Parar    : Stop-ScheduledTask -TaskName InfraWatchAgent" -ForegroundColor White
Write-Host "║  Eliminar : .\infrawatch-agent.ps1 -ServerUrl ... -Uninstall" -ForegroundColor White
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "El equipo aparecerá en el dashboard en ~60 segundos" -ForegroundColor Cyan
