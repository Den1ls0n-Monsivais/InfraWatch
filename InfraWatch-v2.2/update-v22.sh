#!/bin/bash
# InfraWatch v2.2 — Script de Actualización
# Preserva BD, credenciales y datos existentes
# Uso: bash update-v22.sh

set -euo pipefail
G='\033[0;32m'; C='\033[0;36m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
info()    { echo -e "${C}[IW]${N} $1"; }
ok()      { echo -e "${G}[✓]${N} $1"; }
warn()    { echo -e "${Y}[!]${N} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SRC="$SCRIPT_DIR/backend"

# Detectar instalación
TARGET=""
for p in "/home/uriel/InfraWatch/infrawatch" "$HOME/InfraWatch/infrawatch" "/opt/infrawatch"; do
    [ -f "$p/backend/main.py" ] && TARGET="$p" && break
done
[ -z "$TARGET" ] && read -p "Ruta de InfraWatch: " TARGET
[ -f "$TARGET/backend/main.py" ] || { echo -e "${R}No encontrado${N}"; exit 1; }
info "Instalación: $TARGET"

# Backup
BK="${TARGET}/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BK"
for f in main.py static/js/app.js static/css/style.css static/index.html; do
    [ -f "$TARGET/backend/$f" ] && cp "$TARGET/backend/$f" "$BK/$(basename $f).bak" 2>/dev/null || true
done
ok "Backup en: $BK"

# Parar servicio
WAS_ON=false
systemctl is-active --quiet infrawatch 2>/dev/null && WAS_ON=true && sudo systemctl stop infrawatch && ok "Servicio detenido"

# Copiar archivos
info "Copiando archivos nuevos..."
cp "$SRC/main.py"              "$TARGET/backend/main.py"
cp "$SRC/static/js/app.js"     "$TARGET/backend/static/js/app.js"
cp "$SRC/static/css/style.css" "$TARGET/backend/static/css/style.css"
cp "$SRC/static/index.html"    "$TARGET/backend/static/index.html"
cp "$SRC/requirements.txt"     "$TARGET/backend/requirements.txt"
ok "Archivos copiados"

# Directorio uploads
sudo mkdir -p /opt/infrawatch/data/uploads
sudo chmod 777 /opt/infrawatch/data/uploads
ok "Directorio uploads listo"

# Dependencias
VENV=""
for v in "$TARGET/venv" "$(dirname $TARGET)/venv"; do [ -d "$v" ] && VENV="$v" && break; done
if [ -n "$VENV" ]; then
    info "Actualizando dependencias..."
    source "$VENV/bin/activate"
    pip install -q -r "$TARGET/backend/requirements.txt" 2>/dev/null || true
    ok "Dependencias OK"
fi

# Reiniciar
if $WAS_ON; then
    sudo systemctl start infrawatch; sleep 3
    systemctl is-active --quiet infrawatch && ok "Servicio ACTIVO" || warn "Revisa: journalctl -u infrawatch -n 20"
fi

# Verificar
HEALTH=$(curl -sf http://localhost:8000/api/health 2>/dev/null || echo "")
echo ""
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    V=$(echo "$HEALTH" | grep -oP '"version":"\K[^"]+' || echo "2.2.0")
    IP=$(hostname -I | awk '{print $1}')
    echo -e "${G}╔══════════════════════════════════════════════════════╗${N}"
    echo -e "${G}║  ✅  InfraWatch v${V} — Funcionando                  ║${N}"
    echo -e "${G}╠══════════════════════════════════════════════════════╣${N}"
    echo -e "${G}║${N}  URL:  http://${IP}:8000"
    echo -e "${G}║${N}  user: admin / infrawatch"
    echo -e "${G}╠══════════════════════════════════════════════════════╣${N}"
    echo -e "${G}║${N}  Nuevo en v2.2:"
    echo -e "${G}║${N}  ✦ Auto-migración BD (sin borrar datos)"
    echo -e "${G}║${N}  ✦ Rol RH y Rol IT"
    echo -e "${G}║${N}  ✦ Áreas con colores"
    echo -e "${G}║${N}  ✦ Audit Log con email automático"
    echo -e "${G}║${N}  ✦ Dashboard, Personal, Activos, Mantenimiento mejorado"
    echo -e "${G}╚══════════════════════════════════════════════════════╝${N}"
else
    warn "Servidor no responde. Inicia manualmente:"
    echo "  cd $TARGET/backend && source $VENV/bin/activate"
    echo "  DATABASE_URL=sqlite:////opt/infrawatch/data/infrawatch.db python3 -m uvicorn main:app --host 0.0.0.0 --port 8000"
fi
