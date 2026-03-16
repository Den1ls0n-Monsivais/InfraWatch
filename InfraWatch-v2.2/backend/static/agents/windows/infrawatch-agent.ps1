# InfraWatch Agent Windows — Auto-Discovery
# Busca el servidor InfraWatch en la red automaticamente
# PowerShell como Administrador:
#   irm https://raw.githubusercontent.com/Den1ls0n-Monsivais/InfraWatch/main/infrawatch/agents/windows/install.ps1 | iex

param(
    [string]$ServerUrl = $env:INFRAWATCH_SERVER,
    [int]$Port         = 8000,
    [int]$Interval     = 60,
    [switch]$Install,
    [switch]$Uninstall
)

$VERSION   = "2.0"
$AgentDir  = "C:\ProgramData\InfraWatch"
$AgentFile = "$AgentDir\agent.json"
$LogFile   = "$AgentDir\agent.log"
$TaskName  = "InfraWatchAgent"

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $ts   = Get-Date -Format "HH:mm:ss"
    $line = "[$ts][$Level] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

# ─── AUTO-DISCOVERY ──────────────────────────────────────────────────────────

function Find-InfraWatchServer {
    Write-Log "🔍 Buscando servidor InfraWatch en la red..."

    # 1. Probar IPs guardadas anteriormente
    $saved = Load-SavedServer
    if ($saved) {
        Write-Log "Probando servidor guardado: $saved"
        if (Test-Server $saved) { return $saved }
    }

    # 2. Obtener rango de red local
    $localIP = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and
                       $_.IPAddress -ne "127.0.0.1" -and
                       $_.IPAddress -notlike "169.*" } |
        Select-Object -First 1).IPAddress

    if (-not $localIP) { Write-Log "No se pudo detectar IP local" "WARN"; return $null }

    $parts   = $localIP.Split(".")
    $subnet  = "$($parts[0]).$($parts[1]).$($parts[2])"
    Write-Log "Red detectada: $subnet.0/24 — Escaneando puerto $Port..."

    # 3. Escanear subnet en paralelo
    $jobs = @()
    1..254 | ForEach-Object {
        $ip = "$subnet.$_"
        $jobs += Start-Job -ScriptBlock {
            param($ip, $port)
            try {
                $tcp = New-Object System.Net.Sockets.TcpClient
                $con = $tcp.BeginConnect($ip, $port, $null, $null)
                $wait = $con.AsyncWaitHandle.WaitOne(300, $false)
                if ($wait -and $tcp.Connected) {
                    $tcp.Close()
                    # Verify it's InfraWatch
                    $url = "http://${ip}:${port}/api/health"
                    $res = Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
                    if ($res.Content -like "*InfraWatch*") { return "http://${ip}:${port}" }
                }
                $tcp.Close()
            } catch {}
            return $null
        } -ArgumentList $ip, $Port
    }

    # Esperar resultados
    Write-Log "Esperando respuestas..." 
    $found = $null
    $timeout = 15  # segundos máximo
    $elapsed = 0
    while (-not $found -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds 1
        $elapsed++
        foreach ($job in $jobs) {
            if ($job.State -eq "Completed") {
                $result = Receive-Job $job -ErrorAction SilentlyContinue
                if ($result) { $found = $result; break }
            }
        }
        Write-Host "." -NoNewline
    }
    Write-Host ""

    # Limpiar jobs
    $jobs | Stop-Job -ErrorAction SilentlyContinue
    $jobs | Remove-Job -ErrorAction SilentlyContinue

    if ($found) {
        Write-Log "✅ Servidor encontrado: $found"
        Save-Server $found
        return $found
    }

    # 4. Intentar nombre de host común
    foreach ($hostname in @("infrawatch", "infrawatch-server", "monitor", "it-monitor")) {
        try {
            $ip = [System.Net.Dns]::GetHostAddresses($hostname) | Select-Object -First 1
            if ($ip) {
                $url = "http://$($ip.IPAddressToString):${Port}"
                if (Test-Server $url) {
                    Write-Log "✅ Servidor por hostname: $url"
                    Save-Server $url
                    return $url
                }
            }
        } catch {}
    }

    Write-Log "❌ No se encontró el servidor InfraWatch en la red" "ERROR"
    return $null
}

