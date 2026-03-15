#!/bin/bash
# InfraWatch — Instalador de Agente Linux
# Uso: curl -sSL https://raw.githubusercontent.com/TU_USUARIO/infrawatch/main/agents/linux/install.sh | INFRAWATCH_SERVER=http://IP:8000 bash

set -e

INFRAWATCH_SERVER="${INFRAWATCH_SERVER:-http://INFRAWATCH_SERVER_IP:8000}"
INFRAWATCH_INTERVAL="${INFRAWATCH_INTERVAL:-60}"
AGENT_DIR="/opt/infrawatch-agent"
SERVICE_FILE="/etc/systemd/system/infrawatch-agent.service"
AGENT_SCRIPT="${AGENT_DIR}/infrawatch-agent.py"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

info()    { echo -e "${CYAN}[InfraWatch]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo -e "${CYAN}"
echo "  ___        __          _       _       _     "
echo " |_ _|_ __  / _|_ __ __ _| |   _ | | __ _| |_ ___| |__  "
echo "  | || '_ \| |_| '__/ _\` | |  | || |/ _\` | __/ __| '_ \ "
echo "  | || | | |  _| | | (_| | |  |__   _| (_| | || (__| | | |"
echo " |___|_| |_|_| |_|  \__,_|_|     |_|  \__,_|\__\___|_| |_|"
echo -e "${NC}"
info "Instalador de Agente Linux v1.0"
info "Servidor: ${INFRAWATCH_SERVER}"
echo ""

# Check root
[[ $EUID -ne 0 ]] && error "Ejecuta como root: sudo bash install.sh"

# Check python3
if ! command -v python3 &>/dev/null; then
    info "Instalando Python3..."
    if command -v apt-get &>/dev/null; then apt-get install -y python3
    elif command -v yum &>/dev/null;     then yum install -y python3
    elif command -v dnf &>/dev/null;     then dnf install -y python3
    else error "No se pudo instalar Python3. Instálalo manualmente."; fi
fi
success "Python3 disponible: $(python3 --version)"

# Create directories
mkdir -p "${AGENT_DIR}" /etc/infrawatch
success "Directorio: ${AGENT_DIR}"

# Download or copy agent script
if [ -f "$(dirname "$0")/infrawatch-agent.py" ]; then
    cp "$(dirname "$0")/infrawatch-agent.py" "${AGENT_SCRIPT}"
    info "Usando script local"
else
    info "Descargando agente..."
    curl -sSfL "${INFRAWATCH_SERVER}/static/agents/linux/infrawatch-agent.py" -o "${AGENT_SCRIPT}" 2>/dev/null || \
    wget -qO "${AGENT_SCRIPT}" "${INFRAWATCH_SERVER}/static/agents/linux/infrawatch-agent.py" 2>/dev/null || \
    error "No se pudo descargar el agente. Coloca infrawatch-agent.py en el mismo directorio que este script."
fi
chmod +x "${AGENT_SCRIPT}"
success "Script de agente instalado"

# Write systemd service
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=InfraWatch Monitoring Agent
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${AGENT_SCRIPT}
Restart=always
RestartSec=30
Environment="INFRAWATCH_SERVER=${INFRAWATCH_SERVER}"
Environment="INFRAWATCH_INTERVAL=${INFRAWATCH_INTERVAL}"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
success "Servicio systemd creado"

# Enable and start service
systemctl daemon-reload
systemctl enable infrawatch-agent
systemctl restart infrawatch-agent
sleep 2

# Check status
if systemctl is-active --quiet infrawatch-agent; then
    success "Servicio infrawatch-agent ACTIVO"
else
    warn "El servicio no inició. Revisa: journalctl -u infrawatch-agent -n 30"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     ✅  Agente InfraWatch instalado               ║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  Servidor: ${CYAN}${INFRAWATCH_SERVER}${NC}"
echo -e "${GREEN}║${NC}  Hostname: ${CYAN}$(hostname)${NC}"
echo -e "${GREEN}║${NC}  Estado:   ${CYAN}$(systemctl is-active infrawatch-agent)${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  Logs:   journalctl -u infrawatch-agent -f"
echo -e "${GREEN}║${NC}  Stop:   systemctl stop infrawatch-agent"
echo -e "${GREEN}║${NC}  Start:  systemctl start infrawatch-agent"
echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
info "El equipo aparecerá en el dashboard en ~60 segundos"
