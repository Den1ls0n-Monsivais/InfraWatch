# InfraWatch - Agente Windows (PowerShell)
# Ejecutar como Administrador
# Parametros:
#   -ServerUrl  "http://IP:8000"
#   -Interval   60  (segundos entre heartbeats)
#   -Install    (instala como servicio de Windows via Tarea Programada)
#   -Uninstall  (elimina la tarea programada)

param(
    [string]$ServerUrl = $env:INFRAWATCH_SERVER,
    [int]$Interval     = 60,
    [switch]$Install,
    [switch]$Uninstall
)

$VERSION    = "1.0"
$AgentDir   = "C:\ProgramData\InfraWatch"
$AgentFile  = "$AgentDir\agent.json"
$LogFile    = "$AgentDir\agent.log"
$TaskName   = "InfraWatchAgent"

# ── HELPERS ──────────────────────────────────────────────────────────────────

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $ts  = Get-Date -Format "HH:mm:ss"
    $line = "[$ts][$Level] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Invoke-Api {
    param([string]$Path, [hashtable]$Body)
    $url  = "$ServerUrl$Path"
    $json = $Body | ConvertTo-Json -Depth 5 -Compress
    try {
        $response = Invoke-RestMethod -Uri $url -Method POST `
            -ContentType "application/json" -Body $json -TimeoutSec 15 -ErrorAction Stop
        return $response
    } catch {
        Write-Log "API Error: $($_.Exception.Message)" "WARN"
        return $null
    }
}

# ── SYSTEM INFO ──────────────────────────────────────────────────────────────

function Get-AgentInfo {
    $hostname = $env:COMPUTERNAME
    $ip       = ""
    $mac      = ""

    # Get primary network adapter
    $adapter = Get-NetAdapter | Where-Object { $_.Status -eq "Up" -and $_.HardwareInterface -eq $true } |
               Sort-Object -Property Speed -Descending | Select-Object -First 1
    if ($adapter) {
        $ipInfo = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1
        $ip  = if ($ipInfo) { $ipInfo.IPAddress } else { "127.0.0.1" }
        $mac = $adapter.MacAddress -replace "-",":"
    }
    if (-not $ip) {
        try { $ip = (Invoke-WebRequest -Uri "https://api.ipify.org" -TimeoutSec 5).Content } catch { $ip = "127.0.0.1" }
    }

    # OS info
    $os      = Get-CimInstance Win32_OperatingSystem
    $osName  = "Windows"
    $osVer   = $os.Caption -replace "Microsoft Windows ", ""

    # CPU
    $cpu     = Get-CimInstance Win32_Processor | Select-Object -First 1
    $cpuName = $cpu.Name.Trim() -replace '\s+', ' '
    $cores   = $cpu.NumberOfLogicalProcessors

    # RAM
    $ramGb   = [Math]::Round($os.TotalVisibleMemorySize / 1MB, 2)

    # Disk (C:)
    $disk    = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction SilentlyContinue
    $diskGb  = if ($disk) { [Math]::Round($disk.Size / 1GB, 1) } else { 0 }

    return @{
        hostname      = $hostname
        ip_address    = $ip
        mac_address   = $mac
        os_name       = $osName
        os_version    = $osVer
        cpu_model     = $cpuName
        cpu_cores     = $cores
        ram_total_gb  = $ramGb
        disk_total_gb = $diskGb
        agent_version = $VERSION
    }
}

function Get-Metrics {
    # CPU (2 samples)
    $cpuLoad  = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    if ($null -eq $cpuLoad) { $cpuLoad = 0 }

    # RAM
    $os       = Get-CimInstance Win32_OperatingSystem
    $ramTotal = $os.TotalVisibleMemorySize
    $ramFree  = $os.FreePhysicalMemory
    $ramPct   = if ($ramTotal -gt 0) { [Math]::Round((1 - $ramFree / $ramTotal) * 100, 1) } else { 0 }

    # Disk C:
    $disk     = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $diskPct  = if ($disk -and $disk.Size -gt 0) { [Math]::Round((1 - $disk.FreeSpace / $disk.Size) * 100, 1) } else { 0 }

    # Uptime
    $uptime   = (Get-Date) - $os.LastBootUpTime
    $uptimeSec = [Math]::Round($uptime.TotalSeconds, 0)

    # Process count
    $procCount = (Get-Process -ErrorAction SilentlyContinue | Measure-Object).Count

    # Network (bytes from all adapters)
    $netStats = Get-NetAdapterStatistics -ErrorAction SilentlyContinue
    $bytesSent = ($netStats | Measure-Object -Property SentBytes -Sum).Sum
    $bytesRecv = ($netStats | Measure-Object -Property ReceivedBytes -Sum).Sum

    # Listening ports
    $ports = @()
    try {
        $connections = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
        $ports = ($connections | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object | Select-Object -First 30)
    } catch {}

    return @{
        cpu_percent     = [double]$cpuLoad
        ram_percent     = [double]$ramPct
        disk_percent    = [double]$diskPct
        uptime_seconds  = [double]$uptimeSec
        process_count   = $procCount
        net_bytes_sent  = [double]($bytesSent -as [long])
        net_bytes_recv  = [double]($bytesRecv -as [long])
        open_ports      = $ports
    }
}

# ── PERSISTENCE ──────────────────────────────────────────────────────────────

function Save-AgentUid([string]$Uid) {
    if (-not (Test-Path $AgentDir)) { New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null }
    @{ uid = $Uid } | ConvertTo-Json | Set-Content -Path $AgentFile -Encoding UTF8
}

function Load-AgentUid {
    try { return (Get-Content $AgentFile -Raw | ConvertFrom-Json).uid } catch { return $null }
}

# ── REGISTER ─────────────────────────────────────────────────────────────────

function Register-Agent {
    $info = Get-AgentInfo
    Write-Log "Registrando: $($info.hostname) | $($info.ip_address) | $($info.mac_address)"
    $result = Invoke-Api -Path "/api/agents/register" -Body $info
    if ($result -and $result.uid) {
        Save-AgentUid -Uid $result.uid
        Write-Log "Registrado OK. UID: $($result.uid)" "OK"
        return $result.uid
    }
    Write-Log "Error al registrar agente" "ERROR"
    return $null
}

# ── INSTALL AS SCHEDULED TASK ────────────────────────────────────────────────

function Install-AgentTask {
    $scriptPath = $PSCommandPath
    if (-not $scriptPath) { $scriptPath = "$AgentDir\infrawatch-agent.ps1" }

    # Copy script to permanent location
    if (-not (Test-Path $AgentDir)) { New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null }
    if ($scriptPath -ne "$AgentDir\infrawatch-agent.ps1") {
        Copy-Item -Path $scriptPath -Destination "$AgentDir\infrawatch-agent.ps1" -Force
    }

    $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$AgentDir\infrawatch-agent.ps1`" -ServerUrl `"$ServerUrl`" -Interval $Interval"
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description "InfraWatch Monitoring Agent" | Out-Null

    Start-ScheduledTask -TaskName $TaskName
    Write-Log "Tarea programada '$TaskName' creada e iniciada" "OK"

    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║   ✅  Agente InfraWatch instalado en Windows     ║" -ForegroundColor Green
    Write-Host "╠══════════════════════════════════════════════════╣" -ForegroundColor Green
    Write-Host "║  Servidor:  $ServerUrl" -ForegroundColor Cyan
    Write-Host "║  Hostname:  $($env:COMPUTERNAME)" -ForegroundColor Cyan
    Write-Host "║  Tarea:     $TaskName" -ForegroundColor Cyan
    Write-Host "╠══════════════════════════════════════════════════╣" -ForegroundColor Green
    Write-Host "║  Ver tarea:  Get-ScheduledTask -TaskName $TaskName" -ForegroundColor White
    Write-Host "║  Parar:      Stop-ScheduledTask -TaskName $TaskName" -ForegroundColor White
    Write-Host "║  Logs:       $LogFile" -ForegroundColor White
    Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
}

function Uninstall-AgentTask {
    Stop-ScheduledTask  -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log "Agente desinstalado" "OK"
}

# ── MAIN LOOP ────────────────────────────────────────────────────────────────

# Handle install/uninstall flags
if ($Uninstall) { Uninstall-AgentTask; exit 0 }
if (-not $ServerUrl) {
    Write-Host "ERROR: Debes especificar -ServerUrl" -ForegroundColor Red
    Write-Host "Ejemplo: .\infrawatch-agent.ps1 -ServerUrl http://192.168.1.100:8000 -Install"
    exit 1
}
if ($Install) { Install-AgentTask; exit 0 }

# ── Run as monitoring loop ───────────────────────────────────────────────────

if (-not (Test-Path $AgentDir)) { New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null }
Write-Log "InfraWatch Agent v$VERSION iniciando | Servidor: $ServerUrl"

$uid    = Load-AgentUid
$errors = 0

if (-not $uid) { $uid = Register-Agent }
if (-not $uid) { Write-Log "No se pudo registrar. Reintentando en 60s..."; Start-Sleep 60; $uid = Register-Agent }
if (-not $uid) { Write-Log "Error fatal. Saliendo."; exit 1 }

Write-Log "Agente activo. UID: $uid | Intervalo: ${Interval}s"

while ($true) {
    try {
        $metrics = Get-Metrics
        $result  = Invoke-Api -Path "/api/agents/$uid/heartbeat" -Body $metrics
        if ($result) {
            Write-Log "Heartbeat OK | CPU:$($metrics.cpu_percent)% RAM:$($metrics.ram_percent)% Disco:$($metrics.disk_percent)%"
            $errors = 0
        } else {
            $errors++
            Write-Log "Heartbeat fallido ($errors)" "WARN"
            if ($errors -ge 3) { Write-Log "Re-registrando..."; $uid = Register-Agent; $errors = 0 }
        }
    } catch {
        Write-Log "Error: $($_.Exception.Message)" "ERROR"
    }
    Start-Sleep -Seconds $Interval
}
