"""
╔══════════════════════════════════════════════════════════════╗
║  InfraWatch v2.2 — IT Infrastructure Monitor                ║
║  Backend API — FastAPI + SQLAlchemy + SQLite                 ║
╠══════════════════════════════════════════════════════════════╣
║  Nuevas funciones v2.2:                                      ║
║  ✦ Auto-migración segura al arrancar (nunca rompe la BD)    ║
║  ✦ Rol RH — gestión exclusiva de personal                   ║
║  ✦ Rol IT — acceso completo a infraestructura               ║
║  ✦ Áreas gestionadas por IT (CRUD)                          ║
║  ✦ Audit Log — toda modificación queda registrada           ║
║  ✦ Email automático en cualquier cambio de usuario/personal  ║
║  ✦ Agentes → Activos + Mantenimiento automático             ║
║  ✦ QR Code por activo (SVG inline)                          ║
║  ✦ Depreciación de activos (cálculo automático)             ║
║  ✦ Importación masiva CSV de personal                       ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, date
import jwt, bcrypt, os, json, uuid, smtplib, logging, shutil, csv, io, math
import threading, socket, subprocess, time
from typing import Dict, Any

# SNMP opcional — pip install pysnmp
try:
    from pysnmp.hlapi import (getCmd, SnmpEngine, CommunityData,
        UdpTransportTarget, ContextData, ObjectType, ObjectIdentity)
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DATABASE_URL    = os.getenv("DATABASE_URL", "sqlite:////opt/infrawatch/data/infrawatch.db")
SECRET_KEY      = os.getenv("SECRET_KEY", "infrawatch-secret-2024")
JWT_ALGO        = "HS256"
JWT_EXP_HRS     = 24
VERSION         = "2.3.0"
APP_NAME        = "InfraWatch"
UPLOAD_DIR      = "/opt/infrawatch/data/uploads"
MAINT_DAYS      = 365   # días entre mantenimientos preventivos
MAINT_WARN_DAYS = 30    # días de anticipación para alertar

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("/opt/infrawatch/data", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── DATABASE ─────────────────────────────────────────────────────────────────
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── MODELS ───────────────────────────────────────────────────────────────────

class Area(Base):
    """Áreas/Departamentos — gestionadas por IT"""
    __tablename__ = "areas"
    id          = Column(Integer, primary_key=True)
    name        = Column(String, unique=True, index=True)
    description = Column(String, default="")
    color       = Column(String, default="#58a6ff")  # hex color para UI
    is_active   = Column(Boolean, default=True)
    created_by  = Column(String, default="")
    created_at  = Column(DateTime, default=datetime.utcnow)
    personnel   = relationship("Personnel", back_populates="area_rel")

class Personnel(Base):
    """Empleados — gestionados por RH e IT"""
    __tablename__ = "personnel"
    id           = Column(Integer, primary_key=True, index=True)
    employee_id  = Column(String, unique=True, index=True)
    full_name    = Column(String, index=True)
    position     = Column(String, default="")
    department   = Column(String, default="")
    area_id      = Column(Integer, ForeignKey("areas.id"), nullable=True)
    email        = Column(String, default="")
    phone        = Column(String, default="")
    location     = Column(String, default="")
    is_active    = Column(Boolean, default=True)
    notes        = Column(Text, default="")
    created_at   = Column(DateTime, default=datetime.utcnow)
    created_by   = Column(String, default="")
    area_rel     = relationship("Area", back_populates="personnel")
    assets       = relationship("Asset", back_populates="personnel")
    history      = relationship("AssetHistory", back_populates="personnel", cascade="all, delete")

class Agent(Base):
    __tablename__ = "agents"
    id            = Column(Integer, primary_key=True, index=True)
    uid           = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    hostname      = Column(String, index=True)
    ip_address    = Column(String)
    mac_address   = Column(String)
    os_name       = Column(String, default="")
    os_version    = Column(String, default="")
    cpu_model     = Column(String, default="")
    cpu_cores     = Column(Integer, default=0)
    ram_total_gb  = Column(Float, default=0)
    disk_total_gb = Column(Float, default=0)
    tags          = Column(Text, default="[]")
    status        = Column(String, default="online")
    last_seen     = Column(DateTime, default=datetime.utcnow)
    registered_at = Column(DateTime, default=datetime.utcnow)
    agent_version = Column(String, default="1.0")
    metrics       = relationship("Metric", back_populates="agent", cascade="all, delete")
    asset         = relationship("Asset", back_populates="agent", uselist=False)

class Metric(Base):
    __tablename__ = "metrics"
    id             = Column(Integer, primary_key=True)
    agent_id       = Column(Integer, ForeignKey("agents.id"))
    timestamp      = Column(DateTime, default=datetime.utcnow)
    cpu_percent    = Column(Float, default=0)
    ram_percent    = Column(Float, default=0)
    disk_percent   = Column(Float, default=0)
    net_bytes_sent = Column(Float, default=0)
    net_bytes_recv = Column(Float, default=0)
    uptime_seconds = Column(Float, default=0)
    process_count  = Column(Integer, default=0)
    open_ports     = Column(Text, default="[]")
    agent          = relationship("Agent", back_populates="metrics")

class Asset(Base):
    __tablename__ = "assets"
    id               = Column(Integer, primary_key=True)
    asset_code       = Column(String, unique=True, index=True)
    asset_type       = Column(String, default="pc")
    brand            = Column(String, default="")
    model            = Column(String, default="")
    serial_number    = Column(String, default="")
    purchase_date    = Column(String, default="")
    purchase_cost    = Column(Float, default=0)
    useful_life_yrs  = Column(Integer, default=4)  # años vida útil para depreciación
    responsible      = Column(String, default="")
    personnel_id     = Column(Integer, ForeignKey("personnel.id"), nullable=True)
    location         = Column(String, default="")
    status           = Column(String, default="active")
    notes            = Column(Text, default="")
    auto_created     = Column(Boolean, default=False)
    carta_sent       = Column(Boolean, default=False)
    carta_sent_at    = Column(DateTime, nullable=True)
    carta_alta_path  = Column(String, default="")
    carta_baja_path  = Column(String, default="")
    assigned_at      = Column(DateTime, nullable=True)
    unassigned_at    = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    agent_id         = Column(Integer, ForeignKey("agents.id"), nullable=True)
    personnel        = relationship("Personnel", back_populates="assets")
    agent            = relationship("Agent", back_populates="asset")
    maintenances     = relationship("Maintenance", back_populates="asset", cascade="all, delete")
    history          = relationship("AssetHistory", back_populates="asset", cascade="all, delete")

class AssetHistory(Base):
    __tablename__ = "asset_history"
    id           = Column(Integer, primary_key=True)
    asset_id     = Column(Integer, ForeignKey("assets.id"))
    personnel_id = Column(Integer, ForeignKey("personnel.id"), nullable=True)
    action       = Column(String)   # alta / baja
    action_date  = Column(DateTime, default=datetime.utcnow)
    notes        = Column(Text, default="")
    carta_path   = Column(String, default="")
    created_by   = Column(String, default="")
    asset        = relationship("Asset", back_populates="history")
    personnel    = relationship("Personnel", back_populates="history")

class Maintenance(Base):
    __tablename__ = "maintenances"
    id               = Column(Integer, primary_key=True)
    asset_id         = Column(Integer, ForeignKey("assets.id"))
    maintenance_date = Column(String)
    next_date        = Column(String, nullable=True)
    technician       = Column(String, default="TI")
    maint_type       = Column(String, default="preventive")
    observations     = Column(Text, default="")
    status           = Column(String, default="pending")
    auto_created     = Column(Boolean, default=False)
    email_sent       = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow)
    asset            = relationship("Asset", back_populates="maintenances")

class Alert(Base):
    __tablename__ = "alerts"
    id           = Column(Integer, primary_key=True)
    agent_id     = Column(Integer, ForeignKey("agents.id"), nullable=True)
    alert_type   = Column(String)
    severity     = Column(String, default="warning")
    message      = Column(Text)
    acknowledged = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    username      = Column(String, unique=True, index=True)
    password_hash = Column(String)
    full_name     = Column(String, default="")
    email         = Column(String, default="")
    # Roles: admin, it, rh, auditor, viewer
    role          = Column(String, default="viewer")
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    """Registro de auditoría — toda modificación queda registrada"""
    __tablename__ = "audit_log"
    id          = Column(Integer, primary_key=True)
    timestamp   = Column(DateTime, default=datetime.utcnow)
    user        = Column(String)   # quien hizo el cambio
    action      = Column(String)   # CREATE / UPDATE / DELETE
    entity      = Column(String)   # Personnel / Asset / User / Area
    entity_id   = Column(String)
    description = Column(Text)
    ip_address  = Column(String, default="")
    email_sent  = Column(Boolean, default=False)

class SMTPConfig(Base):
    __tablename__ = "smtp_config"
    id        = Column(Integer, primary_key=True)
    host      = Column(String, default="smtp.gmail.com")
    port      = Column(Integer, default=587)
    username  = Column(String, default="")
    password  = Column(String, default="")
    from_name = Column(String, default="InfraWatch")
    company   = Column(String, default="Mi Empresa")
    enabled   = Column(Boolean, default=False)

# ─── MODELS v2.3 ──────────────────────────────────────────────────────────────

class InstalledSoftware(Base):
    """Software instalado detectado por el agente"""
    __tablename__ = "installed_software"
    id           = Column(Integer, primary_key=True)
    agent_id     = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"))
    name         = Column(String, index=True)
    version      = Column(String, default="")
    publisher    = Column(String, default="")
    install_date = Column(String, default="")
    detected_at  = Column(DateTime, default=datetime.utcnow)

class AgentThreshold(Base):
    """Umbrales de alerta configurados por agente"""
    __tablename__ = "agent_thresholds"
    id            = Column(Integer, primary_key=True)
    agent_id      = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), unique=True)
    cpu_warn      = Column(Float, default=75.0)
    cpu_crit      = Column(Float, default=90.0)
    ram_warn      = Column(Float, default=80.0)
    ram_crit      = Column(Float, default=90.0)
    disk_warn     = Column(Float, default=80.0)
    disk_crit     = Column(Float, default=90.0)
    updated_at    = Column(DateTime, default=datetime.utcnow)

class SNMPDevice(Base):
    """Dispositivo monitoreable via SNMP"""
    __tablename__ = "snmp_devices"
    id             = Column(Integer, primary_key=True)
    name           = Column(String, default="")
    ip_address     = Column(String, index=True)
    device_type    = Column(String, default="switch")
    community      = Column(String, default="public")
    snmp_version   = Column(String, default="2c")
    port           = Column(Integer, default=161)
    location       = Column(String, default="")
    area_id        = Column(Integer, ForeignKey("areas.id"), nullable=True)
    status         = Column(String, default="unknown")
    sys_descr      = Column(Text, default="")
    sys_name       = Column(String, default="")
    sys_uptime     = Column(Float, default=0)
    if_count       = Column(Integer, default=0)
    last_polled    = Column(DateTime, nullable=True)
    last_seen      = Column(DateTime, nullable=True)
    poll_interval  = Column(Integer, default=300)
    is_active      = Column(Boolean, default=True)
    notes          = Column(Text, default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    created_by     = Column(String, default="")

class PingDevice(Base):
    """Dispositivo monitoreable solo via ping (impresoras, cámaras, APs...)"""
    __tablename__ = "ping_devices"
    id              = Column(Integer, primary_key=True)
    name            = Column(String)
    ip_address      = Column(String, index=True)
    device_type     = Column(String, default="printer")
    area_id         = Column(Integer, ForeignKey("areas.id"), nullable=True)
    location        = Column(String, default="")
    status          = Column(String, default="unknown")
    response_time_ms= Column(Float, nullable=True)
    last_ping       = Column(DateTime, nullable=True)
    last_seen       = Column(DateTime, nullable=True)
    uptime_pct      = Column(Float, default=0)
    consecutive_failures = Column(Integer, default=0)
    ping_interval   = Column(Integer, default=60)
    is_active       = Column(Boolean, default=True)
    notes           = Column(Text, default="")
    created_at      = Column(DateTime, default=datetime.utcnow)
    created_by      = Column(String, default="")


# ─── SAFE AUTO-MIGRATION ──────────────────────────────────────────────────────

def run_migrations():
    """
    Migración segura — agrega columnas/tablas faltantes SIN borrar datos.
    Funciona aunque ya existan las columnas (idempotente).
    """
    with engine.connect() as conn:
        def col_exists(table, col):
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return any(r[1] == col for r in rows)

        def table_exists(table):
            r = conn.execute(text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            )).fetchone()
            return r is not None

        def safe_add(table, col, definition):
            if table_exists(table) and not col_exists(table, col):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                log.info(f"  ✦ Migración: {table}.{col}")

        # ── assets ────────────────────────────────────────────────────────────
        safe_add("assets", "personnel_id",    "INTEGER REFERENCES personnel(id)")
        safe_add("assets", "auto_created",    "BOOLEAN DEFAULT 0")
        safe_add("assets", "carta_sent",      "BOOLEAN DEFAULT 0")
        safe_add("assets", "carta_sent_at",   "DATETIME")
        safe_add("assets", "carta_alta_path", "VARCHAR DEFAULT ''")
        safe_add("assets", "carta_baja_path", "VARCHAR DEFAULT ''")
        safe_add("assets", "assigned_at",     "DATETIME")
        safe_add("assets", "unassigned_at",   "DATETIME")
        safe_add("assets", "useful_life_yrs", "INTEGER DEFAULT 4")

        # ── maintenances ──────────────────────────────────────────────────────
        safe_add("maintenances", "auto_created", "BOOLEAN DEFAULT 0")
        safe_add("maintenances", "email_sent",   "BOOLEAN DEFAULT 0")

        # ── personnel ─────────────────────────────────────────────────────────
        safe_add("personnel", "area_id",    "INTEGER REFERENCES areas(id)")
        safe_add("personnel", "created_by", "VARCHAR DEFAULT ''")

        # ── users ─────────────────────────────────────────────────────────────
        # Update role column if needed (viewers became viewer etc.)
        if table_exists("users") and col_exists("users", "role"):
            # Rename admin→admin, keep compatible
            pass

        # v2.3 — nuevas tablas (created_all las maneja, safe_add para columnas nuevas en tablas viejas)
        conn.commit()

    # Create tables that might not exist yet (incluyendo las v2.3)
    Base.metadata.create_all(bind=engine)
    log.info("✅ Migraciones completadas")

# ─── SCHEMAS ──────────────────────────────────────────────────────────────────

class AreaSchema(BaseModel):
    name:        str
    description: Optional[str] = ""
    color:       Optional[str] = "#58a6ff"
    is_active:   Optional[bool] = True

class PersonnelSchema(BaseModel):
    employee_id: str
    full_name:   str
    position:    Optional[str] = ""
    department:  Optional[str] = ""
    area_id:     Optional[int] = None
    email:       Optional[str] = ""
    phone:       Optional[str] = ""
    location:    Optional[str] = ""
    is_active:   Optional[bool] = True
    notes:       Optional[str] = ""

class AgentRegisterSchema(BaseModel):
    hostname:      str
    ip_address:    str
    mac_address:   str
    os_name:       Optional[str] = ""
    os_version:    Optional[str] = ""
    cpu_model:     Optional[str] = ""
    cpu_cores:     Optional[int] = 0
    ram_total_gb:  Optional[float] = 0
    disk_total_gb: Optional[float] = 0
    agent_version: Optional[str] = "1.0"

class HeartbeatSchema(BaseModel):
    cpu_percent:    float = 0
    ram_percent:    float = 0
    disk_percent:   float = 0
    net_bytes_sent: float = 0
    net_bytes_recv: float = 0
    uptime_seconds: float = 0
    process_count:  int   = 0
    open_ports:     List[int] = []

class AssetSchema(BaseModel):
    asset_type:     str
    brand:          Optional[str] = ""
    model:          Optional[str] = ""
    serial_number:  Optional[str] = ""
    purchase_date:  Optional[str] = ""
    purchase_cost:  Optional[float] = 0
    useful_life_yrs: Optional[int] = 4
    responsible:    Optional[str] = ""
    personnel_id:   Optional[int] = None
    location:       Optional[str] = ""
    status:         Optional[str] = "active"
    notes:          Optional[str] = ""
    agent_id:       Optional[int] = None

class AssetAssignSchema(BaseModel):
    personnel_id: int
    send_email:   Optional[bool] = True
    notes:        Optional[str] = ""

class AssetBajaSchema(BaseModel):
    notes:      Optional[str] = ""
    send_email: Optional[bool] = True

class MaintenanceSchema(BaseModel):
    asset_id:         int
    maintenance_date: str
    next_date:        Optional[str] = None
    technician:       Optional[str] = ""
    maint_type:       Optional[str] = "preventive"
    observations:     Optional[str] = ""
    status:           Optional[str] = "completed"

class UserLoginSchema(BaseModel):
    username: str
    password: str

class UserCreateSchema(BaseModel):
    username:  str
    password:  str
    full_name: Optional[str] = ""
    email:     Optional[str] = ""
    role:      Optional[str] = "viewer"

class UserUpdateSchema(BaseModel):
    full_name: Optional[str] = ""
    email:     Optional[str] = ""
    role:      Optional[str] = None
    is_active: Optional[bool] = None

class TagUpdateSchema(BaseModel):
    tags: List[str]

class SMTPConfigSchema(BaseModel):
    host:      str
    port:      int
    username:  str
    password:  Optional[str] = ""
    from_name: Optional[str] = "InfraWatch"
    company:   Optional[str] = "Mi Empresa"
    enabled:   Optional[bool] = True

# ─── SCHEMAS v2.3 ────────────────────────────────────────────────────────────

class SoftwareUploadSchema(BaseModel):
    software: List[Dict[str, Any]]

class ThresholdSchema(BaseModel):
    cpu_warn:  Optional[float] = 75.0
    cpu_crit:  Optional[float] = 90.0
    ram_warn:  Optional[float] = 80.0
    ram_crit:  Optional[float] = 90.0
    disk_warn: Optional[float] = 80.0
    disk_crit: Optional[float] = 90.0

class SNMPDeviceSchema(BaseModel):
    name:          str
    ip_address:    str
    device_type:   Optional[str] = "switch"
    community:     Optional[str] = "public"
    snmp_version:  Optional[str] = "2c"
    port:          Optional[int] = 161
    location:      Optional[str] = ""
    area_id:       Optional[int] = None
    poll_interval: Optional[int] = 300
    is_active:     Optional[bool] = True
    notes:         Optional[str] = ""

class PingDeviceSchema(BaseModel):
    name:          str
    ip_address:    str
    device_type:   Optional[str] = "printer"
    area_id:       Optional[int] = None
    location:      Optional[str] = ""
    ping_interval: Optional[int] = 60
    is_active:     Optional[bool] = True
    notes:         Optional[str] = ""


# ─── AUTH ─────────────────────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)

ROLE_HIERARCHY = {"admin": 5, "it": 4, "rh": 3, "auditor": 2, "viewer": 1}

def create_token(uid, username, role):
    return jwt.encode({"sub": str(uid), "username": username, "role": role,
                        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HRS)},
                       SECRET_KEY, algorithm=JWT_ALGO)

def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
                     db: Session = Depends(get_db)):
    if not creds:
        raise HTTPException(status_code=401, detail="No autenticado")
    p = decode_token(creds.credentials)
    u = db.query(User).filter(User.id == int(p["sub"])).first()
    if not u or not u.is_active:
        raise HTTPException(status_code=401, detail="Usuario no válido")
    return u

def require_roles(*roles):
    """Factory: permite acceso solo a los roles indicados"""
    def dep(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403,
                detail=f"Acceso denegado. Rol requerido: {', '.join(roles)}")
        return user
    return dep

# Shortcuts
require_admin      = require_roles("admin")
require_it_admin   = require_roles("admin", "it")
require_rh_admin   = require_roles("admin", "rh")
require_any        = require_roles("admin", "it", "rh", "auditor", "viewer")

def hash_password(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
def verify_password(pw, h): return bcrypt.checkpw(pw.encode(), h.encode())

# ─── SMTP ─────────────────────────────────────────────────────────────────────

def get_smtp(db):
    cfg = db.query(SMTPConfig).first()
    if not cfg:
        cfg = SMTPConfig(); db.add(cfg); db.commit(); db.refresh(cfg)
    return cfg

def send_email(to_email: str, subject: str, html_body: str, db: Session,
               attachment_path: str = None, attachment_name: str = None) -> bool:
    cfg = get_smtp(db)
    if not cfg.enabled or not cfg.username or not to_email:
        return False
    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"]    = f"{cfg.from_name} <{cfg.username}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), _subtype="html")
                part.add_header("Content-Disposition", "attachment",
                                 filename=attachment_name or os.path.basename(attachment_path))
                msg.attach(part)
        with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as srv:
            srv.starttls(); srv.login(cfg.username, cfg.password)
            srv.sendmail(cfg.username, [to_email], msg.as_string())
        log.info(f"✉ Email → {to_email}: {subject}")
        return True
    except Exception as e:
        log.error(f"Email error: {e}")
        return False

# ─── AUDIT LOG ────────────────────────────────────────────────────────────────

def audit(db: Session, user: str, action: str, entity: str, entity_id,
          description: str, ip: str = "", notify_email: str = None):
    """Registra auditoría y envía email si hay destinatario"""
    entry = AuditLog(
        user=user, action=action, entity=entity,
        entity_id=str(entity_id), description=description, ip_address=ip
    )
    db.add(entry)
    if notify_email:
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:550px;margin:0 auto;padding:20px">
        <div style="background:#1a56db;color:#fff;padding:18px 24px;border-radius:8px 8px 0 0">
          <h2 style="margin:0">🛡 InfraWatch — Notificación de Cambio</h2></div>
        <div style="background:#fff;padding:24px;border:1px solid #ddd;border-radius:0 0 8px 8px">
          <p>Se realizó una modificación en el sistema InfraWatch:</p>
          <table style="width:100%;border-collapse:collapse;margin:12px 0">
            <tr style="background:#f0f4ff"><td style="padding:8px;font-weight:700;border:1px solid #ddd;width:35%">Acción</td>
                <td style="padding:8px;border:1px solid #ddd">{action}</td></tr>
            <tr><td style="padding:8px;font-weight:700;border:1px solid #ddd">Entidad</td>
                <td style="padding:8px;border:1px solid #ddd">{entity}</td></tr>
            <tr style="background:#f0f4ff"><td style="padding:8px;font-weight:700;border:1px solid #ddd">Descripción</td>
                <td style="padding:8px;border:1px solid #ddd">{description}</td></tr>
            <tr><td style="padding:8px;font-weight:700;border:1px solid #ddd">Realizado por</td>
                <td style="padding:8px;border:1px solid #ddd">{user}</td></tr>
            <tr style="background:#f0f4ff"><td style="padding:8px;font-weight:700;border:1px solid #ddd">Fecha/Hora</td>
                <td style="padding:8px;border:1px solid #ddd">{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</td></tr>
          </table>
          <p style="color:#666;font-size:12px">Este es un aviso automático del sistema InfraWatch v{VERSION}. No responder a este correo.</p>
        </div></div>"""
        send_email(notify_email, f"[InfraWatch] {action}: {entity} — {description[:60]}", html, db)
        entry.email_sent = True

