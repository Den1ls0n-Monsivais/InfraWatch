#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  InfraWatch Agent v2.3 — Instalador Linux                  ║
# ║  Soporta: Debian/Ubuntu, RHEL/CentOS, Arch                 ║
# ║  ✦ Auto-descubrimiento del servidor                        ║
# ║  ✦ Si no encuentra en 60s → solicita IP manual             ║
# ║  ✦ Instala como servicio systemd                           ║
# ║  ✦ Soporte de tags                                         ║
# ╚══════════════════════════════════════════════════════════════╝
#
# Uso:
#   sudo bash install_linux.sh                        # Descubrimiento automático
#   sudo bash install_linux.sh --server 192.168.1.10  # IP manual
#   sudo bash install_linux.sh --server 192.168.1.10 --tags "SERVIDOR,PROD"

set -euo pipefail

# ── Colores ───────────────────────────────────────────────────────────────────
G='\033[0;32m'; C='\033[0;36m'; Y='\033[1;33m'
R='\033[0;31m'; B='\033[0;34m'; N='\033[0m'; W='\033[1;37m'
info()  { echo -e "${C}[IW]${N} $1"; }
ok()    { echo -e "${G}[✓]${N} $1"; }
warn()  { echo -e "${Y}[!]${N} $1"; }
err()   { echo -e "${R}[✗]${N} $1"; }
step()  { echo -e "\n${W}── $1${N}"; }

# ── Argumentos ────────────────────────────────────────────────────────────────
SERVER_IP=""
AGENT_TAGS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server)  SERVER_IP="$2";   shift 2 ;;
        --tags)    AGENT_TAGS="$2";  shift 2 ;;
        --help|-h)
            echo "Uso: sudo bash install_linux.sh [--server IP] [--tags 'TAG1,TAG2']"
            exit 0 ;;
        *) shift ;;
    esac
done

# ── Verificaciones iniciales ──────────────────────────────────────────────────
step "Verificando requisitos"

if [[ $EUID -ne 0 ]]; then
    err "Este instalador debe ejecutarse como root"
    echo "   Usa: sudo bash install_linux.sh"
    exit 1
fi
ok "Ejecutando como root"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
AGENT_SRC="$SCRIPT_DIR/agent.py"

if [[ ! -f "$AGENT_SRC" ]]; then
    err "No se encontró agent.py en $SCRIPT_DIR"
    exit 1
fi
ok "agent.py encontrado"

# ── Rutas de instalación ──────────────────────────────────────────────────────
INSTALL_DIR="/opt/infrawatch/agent"
CONFIG_DIR="/etc/infrawatch"
LOG_DIR="/var/log/infrawatch"
SVC_FILE="/etc/systemd/system/infrawatch-agent.service"

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR"

# ── Detectar gestor de paquetes ───────────────────────────────────────────────
step "Detectando sistema"
PKG_MGR=""
if   command -v apt-get  &>/dev/null; then PKG_MGR="apt"
elif command -v dnf      &>/dev/null; then PKG_MGR="dnf"
elif command -v yum      &>/dev/null; then PKG_MGR="yum"
elif command -v pacman   &>/dev/null; then PKG_MGR="pacman"
fi
info "Gestor de paquetes: ${PKG_MGR:-desconocido}"

# ── Instalar Python3 si no existe ─────────────────────────────────────────────
step "Python 3"
if ! command -v python3 &>/dev/null; then
    warn "Python3 no encontrado — instalando..."
    case "$PKG_MGR" in
        apt)     apt-get update -qq && apt-get install -y -q python3 python3-pip ;;
        dnf)     dnf install -y python3 python3-pip ;;
        yum)     yum install -y python3 python3-pip ;;
        pacman)  pacman -S --noconfirm python python-pip ;;
        *)       err "No se pudo instalar Python3 automáticamente. Instálalo manualmente."; exit 1 ;;
    esac
fi

PYTHON=$(command -v python3)
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PY_VER en $PYTHON"

# ── Instalar pip si no está ───────────────────────────────────────────────────
if ! "$PYTHON" -m pip --version &>/dev/null; then
    warn "pip no encontrado — instalando..."
    case "$PKG_MGR" in
        apt)    apt-get install -y -q python3-pip ;;
        dnf|yum) dnf install -y python3-pip || yum install -y python3-pip ;;
        *)      curl -sS https://bootstrap.pypa.io/get-pip.py | "$PYTHON" ;;
    esac
fi
ok "pip disponible"

# ── Instalar dependencias ─────────────────────────────────────────────────────
step "Instalando dependencias"
"$PYTHON" -m pip install psutil --quiet --break-system-packages 2>/dev/null || \
"$PYTHON" -m pip install psutil --quiet || true
ok "psutil instalado"

# ── Copiar agente ─────────────────────────────────────────────────────────────
step "Copiando archivos"
cp "$AGENT_SRC" "$INSTALL_DIR/agent.py"
chmod 750 "$INSTALL_DIR/agent.py"
ok "agent.py → $INSTALL_DIR/agent.py"

# ── Descubrir o configurar servidor ──────────────────────────────────────────
step "Configurando servidor"