function Test-Server([string]$Url) {
    try {
        $res = Invoke-WebRequest -Uri "$Url/api/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return $res.Content -like "*InfraWatch*"
    } catch { return $false }
}

function Save-Server([string]$Url) {
    if (-not (Test-Path $AgentDir)) { New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null }
    $data = Get-AgentData
    $data.server_url = $Url
    $data | ConvertTo-Json | Set-Content -Path $AgentFile -Encoding UTF8
}

function Load-SavedServer {
    try { return (Get-Content $AgentFile -Raw | ConvertFrom-Json).server_url } catch { return $null }
}

# ─── AGENT DATA ──────────────────────────────────────────────────────────────

function Get-AgentData {
    try { return (Get-Content $AgentFile -Raw | ConvertFrom-Json) } catch { return @{} }
}

function Save-AgentUid([string]$Uid) {
    if (-not (Test-Path $AgentDir)) { New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null }
    $data = Get-AgentData
    $data | Add-Member -MemberType NoteProperty -Name "uid" -Value $Uid -Force
    $data | ConvertTo-Json | Set-Content -Path $AgentFile -Encoding UTF8
}

function Load-AgentUid {
    try { return (Get-Content $AgentFile -Raw | ConvertFrom-Json).uid } catch { return $null }
}

# ─── API ─────────────────────────────────────────────────────────────────────

function Invoke-Api {
    param([string]$ServerUrl, [string]$Path, [hashtable]$Body)
    $url  = "$ServerUrl$Path"
    $json = $Body | ConvertTo-Json -Depth 5 -Compress
    try {
        return Invoke-RestMethod -Uri $url -Method POST -ContentType "application/json" -Body $json -TimeoutSec 15 -ErrorAction Stop
    } catch {
        Write-Log "API Error [$Path]: $($_.Exception.Message)" "WARN"
        return $null
    }
}

# ─── SYSTEM INFO ─────────────────────────────────────────────────────────────