# ─── ASSET HELPERS ────────────────────────────────────────────────────────────

def calc_depreciation(asset: Asset) -> dict:
    """Calcula depreciación lineal del activo"""
    if not asset.purchase_date or not asset.purchase_cost or asset.purchase_cost <= 0:
        return {"purchase_cost": 0, "current_value": 0, "depreciated_pct": 0, "years_used": 0}
    try:
        purchase = datetime.strptime(asset.purchase_date, "%Y-%m-%d").date()
        years    = (date.today() - purchase).days / 365.25
        life     = asset.useful_life_yrs or 4
        pct      = min(100, (years / life) * 100)
        value    = max(0, asset.purchase_cost * (1 - pct / 100))
        return {
            "purchase_cost":   asset.purchase_cost,
            "current_value":   round(value, 2),
            "depreciated_pct": round(pct, 1),
            "years_used":      round(years, 1),
            "useful_life_yrs": life,
        }
    except:
        return {"purchase_cost": 0, "current_value": 0, "depreciated_pct": 0, "years_used": 0}

def create_auto_maintenance(db, asset_id):
    existing = db.query(Maintenance).filter(
        Maintenance.asset_id == asset_id,
        Maintenance.auto_created == True,
        Maintenance.status == "pending"
    ).first()
    if existing:
        return existing
    today     = date.today()
    next_date = today + timedelta(days=MAINT_DAYS)
    m = Maintenance(
        asset_id=asset_id,
        maintenance_date=today.strftime("%Y-%m-%d"),
        next_date=next_date.strftime("%Y-%m-%d"),
        technician="TI",
        maint_type="preventive",
        observations=f"Mantenimiento preventivo anual — programado automáticamente por InfraWatch v{VERSION}",
        status="pending",
        auto_created=True,
    )
    db.add(m); return m

