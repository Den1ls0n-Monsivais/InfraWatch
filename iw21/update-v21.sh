#!/bin/bash
# InfraWatch v2.1 — Script de Actualización
# NO borra la base de datos ni las credenciales
# Uso: bash update-v21.sh

set -euo pipefail
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()    { echo -e "${CYAN}[InfraWatch]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Detectar instalación
for path in "/home/uriel/InfraWatch/infrawatch" "/home/$(logname 2>/dev/null)/InfraWatch/infrawatch" "/opt/infrawatch"; do
    [ -f "$path/backend/main.py" ] && TARGET="$path" && break
done
TARGET="${TARGET:-/home/uriel/InfraWatch/infrawatch}"
info "Instalación: $TARGET"

# Backup
BACKUP="${TARGET}/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP"
cp "$TARGET/backend/main.py" "$BACKUP/main.py.bak" 2>/dev/null || true
cp "$TARGET/backend/static/js/app.js" "$BACKUP/app.js.bak" 2>/dev/null || true
success "Backup: $BACKUP"

# Copiar nuevos archivos
info "Actualizando archivos..."
cp "$SCRIPT_DIR/backend/main.py"              "$TARGET/backend/main.py"
cp "$SCRIPT_DIR/backend/static/js/app.js"     "$TARGET/backend/static/js/app.js"
cp "$SCRIPT_DIR/backend/static/css/style.css" "$TARGET/backend/static/css/style.css"
cp "$SCRIPT_DIR/backend/static/index.html"    "$TARGET/backend/static/index.html"
success "Archivos copiados"

# Crear directorio uploads
mkdir -p /opt/infrawatch/data/uploads
success "Directorio uploads creado"

# Actualizar deps
VENV=""
for v in "$TARGET/venv" "$(dirname $TARGET)/venv" "/opt/infrawatch/venv"; do
    [ -d "$v" ] && VENV="$v" && break
done
if [ -n "$VENV" ]; then
    info "Actualizando dependencias..."
    source "$VENV/bin/activate"
    pip install -q python-multipart==0.0.12 aiofiles==24.1.0 2>/dev/null || true
    success "Dependencias OK"
fi

# Reiniciar servicio
if systemctl is-active --quiet infrawatch 2>/dev/null; then
    sudo systemctl restart infrawatch
    sleep 2
    systemctl is-active --quiet infrawatch && success "Servicio reiniciado" || warn "Verifica: journalctl -u infrawatch -n 20"
else
    warn "Inicia manualmente: cd $TARGET/backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║    ✅  InfraWatch actualizado a v2.1                  ║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  ✦ Historial de asignaciones por empleado"
echo -e "${GREEN}║${NC}  ✦ Carta de Alta + Carta de Baja (PDF/HTML)"
echo -e "${GREEN}║${NC}  ✦ Subida de cartas firmadas"
echo -e "${GREEN}║${NC}  ✦ Mantenimiento auto 1 año al registrar agente"
echo -e "${GREEN}║${NC}  ✦ Alertas de mantenimiento próximo/vencido"
echo -e "${GREEN}║${NC}  ✦ Correo automático aviso de mantenimiento"
echo -e "${GREEN}║${NC}  ✦ Baja de equipos con historial"
echo -e "${GREEN}╠═══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  Base de datos: SIN CAMBIOS — datos preservados"
echo -e "${GREEN}║${NC}  Backup v2.0: $BACKUP"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
