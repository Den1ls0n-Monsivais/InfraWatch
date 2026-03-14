#!/usr/bin/env python3
"""
InfraWatch Linux Agent
Se registra automáticamente y envía métricas periódicamente
No requiere token — usa hostname/IP/MAC para identificarse
"""

import os, sys, json, time, socket, subprocess, platform, uuid
import urllib.request, urllib.error
from datetime import datetime

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
# Edita esta variable con la IP/dominio de tu servidor InfraWatch
SERVER_URL   = os.getenv("INFRAWATCH_SERVER", "http://INFRAWATCH_SERVER_IP:8000")
INTERVAL_SEC = int(os.getenv("INFRAWATCH_INTERVAL", "60"))
AGENT_FILE   = "/etc/infrawatch/agent.json"
VERSION      = "1.0"
# ─────────────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def api_post(path, data):
    url  = f"{SERVER_URL}{path}"
    body = json.dumps(data).encode()
    req  = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        log(f"HTTP Error {e.code}: {e.read().decode()}")
    except Exception as e:
        log(f"Error API: {e}")
    return None

def get_mac():
    try:
        for iface in ["eth0","ens33","ens3","enp0s3","bond0","em1","wlan0","wlp2s0"]:
            path = f"/sys/class/net/{iface}/address"
            if os.path.exists(path):
                mac = open(path).read().strip()
                if mac and mac != "00:00:00:00:00:00":
                    return mac.upper()
        # Fallback
        for line in open("/proc/net/arp"):
            parts = line.split()
            if len(parts) >= 4 and parts[3] not in ("00:00:00:00:00:00",""):
                return parts[3].upper()
    except:
        pass
    return str(uuid.uuid4())[:17].upper()

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_cpu_model():
    try:
        for line in open("/proc/cpuinfo"):
            if "model name" in line:
                return line.split(":")[1].strip()
    except:
        pass
    return platform.processor() or "Unknown CPU"

def get_cpu_cores():
    try:
        return int(subprocess.check_output(["nproc"], text=True).strip())
    except:
        return os.cpu_count() or 1

def get_ram_total_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 2)
    except:
        pass
    return 0.0

def get_disk_total_gb():
    try:
        out = subprocess.check_output(["df", "/", "--output=size", "-BG"], text=True)
        return round(float(out.split("\n")[1].strip().rstrip("G")), 1)
    except:
        return 0.0

def get_metrics():
    metrics = {
        "cpu_percent": 0, "ram_percent": 0, "disk_percent": 0,
        "net_bytes_sent": 0, "net_bytes_recv": 0,
        "uptime_seconds": 0, "process_count": 0, "open_ports": []
    }
    # CPU (2-sample average)
    try:
        def cpu_sample():
            data = open("/proc/stat").readline().split()
            idle = int(data[4])
            total = sum(int(x) for x in data[1:])
            return idle, total
        i1, t1 = cpu_sample(); time.sleep(1); i2, t2 = cpu_sample()
        idle_delta = i2 - i1; total_delta = t2 - t1
        metrics["cpu_percent"] = round((1 - idle_delta / max(total_delta, 1)) * 100, 1)
    except:
        pass
    # RAM
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":"); mem[k.strip()] = int(v.split()[0])
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", mem.get("MemFree", 0))
        if total:
            metrics["ram_percent"] = round((1 - avail / total) * 100, 1)
    except:
        pass
    # Disk
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free  = st.f_bavail * st.f_frsize
        if total:
            metrics["disk_percent"] = round((1 - free / total) * 100, 1)
    except:
        pass
    # Network
    try:
        def net_sample():
            for line in open("/proc/net/dev"):
                if not line.strip().startswith(("Inter","face","lo","docker","veth","br-")):
                    parts = line.split()
                    if len(parts) > 9:
                        return int(parts[1]), int(parts[9])
            return 0, 0
        r1, s1 = net_sample(); time.sleep(0.5); r2, s2 = net_sample()
        metrics["net_bytes_recv"] = max(0, r2 - r1)
        metrics["net_bytes_sent"] = max(0, s2 - s1)
    except:
        pass
    # Uptime
    try:
        metrics["uptime_seconds"] = float(open("/proc/uptime").read().split()[0])
    except:
        pass
    # Processes
    try:
        metrics["process_count"] = len([p for p in os.listdir("/proc") if p.isdigit()])
    except:
        pass
    # Open ports
    try:
        ports = set()
        for f in ["/proc/net/tcp", "/proc/net/tcp6"]:
            if not os.path.exists(f): continue
            for line in open(f):
                parts = line.split()
                if len(parts) > 3 and parts[3] == "0A":  # LISTEN
                    port = int(parts[1].split(":")[1], 16)
                    if 0 < port < 65536:
                        ports.add(port)
        metrics["open_ports"] = sorted(list(ports))[:30]
    except:
        pass
    return metrics

def save_uid(uid):
    os.makedirs(os.path.dirname(AGENT_FILE), exist_ok=True)
    json.dump({"uid": uid}, open(AGENT_FILE, "w"))

def load_uid():
    try:
        return json.load(open(AGENT_FILE)).get("uid")
    except:
        return None

def register():
    hostname = socket.gethostname()
    ip       = get_ip()
    mac      = get_mac()
    log(f"Registrando agente: {hostname} | {ip} | {mac}")
    data = {
        "hostname":      hostname,
        "ip_address":    ip,
        "mac_address":   mac,
        "os_name":       platform.system(),
        "os_version":    platform.release(),
        "cpu_model":     get_cpu_model(),
        "cpu_cores":     get_cpu_cores(),
        "ram_total_gb":  get_ram_total_gb(),
        "disk_total_gb": get_disk_total_gb(),
        "agent_version": VERSION,
    }
    result = api_post("/api/agents/register", data)
    if result and "uid" in result:
        save_uid(result["uid"])
        log(f"✅ Registrado con UID: {result['uid']} (nuevo={result.get('registered',False)})")
        return result["uid"]
    else:
        log("❌ Error al registrar agente")
        return None

def main():
    log(f"InfraWatch Agent v{VERSION} | Servidor: {SERVER_URL}")
    uid = load_uid()
    if not uid:
        uid = register()
    if not uid:
        log("No se pudo registrar. Reintentando en 60s...")
        time.sleep(60)
        return main()

    log(f"Agente activo. UID: {uid} | Intervalo: {INTERVAL_SEC}s")
    errors = 0
    while True:
        try:
            metrics = get_metrics()
            result  = api_post(f"/api/agents/{uid}/heartbeat", metrics)
            if result:
                log(f"✅ Heartbeat OK | CPU:{metrics['cpu_percent']}% RAM:{metrics['ram_percent']}% Disco:{metrics['disk_percent']}%")
                errors = 0
            else:
                errors += 1
                log(f"⚠ Heartbeat fallido ({errors}). Re-registrando...")
                if errors >= 3:
                    uid = register()
                    errors = 0
        except KeyboardInterrupt:
            log("Agente detenido."); sys.exit(0)
        except Exception as e:
            log(f"Error inesperado: {e}")
        time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    main()