def auto_asset_from_agent(db, agent):
    """Crea activo + mantenimiento automático para un agente nuevo"""
    if db.query(Asset).filter(Asset.agent_id == agent.id).first():
        return None   # ya existe
    count = db.query(Asset).count()
    hn    = (agent.hostname or "").lower()
    atype = ("server" if any(k in hn for k in ["srv","server","svr","dc","nas"]) else
             "laptop" if any(k in hn for k in ["lap","notebook","nb","ltop"]) else "pc")
    asset = Asset(
        asset_code   = f"AUTO-{str(count + 1).zfill(5)}",
        asset_type   = atype,
        model        = agent.cpu_model or "",
        notes        = f"Activo creado automáticamente — Agente: {agent.hostname} ({agent.ip_address})",
        auto_created = True,
        agent_id     = agent.id,
        status       = "active",
    )
    db.add(asset); db.flush()
    create_auto_maintenance(db, asset.id)
    log.info(f"🖥 Auto-activo: {asset.asset_code} ← {agent.hostname}")
    return asset

def check_maintenance_alerts(db):
    today = date.today()
    for m in db.query(Maintenance).filter(Maintenance.status == "pending",
                                           Maintenance.next_date != None).all():
        try:
            nd = datetime.strptime(m.next_date, "%Y-%m-%d").date()
            dl = (nd - today).days
            code = m.asset.asset_code if m.asset else "?"
            if dl < 0:
                _new_alert(db, None, "maintenance_overdue", "critical",
                    f"⚠ Mantenimiento VENCIDO: {code} ({abs(dl)}d)")
            elif dl <= MAINT_WARN_DAYS:
                _new_alert(db, None, "maintenance_due", "warning",
                    f"🔧 Mantenimiento en {dl}d: {code} — {m.next_date}")
                if not m.email_sent and m.asset and m.asset.personnel and m.asset.personnel.email:
                    html = _email_maint(m.asset, m.asset.personnel,
                                        get_smtp(db).company or "Mi Empresa", dl, m.next_date)
                    ok = send_email(m.asset.personnel.email,
                        f"⚠ Mantenimiento preventivo en {dl} días — {code}", html, db)
                    if ok: m.email_sent = True
        except: pass
    db.commit()

def _new_alert(db, agent_id, atype, severity, message):
    cutoff = datetime.utcnow() - timedelta(hours=12)
    if not db.query(Alert).filter(Alert.alert_type==atype, Alert.message==message,
                                   Alert.created_at>cutoff, Alert.acknowledged==False).first():
        db.add(Alert(agent_id=agent_id, alert_type=atype, severity=severity, message=message))

# ─── EMAIL TEMPLATES ──────────────────────────────────────────────────────────

def _css():
    return """<style>@page{size:letter;margin:2cm}body{font-family:Arial,sans-serif;color:#1a1a1a;padding:32px;font-size:13px;line-height:1.5}
    .header{text-align:center;border-bottom:3px solid #1a56db;padding-bottom:16px;margin-bottom:24px}
    .company{font-size:20px;font-weight:900;color:#1a56db;letter-spacing:1px}
    .folio{text-align:right;font-size:11px;color:#777;margin-bottom:16px;font-family:monospace}
    .doc-title{font-size:16px;font-weight:800;text-align:center;text-transform:uppercase;letter-spacing:1px;margin:16px 0;padding:10px;background:#f0f4ff;border-radius:4px}
    .section-title{font-weight:700;background:#f0f4ff;padding:6px 12px;border-left:4px solid #1a56db;margin:16px 0 8px;font-size:12px;text-transform:uppercase}
    table{width:100%;border-collapse:collapse;margin-bottom:16px}td,th{border:1px solid #ddd;padding:7px 12px;font-size:12px}th{background:#f0f4ff;font-weight:700;width:38%}
    .terms{font-size:11px;color:#444;border:1px solid #ddd;padding:12px;background:#fafafa;border-radius:4px;margin-top:16px}.terms ol{padding-left:20px}.terms li{margin-bottom:5px}
    .firma-section{display:flex;justify-content:space-around;margin-top:56px}.firma-box{text-align:center;width:42%}.firma-line{border-top:1px solid #333;padding-top:8px;margin-top:56px;font-size:11px}
    .footer{text-align:center;font-size:10px;color:#999;margin-top:32px;border-top:1px solid #eee;padding-top:10px}
    .badge-alta{background:#d4edda;color:#155724;border:1px solid #c3e6cb;padding:4px 12px;border-radius:4px;font-weight:700;display:inline-block}
    .badge-baja{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;padding:4px 12px;border-radius:4px;font-weight:700;display:inline-block}
    .no-print{text-align:center;padding:12px;color:#fff;margin-bottom:20px;cursor:pointer;border-radius:4px}
    @media print{.no-print{display:none!important}}</style>"""

def generate_carta_alta(asset, person, company):
    today = datetime.now().strftime("%d de %B de %Y")
    folio = f"ALTA-{asset.asset_code}-{datetime.now().strftime('%Y%m%d%H%M')}"
    atype = {"laptop":"Laptop","pc":"Computadora","server":"Servidor",
              "switch":"Switch","firewall":"Firewall","printer":"Impresora"}.get(asset.asset_type,"Equipo")
    h = asset.agent.hostname if asset.agent else "—"
    ip = asset.agent.ip_address if asset.agent else "—"
    mac = asset.agent.mac_address if asset.agent else "—"
    so = f"{asset.agent.os_name} {asset.agent.os_version or ''}" if asset.agent else "—"
    dep = calc_depreciation(asset)
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
    <title>Carta Alta — {asset.asset_code}</title>{_css()}</head><body>
    <div class="no-print" style="background:#1a56db" onclick="window.print()">🖨 Imprimir / Guardar PDF</div>
    <div class="header"><div class="company">{company}</div>
    <div style="color:#555;font-size:13px">Departamento de Tecnologías de Información</div></div>
    <div class="folio">Folio: {folio}</div>
    <div class="doc-title">📋 Carta de Alta — Resguardo de Equipo de Cómputo</div>
    <div style="text-align:center;margin-bottom:16px"><span class="badge-alta">✅ ALTA DE EQUIPO</span></div>
    <p style="text-align:justify;margin-bottom:16px">Por medio del presente, yo <strong>{person.full_name}</strong>,
    empleado con número <strong>{person.employee_id}</strong>, declaro haber recibido en conformidad el equipo
    descrito a continuación, asignado por el Departamento de TI de <strong>{company}</strong>, y me comprometo
    a su cuidado y uso exclusivo para actividades laborales.</p>
    <div class="section-title">Datos del Responsable</div>
    <table>
      <tr><th>Nombre Completo</th><td>{person.full_name}</td></tr>
      <tr><th>No. Empleado</th><td>{person.employee_id}</td></tr>
      <tr><th>Puesto</th><td>{person.position}</td></tr>
      <tr><th>Área / Departamento</th><td>{person.department}</td></tr>
      <tr><th>Ubicación</th><td>{person.location or "—"}</td></tr>
      <tr><th>Correo</th><td>{person.email}</td></tr>
      <tr><th>Teléfono</th><td>{person.phone or "—"}</td></tr>
    </table>
    <div class="section-title">Datos del Equipo Asignado</div>
    <table>
      <tr><th>Código de Activo</th><td><strong>{asset.asset_code}</strong></td></tr>
      <tr><th>Tipo de Equipo</th><td>{atype}</td></tr>
      <tr><th>Marca</th><td>{asset.brand or "—"}</td></tr>
      <tr><th>Modelo</th><td>{asset.model or "—"}</td></tr>
      <tr><th>Número de Serie</th><td>{asset.serial_number or "—"}</td></tr>
      <tr><th>Hostname / Nombre</th><td>{h}</td></tr>
      <tr><th>Dirección IP</th><td>{ip}</td></tr>
      <tr><th>MAC Address</th><td>{mac}</td></tr>
      <tr><th>Sistema Operativo</th><td>{so}</td></tr>
      <tr><th>Ubicación Asignada</th><td>{asset.location or "—"}</td></tr>
      <tr><th>Valor del Equipo</th><td>${dep['purchase_cost']:,.2f} MXN</td></tr>
      <tr><th>Valor Actual (depreciado)</th><td>${dep['current_value']:,.2f} MXN ({dep['depreciated_pct']}% depreciado)</td></tr>
      <tr><th>Fecha de Alta</th><td><strong>{today}</strong></td></tr>
    </table>
    <div class="terms"><strong>El responsable acepta las siguientes condiciones de uso:</strong><ol>
      <li>El equipo es propiedad exclusiva de {company} y se usará solo para actividades laborales.</li>
      <li>Deberá notificar inmediatamente al área de TI cualquier falla, pérdida, robo o daño.</li>
      <li>Queda prohibida la instalación de software no autorizado por TI.</li>
      <li>El equipo deberá devolverse al término de la relación laboral o cuando TI lo requiera.</li>
      <li>El área de TI puede realizar auditorías y monitoreo del equipo en cualquier momento.</li>
      <li>No podrá prestar el equipo a terceros sin autorización del área de TI.</li>
      <li>En caso de pérdida o daño por negligencia, el responsable cubrirá el costo de reposición.</li>
    </ol></div>
    <div class="firma-section">
      <div class="firma-box"><div class="firma-line"><strong>{person.full_name}</strong><br>
      {person.employee_id} — {person.position}<br><em>Recibí conforme</em></div></div>
      <div class="firma-box"><div class="firma-line"><strong>Responsable de TI</strong><br>
      Departamento TI — {company}<br><em>Entregué</em></div></div>
    </div>
    <div class="footer">InfraWatch v{VERSION} — {company} — {today} — Folio: {folio}</div>
    </body></html>"""

def generate_carta_baja(asset, person, company, notes=""):
    today  = datetime.now().strftime("%d de %B de %Y")
    folio  = f"BAJA-{asset.asset_code}-{datetime.now().strftime('%Y%m%d%H%M')}"
    since  = asset.assigned_at.strftime("%d/%m/%Y") if asset.assigned_at else "—"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
    <title>Carta Baja — {asset.asset_code}</title>{_css()}</head><body>
    <div class="no-print" style="background:#dc3545" onclick="window.print()">🖨 Imprimir / Guardar PDF</div>
    <div class="header"><div class="company">{company}</div>
    <div style="color:#555;font-size:13px">Departamento de Tecnologías de Información</div></div>
    <div class="folio">Folio: {folio}</div>
    <div class="doc-title">📋 Carta de Baja — Devolución de Equipo</div>
    <div style="text-align:center;margin-bottom:16px"><span class="badge-baja">🔴 BAJA DE EQUIPO</span></div>
    <p style="text-align:justify;margin-bottom:16px">Por medio del presente, yo <strong>{person.full_name}</strong>,
    empleado con número <strong>{person.employee_id}</strong>, declaro haber devuelto en conformidad el equipo
    descrito a continuación al Departamento de TI de <strong>{company}</strong>.</p>
    <div class="section-title">Datos del Empleado</div>
    <table>
      <tr><th>Nombre Completo</th><td>{person.full_name}</td></tr>
      <tr><th>No. Empleado</th><td>{person.employee_id}</td></tr>
      <tr><th>Puesto</th><td>{person.position}</td></tr>
      <tr><th>Departamento</th><td>{person.department}</td></tr>
    </table>
    <div class="section-title">Datos del Equipo Devuelto</div>
    <table>
      <tr><th>Código de Activo</th><td><strong>{asset.asset_code}</strong></td></tr>
      <tr><th>Tipo / Equipo</th><td>{asset.asset_type} — {asset.brand} {asset.model}</td></tr>
      <tr><th>Número de Serie</th><td>{asset.serial_number or "—"}</td></tr>
      <tr><th>Fecha de Alta</th><td>{since}</td></tr>
      <tr><th>Fecha de Baja</th><td><strong>{today}</strong></td></tr>
      <tr><th>Motivo</th><td>{notes or "Baja de equipo"}</td></tr>
    </table>
    <p>Ambas partes confirman que el equipo fue revisado y devuelto en las condiciones acordadas.</p>
    <div class="firma-section">
      <div class="firma-box"><div class="firma-line"><strong>{person.full_name}</strong><br>
      {person.employee_id}<br><em>Entregué</em></div></div>
      <div class="firma-box"><div class="firma-line"><strong>Responsable de TI</strong><br>
      Departamento TI — {company}<br><em>Recibí</em></div></div>
    </div>
    <div class="footer">InfraWatch v{VERSION} — {company} — {today} — Folio: {folio}</div>
    </body></html>"""