function Get-AgentInfo {
    $hostname = $env:COMPUTERNAME
    $adapter  = Get-NetAdapter | Where-Object { $_.Status -eq "Up" -and $_.HardwareInterface } | Sort-Object Speed -Descending | Select-Object -First 1
    $ip = "127.0.0.1"; $mac = ""
    if ($adapter) {
        $ipInfo = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1
        $ip  = if ($ipInfo) { $ipInfo.IPAddress } else { "127.0.0.1" }
        $mac = $adapter.MacAddress -replace "-",":"
    }
    $os      = Get-CimInstance Win32_OperatingSystem
    $cpu     = Get-CimInstance Win32_Processor | Select-Object -First 1
    $disk    = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction SilentlyContinue
    return @{
        hostname      = $hostname
        ip_address    = $ip
        mac_address   = $mac
        os_name       = "Windows"
        os_version    = $os.Caption -replace "Microsoft Windows ",""
        cpu_model     = $cpu.Name.Trim() -replace '\s+',' '
        cpu_cores     = $cpu.NumberOfLogicalProcessors
        ram_total_gb  = [Math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
        disk_total_gb = if ($disk) { [Math]::Round($disk.Size / 1GB, 1) } else { 0 }
        agent_version = $VERSION
    }
}

function Get-Metrics {
    $cpuLoad  = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    $os       = Get-CimInstance Win32_OperatingSystem
    $ramPct   = if ($os.TotalVisibleMemorySize -gt 0) { [Math]::Round((1 - $os.FreePhysicalMemory / $os.TotalVisibleMemorySize) * 100, 1) } else { 0 }
    $disk     = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $diskPct  = if ($disk -and $disk.Size -gt 0) { [Math]::Round((1 - $disk.FreeSpace / $disk.Size) * 100, 1) } else { 0 }
    $uptime   = (Get-Date) - $os.LastBootUpTime
    $ports    = @()
    try { $ports = (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object | Select-Object -First 30) } catch {}
    return @{
        cpu_percent     = [double]($cpuLoad -as [double])
        ram_percent     = [double]$ramPct
        disk_percent    = [double]$diskPct
        uptime_seconds  = [double][Math]::Round($uptime.TotalSeconds)
        process_count   = (Get-Process -ErrorAction SilentlyContinue | Measure-Object).Count
        net_bytes_sent  = 0.0
        net_bytes_recv  = 0.0
        open_ports      = $ports
    }
}

# ─── INSTALL ─────────────────────────────────────────────────────────────────

function Install-Agent {
    if (-not (Test-Path $AgentDir)) { New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null }

    # Copiar este script al directorio permanente
    $scriptDest = "$AgentDir\infrawatch-agent.ps1"
    Copy-Item -Path $PSCommandPath -Destination $scriptDest -Force -ErrorAction SilentlyContinue

    $action   = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptDest`" -Interval $Interval"
    $triggers  = @(New-ScheduledTaskTrigger -AtStartup)
    $settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
        -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
        -Settings $settings -Principal $principal -Description "InfraWatch Monitoring Agent" | Out-Null
    Start-ScheduledTask -TaskName $TaskName

    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" } | Select-Object -First 1).IPAddress

    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║   ✅  Agente InfraWatch instalado                    ║" -ForegroundColor Green
    Write-Host "╠══════════════════════════════════════════════════════╣" -ForegroundColor Green
    Write-Host "║  Hostname : $($env:COMPUTERNAME)" -ForegroundColor Cyan
    Write-Host "║  IP       : $ip" -ForegroundColor Cyan
    Write-Host "║  Modo     : Auto-Discovery (busca el servidor solo)" -ForegroundColor Cyan
    Write-Host "╠══════════════════════════════════════════════════════╣" -ForegroundColor Green
    Write-Host "║  El equipo aparecerá en InfraWatch en ~60 segundos  ║" -ForegroundColor White
    Write-Host "║  Logs: $LogFile" -ForegroundColor White
    Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
}

function Uninstall-Agent {
    Stop-ScheduledTask  -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log "Agente desinstalado"
}

# ─── MAIN ────────────────────────────────────────────────────────────────────

if ($Uninstall) { Uninstall-Agent; exit 0 }
if ($Install)   { Install-Agent;   exit 0 }

if (-not (Test-Path $AgentDir)) { New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null }
Write-Log "InfraWatch Agent v$VERSION iniciando..."

# Obtener servidor (manual o auto-discovery)
if (-not $ServerUrl) { $ServerUrl = Find-InfraWatchServer }
if (-not $ServerUrl) {
    Write-Log "No se encontró servidor. Reintentando en 5 minutos..." "WARN"
    Start-Sleep -Seconds 300
    $ServerUrl = Find-InfraWatchServer
}
if (-not $ServerUrl) { Write-Log "No se pudo encontrar el servidor. Saliendo." "ERROR"; exit 1 }

Write-Log "Servidor: $ServerUrl"

# Registro
$uid    = Load-AgentUid
$errors = 0

if (-not $uid) {
    $info   = Get-AgentInfo
    $result = Invoke-Api -ServerUrl $ServerUrl -Path "/api/agents/register" -Body $info
    if ($result -and $result.uid) {
        Save-AgentUid -Uid $result.uid
        $uid = $result.uid
        Write-Log "✅ Registrado. UID: $uid"
    } else {
        Write-Log "Error al registrar" "ERROR"; exit 1
    }
}

Write-Log "Agente activo. Intervalo: ${Interval}s"

while ($true) {
    try {
        $metrics = Get-Metrics
        $result  = Invoke-Api -ServerUrl $ServerUrl -Path "/api/agents/$uid/heartbeat" -Body $metrics
        if ($result) {
            Write-Log "✅ Heartbeat OK | CPU:$($metrics.cpu_percent)% RAM:$($metrics.ram_percent)% Disco:$($metrics.disk_percent)%"
            $errors = 0
        } else {
            $errors++
            Write-Log "Heartbeat fallido ($errors)" "WARN"
            if ($errors -ge 5) {
                Write-Log "Re-buscando servidor..."
                $ServerUrl = Find-InfraWatchServer
                if (-not $ServerUrl) { Start-Sleep -Seconds 60; continue }
                $errors = 0
            }
        }
    } catch {
        Write-Log "Error: $($_.Exception.Message)" "ERROR"
    }
    Start-Sleep -Seconds $Interval
}
