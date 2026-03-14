# 🛡 InfraWatch — IT Infrastructure Monitor

Sistema centralizado de monitoreo de infraestructura TI, inventario automático,
gestión de activos fijos y control de mantenimientos preventivos.

> **Similar a Zabbix + OCS Inventory + activos fijos — todo en uno.**

---

## 🚀 Instalación rápida (AlmaLinux / RHEL / Rocky)

```bash
# 1. Clonar repositorio
git clone https://github.com/TU_USUARIO/infrawatch.git
cd infrawatch

# 2. Ejecutar instalador (como root)
sudo bash install.sh
```

### O con curl directamente desde GitHub:
```bash
curl -sSL https://raw.githubusercontent.com/TU_USUARIO/infrawatch/main/install.sh \
  -o /tmp/install.sh && sudo bash /tmp/install.sh
```

### Con contraseña admin personalizada:
```bash
sudo ADMIN_PASSWORD="MiPassword123" bash install.sh
```

Después de la instalación, el sistema estará disponible en:
- **URL:** `http://IP_SERVIDOR`
- **Usuario:** `admin`
- **Contraseña:** `infrawatch` (o la que configuraste)

---

## 📦 Instalación de Agentes

### Linux (cualquier distro con Python3)

```bash
# Con un solo comando desde el servidor InfraWatch:
curl -sSL http://IP_SERVIDOR/static/agents/linux/install.sh | \
  INFRAWATCH_SERVER=http://IP_SERVIDOR bash
```

**O manualmente:**
```bash
git clone https://github.com/TU_USUARIO/infrawatch.git
cd infrawatch/agents/linux
sudo INFRAWATCH_SERVER=http://IP_SERVIDOR bash install.sh
```

### Windows (PowerShell como Administrador)

```powershell
# Opción 1 — Un comando:
$env:INFRAWATCH_SERVER="http://IP_SERVIDOR"
irm http://IP_SERVIDOR/static/agents/windows/install.ps1 | iex

# Opción 2 — Descarga y ejecuta:
Invoke-WebRequest -Uri "http://IP_SERVIDOR/static/agents/windows/install.ps1" -OutFile install.ps1
.\install.ps1 -ServerUrl "http://IP_SERVIDOR" -Install
```

---

## 🖥 Módulos del Sistema

| Módulo | Descripción |
|--------|-------------|
| **Dashboard NOC** | Vista general en tiempo real — hosts activos, métricas, alertas |
| **Inventario** | Detección automática via agentes — CPU, RAM, disco, SO, puertos |
| **Activos Fijos** | Gestión manual — código, tipo, marca, modelo, responsable, costo |
| **Mantenimientos** | Registro preventivo/correctivo con fechas y técnico |
| **Alertas** | Auto-generadas por CPU>90%, RAM>90%, disco>90%, host offline |
| **Usuarios** | Roles: admin / técnico / auditor / viewer |

---

## 🏷 Tags

Los tags permiten clasificar equipos. Se configuran desde el inventario:
```
FINANZAS    SERVIDORES    LAPTOP    CRITICO
SUCURSAL-1  OFICINA-2     WINDOWS   LINUX
```

---

## 📁 Estructura del Proyecto

```
infrawatch/
├── install.sh                    ← Instalador principal
├── README.md
├── backend/
│   ├── main.py                   ← API FastAPI completa
│   ├── requirements.txt
│   └── static/
│       ├── index.html            ← Frontend SPA
│       ├── css/style.css
│       ├── js/app.js
│       └── agents/               ← Agentes (servidos por la web)
│           ├── linux/
│           └── windows/
└── agents/
    ├── linux/
    │   ├── infrawatch-agent.py   ← Agente Python
    │   └── install.sh
    └── windows/
        ├── infrawatch-agent.ps1  ← Agente PowerShell
        └── install.ps1
```

---

## ⚙️ Configuración del Servidor

### Variables de entorno (en `/etc/systemd/system/infrawatch.service`):

```ini
Environment=DATABASE_URL=sqlite:////opt/infrawatch/data/infrawatch.db
Environment=SECRET_KEY=tu-clave-secreta
```

### Cambiar contraseña admin:
```bash
# Via API
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"infrawatch"}'
```

---

## 🔧 Gestión del Servicio

```bash
# Estado
systemctl status infrawatch nginx

# Logs en tiempo real
journalctl -u infrawatch -f

# Reiniciar
systemctl restart infrawatch

# Ver base de datos
sqlite3 /opt/infrawatch/data/infrawatch.db ".tables"
```

---

## 🛠 Desinstalar

```bash
systemctl stop infrawatch nginx
systemctl disable infrawatch
rm -rf /opt/infrawatch
rm /etc/systemd/system/infrawatch.service
rm /etc/nginx/conf.d/infrawatch.conf
systemctl daemon-reload
```

---

## 📡 API Endpoints Principales

```
POST /api/auth/login              ← Login usuario web
GET  /api/dashboard               ← Stats generales
GET  /api/agents                  ← Lista de hosts
POST /api/agents/register         ← Registro de agente (sin auth)
POST /api/agents/{uid}/heartbeat  ← Métricas del agente (sin auth)
GET  /api/alerts                  ← Alertas del sistema
GET/POST/PUT/DELETE /api/assets   ← Activos fijos
GET/POST/DELETE /api/maintenance  ← Mantenimientos
GET  /api/reports/inventory       ← Reporte inventario JSON
GET  /api/reports/assets          ← Reporte activos JSON
GET  /api/docs                    ← Swagger UI
```

---

## 🔐 Roles de Usuario

| Rol | Permisos |
|-----|----------|
| `admin` | Todo — incluyendo gestión de usuarios |
| `technician` | Ver + registrar mantenimientos y activos |
| `auditor` | Solo lectura + exportar reportes |
| `viewer` | Solo lectura del dashboard |

---

## 📋 Requisitos

**Servidor:**
- AlmaLinux 8/9, Rocky Linux, RHEL 8/9, CentOS Stream
- 1 GB RAM mínimo (2 GB recomendado)
- Python 3.8+, Nginx

**Agente Linux:**
- Python 3.6+
- Sin dependencias externas (solo stdlib)

**Agente Windows:**
- Windows 10/11 o Windows Server 2016+
- PowerShell 5.1+

---

## 📄 Licencia

MIT License — Úsalo, modifícalo, mejóralo libremente.