def _email_maint(asset, person, company, days, next_date):
    color = "#dc3545" if days<=7 else "#fd7e14" if days<=14 else "#ffc107"
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f5f7fa;padding:20px">
    <div style="background:{color};color:#fff;padding:22px;border-radius:8px 8px 0 0;text-align:center">
      <h1 style="margin:0">⚠️ InfraWatch — {company}</h1><p style="margin:4px 0 0">Aviso Mantenimiento Preventivo</p></div>
    <div style="background:#fff;padding:24px;border-radius:0 0 8px 8px">
      <p>Estimado/a <strong>{person.full_name}</strong>, el equipo a su cargo requiere mantenimiento preventivo
      en <strong style="color:{color}">{days} días</strong>.</p>
      <table style="width:100%;border-collapse:collapse;margin:14px 0">
        <tr style="background:#fff8e1"><td style="padding:8px;font-weight:700;border:1px solid #ddd">Activo</td>
            <td style="padding:8px;border:1px solid #ddd"><strong>{asset.asset_code}</strong></td></tr>
        <tr><td style="padding:8px;font-weight:700;border:1px solid #ddd">Equipo</td>
            <td style="padding:8px;border:1px solid #ddd">{asset.asset_type} {asset.brand} {asset.model}</td></tr>
        <tr style="background:#fff8e1"><td style="padding:8px;font-weight:700;border:1px solid #ddd;color:{color}">Fecha límite</td>
            <td style="padding:8px;border:1px solid #ddd;font-weight:700;color:{color}">{next_date}</td></tr>
      </table>
      <p>Por favor coordine con TI para programar el mantenimiento.</p>
    </div></div>"""

def _email_asignacion(asset, person, company, carta_url):
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f5f7fa;padding:20px">
    <div style="background:#1a56db;color:#fff;padding:22px;border-radius:8px 8px 0 0;text-align:center">
      <h1 style="margin:0">🛡 InfraWatch — {company}</h1><p style="margin:4px 0 0">Asignación de Equipo</p></div>
    <div style="background:#fff;padding:24px;border-radius:0 0 8px 8px">
      <p>Estimado/a <strong>{person.full_name}</strong>, se le ha asignado el siguiente equipo.</p>
      <p>Por favor imprima la carta responsiva, fírmela y entréguela al área de TI.</p>
      <table style="width:100%;border-collapse:collapse;margin:14px 0">
        <tr style="background:#f0f4ff"><td style="padding:8px;font-weight:700;border:1px solid #ddd">Código</td>
            <td style="padding:8px;border:1px solid #ddd"><strong>{asset.asset_code}</strong></td></tr>
        <tr><td style="padding:8px;font-weight:700;border:1px solid #ddd">Equipo</td>
            <td style="padding:8px;border:1px solid #ddd">{asset.asset_type} {asset.brand} {asset.model}</td></tr>
        <tr style="background:#f0f4ff"><td style="padding:8px;font-weight:700;border:1px solid #ddd">Hostname</td>
            <td style="padding:8px;border:1px solid #ddd">{asset.agent.hostname if asset.agent else '—'}</td></tr>
      </table>
      <div style="text-align:center;margin:20px 0">
        <a href="{carta_url}" style="background:#1a56db;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700">
          📄 Ver e Imprimir Carta de Alta
        </a>
      </div>
    </div></div>"""

