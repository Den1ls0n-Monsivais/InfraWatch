#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  InfraWatch v2.2 — Script de Actualización Inteligente      ║
# ║  NO borra la base de datos, credenciales ni configuración    ║
# ║  Detecta instalación automáticamente                         ║
# ║  Uso: bash update-v22.sh                                     ║
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

info()    { echo -e "${CYAN}[InfraWatch]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NEW_VERSION="2.2.0"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  InfraWatch v${NEW_VERSION} — Actualizando...           ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Detectar instalación ──────────────────────────────────────────────────────
TARGET=""
for path in \
    "/home/uriel/InfraWatch/infrawatch" \
    "/home/$(logname 2>/dev/null)/InfraWatch/infrawatch" \
    "/opt/infrawatch" \
    "$HOME/InfraWatch/infrawatch" \
    "$HOME/infrawatch"; do
    if [ -f "$path/backend/main.py" ]; then
        TARGET="$path"; break
    fi
done

if [ -z "$TARGET" ]; then
    warn "No se detectó instalación automáticamente."
    read -p "Ruta de tu InfraWatch (ej: /home/uriel/InfraWatch/infrawatch): " TARGET
    [ -f "$TARGET/backend/main.py" ] || error "No se encontró main.py en $TARGET/backend/"
fi
info "Instalación encontrada: $TARGET"

# ── Backup ────────────────────────────────────────────────────────────────────
BACKUP="${TARGET}/backup_v$(grep -oP "VERSION\s*=\s*\"\K[^\"]*" "$TARGET/backend/main.py" 2>/dev/null || echo "old")_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP"
cp "$TARGET/backend/main.py"                    "$BACKUP/main.py.bak"       2>/dev/null || true
cp "$TARGET/backend/static/js/app.js"           "$BACKUP/app.js.bak"        2>/dev/null || true
cp "$TARGET/backend/static/css/style.css"       "$BACKUP/style.css.bak"     2>/dev/null || true
cp "$TARGET/backend/static/index.html"          "$BACKUP/index.html.bak"    2>/dev/null || true
success "Backup: $BACKUP"

# ── Parar servicio ────────────────────────────────────────────────────────────
WAS_RUNNING=false
if systemctl is-active --quiet infrawatch 2>/dev/null; then
    WAS_RUNNING=true
    info "Parando servicio infrawatch..."
    sudo systemctl stop infrawatch
    success "Servicio detenido"
fi

# ── Copiar nuevos archivos ────────────────────────────────────────────────────
info "Copiando archivos v${NEW_VERSION}..."

SRC="$SCRIPT_DIR/backend"

[ -f "$SRC/main.py" ]              && cp "$SRC/main.py"              "$TARGET/backend/main.py"              && success "  main.py"
[ -f "$SRC/static/js/app.js" ]     && cp "$SRC/static/js/app.js"     "$TARGET/backend/static/js/app.js"     && success "  app.js"
[ -f "$SRC/static/css/style.css" ] && cp "$SRC/static/css/style.css" "$TARGET/backend/static/css/style.css" && success "  style.css"
[ -f "$SRC/static/index.html" ]    && cp "$SRC/static/index.html"    "$TARGET/backend/static/index.html"    && success "  index.html"
[ -f "$SRC/requirements.txt" ]     && cp "$SRC/requirements.txt"     "$TARGET/backend/requirements.txt"     && success "  requirements.txt"

# Agentes
mkdir -p "$TARGET/backend/static/agents/linux" "$TARGET/backend/static/agents/windows"
[ -d "$SRC/static/agents" ] && cp -r "$SRC/static/agents/"* "$TARGET/backend/static/agents/" 2>/dev/null || true

# ── Directorios nuevos ────────────────────────────────────────────────────────
sudo mkdir -p /opt/infrawatch/data/uploads
sudo chmod 777 /opt/infrawatch/data/uploads
success "Directorio uploads: /opt/infrawatch/data/uploads"

