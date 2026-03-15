#!/bin/bash
# ╔═══════════════════════════════════════════════════════════════════╗
# ║   InfraWatch — Instalador Automático para AlmaLinux / RHEL       ║
# ║   Uso: curl -sSL https://raw.githubusercontent.com/TU_USUARIO/  ║
# ║         infrawatch/main/install.sh | bash                        ║
# ╚═══════════════════════════════════════════════════════════════════╝

set -euo pipefail

# ── CONFIGURACIÓN ────────────────────────────────────────────────────────────
INFRAWATCH_PORT="${INFRAWATCH_PORT:-8000}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-infrawatch}"
INSTALL_DIR="/opt/infrawatch"
DATA_DIR="/opt/infrawatch/data"
VENV_DIR="/opt/infrawatch/venv"
SERVICE_NAME="infrawatch"
NGINX_CONF="/etc/nginx/conf.d/infrawatch.conf"
REPO_URL="${REPO_URL:-https://github.com/TU_USUARIO/infrawatch}"
# ─────────────────────────────────────────────────────────────────────────────

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}${BOLD}[InfraWatch]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step()    { echo -e "\n${BOLD}${CYAN}━━ Paso $1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

print_banner() {
cat << 'BANNER'

  ___        __          _       _       _     
 |_ _|_ __  / _|_ __ __ _| |   _ | | __ _| |_ ___| |__  
  | || '_ \| |_| '__/ _` | |  | || |/ _` | __/ __| '_ \ 
  | || | | |  _| | | (_| | |  |__   _| (_| | || (__| | | |
 |___|_| |_|_| |_|  \__,_|_|     |_|  \__,_|\__\___|_| |_|

BANNER
  echo -e "${CYAN}  IT Infrastructure Monitor v1.0${NC}"
  echo -e "${CYAN}  Instalación automática para AlmaLinux / RHEL${NC}\n"
}

print_banner

# Check root
[[ $EUID -ne 0 ]] && error "Ejecuta como root: sudo bash install.sh"

# Detect OS
if [ -f /etc/os-release ]; then
    source /etc/os-release
    OS_NAME="$NAME"
else
    OS_NAME="Unknown"
fi
info "Sistema detectado: ${OS_NAME}"

# ─── PASO 1: DEPENDENCIAS ────────────────────────────────────────────────────
step "1/6: Instalando dependencias del sistema"

dnf update -y -q 2>/dev/null || yum update -y -q 2>/dev/null || warn "Update falló, continuando..."

# Enable EPEL
if ! rpm -q epel-release &>/dev/null; then
    dnf install -y epel-release 2>/dev/null || yum install -y epel-release 2>/dev/null || true
fi

PACKAGES="python3 python3-pip python3-devel nginx git curl wget gcc openssl-devel"
for pkg in $PACKAGES; do
    if ! rpm -q "$pkg" &>/dev/null 2>&1; then
        info "Instalando $pkg..."
        dnf install -y "$pkg" 2>/dev/null || yum install -y "$pkg" 2>/dev/null || warn "No se pudo instalar $pkg"
    fi
done
success "Dependencias instaladas"

# ─── PASO 2: CREAR ESTRUCTURA ────────────────────────────────────────────────
step "2/6: Preparando directorios"

mkdir -p "${INSTALL_DIR}"/{backend/static/{css,js},agents/{linux,windows}}
mkdir -p "${DATA_DIR}"
mkdir -p /var/log/infrawatch

# Create system user (no login)
if ! id -u infrawatch &>/dev/null; then
    useradd -r -s /bin/false -d "${INSTALL_DIR}" infrawatch 2>/dev/null || true
fi
success "Directorios creados: ${INSTALL_DIR}"

# ─── PASO 3: DESCARGAR CÓDIGO ─────────────────────────────────────────────────
step "3/6: Descargando código fuente"

# If running from a git clone (install.sh in project root), copy files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if [ -f "${SCRIPT_DIR}/backend/main.py" ]; then
    info "Usando archivos locales desde ${SCRIPT_DIR}"
    cp -r "${SCRIPT_DIR}/backend/"* "${INSTALL_DIR}/backend/"
    cp -r "${SCRIPT_DIR}/agents/"*  "${INSTALL_DIR}/agents/"   2>/dev/null || true
    success "Archivos copiados desde directorio local"
elif command -v git &>/dev/null && [ -n "${REPO_URL}" ] && [[ "${REPO_URL}" != *"TU_USUARIO"* ]]; then
    info "Clonando repositorio: ${REPO_URL}"
    TMPDIR=$(mktemp -d)
    git clone --depth=1 "${REPO_URL}" "${TMPDIR}/repo" 2>&1 | tail -1
    cp -r "${TMPDIR}/repo/backend/"* "${INSTALL_DIR}/backend/"
    cp -r "${TMPDIR}/repo/agents/"*  "${INSTALL_DIR}/agents/" 2>/dev/null || true
    rm -rf "${TMPDIR}"
    success "Repositorio clonado"
else
    # Generate minimal main.py inline if not available
    warn "No se encontraron archivos fuente. Descarga manual necesaria."
    warn "Coloca los archivos del proyecto en ${INSTALL_DIR}/backend/ y re-ejecuta."
    warn "O clona el repo: git clone ${REPO_URL} y ejecuta desde ese directorio."
    error "Instalación incompleta. Ver instrucciones en README.md"
fi

# ─── PASO 4: PYTHON VIRTUALENV ───────────────────────────────────────────────
step "4/6: Configurando entorno Python"

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

info "Instalando paquetes Python..."
pip install --upgrade pip -q
pip install -r "${INSTALL_DIR}/backend/requirements.txt" -q
success "Entorno Python configurado: ${VENV_DIR}"

# ─── PASO 5: SERVICIO SYSTEMD ────────────────────────────────────────────────
step "5/6: Configurando servicios del sistema"

# Generate a random secret key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# InfraWatch systemd service
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=InfraWatch IT Infrastructure Monitor
After=network.target

[Service]
Type=exec
User=infrawatch
Group=infrawatch
WorkingDirectory=${INSTALL_DIR}/backend
ExecStart=${VENV_DIR}/bin/python -m uvicorn main:app --host 0.0.0.0 --port ${INFRAWATCH_PORT} --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=DATABASE_URL=sqlite:///${DATA_DIR}/infrawatch.db
Environment=SECRET_KEY=${SECRET_KEY}

[Install]
WantedBy=multi-user.target
EOF
success "Servicio systemd configurado"

# Set proper permissions
chown -R infrawatch:infrawatch "${INSTALL_DIR}" "${DATA_DIR}" /var/log/infrawatch
chmod -R 750 "${INSTALL_DIR}"
chmod -R 770 "${DATA_DIR}"
success "Permisos configurados"

# ─── NGINX ───────────────────────────────────────────────────────────────────
SERVER_IP=$(hostname -I | awk '{print $1}')

cat > "${NGINX_CONF}" << EOF
server {
    listen 80;
    server_name _;
    client_max_body_size 20M;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass         http://127.0.0.1:${INFRAWATCH_PORT};
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_http_version 1.1;
        proxy_read_timeout 300;
        proxy_connect_timeout 60;
    }

    # Cache static files
    location /static/ {
        proxy_pass http://127.0.0.1:${INFRAWATCH_PORT}/static/;
        proxy_cache_valid 200 1d;
        expires 1d;
    }
}
EOF
success "Nginx configurado"

# Remove default nginx config if it conflicts
[ -f /etc/nginx/conf.d/default.conf ] && mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak 2>/dev/null || true

# Test nginx config
nginx -t 2>/dev/null && success "Nginx configuración válida" || warn "Error en config nginx, verifica manualmente"

# ─── PASO 6: FIREWALL Y INICIO ───────────────────────────────────────────────
step "6/6: Configurando firewall e iniciando servicios"

# Firewall
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-service=http  2>/dev/null || true
    firewall-cmd --permanent --add-service=https 2>/dev/null || true
    firewall-cmd --permanent --add-port=${INFRAWATCH_PORT}/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    success "Firewall: puertos 80, 443, ${INFRAWATCH_PORT} abiertos"
elif command -v iptables &>/dev/null; then
    iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
    iptables -I INPUT -p tcp --dport ${INFRAWATCH_PORT} -j ACCEPT 2>/dev/null || true
    success "iptables: puertos abiertos"
fi

# SELinux
if command -v setsebool &>/dev/null; then
    setsebool -P httpd_can_network_connect 1 2>/dev/null || true
    success "SELinux: httpd_can_network_connect habilitado"
fi

# Enable and start services
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}" nginx
sleep 3

# ─── VERIFICACIÓN ─────────────────────────────────────────────────────────────

HEALTH=$(curl -sf "http://localhost:${INFRAWATCH_PORT}/api/health" 2>/dev/null || echo "")

echo ""
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║         ✅  InfraWatch instalado y funcionando               ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  URL:       ${CYAN}http://${SERVER_IP}${NC}"
    echo -e "${GREEN}║${NC}  API Docs:  ${CYAN}http://${SERVER_IP}/api/docs${NC}"
    echo -e "${GREEN}║${NC}  Usuario:   ${CYAN}admin${NC}"
    echo -e "${GREEN}║${NC}  Contraseña:${CYAN} ${ADMIN_PASSWORD}${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  Logs:  journalctl -u infrawatch -f"
    echo -e "${GREEN}║${NC}  Stop:  systemctl stop infrawatch"
    echo -e "${GREEN}║${NC}  DB:    ${DATA_DIR}/infrawatch.db"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  ${BOLD}AGENTE LINUX — instalar en endpoints:${NC}"
    echo -e "${GREEN}║${NC}  ${CYAN}curl -sSL http://${SERVER_IP}/static/agents/linux/install.sh | \\"
    echo -e "${GREEN}║${NC}  ${CYAN}  INFRAWATCH_SERVER=http://${SERVER_IP} bash${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  ${BOLD}AGENTE WINDOWS — ejecutar en PowerShell como Admin:${NC}"
    echo -e "${GREEN}║${NC}  ${CYAN}irm http://${SERVER_IP}/static/agents/windows/install.ps1 | iex${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
else
    warn "El servicio puede estar iniciando. Verifica en 30 segundos:"
    echo "  curl http://localhost:${INFRAWATCH_PORT}/api/health"
    echo "  journalctl -u infrawatch -n 30"
fi
echo ""

# Copy agent files to static directory for web download
cp -r "${INSTALL_DIR}/agents/" "${INSTALL_DIR}/backend/static/" 2>/dev/null || true
success "Agentes disponibles en /static/agents/"
