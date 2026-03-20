"""
╔══════════════════════════════════════════════════════════════╗
║  InfraWatch Agent v2.3                                       ║
║  Plataformas: Windows & Linux                                ║
║  ✦ Auto-descubrimiento del servidor (broadcast + escaneo)   ║
║  ✦ Si no encuentra en 60s → modo manual                     ║
║  ✦ Software instalado (Windows registry / dpkg / rpm)       ║
║  ✦ Métricas: CPU, RAM, disco, red, puertos, uptime          ║
║  ✦ Tags configurables                                        ║
║  ✦ Se instala como servicio (Windows / systemd)              ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, socket, logging, subprocess, platform
import threading, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

# ── Auto-instalar psutil si no está ───────────────────────────────────────────
try:
    import psutil
except ImportError:
    print("[IW] Instalando psutil...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "-q"])
    import psutil

# ── Plataforma ────────────────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# ── Directorios de configuración ──────────────────────────────────────────────
if IS_WINDOWS:
    CONFIG_DIR = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "InfraWatch"
else:
    CONFIG_DIR = Path("/etc/infrawatch")

CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE    = CONFIG_DIR / "agent.log"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("iw-agent")

# ── Constantes ────────────────────────────────────────────────────────────────
DISCOVERY_UDP_PORT  = 47777
HEARTBEAT_INTERVAL  = 30     # segundos entre heartbeats
SOFTWARE_INTERVAL   = 300    # segundos entre escaneos de software (5 min)
DISCOVERY_TIMEOUT   = 60     # segundos antes de pedir IP manual
VERSION             = "2.3"

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ─────────────────────────────────────────────────────────────────────────────
#  DESCUBRIMIENTO DE SERVIDOR
# ─────────────────────────────────────────────────────────────────────────────

def ping_server(ip: str, port: int = 8000, timeout: int = 3) -> bool:
    """Verifica si hay un servidor InfraWatch en ip:port"""
    try:
        url = f"http://{ip}:{port}/api/health"
        req = urllib.request.Request(
            url, headers={"User-Agent": f"InfraWatch-Agent/{VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
            return data.get("app") == "InfraWatch"
    except Exception:
        return False

def get_default_gateway() -> str:
    """Obtiene la IP del gateway por defecto"""
    try:
        if IS_WINDOWS:
            out = subprocess.check_output(
                "ipconfig", encoding="utf-8", errors="ignore"
            )
            for line in out.splitlines():
                if "Default Gateway" in line or "Puerta de enlace predeterminada" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        gw = parts[-1].strip()
                        if gw and "." in gw and gw != "0.0.0.0":
                            return gw
        else:
            out = subprocess.check_output(
                ["ip", "route", "show", "default"],
                encoding="utf-8", errors="ignore"
            )
            for line in out.splitlines():
                if "default via" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2]
    except Exception:
        pass
    return ""

def get_local_ip() -> str:
    """Obtiene la IP local de la interfaz principal"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def discover_via_broadcast(timeout: int = 5) -> str:
    """Envía broadcast UDP — el servidor responde con su IP"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        msg = b"INFRAWATCH_DISCOVER_V23"
        sock.sendto(msg, ("<broadcast>", DISCOVERY_UDP_PORT))
        data, addr = sock.recvfrom(512)
        sock.close()
        if b"INFRAWATCH_HERE" in data:
            log.info(f"🔍 Broadcast: servidor en {addr[0]}")
            return addr[0]
    except Exception:
        pass
    return ""

def discover_server(timeout_total: int = DISCOVERY_TIMEOUT,
                    progress_cb=None) -> str:
    """
    Estrategia de descubrimiento (en orden):
    1. Broadcast UDP
    2. Gateway
    3. IPs comunes del subnet
    """
    deadline = time.time() + timeout_total
    local_ip = get_local_ip()
    subnet   = ".".join(local_ip.split(".")[:3])  # ej: "192.168.1"

    # 1 — Broadcast
    if progress_cb: progress_cb("Enviando broadcast UDP...", 5)
    ip = discover_via_broadcast(timeout=4)
    if ip and ping_server(ip):
        return ip

    # 2 — Gateway
    gw = get_default_gateway()
    if gw:
        if progress_cb: progress_cb(f"Probando gateway {gw}...", 15)
        if ping_server(gw):
            log.info(f"✅ Servidor en gateway: {gw}")
            return gw

    # 3 — IPs comunes del subnet
    common_last = [1, 2, 10, 20, 50, 100, 101, 200, 201, 254]
    all_candidates = [f"{subnet}.{n}" for n in common_last]

    log.info(f"🔍 Escaneando subnet {subnet}.0/24 (candidatas: {len(all_candidates)})...")

    def check(ip_):
        return ip_ if ping_server(ip_, timeout=2) else None

    pct = 20
    for candidate in all_candidates:
        if time.time() > deadline:
            break
        if progress_cb: progress_cb(f"Probando {candidate}...", min(pct, 90))
        pct += 5
        result = check(candidate)
        if result:
            log.info(f"✅ Servidor encontrado: {result}")
            return result

    return ""

# ─────────────────────────────────────────────────────────────────────────────
#  INFORMACIÓN DEL SISTEMA
# ─────────────────────────────────────────────────────────────────────────────

def get_system_info() -> dict:
    """Recopila info estática del equipo para el registro"""
    info = {
        "hostname":      socket.gethostname(),
        "ip_address":    get_local_ip(),
        "mac_address":   _get_mac(),
        "os_name":       platform.system(),
        "os_version":    platform.version()[:120],
        "cpu_model":     _get_cpu_model()[:100],
        "cpu_cores":     psutil.cpu_count(logical=True) or 0,
        "ram_total_gb":  round(psutil.virtual_memory().total / (1024**3), 2),
        "disk_total_gb": _get_disk_total(),
        "agent_version": VERSION,
    }
    return info

def _get_mac() -> str:
    try:
        import uuid
        mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
        return ":".join(mac[i:i+2] for i in range(0, 12, 2)).upper()
    except Exception:
        return "00:00:00:00:00:00"

def _get_cpu_model() -> str:
    try:
        if IS_WINDOWS:
            out = subprocess.check_output(
                "wmic cpu get name /value",
                shell=True, encoding="utf-8", errors="ignore"
            )
            for line in out.splitlines():
                if "Name=" in line and len(line) > 5:
                    return line.split("=", 1)[1].strip()
        else:
            with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "Unknown CPU"

def _get_disk_total() -> float:
    try:
        root = "C:\\" if IS_WINDOWS else "/"
        return round(psutil.disk_usage(root).total / (1024**3), 2)
    except Exception:
        return 0.0

# ─────────────────────────────────────────────────────────────────────────────
#  MÉTRICAS EN TIEMPO REAL
# ─────────────────────────────────────────────────────────────────────────────

def get_metrics() -> dict:
    """Métricas para el heartbeat"""
    try:
        root   = "C:\\" if IS_WINDOWS else "/"
        net    = psutil.net_io_counters()
        disk   = psutil.disk_usage(root)
        cpu    = psutil.cpu_percent(interval=1)
        ram    = psutil.virtual_memory()
        uptime = time.time() - psutil.boot_time()

        ports = []
        try:
            for c in psutil.net_connections(kind="inet"):
                if getattr(c, "status", "") == "LISTEN":
                    p = c.laddr.port if hasattr(c.laddr, "port") else 0
                    if p and p not in ports:
                        ports.append(p)
        except Exception:
            pass

        return {
            "cpu_percent":    round(cpu, 1),
            "ram_percent":    round(ram.percent, 1),
            "disk_percent":   round(disk.percent, 1),
            "net_bytes_sent": net.bytes_sent,
            "net_bytes_recv": net.bytes_recv,
            "uptime_seconds": round(uptime, 0),
            "process_count":  len(psutil.pids()),
            "open_ports":     sorted(ports)[:60],
        }
    except Exception as e:
        log.error(f"Error en métricas: {e}")
        return {
            "cpu_percent": 0, "ram_percent": 0, "disk_percent": 0,
            "net_bytes_sent": 0, "net_bytes_recv": 0, "uptime_seconds": 0,
            "process_count": 0, "open_ports": [],
        }

# ─────────────────────────────────────────────────────────────────────────────
#  SOFTWARE INSTALADO
# ─────────────────────────────────────────────────────────────────────────────

def get_installed_software() -> list:
    """Devuelve lista de software instalado según la plataforma"""
    log.info("📦 Escaneando software instalado...")
    software = []

    if IS_WINDOWS:
        software = _software_windows()
    elif IS_LINUX:
        software = _software_linux()

    # Deduplicar por nombre
    seen, unique = set(), []
    for s in software:
        key = s.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(s)

    unique.sort(key=lambda x: x.get("name", "").lower())
    log.info(f"📦 {len(unique)} programas detectados")
    return unique[:600]

def _software_windows() -> list:
    """Lee el registro de Windows para obtener programas instalados"""
    items = []
    try:
        import winreg
        hives_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, path in hives_paths:
            try:
                root = winreg.OpenKey(hive, path)
                count = winreg.QueryInfoKey(root)[0]
                for i in range(count):
                    try:
                        sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
                        def rval(k, d=""):
                            try: return winreg.QueryValueEx(sub, k)[0]
                            except: return d
                        name = rval("DisplayName")
                        if not name or not name.strip():
                            continue
                        items.append({
                            "name":         str(name)[:120],
                            "version":      str(rval("DisplayVersion"))[:60],
                            "publisher":    str(rval("Publisher"))[:100],
                            "install_date": str(rval("InstallDate"))[:20],
                        })
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception as e:
        log.warning(f"Software Windows error: {e}")
    return items

def _software_linux() -> list:
    """Obtiene software en Linux via dpkg, rpm o pacman"""
    items = []

    # Debian/Ubuntu
    try:
        out = subprocess.check_output(
            ["dpkg-query", "-W",
             "--showformat=${Package}\t${Version}\t${Maintainer}\t${Installed-Size}\n"],
            encoding="utf-8", errors="ignore", timeout=30
        )
        for line in out.strip().splitlines():
            p = line.split("\t")
            if p[0].strip():
                items.append({
                    "name":         p[0].strip()[:120],
                    "version":      p[1].strip()[:60] if len(p) > 1 else "",
                    "publisher":    p[2].strip()[:100] if len(p) > 2 else "",
                    "install_date": "",
                })
        if items:
            return items
    except Exception:
        pass

    # RHEL/CentOS/Fedora
    try:
        out = subprocess.check_output(
            ["rpm", "-qa", "--queryformat",
             "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VENDOR}\n"],
            encoding="utf-8", errors="ignore", timeout=30
        )
        for line in out.strip().splitlines():
            p = line.split("\t")
            if p[0].strip():
                items.append({
                    "name":         p[0].strip()[:120],
                    "version":      p[1].strip()[:60] if len(p) > 1 else "",
                    "publisher":    p[2].strip()[:100] if len(p) > 2 else "",
                    "install_date": "",
                })
        if items:
            return items
    except Exception:
        pass

    # Arch Linux / pacman
    try:
        out = subprocess.check_output(
            ["pacman", "-Q"],
            encoding="utf-8", errors="ignore", timeout=30
        )
        for line in out.strip().splitlines():
            p = line.split()
            if len(p) >= 2:
                items.append({
                    "name": p[0][:120], "version": p[1][:60],
                    "publisher": "", "install_date": "",
                })
        if items:
            return items
    except Exception:
        pass

    return items

# ─────────────────────────────────────────────────────────────────────────────
#  HTTP HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def http_post(url: str, data: dict, timeout: int = 15) -> dict:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req  = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type":  "application/json",
            "User-Agent":    f"InfraWatch-Agent/{VERSION}",
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def http_get(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": f"InfraWatch-Agent/{VERSION}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

# ─────────────────────────────────────────────────────────────────────────────
#  AGENTE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class InfraWatchAgent:

    def __init__(self):
        self.cfg        = load_config()
        self.server_url = self.cfg.get("server_url", "")
        self.uid        = self.cfg.get("uid", "")
        self.agent_id   = self.cfg.get("agent_id", None)
        self.tags       = self.cfg.get("tags", [])
        self._sw_cache  = []
        self._sw_ts     = 0.0
        self._running   = True

    # ── Setup ──────────────────────────────────────────────────────────────

    def configure_server(self, server_ip: str = None, progress_cb=None):
        """Determina la URL del servidor (config, argumento o descubrimiento)"""
        if server_ip:
            self.server_url = f"http://{server_ip}:8000"
        elif self.server_url:
            log.info(f"📡 Usando servidor guardado: {self.server_url}")
            return
        else:
            log.info("🔍 Buscando servidor InfraWatch...")
            ip = discover_server(DISCOVERY_TIMEOUT, progress_cb=progress_cb)
            if not ip:
                raise ConnectionError(
                    "Servidor InfraWatch no encontrado en la red. "
                    "Usa --server IP para especificarlo manualmente."
                )
            self.server_url = f"http://{ip}:8000"

        self.cfg["server_url"] = self.server_url
        save_config(self.cfg)
        log.info(f"✅ Servidor configurado: {self.server_url}")

    # ── Registro ───────────────────────────────────────────────────────────

    def register(self):
        """Registra o actualiza el agente en el servidor"""
        data = get_system_info()
        r    = http_post(f"{self.server_url}/api/agents/register", data)
        self.uid      = r.get("uid", self.uid)
        self.agent_id = r.get("id",  self.agent_id)
        self.cfg.update({"uid": self.uid, "agent_id": self.agent_id})
        save_config(self.cfg)

        # Aplicar tags si hay
        if self.tags:
            self._push_tags()

        log.info(f"✅ Registrado — uid={self.uid}  id={self.agent_id}")

    def _push_tags(self):
        try:
            http_post(
                f"{self.server_url}/api/agents/{self.agent_id}/tags",
                {"tags": self.tags}
            )
        except Exception as e:
            log.warning(f"Tags error: {e}")

    # ── Heartbeat ──────────────────────────────────────────────────────────

    def send_heartbeat(self):
        if not self.uid:
            return
        metrics = get_metrics()
        try:
            http_post(f"{self.server_url}/api/agents/{self.uid}/heartbeat", metrics)
        except Exception as e:
            log.warning(f"Heartbeat error: {e}")
            raise  # re-raise para que el loop principal lo maneje

    # ── Software ───────────────────────────────────────────────────────────

    def _maybe_send_software(self):
        now = time.time()
        if now - self._sw_ts < SOFTWARE_INTERVAL:
            return
        self._sw_cache = get_installed_software()
        self._sw_ts    = now
        if not self._sw_cache:
            return
        try:
            http_post(
                f"{self.server_url}/api/agents/{self.uid}/software",
                {"software": self._sw_cache}
            )
            log.info(f"📦 Software enviado: {len(self._sw_cache)} paquetes")
        except Exception as e:
            log.warning(f"Software upload error: {e}")

    # ── Thresholds (obtener del servidor) ──────────────────────────────────

    def _get_thresholds(self) -> dict:
        try:
            return http_get(
                f"{self.server_url}/api/agents/{self.agent_id}/thresholds"
            )
        except Exception:
            return {}

    # ── Bucle principal ────────────────────────────────────────────────────

    def run(self, server_ip: str = None, progress_cb=None):
        """Bucle principal — se llama desde el servicio o CLI"""
        # 1. Configurar servidor
        self.configure_server(server_ip, progress_cb=progress_cb)

        # 2. Registrar (con reintentos)
        retry = 0
        while self._running:
            try:
                self.register()
                break
            except Exception as e:
                retry += 1
                wait = min(30 * retry, 300)
                log.error(f"Registro error (intento {retry}): {e} — reintentando en {wait}s")
                time.sleep(wait)

        # 3. Primer escaneo de software en hilo aparte
        threading.Thread(
            target=self._maybe_send_software,
            daemon=True, name="sw-scan"
        ).start()

        # 4. Bucle de heartbeat
        log.info(f"🚀 Agente activo — heartbeat cada {HEARTBEAT_INTERVAL}s")
        consec_errors = 0
        while self._running:
            try:
                self.send_heartbeat()
                self._maybe_send_software()
                consec_errors = 0
            except Exception as e:
                consec_errors += 1
                log.error(f"Error en bucle ({consec_errors} consecutivos): {e}")
                if consec_errors >= 5:
                    log.warning("Demasiados errores — re-registrando...")
                    try:
                        self.register()
                        consec_errors = 0
                    except Exception:
                        pass
            time.sleep(HEARTBEAT_INTERVAL)

    def stop(self):
        self._running = False


# ─────────────────────────────────────────────────────────────────────────────
#  WINDOWS SERVICE
# ─────────────────────────────────────────────────────────────────────────────

if IS_WINDOWS:
    try:
        import win32serviceutil, win32service, win32event, servicemanager

        class InfraWatchService(win32serviceutil.ServiceFramework):
            _svc_name_         = "InfraWatchAgent"
            _svc_display_name_ = "InfraWatch Agent v2.3"
            _svc_description_  = "Agente de monitoreo InfraWatch — IT Infrastructure Monitor"

            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.stop_event = win32event.CreateEvent(None, 0, 0, None)
                self.agent = InfraWatchAgent()

            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                self.agent.stop()
                win32event.SetEvent(self.stop_event)

            def SvcDoRun(self):
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, "v2.3")
                )
                self.agent.run()

    except ImportError:
        pass  # pywin32 no disponible — el instalador lo gestiona


# ─────────────────────────────────────────────────────────────────────────────
#  LINUX SYSTEMD UNIT
# ─────────────────────────────────────────────────────────────────────────────

SYSTEMD_UNIT = """\
[Unit]
Description=InfraWatch Agent v2.3
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python} {script} --run
Restart=always
RestartSec=15
User=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=infrawatch-agent
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