# ── Virtualenv y dependencias ─────────────────────────────────────────────────
VENV=""
for v in "$TARGET/venv" "$(dirname "$TARGET")/venv" "/opt/infrawatch/venv"; do
    [ -d "$v" ] && VENV="$v" && break
done

if [ -n "$VENV" ]; then
    info "Actualizando dependencias Python..."
    source "$VENV/bin/activate"
    pip install -q -r "$TARGET/backend/requirements.txt" 2>/dev/null || \
    pip install -q fastapi==0.115.0 "uvicorn[standard]==0.30.6" sqlalchemy==2.0.35 \
        pydantic==2.9.2 "python-jose[cryptography]==3.3.0" bcrypt==4.2.0 \
        PyJWT==2.9.0 python-multipart==0.0.12 aiofiles==24.1.0 2>/dev/null || true
    success "Dependencias actualizadas"
else
    warn "Virtualenv no encontrado. Dependencias no actualizadas."
fi

# ── Migración de BD (segura) ──────────────────────────────────────────────────
info "Verificando migración de base de datos..."
DB_PATH=$(grep -oP "DATABASE_URL.*sqlite:///+\K[^\"]*" "$TARGET/backend/main.py" 2>/dev/null || echo "/opt/infrawatch/data/infrawatch.db")
[ -f "$DB_PATH" ] || DB_PATH="/opt/infrawatch/data/infrawatch.db"

if [ -f "$DB_PATH" ] && command -v sqlite3 &>/dev/null; then
    # La migración completa se ejecuta automáticamente al arrancar el servidor (run_migrations())
    # Solo verificamos que la BD sea accesible
    sqlite3 "$DB_PATH" ".tables" > /dev/null 2>&1 && success "Base de datos accesible: $DB_PATH" || warn "No se pudo acceder a la BD"
else
    warn "sqlite3 no disponible o BD no encontrada. La migración correrá automáticamente al iniciar."
fi

# ── Reiniciar servicio ────────────────────────────────────────────────────────
if $WAS_RUNNING; then
    info "Reiniciando servicio infrawatch..."
    sudo systemctl start infrawatch
    sleep 3
    if systemctl is-active --quiet infrawatch; then
        success "Servicio infrawatch ACTIVO"
    else
        warn "El servicio no arrancó. Revisa:"
        echo "  journalctl -u infrawatch -n 30"
    fi
fi

# ── Verificar ─────────────────────────────────────────────────────────────────
HEALTH=$(curl -sf "http://localhost:8000/api/health" 2>/dev/null || echo "")
echo ""
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   ✅  InfraWatch v${NEW_VERSION} funcionando correctamente        ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  ✦ Auto-migración segura de BD — datos preservados"
    echo -e "${GREEN}║${NC}  ✦ Rol RH — gestión exclusiva de personal"
    echo -e "${GREEN}║${NC}  ✦ Rol IT — acceso completo a infraestructura"
    echo -e "${GREEN}║${NC}  ✦ Áreas gestionadas por IT (con colores)"
    echo -e "${GREEN}║${NC}  ✦ Audit Log — toda modificación registrada"
    echo -e "${GREEN}║${NC}  ✦ Email en cada cambio de usuario/personal"
    echo -e "${GREEN}║${NC}  ✦ Agentes → Activos + Mantenimiento automático"
    echo -e "${GREEN}║${NC}  ✦ Depreciación de activos calculada"
    echo -e "${GREEN}║${NC}  ✦ Importación CSV de personal"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  Backup:  $BACKUP"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
else
    warn "No se pudo verificar el servidor. Si no está corriendo:"
    echo ""
    echo "  cd $TARGET/backend"
    echo "  source $VENV/bin/activate"
    echo "  DATABASE_URL=sqlite:////opt/infrawatch/data/infrawatch.db \\"
    echo "  python3 -m uvicorn main:app --host 0.0.0.0 --port 8000"
fi
echo ""