def _email_baja(asset, person, company, carta_url):
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f5f7fa;padding:20px">
    <div style="background:#dc3545;color:#fff;padding:22px;border-radius:8px 8px 0 0;text-align:center">
      <h1 style="margin:0">🛡 InfraWatch — {company}</h1><p style="margin:4px 0 0">Baja de Equipo</p></div>
    <div style="background:#fff;padding:24px;border-radius:0 0 8px 8px">
      <p>Estimado/a <strong>{person.full_name}</strong>, se ha procesado la <strong>baja del equipo</strong> {asset.asset_code}.</p>
      <div style="text-align:center;margin:20px 0">
        <a href="{carta_url}" style="background:#dc3545;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700">
          📄 Ver e Imprimir Carta de Baja
        </a>
      </div>
    </div></div>"""

# ─── INIT DB ──────────────────────────────────────────────────────────────────

def init_db():
    db = SessionLocal()
    # Admin user
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=hash_password("infrawatch"),
                    full_name="Administrador", email="admin@infrawatch.local", role="admin"))
        db.commit()
        log.info("✅ admin / infrawatch creado")
    # SMTP config
    if not db.query(SMTPConfig).first():
        db.add(SMTPConfig()); db.commit()
    # Default areas
    for area_name, color in [("TI","#58a6ff"),("RH","#a371f7"),("Administración","#3fb950"),
                               ("Producción","#d29922"),("Finanzas","#f778ba"),("Dirección","#e3b341")]:
        if not db.query(Area).filter(Area.name == area_name).first():
            db.add(Area(name=area_name, color=color, created_by="system"))
    db.commit()
    db.close()

# ─── APP ──────────────────────────────────────────────────────────────────────
app = FastAPI(title=APP_NAME, version=VERSION, docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(data: UserLoginSchema, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == data.username).first()
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    return {"token": create_token(u.id, u.username, u.role),
            "username": u.username, "role": u.role, "full_name": u.full_name}

@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role,
            "full_name": user.full_name, "email": user.email}

# ─── AREAS (solo IT/admin) ────────────────────────────────────────────────────

@app.get("/api/areas")
def list_areas(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": a.id, "name": a.name, "description": a.description,
             "color": a.color, "is_active": a.is_active,
             "personnel_count": len(a.personnel)} for a in db.query(Area).all()]

@app.post("/api/areas")
def create_area(data: AreaSchema, user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    if db.query(Area).filter(Area.name == data.name).first():
        raise HTTPException(400, "Área ya existe")
    a = Area(**data.dict(), created_by=user.username); db.add(a); db.commit(); db.refresh(a)
    audit(db, user.username, "CREATE", "Area", a.id, f"Nueva área: {a.name}")
    db.commit()
    return {"id": a.id, "name": a.name}

@app.put("/api/areas/{aid}")
def update_area(aid: int, data: AreaSchema, user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    a = db.query(Area).filter(Area.id == aid).first()
    if not a: raise HTTPException(404)
    for k, v in data.dict().items(): setattr(a, k, v)
    db.commit()
    audit(db, user.username, "UPDATE", "Area", aid, f"Área modificada: {a.name}")
    db.commit()
    return {"updated": True}

@app.delete("/api/areas/{aid}")
def delete_area(aid: int, user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    a = db.query(Area).filter(Area.id == aid).first()
    if not a: raise HTTPException(404)
    if a.personnel: raise HTTPException(400, "No se puede eliminar área con personal asignado")
    db.delete(a); db.commit()
    return {"deleted": True}

# ─── PERSONNEL (RH e IT) ──────────────────────────────────────────────────────

def _person_dict(p):
    return {
        "id": p.id, "employee_id": p.employee_id, "full_name": p.full_name,
        "position": p.position, "department": p.department,
        "area_id": p.area_id,
        "area_name": p.area_rel.name if p.area_rel else p.department,
        "area_color": p.area_rel.color if p.area_rel else "#58a6ff",
        "email": p.email, "phone": p.phone, "location": p.location,
        "is_active": p.is_active, "notes": p.notes,
        "created_at": p.created_at.isoformat(),
        "asset_count": len([a for a in p.assets if a.personnel_id == p.id]),
        "current_assets": [{"id": a.id, "asset_code": a.asset_code, "asset_type": a.asset_type,
            "brand": a.brand, "model": a.model,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None}
            for a in p.assets if a.personnel_id == p.id],
    }

@app.get("/api/personnel")
def list_personnel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_person_dict(p) for p in db.query(Personnel).order_by(Personnel.full_name).all()]

@app.get("/api/personnel/{pid}")
def get_personnel(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(404)
    return _person_dict(p)

@app.get("/api/personnel/{pid}/history")
def personnel_history(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = db.query(AssetHistory).filter(AssetHistory.personnel_id == pid)\
          .order_by(AssetHistory.action_date.desc()).all()
    return [{"id": x.id, "action": x.action, "action_date": x.action_date.isoformat(),
             "notes": x.notes, "created_by": x.created_by, "carta_path": bool(x.carta_path),
             "asset": {"id": x.asset.id, "asset_code": x.asset.asset_code,
                        "asset_type": x.asset.asset_type, "brand": x.asset.brand,
                        "model": x.asset.model} if x.asset else None} for x in h]

@app.post("/api/personnel")
def create_personnel(data: PersonnelSchema, request: Request,
                     user: User = Depends(require_rh_admin), db: Session = Depends(get_db)):
    if user.role == "rh" and user.role not in ["admin", "it", "rh"]:
        raise HTTPException(403)
    if db.query(Personnel).filter(Personnel.employee_id == data.employee_id).first():
        raise HTTPException(400, "ID de empleado ya existe")
    p = Personnel(**data.dict(), created_by=user.username)
    db.add(p); db.commit(); db.refresh(p)
    audit(db, user.username, "CREATE", "Personnel", p.id,
          f"Nuevo empleado: {p.full_name} ({p.employee_id})", notify_email=p.email)
    db.commit()
    return {"id": p.id, "employee_id": p.employee_id}

@app.put("/api/personnel/{pid}")
def update_personnel(pid: int, data: PersonnelSchema, request: Request,
                     user: User = Depends(require_rh_admin), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(404)
    changes = []
    for k, v in data.dict().items():
        old = getattr(p, k)
        if str(old) != str(v): changes.append(f"{k}: {old}→{v}")
        setattr(p, k, v)
    db.commit()
    if changes:
        desc = f"Empleado modificado: {p.full_name} — " + ", ".join(changes[:3])
        audit(db, user.username, "UPDATE", "Personnel", pid, desc, notify_email=p.email)
        db.commit()
    return {"updated": True}

@app.patch("/api/personnel/{pid}/toggle")
def toggle_personnel(pid: int, user: User = Depends(require_rh_admin), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(404)
    p.is_active = not p.is_active; db.commit()
    action = "activado" if p.is_active else "desactivado"
    audit(db, user.username, "UPDATE", "Personnel", pid,
          f"Empleado {action}: {p.full_name}", notify_email=p.email)
    db.commit()
    return {"is_active": p.is_active}

@app.delete("/api/personnel/{pid}")
def delete_personnel(pid: int, user: User = Depends(require_rh_admin), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(404)
    if any(a.personnel_id == p.id for a in p.assets):
        raise HTTPException(400, "Tiene equipos activos asignados. Da de baja los equipos primero.")
    name = p.full_name; email = p.email
    db.delete(p); db.commit()
    audit(db, user.username, "DELETE", "Personnel", pid,
          f"Empleado eliminado: {name}", notify_email=email)
    db.commit()
    return {"deleted": True}

@app.post("/api/personnel/import-csv")
async def import_personnel_csv(file: UploadFile = File(...),
                                user: User = Depends(require_rh_admin),
                                db: Session = Depends(get_db)):
    content = (await file.read()).decode("utf-8-sig")
    reader  = csv.DictReader(io.StringIO(content))
    created = 0; errors = []
    for row in reader:
        try:
            emp_id = (row.get("employee_id") or row.get("id") or "").strip()
            name   = (row.get("full_name") or row.get("nombre") or "").strip()
            if not emp_id or not name: continue
            if db.query(Personnel).filter(Personnel.employee_id == emp_id).first():
                errors.append(f"{emp_id}: ya existe")
                continue
            p = Personnel(
                employee_id=emp_id, full_name=name,
                position=(row.get("position") or row.get("puesto") or "").strip(),
                department=(row.get("department") or row.get("departamento") or "").strip(),
                email=(row.get("email") or "").strip(),
                phone=(row.get("phone") or row.get("telefono") or "").strip(),
                location=(row.get("location") or row.get("ubicacion") or "").strip(),
                created_by=user.username,
            )
            db.add(p); created += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    return {"created": created, "errors": errors}

# ─── AGENTS ───────────────────────────────────────────────────────────────────

@app.post("/api/agents/register")
def agent_register(data: AgentRegisterSchema, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(
        (Agent.mac_address == data.mac_address) | (Agent.hostname == data.hostname)
    ).first()
    is_new = not agent
    if agent:
        for k, v in data.dict().items(): setattr(agent, k, v)
        agent.status = "online"; agent.last_seen = datetime.utcnow()
    else:
        agent = Agent(**data.dict(), status="online"); db.add(agent); db.flush()
        _new_alert(db, agent.id, "new_device", "info",
                   f"Nuevo dispositivo: {data.hostname} ({data.ip_address})")
    db.commit(); db.refresh(agent)
    if is_new:
        auto_asset_from_agent(db, agent)
        db.commit()
    log.info(f"{'📥 Nuevo' if is_new else '🔄'} agente: {agent.hostname}")
    return {"uid": agent.uid, "id": agent.id, "registered": is_new}

@app.post("/api/agents/{uid}/heartbeat")
def agent_heartbeat(uid: str, data: HeartbeatSchema, db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.uid == uid).first()
    if not a: raise HTTPException(404)
    a.status = "online"; a.last_seen = datetime.utcnow()
    db.add(Metric(agent_id=a.id, **{k:v for k,v in data.dict().items() if k!="open_ports"},
                  open_ports=json.dumps(data.open_ports)))
    # v2.3 — umbrales configurables por agente
    t = db.query(AgentThreshold).filter(AgentThreshold.agent_id == a.id).first()
    cpu_w  = t.cpu_warn  if t else 75; cpu_c  = t.cpu_crit  if t else 90
    ram_w  = t.ram_warn  if t else 80; ram_c  = t.ram_crit  if t else 90
    disk_w = t.disk_warn if t else 80; disk_c = t.disk_crit if t else 90
    if data.cpu_percent  >= cpu_c:  _new_alert(db,a.id,"cpu","critical",  f"{a.hostname}: CPU {data.cpu_percent:.0f}% (≥{cpu_c}%)")
    elif data.cpu_percent>= cpu_w:  _new_alert(db,a.id,"cpu","warning",   f"{a.hostname}: CPU {data.cpu_percent:.0f}% (≥{cpu_w}%)")
    if data.ram_percent  >= ram_c:  _new_alert(db,a.id,"ram","critical",  f"{a.hostname}: RAM {data.ram_percent:.0f}% (≥{ram_c}%)")
    elif data.ram_percent>= ram_w:  _new_alert(db,a.id,"ram","warning",   f"{a.hostname}: RAM {data.ram_percent:.0f}%")
    if data.disk_percent >= disk_c: _new_alert(db,a.id,"disk","critical", f"{a.hostname}: Disco {data.disk_percent:.0f}% (≥{disk_c}%)")
    elif data.disk_percent>=disk_w: _new_alert(db,a.id,"disk","warning",  f"{a.hostname}: Disco {data.disk_percent:.0f}%")
    db.commit()
    return {"status": "ok"}

@app.get("/api/agents")
def list_agents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    for a in db.query(Agent).filter(Agent.last_seen < cutoff, Agent.status=="online").all():
        a.status = "offline"
        _new_alert(db, a.id, "offline", "warning", f"{a.hostname} está OFFLINE")
    db.commit(); check_maintenance_alerts(db)
    result = []
    for a in db.query(Agent).all():
        m     = db.query(Metric).filter(Metric.agent_id==a.id).order_by(Metric.timestamp.desc()).first()
        asset = db.query(Asset).filter(Asset.agent_id==a.id).first()
        result.append({
            "id": a.id, "uid": a.uid, "hostname": a.hostname,
            "ip_address": a.ip_address, "mac_address": a.mac_address,
            "os_name": a.os_name, "os_version": a.os_version,
            "cpu_model": a.cpu_model, "cpu_cores": a.cpu_cores,
            "ram_total_gb": a.ram_total_gb, "disk_total_gb": a.disk_total_gb,
            "tags": json.loads(a.tags or "[]"), "status": a.status,
            "last_seen": a.last_seen.isoformat() if a.last_seen else None,
            "asset_code": asset.asset_code if asset else None,
            "asset_id":   asset.id if asset else None,
            "personnel":  {"id": asset.personnel.id, "full_name": asset.personnel.full_name,
                           "position": asset.personnel.position, "department": asset.personnel.department}
                          if asset and asset.personnel else None,
            "metrics": {"cpu_percent": m.cpu_percent, "ram_percent": m.ram_percent,
                        "disk_percent": m.disk_percent, "uptime_seconds": m.uptime_seconds,
                        "process_count": m.process_count} if m else None
        })
    return result

@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(404)
    metrics = db.query(Metric).filter(Metric.agent_id==agent_id)\
                .order_by(Metric.timestamp.desc()).limit(60).all()
    asset   = db.query(Asset).filter(Asset.agent_id==agent_id).first()
    nm = None
    if asset:
        pm = db.query(Maintenance).filter(Maintenance.asset_id==asset.id,
              Maintenance.status=="pending").order_by(Maintenance.next_date).first()
        if pm and pm.next_date:
            dl = (datetime.strptime(pm.next_date,"%Y-%m-%d").date()-date.today()).days
            nm = {"next_date": pm.next_date, "days_left": dl}
    return {
        "id": a.id, "uid": a.uid, "hostname": a.hostname,
        "ip_address": a.ip_address, "mac_address": a.mac_address,
        "os_name": a.os_name, "os_version": a.os_version,
        "cpu_model": a.cpu_model, "cpu_cores": a.cpu_cores,
        "ram_total_gb": a.ram_total_gb, "disk_total_gb": a.disk_total_gb,
        "tags": json.loads(a.tags or "[]"), "status": a.status,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        "asset": {"id": asset.id, "asset_code": asset.asset_code,
                  "personnel_id": asset.personnel_id,
                  "personnel_name": asset.personnel.full_name if asset.personnel else None,
                  "auto_created": asset.auto_created,
                  "carta_alta_uploaded": bool(asset.carta_alta_path),
                  "carta_baja_uploaded": bool(asset.carta_baja_path),
                  "depreciation": calc_depreciation(asset)} if asset else None,
        "next_maintenance": nm,
        "metrics_history": [{"timestamp": m.timestamp.isoformat(), "cpu_percent": m.cpu_percent,
            "ram_percent": m.ram_percent, "disk_percent": m.disk_percent,
            "net_sent": m.net_bytes_sent, "net_recv": m.net_bytes_recv,
            "process_count": m.process_count, "open_ports": json.loads(m.open_ports or "[]")}
            for m in reversed(metrics)]
    }

@app.put("/api/agents/{agent_id}/tags")
def update_tags(agent_id: int, data: TagUpdateSchema,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(404)
    a.tags = json.dumps([t.upper().strip() for t in data.tags])
    db.commit(); return {"tags": json.loads(a.tags)}

@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(404)
    db.delete(a); db.commit(); return {"deleted": True}

# ─── ASSETS ───────────────────────────────────────────────────────────────────

def _asset_dict(a: Asset):
    dep = calc_depreciation(a)
    pm  = min((m.next_date for m in a.maintenances if m.next_date and m.status=="pending"), default=None)
    return {
        "id": a.id, "asset_code": a.asset_code, "asset_type": a.asset_type,
        "brand": a.brand, "model": a.model, "serial_number": a.serial_number,
        "purchase_date": a.purchase_date, "purchase_cost": a.purchase_cost,
        "useful_life_yrs": a.useful_life_yrs,
        "responsible": a.responsible, "personnel_id": a.personnel_id,
        "location": a.location, "status": a.status, "notes": a.notes,
        "auto_created": a.auto_created, "carta_sent": a.carta_sent,
        "carta_sent_at": a.carta_sent_at.isoformat() if a.carta_sent_at else None,
        "carta_alta_uploaded": bool(a.carta_alta_path),
        "carta_baja_uploaded": bool(a.carta_baja_path),
        "assigned_at":   a.assigned_at.isoformat() if a.assigned_at else None,
        "unassigned_at": a.unassigned_at.isoformat() if a.unassigned_at else None,
        "created_at":    a.created_at.isoformat(),
        "agent_id": a.agent_id,
        "depreciation": dep,
        "agent": {"hostname": a.agent.hostname, "ip_address": a.agent.ip_address,
                  "mac_address": a.agent.mac_address, "os_name": a.agent.os_name,
                  "os_version": a.agent.os_version, "status": a.agent.status} if a.agent else None,
        "personnel": {"id": a.personnel.id, "full_name": a.personnel.full_name,
                      "employee_id": a.personnel.employee_id, "position": a.personnel.position,
                      "department": a.personnel.department, "email": a.personnel.email,
                      "area_name": a.personnel.area_rel.name if a.personnel.area_rel else a.personnel.department,
                      "area_color": a.personnel.area_rel.color if a.personnel.area_rel else "#58a6ff"
                     } if a.personnel else None,
        "maintenance_count": len(a.maintenances),
        "last_maintenance":  max((m.maintenance_date for m in a.maintenances), default=None),
        "next_maintenance":  pm,
    }

@app.get("/api/assets")
def list_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_asset_dict(a) for a in db.query(Asset).all()]

@app.post("/api/assets")
def create_asset(data: AssetSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(Asset).count()
    asset = Asset(asset_code=f"ACT-{str(count+1).zfill(5)}", **data.dict())
    db.add(asset); db.flush()
    create_auto_maintenance(db, asset.id)
    db.commit(); db.refresh(asset)
    audit(db, user.username, "CREATE", "Asset", asset.id, f"Nuevo activo: {asset.asset_code}")
    db.commit()
    return {"id": asset.id, "asset_code": asset.asset_code}

@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, data: AssetSchema,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    for k, v in data.dict().items(): setattr(a, k, v)
    db.commit()
    return {"updated": True}

@app.post("/api/assets/{asset_id}/assign")
def assign_asset(asset_id: int, data: AssetAssignSchema, background_tasks: BackgroundTasks,
                 request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset  = db.query(Asset).filter(Asset.id == asset_id).first()
    person = db.query(Personnel).filter(Personnel.id == data.personnel_id).first()
    if not asset:  raise HTTPException(404, "Activo no encontrado")
    if not person: raise HTTPException(404, "Empleado no encontrado")
    if not person.is_active: raise HTTPException(400, "El empleado está inactivo")

    # Baja del responsable anterior si hay cambio
    if asset.personnel_id and asset.personnel_id != data.personnel_id:
        db.add(AssetHistory(asset_id=asset_id, personnel_id=asset.personnel_id,
                            action="baja", notes="Reasignación a nuevo responsable",
                            created_by=user.username))

    asset.personnel_id  = data.personnel_id
    asset.responsible   = person.full_name
    asset.assigned_at   = datetime.utcnow()
    asset.unassigned_at = None
    asset.carta_sent    = False

    db.add(AssetHistory(asset_id=asset_id, personnel_id=data.personnel_id,
                        action="alta", notes=data.notes or "Asignación de equipo",
                        created_by=user.username))
    db.commit(); db.refresh(asset)

    base_url  = str(request.base_url).rstrip("/")
    carta_url = f"{base_url}/api/assets/{asset_id}/carta/alta"

    if data.send_email and person.email:
        html = _email_asignacion(asset, person, get_smtp(db).company or "Mi Empresa", carta_url)
        background_tasks.add_task(send_email, person.email,
            f"📋 Asignación de equipo {asset.asset_code}", html, db)
        asset.carta_sent    = True
        asset.carta_sent_at = datetime.utcnow()
        db.commit()

    audit(db, user.username, "UPDATE", "Asset", asset_id,
          f"Asignado {asset.asset_code} → {person.full_name}", notify_email=person.email)
    db.commit()
    return {"assigned": True, "personnel": person.full_name, "carta_url": carta_url}

@app.post("/api/assets/{asset_id}/baja")
def baja_asset(asset_id: int, data: AssetBajaSchema, background_tasks: BackgroundTasks,
               request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset: raise HTTPException(404)
    if not asset.personnel_id: raise HTTPException(400, "Sin responsable asignado")

    person    = db.query(Personnel).filter(Personnel.id == asset.personnel_id).first()
    base_url  = str(request.base_url).rstrip("/")
    carta_url = f"{base_url}/api/assets/{asset_id}/carta/baja"

    db.add(AssetHistory(asset_id=asset_id, personnel_id=asset.personnel_id,
                        action="baja", notes=data.notes or "Baja de equipo",
                        created_by=user.username))

    if data.send_email and person and person.email:
        html = _email_baja(asset, person, get_smtp(db).company or "Mi Empresa", carta_url)
        background_tasks.add_task(send_email, person.email,
            f"📋 Baja de equipo {asset.asset_code}", html, db)

    if person:
        audit(db, user.username, "UPDATE", "Asset", asset_id,
              f"Baja {asset.asset_code} ← {person.full_name} ({data.notes or ''})",
              notify_email=person.email)

    asset.unassigned_at = datetime.utcnow()
    asset.personnel_id  = None
    asset.responsible   = ""
    asset.carta_sent    = False
    db.commit()
    return {"baja": True, "carta_url": carta_url}

@app.get("/api/assets/{asset_id}/carta/alta", response_class=HTMLResponse)
def carta_alta_view(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    if not a.personnel:
        return HTMLResponse("<h2 style='font-family:Arial;padding:40px;color:#dc3545'>Sin responsable asignado</h2>", 400)
    cfg = get_smtp(db)
    return HTMLResponse(generate_carta_alta(a, a.personnel, cfg.company or "Mi Empresa"))

@app.get("/api/assets/{asset_id}/carta/baja", response_class=HTMLResponse)
def carta_baja_view(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    h = db.query(AssetHistory).filter(AssetHistory.asset_id==asset_id,
          AssetHistory.action=="baja").order_by(AssetHistory.action_date.desc()).first()
    if not h or not h.personnel:
        return HTMLResponse("<h2 style='font-family:Arial;padding:40px'>Sin historial de baja</h2>", 400)
    cfg = get_smtp(db)
    return HTMLResponse(generate_carta_baja(a, h.personnel, cfg.company or "Mi Empresa", h.notes))

@app.get("/api/assets/{asset_id}/carta", response_class=HTMLResponse)
def carta_legacy(asset_id: int, db: Session = Depends(get_db)):
    return carta_alta_view(asset_id, db)

@app.post("/api/assets/{asset_id}/upload/{tipo}")
async def upload_carta(asset_id: int, tipo: str, file: UploadFile = File(...),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if tipo not in ("alta","baja"): raise HTTPException(400, "tipo debe ser alta o baja")
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    ext      = os.path.splitext(file.filename or "")[1] or ".pdf"
    filename = f"carta_{tipo}_{asset_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
    path     = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f: shutil.copyfileobj(file.file, f)
    if tipo == "alta": a.carta_alta_path = path
    else:              a.carta_baja_path = path
    # Update history record
    hist = db.query(AssetHistory).filter(AssetHistory.asset_id==asset_id,
            AssetHistory.action==tipo).order_by(AssetHistory.action_date.desc()).first()
    if hist: hist.carta_path = path
    db.commit()
    return {"uploaded": True, "filename": filename}

@app.get("/api/assets/{asset_id}/download/{tipo}")
def download_carta(asset_id: int, tipo: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    path = a.carta_alta_path if tipo == "alta" else a.carta_baja_path
    if not a or not path or not os.path.exists(path):
        raise HTTPException(404, "Carta no encontrada")
    return FileResponse(path, filename=f"carta_{tipo}_{a.asset_code}.pdf")

@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    db.delete(a); db.commit(); return {"deleted": True}

# ─── MAINTENANCE ──────────────────────────────────────────────────────────────

@app.get("/api/maintenance")
def list_maintenance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    return [{
        "id": m.id, "asset_id": m.asset_id,
        "asset_code": m.asset.asset_code if m.asset else "",
        "asset_name": f"{m.asset.brand} {m.asset.model}" if m.asset else "",
        "responsible": m.asset.personnel.full_name if m.asset and m.asset.personnel else "Sin asignar",
        "resp_email":  m.asset.personnel.email if m.asset and m.asset.personnel else "",
        "maintenance_date": m.maintenance_date, "next_date": m.next_date,
        "technician": m.technician, "maint_type": m.maint_type,
        "observations": m.observations, "status": m.status,
        "auto_created": m.auto_created, "email_sent": m.email_sent,
        "days_left": (datetime.strptime(m.next_date,"%Y-%m-%d").date()-today).days if m.next_date else None,
        "created_at": m.created_at.isoformat(),
    } for m in db.query(Maintenance).order_by(Maintenance.created_at.desc()).all()]

@app.post("/api/maintenance")
def create_maintenance(data: MaintenanceSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = Maintenance(**data.dict()); db.add(m)
    a = db.query(Asset).filter(Asset.id == data.asset_id).first()
    if a: a.status = "active" if data.status == "completed" else "maintenance"
    db.commit(); db.refresh(m); return {"id": m.id}

@app.put("/api/maintenance/{mid}/complete")
def complete_maintenance(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Maintenance).filter(Maintenance.id == mid).first()
    if not m: raise HTTPException(404)
    m.status           = "completed"
    m.maintenance_date = date.today().strftime("%Y-%m-%d")
    if m.asset_id:
        next_year = date.today() + timedelta(days=MAINT_DAYS)
        db.add(Maintenance(asset_id=m.asset_id,
            maintenance_date=date.today().strftime("%Y-%m-%d"),
            next_date=next_year.strftime("%Y-%m-%d"), technician=m.technician,
            maint_type="preventive",
            observations=f"Mantenimiento preventivo anual renovado — InfraWatch v{VERSION}",
            status="pending", auto_created=True))
    db.commit(); return {"completed": True}

@app.delete("/api/maintenance/{mid}")
def delete_maintenance(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Maintenance).filter(Maintenance.id == mid).first()
    if not m: raise HTTPException(404)
    db.delete(m); db.commit(); return {"deleted": True}

# ─── ALERTS ───────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": a.id, "agent_id": a.agent_id, "alert_type": a.alert_type,
             "severity": a.severity, "message": a.message, "acknowledged": a.acknowledged,
             "created_at": a.created_at.isoformat()}
            for a in db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()]

@app.put("/api/alerts/{alert_id}/acknowledge")
def ack_alert(alert_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Alert).filter(Alert.id == alert_id).first()
    if not a: raise HTTPException(404)
    a.acknowledged = True; db.commit(); return {"acknowledged": True}

@app.post("/api/alerts/ack-all")
def ack_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.acknowledged==False).update({"acknowledged": True})
    db.commit(); return {"acknowledged": True}

# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_maintenance_alerts(db)
    agents = db.query(Agent).all()
    online = [a for a in agents if a.status == "online"]
    assets = db.query(Asset).all()
    today  = date.today()

    overdue = upcoming_list = []
    pending_m = 0
    for m in db.query(Maintenance).filter(Maintenance.status=="pending", Maintenance.next_date!=None).all():
        try:
            nd = datetime.strptime(m.next_date,"%Y-%m-%d").date()
            dl = (nd-today).days; pending_m += 1
            if dl < 0 or dl <= 30:
                upcoming_list.append({"asset_code": m.asset.asset_code if m.asset else "",
                    "asset_name": f"{m.asset.brand} {m.asset.model}" if m.asset else "",
                    "responsible": m.asset.personnel.full_name if m.asset and m.asset.personnel else "Sin asignar",
                    "next_date": m.next_date, "days_left": dl})
        except: pass
    upcoming_list.sort(key=lambda x: x["days_left"])

    cpus=[]; rams=[]; disks=[]
    for a in online:
        m = db.query(Metric).filter(Metric.agent_id==a.id).order_by(Metric.timestamp.desc()).first()
        if m: cpus.append(m.cpu_percent); rams.append(m.ram_percent); disks.append(m.disk_percent)

    os_dist = {}; type_dist = {}; dept_dist = {}
    for a in agents:
        k = a.os_name or "Unknown"; os_dist[k] = os_dist.get(k,0)+1
    for a in assets:
        type_dist[a.asset_type] = type_dist.get(a.asset_type,0)+1
    for p in db.query(Personnel).all():
        d = (p.area_rel.name if p.area_rel else p.department) or "Sin área"
        dept_dist[d] = dept_dist.get(d,0)+1

    overdue_count = sum(1 for x in upcoming_list if x["days_left"]<0)

    return {
        "agents":    {"total": len(agents), "online": len(online), "offline": len(agents)-len(online)},
        "assets":    {"total": len(assets), "active": sum(1 for a in assets if a.status=="active"),
                      "pending_assign": sum(1 for a in assets if not a.personnel_id),
                      "auto_created":   sum(1 for a in assets if a.auto_created)},
        "personnel": {"total": db.query(Personnel).count(),
                      "active": db.query(Personnel).filter(Personnel.is_active==True).count()},
        "maintenance": {"pending": pending_m, "overdue": overdue_count,
                        "upcoming_30d": len([x for x in upcoming_list if 0<=x["days_left"]<=30]),
                        "upcoming_list": upcoming_list[:6]},
        "alerts":    {"unacknowledged": db.query(Alert).filter(Alert.acknowledged==False).count(),
                      "critical": db.query(Alert).filter(Alert.acknowledged==False,Alert.severity=="critical").count()},
        "avg_metrics": {"cpu": round(sum(cpus)/len(cpus),1) if cpus else 0,
                        "ram": round(sum(rams)/len(rams),1) if rams else 0,
                        "disk": round(sum(disks)/len(disks),1) if disks else 0},
        "os_distribution":    os_dist,
        "asset_distribution": type_dist,
        "dept_distribution":  dept_dist,
        "server_time": datetime.utcnow().isoformat(),
        "version": VERSION,
    }

# ─── USERS ────────────────────────────────────────────────────────────────────

@app.get("/api/users")
def list_users(user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    return [{"id": u.id, "username": u.username, "full_name": u.full_name,
             "email": u.email, "role": u.role, "is_active": u.is_active,
             "created_at": u.created_at.isoformat()} for u in db.query(User).all()]

@app.post("/api/users")
def create_user(data: UserCreateSchema, user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    # RH solo puede crear viewers
    if user.role == "rh" and data.role not in ("viewer",):
        raise HTTPException(403, "RH solo puede crear usuarios viewer")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "Usuario ya existe")
    u = User(username=data.username, password_hash=hash_password(data.password),
             full_name=data.full_name, email=data.email, role=data.role)
    db.add(u); db.commit()
    audit(db, user.username, "CREATE", "User", u.id,
          f"Nuevo usuario: {u.username} (rol: {u.role})", notify_email=u.email)
    db.commit()
    return {"id": u.id}

@app.put("/api/users/{uid}")
def update_user(uid: int, data: UserUpdateSchema, user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404)
    if u.username == "admin" and user.username != "admin":
        raise HTTPException(403, "Solo admin puede modificar admin")
    changes = []
    if data.full_name is not None: u.full_name = data.full_name; changes.append(f"nombre→{data.full_name}")
    if data.email is not None:     u.email = data.email; changes.append(f"email→{data.email}")
    if data.role is not None and user.role == "admin": u.role = data.role; changes.append(f"rol→{data.role}")
    if data.is_active is not None: u.is_active = data.is_active; changes.append(f"activo→{data.is_active}")
    db.commit()
    if changes:
        audit(db, user.username, "UPDATE", "User", uid,
              f"Usuario modificado: {u.username} — "+", ".join(changes), notify_email=u.email)
        db.commit()
    return {"updated": True}

@app.delete("/api/users/{uid}")
def delete_user(uid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404)
    if u.username == "admin": raise HTTPException(400, "No se puede eliminar admin")
    db.delete(u); db.commit(); return {"deleted": True}

# ─── AUDIT LOG ────────────────────────────────────────────────────────────────

@app.get("/api/audit")
def get_audit(user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200).all()
    return [{"id": l.id, "timestamp": l.timestamp.isoformat(), "user": l.user,
             "action": l.action, "entity": l.entity, "entity_id": l.entity_id,
             "description": l.description, "email_sent": l.email_sent} for l in logs]

# ─── SMTP CONFIG ──────────────────────────────────────────────────────────────

@app.get("/api/config/smtp")
def get_smtp_cfg(user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    c = get_smtp(db)
    return {"host": c.host, "port": c.port, "username": c.username,
            "password": "***" if c.password else "", "from_name": c.from_name,
            "company": c.company, "enabled": c.enabled}

@app.put("/api/config/smtp")
def update_smtp_cfg(data: SMTPConfigSchema, user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    c = get_smtp(db)
    c.host=data.host; c.port=data.port; c.username=data.username
    if data.password and data.password != "***": c.password = data.password
    c.from_name=data.from_name; c.company=data.company; c.enabled=data.enabled
    db.commit(); return {"updated": True}

@app.post("/api/config/smtp/test")
def test_smtp(user: User = Depends(require_it_admin), db: Session = Depends(get_db)):
    cfg = get_smtp(db)
    ok  = send_email(cfg.username, "✅ Test InfraWatch SMTP",
                     f"<h2>✅ SMTP configurado correctamente</h2><p>InfraWatch v{VERSION} puede enviar correos.</p>", db)
    return {"success": ok, "message": "Email enviado" if ok else "Error. Verifica la configuración SMTP."}

# ─── REPORTS ──────────────────────────────────────────────────────────────────

@app.get("/api/reports/inventory")
def rep_inv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(agents),
            "data": [{"hostname": a.hostname, "ip": a.ip_address, "mac": a.mac_address,
                       "os": f"{a.os_name} {a.os_version}", "cpu": a.cpu_model,
                       "ram_gb": a.ram_total_gb, "disk_gb": a.disk_total_gb,
                       "status": a.status, "tags": json.loads(a.tags or "[]"),
                       "last_seen": a.last_seen.isoformat() if a.last_seen else ""} for a in agents]}

@app.get("/api/reports/assets")
def rep_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assets = db.query(Asset).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(assets),
            "data": [{"asset_code": a.asset_code, "type": a.asset_type, "brand": a.brand,
                       "model": a.model, "serial": a.serial_number, "responsible": a.responsible,
                       "personnel": a.personnel.full_name if a.personnel else "",
                       "department": a.personnel.department if a.personnel else "",
                       "location": a.location, "status": a.status,
                       "carta_sent": a.carta_sent,
                       "current_value": calc_depreciation(a)["current_value"],
                       "next_maintenance": min((m.next_date for m in a.maintenances if m.next_date and m.status=="pending"), default="")
                      } for a in assets]}

@app.get("/api/reports/personnel")
def rep_personnel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    people = db.query(Personnel).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(people),
            "data": [{"employee_id": p.employee_id, "full_name": p.full_name,
                       "position": p.position, "department": p.department,
                       "area": p.area_rel.name if p.area_rel else p.department,
                       "email": p.email, "phone": p.phone, "is_active": p.is_active,
                       "assets": [a.asset_code for a in p.assets],
                       "asset_count": len(p.assets)} for p in people]}



# ─── RUTAS v2.3 — SOFTWARE INSTALADO ─────────────────────────────────────────

@app.post("/api/agents/{uid}/software")
def upload_software(uid: str, data: SoftwareUploadSchema,
                    db: Session = Depends(get_db)):
    """Recibe lista de software instalado desde el agente"""
    a = db.query(Agent).filter(Agent.uid == uid).first()
    if not a: raise HTTPException(404, "Agente no encontrado")
    db.query(InstalledSoftware).filter(InstalledSoftware.agent_id == a.id).delete()
    now   = datetime.utcnow()
    items = [InstalledSoftware(
        agent_id     = a.id,
        name         = (sw.get("name") or "")[:120],
        version      = (sw.get("version") or "")[:60],
        publisher    = (sw.get("publisher") or "")[:100],
        install_date = (sw.get("install_date") or "")[:20],
        detected_at  = now,
    ) for sw in data.software[:600] if sw.get("name")]
    db.bulk_save_objects(items)
    db.commit()
    log.info(f"📦 Software {a.hostname}: {len(items)} paquetes")
    return {"updated": len(items)}

@app.get("/api/agents/{agent_id}/software")
def get_agent_software(agent_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    a  = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(404)
    sw = db.query(InstalledSoftware).filter(InstalledSoftware.agent_id == agent_id)           .order_by(InstalledSoftware.name).all()
    return {
        "agent_id": agent_id, "hostname": a.hostname, "total": len(sw),
        "detected_at": sw[0].detected_at.isoformat() if sw else None,
        "software": [{"id": s.id, "name": s.name, "version": s.version,
                       "publisher": s.publisher, "install_date": s.install_date} for s in sw]
    }

@app.get("/api/software/search")
def search_software(q: str = "", user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if len(q) < 2: raise HTTPException(400, "Mínimo 2 caracteres")
    rows = db.query(InstalledSoftware).filter(
        InstalledSoftware.name.ilike(f"%{q}%")).limit(300).all()
    grouped: dict = {}
    for s in rows:
        ag  = db.query(Agent).filter(Agent.id == s.agent_id).first()
        key = s.name.lower()
        if key not in grouped:
            grouped[key] = {"name": s.name, "versions": [], "agents": [], "count": 0}
        grouped[key]["count"] += 1
        if s.version not in grouped[key]["versions"]:
            grouped[key]["versions"].append(s.version)
        if ag:
            grouped[key]["agents"].append(
                {"agent_id": ag.id, "hostname": ag.hostname, "version": s.version})
    return {"query": q, "matches": len(grouped), "results": list(grouped.values())}

# ─── RUTAS v2.3 — UMBRALES ────────────────────────────────────────────────────

@app.get("/api/agents/{agent_id}/thresholds")
def get_thresholds(agent_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    t = db.query(AgentThreshold).filter(AgentThreshold.agent_id == agent_id).first()
    if not t: return ThresholdSchema().dict()
    return {"cpu_warn": t.cpu_warn, "cpu_crit": t.cpu_crit,
            "ram_warn": t.ram_warn, "ram_crit": t.ram_crit,
            "disk_warn": t.disk_warn, "disk_crit": t.disk_crit,
            "updated_at": t.updated_at.isoformat()}

@app.put("/api/agents/{agent_id}/thresholds")
def set_thresholds(agent_id: int, data: ThresholdSchema,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.query(Agent).filter(Agent.id == agent_id).first(): raise HTTPException(404)
    t = db.query(AgentThreshold).filter(AgentThreshold.agent_id == agent_id).first()
    if not t:
        t = AgentThreshold(agent_id=agent_id); db.add(t)
    for k, v in data.dict().items():
        if v is not None: setattr(t, k, v)
    t.updated_at = datetime.utcnow()
    db.commit()
    return {"updated": True}

# ─── RUTAS v2.3 — SNMP ───────────────────────────────────────────────────────

def _snmp_get(ip: str, community: str = "public", port: int = 161, ver: str = "2c") -> dict:
    if not SNMP_AVAILABLE: return {"error": "pysnmp no instalado"}
    OIDs = {"sysDescr":"1.3.6.1.2.1.1.1.0","sysName":"1.3.6.1.2.1.1.5.0",
            "sysUpTime":"1.3.6.1.2.1.1.3.0","ifNumber":"1.3.6.1.2.1.2.1.0"}
    model = 1 if ver in ("2c","2") else 0
    result = {}
    for name, oid in OIDs.items():
        try:
            ei, es, _, vbs = next(getCmd(
                SnmpEngine(), CommunityData(community, mpModel=model),
                UdpTransportTarget((ip, port), timeout=3, retries=1),
                ContextData(), ObjectType(ObjectIdentity(oid))))
            if not ei and not es:
                result[name] = str(vbs[0][1])
        except Exception: pass
    return result

def _snmp_dict(d: SNMPDevice) -> dict:
    return {"id": d.id, "name": d.name, "ip_address": d.ip_address,
            "device_type": d.device_type, "community": d.community,
            "snmp_version": d.snmp_version, "port": d.port,
            "location": d.location, "area_id": d.area_id, "status": d.status,
            "sys_descr": d.sys_descr, "sys_name": d.sys_name,
            "sys_uptime": d.sys_uptime, "if_count": d.if_count,
            "last_polled": d.last_polled.isoformat() if d.last_polled else None,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "poll_interval": d.poll_interval, "is_active": d.is_active,
            "notes": d.notes, "created_at": d.created_at.isoformat()}

@app.get("/api/snmp")
def list_snmp(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_snmp_dict(d) for d in db.query(SNMPDevice).order_by(SNMPDevice.name).all()]

@app.post("/api/snmp")
def create_snmp(data: SNMPDeviceSchema, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    d = SNMPDevice(**data.dict(), created_by=user.username)
    db.add(d); db.commit(); db.refresh(d)
    return {"id": d.id}

@app.put("/api/snmp/{did}")
def update_snmp(did: int, data: SNMPDeviceSchema, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    d = db.query(SNMPDevice).filter(SNMPDevice.id == did).first()
    if not d: raise HTTPException(404)
    for k, v in data.dict().items(): setattr(d, k, v)
    db.commit(); return {"updated": True}

@app.delete("/api/snmp/{did}")
def delete_snmp(did: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    d = db.query(SNMPDevice).filter(SNMPDevice.id == did).first()
    if not d: raise HTTPException(404)
    db.delete(d); db.commit(); return {"deleted": True}

def _poll_snmp_bg(device_id: int):
    db  = SessionLocal()
    dev = db.query(SNMPDevice).filter(SNMPDevice.id == device_id).first()
    if not dev: db.close(); return
    data = _snmp_get(dev.ip_address, dev.community, dev.port, dev.snmp_version)
    now  = datetime.utcnow()
    dev.last_polled = now
    if "error" in data or not data:
        dev.status = "offline"
        _new_alert(db, None, "snmp_offline", "warning",
                   f"🔌 SNMP sin respuesta: {dev.name} ({dev.ip_address})")
    else:
        dev.status = "online"; dev.last_seen = now
        if "sysDescr" in data:  dev.sys_descr = data["sysDescr"][:500]
        if "sysName"  in data:  dev.sys_name  = data["sysName"][:100]
        if "sysUpTime"in data:
            try: dev.sys_uptime = float(data["sysUpTime"]) / 100
            except: pass
        if "ifNumber" in data:
            try: dev.if_count = int(data["ifNumber"])
            except: pass
    db.commit(); db.close()

@app.post("/api/snmp/{did}/poll")
def force_snmp_poll(did: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    d = db.query(SNMPDevice).filter(SNMPDevice.id == did).first()
    if not d: raise HTTPException(404)
    if not SNMP_AVAILABLE:
        return {"error": "pysnmp no instalado. Ejecuta: pip install pysnmp"}
    threading.Thread(target=_poll_snmp_bg, args=(did,), daemon=True).start()
    return {"polling": True, "ip": d.ip_address}

# ─── RUTAS v2.3 — PING DEVICES ───────────────────────────────────────────────

def _ping_host(ip: str, timeout: int = 3):
    import platform as _plat, re as _re
    system = _plat.system().lower()
    cmd    = (["ping","-n","1","-w",str(timeout*1000),ip]
              if system=="windows" else ["ping","-c","1","-W",str(timeout),ip])
    try:
        r   = __import__("subprocess").run(cmd, capture_output=True, text=True, timeout=timeout+2)
        ok  = r.returncode == 0
        rtt = None
        if ok:
            m = _re.search(r"(?:time[<=]?|temps=)(\d+\.?\d*)\s*ms", r.stdout, _re.IGNORECASE)
            if m: rtt = float(m.group(1))
        return ok, rtt
    except Exception:
        return False, None

def _ping_dict(d: PingDevice) -> dict:
    return {"id": d.id, "name": d.name, "ip_address": d.ip_address,
            "device_type": d.device_type, "area_id": d.area_id,
            "location": d.location, "status": d.status,
            "response_time_ms": d.response_time_ms,
            "last_ping": d.last_ping.isoformat() if d.last_ping else None,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "uptime_pct": d.uptime_pct,
            "consecutive_failures": d.consecutive_failures,
            "ping_interval": d.ping_interval, "is_active": d.is_active,
            "notes": d.notes, "created_at": d.created_at.isoformat()}

def _poll_ping_bg(device_id: int):
    db  = SessionLocal()
    dev = db.query(PingDevice).filter(PingDevice.id == device_id).first()
    if not dev: db.close(); return
    alive, rtt = _ping_host(dev.ip_address)
    now = datetime.utcnow()
    dev.last_ping        = now
    dev.response_time_ms = rtt
    if alive:
        dev.status = "online"; dev.last_seen = now
        dev.consecutive_failures = 0
    else:
        dev.consecutive_failures = (dev.consecutive_failures or 0) + 1
        dev.status = "offline"
        if dev.consecutive_failures == 2:
            _new_alert(db, None, "ping_offline", "warning",
                       f"📡 {dev.name} ({dev.ip_address}) sin respuesta ping")
    db.commit(); db.close()

@app.get("/api/ping-devices")
def list_ping(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_ping_dict(d) for d in db.query(PingDevice).order_by(PingDevice.name).all()]

@app.post("/api/ping-devices")
def create_ping(data: PingDeviceSchema, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    d = PingDevice(**data.dict(), created_by=user.username)
    db.add(d); db.commit(); db.refresh(d)
    threading.Thread(target=_poll_ping_bg, args=(d.id,), daemon=True).start()
    return {"id": d.id}

@app.put("/api/ping-devices/{did}")
def update_ping(did: int, data: PingDeviceSchema, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    d = db.query(PingDevice).filter(PingDevice.id == did).first()
    if not d: raise HTTPException(404)
    for k, v in data.dict().items(): setattr(d, k, v)
    db.commit(); return {"updated": True}

@app.delete("/api/ping-devices/{did}")
def delete_ping(did: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    d = db.query(PingDevice).filter(PingDevice.id == did).first()
    if not d: raise HTTPException(404)
    db.delete(d); db.commit(); return {"deleted": True}

@app.post("/api/ping-devices/scan-all")
def scan_all_ping(background_tasks: BackgroundTasks, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    ids = [d.id for d in db.query(PingDevice).filter(PingDevice.is_active == True).all()]
    for did in ids:
        background_tasks.add_task(_poll_ping_bg, did)
    return {"scanning": len(ids)}


# ─── HEALTH ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": VERSION,
            "time": datetime.utcnow().isoformat()}

# ─── STATIC / SPA ─────────────────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str = ""):
        if full_path.startswith("api/"): raise HTTPException(404)
        idx = os.path.join(STATIC_DIR, "index.html")
        return FileResponse(idx) if os.path.exists(idx) else JSONResponse({"status":"ok"})

# ─── STARTUP ──────────────────────────────────────────────────────────────────


# ─── UDP DISCOVERY LISTENER v2.3 ─────────────────────────────────────────────

_DISCOVERY_UDP_PORT = 47777

def _udp_discovery_listener():
    """Responde a broadcasts del agente → auto-descubrimiento del servidor"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", _DISCOVERY_UDP_PORT))
        sock.settimeout(2)
        log.info(f"🔊 UDP Discovery escuchando en :{_DISCOVERY_UDP_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(512)
                if b"INFRAWATCH_DISCOVER_V23" in data:
                    sock.sendto(b"INFRAWATCH_HERE", addr)
                    log.info(f"🔍 Discovery respondido a {addr[0]}")
            except socket.timeout: continue
            except Exception as e: log.debug(f"UDP: {e}")
    except Exception as e:
        log.warning(f"UDP Discovery listener no pudo iniciar: {e}")

def _polling_loop():
    """Hilo background: ping cada 60s + SNMP cada 5min"""
    log.info("🔄 Polling background iniciado")
    last_snmp = 0.0
    while True:
        try:
            db    = SessionLocal()
            p_ids = [d.id for d in db.query(PingDevice).filter(PingDevice.is_active==True).all()]
            s_ids = [d.id for d in db.query(SNMPDevice).filter(SNMPDevice.is_active==True).all()]
            db.close()
            for did in p_ids:
                try: _poll_ping_bg(did)
                except Exception: pass
            now = time.time()
            if now - last_snmp >= 300:
                last_snmp = now
                for did in s_ids:
                    try: _poll_snmp_bg(did)
                    except Exception: pass
        except Exception as e:
            log.error(f"Polling loop: {e}")
        time.sleep(60)


@app.on_event("startup")
def startup():
    log.info(f"╔══════════════════════════════════════════╗")
    log.info(f"║  {APP_NAME} v{VERSION} — iniciando v2.3  ║")
    log.info(f"╚══════════════════════════════════════════╝")
    run_migrations()
    init_db()
    # v2.3: UDP discovery listener (auto-descubrimiento de agentes)
    threading.Thread(target=_udp_discovery_listener, daemon=True, name="udp-disc").start()
    # v2.3: Polling background — ping + SNMP
    threading.Thread(target=_polling_loop, daemon=True, name="poll-bg").start()
    log.info("✅ Sistema listo — UDP discovery + polling activos")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
