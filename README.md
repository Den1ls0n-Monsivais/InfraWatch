# InfraWatch v2.3 — IT Infrastructure Monitor

Sistema de monitoreo de infraestructura IT desarrollado con FastAPI + SQLite + Vanilla JS.

**Autor:** Denilson Monsivais · SiiX EMS

---

## Estructura del repositorio

```
InfraWatch-v2.3/
├── backend/
│   ├── main.py                  ← API FastAPI (backend completo)
│   ├── requirements.txt         ← Dependencias Python
│   └── static/
│       ├── index.html           ← SPA entry point
│       ├── js/app.js            ← Frontend completo
│       └── css/style.css        ← Tema dark NOC
├── agent/
│   ├── agent.py                 ← Agente cross-platform (Windows + Linux)
│   ├── installer_windows.py     ← Instalador GUI → compila a .exe
│   ├── build_exe.bat            ← Script PyInstaller para generar .exe
│   ├── install_linux.sh         ← Instalador bash (Debian/Ubuntu/RHEL/Arch)
│   └── requirements.txt         ← Dependencias del agente
├── update-v23.sh                ← Script de actualización del servidor
└── README.md
```

---

## Instalación del servidor

### Requisitos
- Python 3.8+
- pip

### Pasos

```bash
# 1. Clonar
git clone https://github.com/tu-usuario/InfraWatch-v2.3.git
cd InfraWatch-v2.3/backend

# 2. Entorno virtual
python3 -m venv venv
source venv/bin/activate          # Linux
# venv\Scripts\activate            # Windows

# 3. Dependencias
pip install -r requirements.txt
pip install pysnmp                 # Opcional: para monitoreo SNMP

# 4. Crear directorios de datos
sudo mkdir -p /opt/infrawatch/data/uploads
sudo chmod 777 /opt/infrawatch/data

# 5. Iniciar
DATABASE_URL=sqlite:////opt/infrawatch/data/infrawatch.db \
  python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**Credenciales iniciales:** `admin` / `infrawatch`

---

## Actualización desde v2.2

```bash
bash update-v23.sh
```

---

## Instalación del agente

### Linux

```bash
sudo bash agent/install_linux.sh

# Con IP del servidor fija
sudo bash agent/install_linux.sh --server 192.168.1.10

# Con tags
sudo bash agent/install_linux.sh --server 192.168.1.10 --tags "SERVIDOR,PRODUCCION"
```

### Windows (.exe)

**Opción 1 — Compilar el .exe (en equipo Windows con Python):**
```bat
cd agent
pip install pyinstaller psutil pywin32
build_exe.bat
# Resultado: agent\dist\InfraWatch-Agent-Installer.exe
```

**Opción 2 — Ejecutar directamente con Python:**
```bat
pip install psutil pywin32
python agent\installer_windows.py
```

El instalador:
- Busca el servidor automáticamente en la red (60 segundos)
- Si no encuentra → permite ingresar IP manualmente
- Permite configurar tags del equipo
- Instala como servicio Windows con arranque automático

---

## Novedades v2.3 — Categoría 1: Agente y Monitoreo

| # | Mejora | Descripción |
|---|--------|-------------|
| 1 | **Software instalado** | Detecta automáticamente todos los programas (Windows: registro, Linux: dpkg/rpm/pacman) |
| 2 | **SNMP** | Monitoreo de switches, routers, firewalls sin agente — polling automático cada 5 min |
| 3 | **Ping / ICMP** | Monitoreo de impresoras, cámaras, APs, pantallas — alertas tras 2 fallos consecutivos |
| 4 | **Umbrales configurables** | CPU/RAM/Disco configurables por equipo — no fijo al 90% |

### Auto-descubrimiento
El servidor escucha en UDP 47777. El agente hace broadcast y el servidor responde automáticamente — sin necesidad de configurar IP manualmente en la mayoría de los casos.

---

## API

Documentación interactiva disponible en: `http://servidor:8000/api/docs`

### Rutas principales

```
POST   /api/auth/login
GET    /api/agents
POST   /api/agents/register
POST   /api/agents/{uid}/heartbeat
POST   /api/agents/{uid}/software       ← NUEVO v2.3
GET    /api/agents/{id}/software        ← NUEVO v2.3
GET    /api/agents/{id}/thresholds      ← NUEVO v2.3
PUT    /api/agents/{id}/thresholds      ← NUEVO v2.3
GET    /api/software/search?q=          ← NUEVO v2.3
GET    /api/snmp                        ← NUEVO v2.3
POST   /api/snmp                        ← NUEVO v2.3
POST   /api/snmp/{id}/poll             ← NUEVO v2.3
GET    /api/ping-devices                ← NUEVO v2.3
POST   /api/ping-devices                ← NUEVO v2.3
POST   /api/ping-devices/scan-all      ← NUEVO v2.3
GET    /api/assets
GET    /api/personnel
GET    /api/maintenance
GET    /api/alerts
GET    /api/dashboard
```

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI + Uvicorn |
| Base de datos | SQLite (SQLAlchemy ORM) |
| Autenticación | JWT + bcrypt |
| Frontend | Vanilla JS (SPA) + Chart.js |
| Agente | Python 3 (psutil) |
| Servicio Windows | pywin32 |
| Servicio Linux | systemd |
| SNMP | pysnmp (opcional) |

---

## Roles de usuario

| Rol | Permisos |
|-----|---------|
| `admin` | Acceso total |
| `it` | Inventario, activos, áreas, usuarios, configuración |
| `rh` | Personal |
| `auditor` | Solo lectura + auditoría |
| `viewer` | Solo lectura |