discover_server() {
    local timeout=60
    local deadline=$((SECONDS + timeout))
    local gw=""
    local subnet=""
    local local_ip=""

    # Obtener IP y gateway
    local_ip=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K\S+' | head -1 || echo "")
    gw=$(ip route show default 2>/dev/null | grep -oP 'via \K\S+' | head -1 || echo "")
    subnet=$(echo "$local_ip" | cut -d. -f1-3)

    info "IP local: ${local_ip:-desconocida}  Gateway: ${gw:-desconocido}"

    # 1. Probar gateway
    if [[ -n "$gw" ]]; then
        info "Probando gateway $gw..."
        if curl -sf --connect-timeout 3 "http://$gw:8000/api/health" 2>/dev/null | grep -q '"InfraWatch"'; then
            echo "$gw"; return 0
        fi
    fi

    # 2. Escanear IPs comunes del subnet
    if [[ -n "$subnet" ]]; then
        info "Escaneando $subnet.0/24..."
        for last in 1 2 10 20 50 100 101 200 201 254; do
            [[ $SECONDS -ge $deadline ]] && break
            ip_try="$subnet.$last"
            if curl -sf --connect-timeout 2 "http://$ip_try:8000/api/health" 2>/dev/null | grep -q '"InfraWatch"'; then
                echo "$ip_try"; return 0
            fi
        done
    fi

    return 1
}

if [[ -n "$SERVER_IP" ]]; then
    info "Usando IP especificada: $SERVER_IP"
    if ! curl -sf --connect-timeout 5 "http://$SERVER_IP:8000/api/health" 2>/dev/null | grep -q '"InfraWatch"'; then
        warn "No se puede verificar el servidor en $SERVER_IP:8000"
        warn "¿Continuar de todos modos? [s/N]"
        read -r resp
        [[ "${resp,,}" != "s" ]] && exit 1
    fi
else
    info "Buscando servidor InfraWatch en la red (60 segundos)..."
    if SERVER_IP=$(discover_server); then
        ok "Servidor encontrado: $SERVER_IP"
    else
        warn "No se encontró servidor InfraWatch automáticamente"
        echo ""
        read -p "  Ingresa la IP del servidor InfraWatch: " SERVER_IP
        SERVER_IP="${SERVER_IP// /}"
        if [[ -z "$SERVER_IP" ]]; then
            err "IP no proporcionada. Abortando."
            exit 1
        fi
    fi
fi

ok "Servidor configurado: $SERVER_IP"

# ── Guardar configuración ─────────────────────────────────────────────────────
step "Guardando configuración"

TAGS_JSON="[]"
if [[ -n "$AGENT_TAGS" ]]; then
    # Convertir "TAG1,TAG2,TAG3" a JSON array
    TAGS_JSON=$(python3 -c "
import json, sys
raw = '$AGENT_TAGS'
tags = [t.strip().upper() for t in raw.split(',') if t.strip()]
print(json.dumps(tags))
")
fi

python3 -c "
import json
cfg = {
    'server_url': 'http://$SERVER_IP:8000',
    'tags': $TAGS_JSON,
    'version': '2.3',
    'installed_at': '$(date +%Y-%m-%d\ %H:%M:%S)',
}
with open('$CONFIG_DIR/config.json', 'w') as f:
    json.dump(cfg, f, indent=2)
print('Config guardada')
"
ok "Configuración guardada en $CONFIG_DIR/config.json"

# ── Crear servicio systemd ────────────────────────────────────────────────────
step "Creando servicio systemd"

cat > "$SVC_FILE" <<EOF
[Unit]
Description=InfraWatch Agent v2.3
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$PYTHON $INSTALL_DIR/agent.py --run
Restart=always
RestartSec=15
User=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=infrawatch-agent
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

ok "Archivo de servicio creado: $SVC_FILE"

# ── Activar y arrancar servicio ───────────────────────────────────────────────
step "Iniciando servicio"

systemctl daemon-reload
systemctl enable infrawatch-agent --now

sleep 3  # Esperar a que inicie

if systemctl is-active --quiet infrawatch-agent; then
    ok "Servicio ACTIVO"
    ACTIVE_STATUS="${G}ACTIVO${N}"
else
    warn "El servicio no pudo iniciar"
    ACTIVE_STATUS="${Y}INACTIVO${N}"
fi

# ── Registrar agente (primera ejecución) ──────────────────────────────────────
step "Verificando conexión con servidor"

if curl -sf "http://$SERVER_IP:8000/api/health" | grep -q '"InfraWatch"'; then
    ok "Conexión con servidor: OK"
else
    warn "No se pudo verificar el servidor. El agente reintentará automáticamente."
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${G}╔══════════════════════════════════════════════════════════════╗${N}"
echo -e "${G}║  ✅  InfraWatch Agent v2.3 — Instalado                      ║${N}"
echo -e "${G}╠══════════════════════════════════════════════════════════════╣${N}"
echo -e "${G}║${N}  Estado:       $(echo -e "$ACTIVE_STATUS")"
echo -e "${G}║${N}  Servidor:     http://$SERVER_IP:8000"
echo -e "${G}║${N}  Agente:       $INSTALL_DIR/agent.py"
echo -e "${G}║${N}  Config:       $CONFIG_DIR/config.json"
echo -e "${G}║${N}  Tags:         ${AGENT_TAGS:-ninguna}"
echo -e "${G}╠══════════════════════════════════════════════════════════════╣${N}"
echo -e "${G}║${N}  Comandos útiles:"
echo -e "${G}║${N}    systemctl status infrawatch-agent"
echo -e "${G}║${N}    journalctl -u infrawatch-agent -f"
echo -e "${G}║${N}    systemctl restart infrawatch-agent"
echo -e "${G}║${N}    python3 $INSTALL_DIR/agent.py --status"
echo -e "${G}╚══════════════════════════════════════════════════════════════╝${N}"
echo ""