def install_linux_service(server_ip: str = None):
    if os.geteuid() != 0:
        print("❌ Ejecuta como root: sudo python3 agent.py --install")
        sys.exit(1)
    if server_ip:
        cfg = load_config()
        cfg["server_url"] = f"http://{server_ip}:8000"
        save_config(cfg)
    script  = os.path.abspath(__file__)
    python  = sys.executable
    unit    = SYSTEMD_UNIT.format(python=python, script=script)
    svc_path = "/etc/systemd/system/infrawatch-agent.service"
    with open(svc_path, "w") as f:
        f.write(unit)
    os.system("systemctl daemon-reload")
    os.system("systemctl enable infrawatch-agent --now")
    time.sleep(2)
    rc = os.system("systemctl is-active --quiet infrawatch-agent")
    if rc == 0:
        print("✅ Servicio infrawatch-agent instalado y ACTIVO")
    else:
        print("⚠️  Servicio instalado pero no pudo iniciar.")
        print("   Revisa: journalctl -u infrawatch-agent -n 30")

def uninstall_linux_service():
    os.system("systemctl stop infrawatch-agent 2>/dev/null")
    os.system("systemctl disable infrawatch-agent 2>/dev/null")
    svc = "/etc/systemd/system/infrawatch-agent.service"
    if os.path.exists(svc):
        os.remove(svc)
    os.system("systemctl daemon-reload")
    print("✅ Servicio infrawatch-agent desinstalado")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    # Windows service control (pywin32 intercept)
    if IS_WINDOWS and len(sys.argv) > 1 and sys.argv[1] in \
            ["install", "remove", "start", "stop", "restart", "debug", "update"]:
        try:
            win32serviceutil.HandleCommandLine(InfraWatchService)
        except NameError:
            print("pywin32 no instalado. Usa el instalador .exe")
        return

    parser = argparse.ArgumentParser(
        description="InfraWatch Agent v2.3",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run",       action="store_true",
                        help="Ejecutar agente (modo servicio)")
    parser.add_argument("--server",    metavar="IP",
                        help="IP del servidor InfraWatch")
    parser.add_argument("--tags",      metavar="TAG1,TAG2",
                        help="Tags separados por coma")
    parser.add_argument("--install",   action="store_true",
                        help="Instalar como servicio systemd (Linux, requiere root)")
    parser.add_argument("--uninstall", action="store_true",
                        help="Desinstalar servicio systemd (Linux, requiere root)")
    parser.add_argument("--status",    action="store_true",
                        help="Mostrar estado del agente")
    args = parser.parse_args()

    # Guardar tags si se proporcionaron
    if args.tags:
        cfg  = load_config()
        tags = [t.strip().upper() for t in args.tags.split(",") if t.strip()]
        cfg["tags"] = tags
        save_config(cfg)
        print(f"✅ Tags guardados: {tags}")
        if not (args.run or args.install):
            return

    if args.status:
        cfg = load_config()
        print(json.dumps({
            "server_url": cfg.get("server_url", "no configurado"),
            "uid":        cfg.get("uid", "no registrado"),
            "tags":       cfg.get("tags", []),
            "version":    VERSION,
            "platform":   platform.system(),
            "hostname":   socket.gethostname(),
        }, indent=2, ensure_ascii=False))
        return

    if args.install:
        if IS_LINUX:
            install_linux_service(args.server)
        else:
            print("En Windows usa el instalador .exe")
        return

    if args.uninstall:
        if IS_LINUX:
            uninstall_linux_service()
        return

    # Ejecutar agente (--run o por defecto)
    agent = InfraWatchAgent()
    try:
        agent.run(server_ip=args.server)
    except KeyboardInterrupt:
        log.info("Agente detenido por el usuario")
    except ConnectionError as e:
        log.critical(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
